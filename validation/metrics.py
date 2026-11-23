"""Repeated operations with explicit boundaries; one build or target operation at a time."""
import json
from pathlib import Path
import time

from .common import Recorder, checked_workspace, describe, save, utc, input_manifest
from .flight import Flight


def build(root, output, target):
    flight = Flight(root, output, target)
    report = {'kind': 'full_build', 'target': target, 'n': 1, 'started_utc': utc(), 'status': 'running'}
    try:
        build_dir = flight.root / flight.lab.hardware.build_directory(target)
        if build_dir.exists():
            raise ValueError('Full-build measurement requires an absent build directory; use a new dedicated workspace')
        report['measurement'] = flight.job('build')
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=flight.redact(f'{type(error).__name__}: {error}'))
        raise
    finally:
        report['ended_utc'] = utc(); save(flight.output / 'metrics.json', report); flight.close()
    return report


def cycles(root, output, repetitions=10):
    if repetitions < 1:
        raise ValueError('Choose a positive development cycle count')
    root = checked_workspace(root)
    recorder = Recorder(root, output)
    report = {'kind': 'development_cycles', 'target': 'native', 'planned_n': repetitions,
              'started_utc': utc(), 'status': 'running', 'cycles': []}
    if not (root / 'mission/build-native/exe/cpu1/core-cpu1').is_file():
        raise ValueError('Measure the full Native build before incremental cycles')
    try:
        for index in range(1, repetitions + 1):
            name = f'eval_cycle_{index:02d}'
            created = recorder.cli('create-' + name, 'app', 'new', name, '--json')
            compiled = recorder.cli('build-' + name, 'build', '--target', 'native', '--json', timeout=3600)
            deleted = recorder.cli('delete-' + name, 'app', 'delete', name, '--json')
            if (root / 'cFS/apps' / name).exists() or (root / 'project/apps' / (name + '.json')).exists():
                raise ValueError('Cycle app sources remained after deletion')
            report['cycles'].append({'repetition': index, 'app': name, 'create_s': created['elapsed_s'],
                                     'build_s': compiled['elapsed_s'], 'delete_s': deleted['elapsed_s']})
            save(recorder.output / 'metrics.json', report)
        # Deletion changes the source fingerprint. Rebuild the unchanged base mission
        # once, explicitly outside the N measured development cycles.
        report['restoration_build'] = recorder.cli('restore-base-mission', 'build', '--target', 'native', '--json')
        save(recorder.output / 'sources-after-cycles.json', input_manifest(root))
        report['summary'] = {name: describe(row[name] for row in report['cycles']) for name in ('create_s', 'build_s', 'delete_s')}
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['ended_utc'] = utc(); save(recorder.output / 'metrics.json', report)
    return report


def starts(root, output, target, repetitions=10, guest_boots=False, leave_running=False, timeout=90):
    if guest_boots and target != 'qemu':
        raise ValueError('Power-cycle measurements are only implemented for the isolated QEMU guest')
    if repetitions < 1:
        raise ValueError('Choose at least one repetition')
    flight = Flight(root, output, target, timeout)
    report = {'kind': 'guest_boots' if guest_boots else 'cfs_starts', 'target': target,
              'planned_n': repetitions, 'started_utc': utc(), 'runs': [], 'status': 'running',
              'guest_condition': 'same prepared image and persistent disk; guest off before each repetition' if guest_boots else 'OS already running'}
    try:
        if target == 'qemu' and not guest_boots and not flight.lab.hardware._qemu_running():
            raise ValueError('Start measurements require QEMU Linux already running; use boots for OS startup')
        for index in range(1, repetitions + 1):
            # Stop only the managed flight belonging to this dedicated workspace.
            if index > 1:
                flight.lab.ground.stop()
                flight.job('stop')
                if guest_boots:
                    flight.job('shutdown')
            start = time.monotonic()
            row = {'repetition': index, 'started_utc': utc()}
            if guest_boots:
                row['guest_boot_to_ssh'] = flight.job('boot')
            row['run_to_operational'] = flight.job('run')
            if 'operational_observed_s' not in row['run_to_operational']:
                raise ValueError('Run completed without a newly observed OPERATIONAL marker')
            row['ground_to_first_hk'] = flight.connect()
            row['total_to_first_hk_s'] = time.monotonic()-start
            report['runs'].append(row); save(flight.output / 'metrics.json', report)
        report['summary'] = {'run_total_s': describe(row['run_to_operational']['elapsed_s'] for row in report['runs']),
                             'operational_observed_s': describe(row['run_to_operational']['operational_observed_s'] for row in report['runs']),
                             'ground_to_first_hk_s': describe(row['ground_to_first_hk']['elapsed_s'] for row in report['runs']),
                             'total_to_first_hk_s': describe(row['total_to_first_hk_s'] for row in report['runs'])}
        if guest_boots:
            report['summary']['guest_boot_total_s'] = describe(row['guest_boot_to_ssh']['elapsed_s'] for row in report['runs'])
            report['summary']['guest_ssh_ready_observed_s'] = describe(row['guest_boot_to_ssh']['guest_ssh_ready_observed_s']
                for row in report['runs'] if 'guest_ssh_ready_observed_s' in row['guest_boot_to_ssh'])
        report['status'] = 'passed'
        if not leave_running:
            flight.lab.ground.stop(); flight.job('stop')
            if guest_boots:
                flight.job('shutdown')
    except BaseException as error:
        report.update(status='failed', error=flight.redact(f'{type(error).__name__}: {error}'))
        raise
    finally:
        report['ended_utc'] = utc(); save(flight.output / 'metrics.json', report); flight.close()
    return report
