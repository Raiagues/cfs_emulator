"""Measure shared QEMU/physical compilation cycles on an independent frozen mission."""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from . import common

TIMING_FIELDS = ['kind', 'target', 'repetition', 'stage', 'seconds']
STAT_FIELDS = ['kind', 'target', 'stage', 'n', 'min', 'q1', 'median', 'q3', 'iqr', 'max']
STAGES = ('create_s', 'build_s', 'delete_s')


def procedure_identity():
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files = {}
    for name in ('validation/compilation.py', 'validation/common.py'):
        committed = subprocess.check_output(['git', 'show', revision + ':' + name], cwd=root)
        if (root / name).read_bytes() != committed:
            raise ValueError('Commit the measurement procedure before running it: ' + name)
        files[name] = common.sha256(root / name)
    return {'commit': revision, 'files': files}


def write_tables(output, cycles, repetitions):
    if len(cycles) != repetitions or [r['repetition'] for r in cycles] != list(range(1, repetitions + 1)):
        raise ValueError('Incomplete or reordered compilation cycles')
    rows = []
    for cycle in cycles:
        for stage in STAGES:
            seconds = cycle[stage]
            if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError('Invalid measured duration')
            rows.append(dict(kind='development_cycles', target='qemu', repetition=cycle['repetition'],
                             stage=stage, seconds=seconds))
    statistics = [dict(kind='development_cycles', target='qemu', stage=stage,
                       **common.describe(row['seconds'] for row in rows if row['stage'] == stage)) for stage in STAGES]
    tables = {}
    for name, fields, values in [('q5_timings.csv', TIMING_FIELDS, rows),
                                 ('q5_statistics.csv', STAT_FIELDS, statistics)]:
        with (output / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(values)
        tables[name] = {'sha256': common.sha256(output / name), 'rows': len(values), 'columns': fields}
    return tables


def run(workspace, output, repetitions=10):
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError('Choose a positive number of compilation cycles')
    root = common.checked_workspace(workspace)
    output = Path(output).resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError('Store measurements outside the isolated mission')
    marker = json.loads((root / '.evaluation.json').read_text())
    revision = marker.get('platform_commit', '')
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('The independent mission must identify its frozen platform commit')
    if (root / 'mission/build-flight').exists():
        raise ValueError('Prepare a new independent mission without existing ARM build artifacts')
    for index in range(1, repetitions + 1):
        name = f'eval_cycle_{index:02d}'
        if (root / 'cFS/apps' / name).exists() or (root / 'project/apps' / (name + '.json')).exists():
            raise ValueError('A measured cycle app already exists: ' + name)
    procedure = procedure_identity()
    recorder = common.Recorder(root, output)
    report = {'kind': 'q5_compilation_supplement', 'status': 'running', 'started_utc': common.utc(),
              'platform_commit': revision, 'nasa_commit': marker.get('nasa_commit'),
              'procedure': procedure, 'host': common.host_info(), 'planned_n': repetitions,
              'target': 'qemu', 'build_destinations': ['qemu', 'physical'],
              'scope': 'Host source operations and shared cross-build; no emulator or physical-board execution',
              'prerequisite_scope': 'Fresh baseline ARM build before the measured incremental cycles',
              'cycles': []}
    common.save(output / 'metrics.json', report)
    try:
        report['baseline_build'] = recorder.cli('prepare-baseline', 'build', '--target', 'qemu', '--json')
        if not (root / 'mission/build-flight/exe/cpu1/core-cpu1').is_file():
            raise ValueError('Baseline build did not produce the flight executable')
        before = common.input_manifest(root)
        common.save(output / 'sources-before-cycles.json', before)
        # Preserve reviewable baseline bytes outside every timed CLI operation.
        for name in before:
            if name.startswith('mission/sample_defs/') or name == 'mission/modules.cmake':
                reference = output / 'baseline-reference' / name
                reference.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / name, reference)
        report['baseline_reference'] = 'baseline-reference'
        for index in range(1, repetitions + 1):
            name = f'eval_cycle_{index:02d}'
            created = recorder.cli('create-' + name, 'app', 'new', name, '--json')
            compiled = recorder.cli('build-' + name, 'build', '--target', 'qemu', '--json')
            deleted = recorder.cli('delete-' + name, 'app', 'delete', name, '--json')
            if (root / 'cFS/apps' / name).exists() or (root / 'project/apps' / (name + '.json')).exists():
                raise ValueError('Cycle app sources remained after deletion: ' + name)
            report['cycles'].append({'repetition': index, 'app': name, 'create_s': created['elapsed_s'],
                                     'build_s': compiled['elapsed_s'], 'delete_s': deleted['elapsed_s']})
            common.save(output / 'metrics.json', report)
            print(f'Compilation cycle {index}/{repetitions} completed.', flush=True)
        report['restoration_build'] = recorder.cli('restore-base-mission', 'build', '--target', 'qemu', '--json')
        after = common.input_manifest(root)
        common.save(output / 'sources-after-cycles.json', after)
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        report['source_differences_after_restoration'] = changed
        if changed:
            raise ValueError('The source baseline was not restored: ' + ', '.join(changed))
        report['tables'] = write_tables(output, report['cycles'], repetitions)
        report['status'] = 'final'
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['ended_utc'] = common.utc()
        common.save(output / 'metrics.json', report)
    summary = {key: value for key, value in report.items() if key not in {'cycles'}}
    summary['source_manifests'] = {name: common.sha256(output / name) for name in
                                 ('sources-before-cycles.json', 'sources-after-cycles.json')}
    summary['commands_sha256'] = common.sha256(output / 'commands.json')
    common.save(output / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=10)
    args = parser.parse_args()
    result = run(args.workspace, args.output, args.repetitions)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
