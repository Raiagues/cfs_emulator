"""Audit completed compilation timings while preserving their original collection record."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from . import common
from .compilation import write_tables
from project.mission_config import MissionConfig
from project.mission_tables import _guard_install

TABLES = ('sch_lab_table.c', 'to_lab_sub.c', 'to_lab_sub_alt.c', 'to_lab_sub_bad.c')
MODULES = 'mission/modules.cmake'
INSTALL = 'mission/sample_defs/cpu1/install_custom.cmake'
CHANGES = {MODULES, INSTALL, *('mission/sample_defs/tables/' + name for name in TABLES)}
WRAPPER = (r'^#if !defined\(CFS_CPU1_MODULE_SELECTION\) \|\| \(defined\(CFS_MODULE_[A-Z0-9_]+\)'
           r'(?: && defined\(CFS_MODULE_[A-Z0-9_]+\))*\)\n([^#]*?|#include[^\n]*)\n#endif$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def analysis_identity():
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files = {}
    for name in ('validation/compilation_summary.py', 'validation/compilation.py', 'validation/common.py',
                 'project/mission_config.py', 'project/mission_tables.py'):
        require((root / name).read_bytes() == subprocess.check_output(['git', 'show', commit + ':' + name], cwd=root),
                'Commit the analysis procedure first: ' + name)
        files[name] = common.sha256(root / name)
    return {'commit': commit, 'files': files}


def validate_commands(report, commands, root):
    require(report['kind'] == 'q5_compilation_supplement' and report['planned_n'] == 10, 'Expected ten planned cycles')
    require(report['target'] == 'qemu' and report['build_destinations'] == ['qemu', 'physical'], 'Wrong build destinations')
    require(report['host']['build_jobs'] == 1, 'Expected one compilation worker')
    expected = [('prepare-baseline', ['build', '--target', 'qemu', '--json'])]
    for index in range(1, 11):
        name = f'eval_cycle_{index:02d}'
        expected += [('create-' + name, ['app', 'new', name, '--json']),
                     ('build-' + name, ['build', '--target', 'qemu', '--json']),
                     ('delete-' + name, ['app', 'delete', name, '--json'])]
    expected.append(('restore-base-mission', ['build', '--target', 'qemu', '--json']))
    require(len(commands) == len(expected) == 32, 'Expected baseline, thirty cycle operations and restoration')
    for record, (name, args) in zip(commands, expected):
        require(record['name'] == name and record['argv'] == [str(root / 'start'), '--no-ui', *args],
                'Unexpected command or order: ' + name)
        require(record['exit_code'] == 0 and not record.get('timeout'), 'Unsuccessful command: ' + name)
    require(len(report['cycles']) == 10, 'Incomplete measured cycles')
    for index, row in enumerate(report['cycles'], 1):
        require(row['repetition'] == index and row['app'] == f'eval_cycle_{index:02d}', 'Unexpected cycle order')
        for offset, stage in enumerate(('create_s', 'build_s', 'delete_s')):
            require(row[stage] == commands[1 + 3 * (index - 1) + offset]['elapsed_s'], 'Timing differs from command record')
    require(report['baseline_build'] == commands[0] and report['restoration_build'] == commands[-1],
            'Preparation/restoration record mismatch')


def preprocessing(root, output, image):
    records = []
    for path in sorted((root / 'mission/build-flight/cache').rglob('compile_commands.json')):
        for entry in json.loads(path.read_text()):
            if Path(entry['file']).name not in TABLES:
                continue
            args = shlex.split(entry['command'])
            filtered = []; position = 1
            while position < len(args):
                value = args[position]
                if value == '-o': position += 2; continue
                if value != '-c' and value != entry['file']: filtered.append(value)
                position += 1
            cpu = next(part for part in Path(entry['directory']).parts if part.startswith('default_cpu'))
            stem = cpu + '-' + Path(entry['file']).stem
            values = {}
            for phase in ('before', 'after'):
                source = '/audit/' + phase + entry['file']
                argv = ['docker', 'run', '--rm', '--network=none',
                        '-v', str(root / 'cFS') + ':/cFS:ro', '-v', str(root / 'mission') + ':/mission:ro',
                        '-v', str(output) + ':/audit:ro', '-w', entry['directory'], image,
                        args[0], *filtered, '-E', '-P', source]
                result = subprocess.run(argv, capture_output=True, check=True)
                destination = output / 'preprocessed' / (stem + '-' + phase + '.i')
                destination.parent.mkdir(exist_ok=True)
                destination.write_bytes(result.stdout)
                values[phase] = common.sha256(destination)
            require(values['before'] == values['after'], 'Preprocessed table changed: ' + stem)
            records.append({'cpu': cpu, 'table': Path(entry['file']).name, 'sha256': values,
                            'compile_command': entry, 'equal': True})
    require(len(records) == 8 and len({(r['cpu'], r['table']) for r in records}) == 8,
            'Expected all four shared tables for both configured CPUs')
    return records


def audit_sources(root, measurements, reference, output, image):
    before = json.loads((measurements / 'sources-before-cycles.json').read_text())
    after = json.loads((measurements / 'sources-after-cycles.json').read_text())
    require(common.input_manifest(root) == after, 'Mission sources changed after the recorded restoration')
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    require(changed == CHANGES, 'Unexpected source differences')
    require(MODULES not in before, 'Module override already existed before the cycles')
    for name in sorted(changed):
        current = root / name
        destination = output / 'after' / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current, destination)
        if name in before:
            source = reference / name
            require(common.sha256(source) == before[name]['sha256'], 'Reference bytes differ from recorded baseline: ' + name)
            destination = output / 'before' / name; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            original, final = source.read_text(), current.read_text()
            if name == INSTALL:
                require(_guard_install(original) == final, 'Unexpected install configuration edits')
            else:
                require(re.sub(WRAPPER, r'\1', final, flags=re.M) == original, 'Non-wrapper table edits: ' + name)
    mission = MissionConfig(root)
    require(mission.selection() == {'added': set(), 'removed': set()}, 'Module membership did not return to baseline')
    require(mission.selection_plan()[MODULES] == (root / MODULES).read_text(), 'Unexpected module integration code')
    remaining = [name for name in after if '/eval_cycle_' in name]
    require(not remaining, 'Cycle source modules remain')
    for name in after:
        if name.startswith(('mission/sample_defs/', 'project/apps/')) or name in (MODULES, 'mission/cpu1_cfe_es_startup.scr', 'project/config.json'):
            require(b'eval_cycle_' not in (root / name).read_bytes().lower(), 'Cycle integration remains: ' + name)
    tables = preprocessing(root, output, image)
    audit = {'byte_identical': False, 'semantic_checks_passed': True, 'managed_materialization': sorted(changed),
             'unchanged_manifest_entries': len(set(before) & set(after)) - 5,
             'unchanged_scope': 'All app sources, manifests, project configuration, startup entries, generated MID/schedule fragments and original NASA files',
             'module_overrides': {'added': [], 'removed': []}, 'cycle_sources_or_references_remaining': [],
             'preprocessed_tables': tables, 'before_manifest_sha256': common.sha256(measurements / 'sources-before-cycles.json'),
             'after_manifest_sha256': common.sha256(measurements / 'sources-after-cycles.json')}
    common.save(output / 'source-audit.json', audit)
    return audit


def run(workspace, measurements, reference, output, image='flight-studio-builder:bookworm'):
    root = common.checked_workspace(workspace)
    measurements, reference, output = map(lambda p: Path(p).resolve(), (measurements, reference, output))
    require(not output.exists() and not output.is_relative_to(root) and not output.is_relative_to(measurements),
            'Use a new analysis directory outside the mission and raw measurements')
    identity = analysis_identity()
    report = json.loads((measurements / 'metrics.json').read_text())
    commands = json.loads((measurements / 'commands.json').read_text())['commands']
    require(report['status'] == 'failed' and report['error'].startswith('ValueError: The source baseline was not restored:'),
            'This analysis handles only the completed collection with the strict byte-restoration postcondition')
    validate_commands(report, commands, root)
    for record in commands:
        for stream in ('stdout', 'stderr'):
            require((measurements / record[stream]).is_file(), 'Missing operation log')
    output.mkdir(parents=True)
    audit = audit_sources(root, measurements, reference, output, image)
    tables = write_tables(output, report['cycles'], 10)
    summary = {'kind': 'q5_compilation_supplement', 'status': 'final', 'platform_commit': report['platform_commit'],
               'nasa_commit': report['nasa_commit'], 'procedure': report['procedure'], 'analysis': identity,
               'analyzed_utc': common.utc(), 'target': 'qemu', 'build_destinations': ['qemu', 'physical'],
               'planned_n': 10, 'completed_n': 10, 'successful_cli_operations': 32, 'tables': tables,
               'scope': report['scope'], 'source_restoration': audit,
               'collection_record': {'status': report['status'], 'sha256': common.sha256(measurements / 'metrics.json'),
                  'interpretation': 'All timed CLI operations succeeded. The original strict byte-restoration result is retained; this analysis verifies persistent module-selection scaffolding separately.'},
               'commands_sha256': common.sha256(measurements / 'commands.json'),
               'baseline_build': report['baseline_build'], 'restoration_build': report['restoration_build']}
    common.save(output / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'measurements', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.workspace, args.measurements, args.reference, args.output)
    print(json.dumps({'status': result['status'], 'completed_n': result['completed_n'], 'tables': result['tables']}, indent=2))


if __name__ == '__main__':
    main()
