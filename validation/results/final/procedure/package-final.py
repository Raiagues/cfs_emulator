#!/usr/bin/env python3
"""Package the completed campaign without changing any evidence bytes.

Default action prints the finite allowlist. --execute checks completed final results,
scans public candidates for credentials/private endpoints, copies bytes with metadata,
verifies hashes, and atomically installs a NEW destination. It never builds, boots,
sends a flight command, rewrites measurements, deletes inputs, or commits to Git.

Run only after physical collection and final table generation have ended.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile

FROZEN_COMMIT = '64add2472dbf6869563612cf6b2c427b181dba5d'
DEFAULT_CAMPAIGN = Path('/tmp/flight-evaluation-20261123-final')
DEFAULT_TABLES = Path('/tmp/flight-evaluation-20261123-tables')
DEFAULT_REPO = Path('/home/rodriger/Documents/raspi/pi4-emulator/boot_cfs-estudio')
TARGETS = ('native', 'qemu', 'physical')
TABLES = (
    'q1_commands.csv', 'q1_attempts.csv', 'q2_errors.csv', 'q2_samples.csv',
    'physical_readings.csv', 'q3_interruptions.csv', 'q3_hal_samples.csv',
    'q3_recovery.csv', 'q4_artifacts.csv', 'q5_timings.csv', 'q5_statistics.csv',
    'summary.json', 'examples.json',
)
PROCEDURES = (
    'capture-evaluation-ground.cjs', 'capture-evaluation-ground.cjs.sha256',
    'qemu-procedure.json', 'run-qemu-campaign.py', 'run-physical-campaign.py',
    'run-physical-campaign.sha256', 'verify-nasa-sources.py',
)
ROOT_RAW = (
    'environment.json', 'environment-physical.json', 'prepare.json', 'sources.json',
    'nasa-before.json', 'nasa-after.json', 'nasa-preservation.json',
    'qemu-orchestration.json', 'physical-orchestration.json',
    'physical-launch.json', 'physical-preflight.json',
)
# Each member is a complete known path, or part of a fixed numbered series below.
# No recursive directory copy or wildcard inclusion is used.
PREPARE_STEMS = (
    '001-source-install', '002-profile', '003-add-bus', '004-device-eval_temp',
    '005-app-eval_temp', '006-reader-eval_temp', '007-device-eval_mag',
    '008-app-eval_mag', '009-reader-eval_mag', '010-device-eval_mpu',
    '011-app-eval_mpu', '012-reader-eval_mpu', '013-sync',
)
EXCLUSIONS = {
    'flight/': 'Local workspace, cloned NASA sources, runtime database, SSH material, guest disks and binaries; never exported.',
    'setup-qemu/': 'Image-candidate exploration; final image identity is retained in setup-qemu-final and setup-qemu-image-final.',
    'setup-qemu-image/': 'Interrupted preparation and diagnostic material outside the completed final campaign.',
    'setup-qemu-image-retry-1/': 'Interrupted retry and process diagnostics outside the completed final campaign.',
    'run-qemu-campaign.py': 'Duplicate coordinator; exact preserved copy is exported from procedure/.',
    'run-physical-campaign.py': 'Duplicate coordinator; exact preserved copy is exported from procedure/.',
    'qemu-orchestration.log': 'Console progress duplicate; complete structured orchestration receipt is exported.',
    'physical-orchestration.log': 'Console progress duplicate; complete structured orchestration receipt is exported.',
    'anything not on the finite allowlist': 'Not part of this publication selection; no automatic additions.',
    'private local HTTP server logs outside campaign': 'Contain local launch-session credentials; neither located nor exported by this script.',
}


def raw_paths():
    paths = list(ROOT_RAW)
    def add(directory, names):
        paths.extend(directory + '/' + name for name in names)
    def logs(directory, stem):
        add(directory, [stem + '.stdout.log', stem + '.stderr.log'])
    for stem in PREPARE_STEMS:
        logs('prepare', stem)
    add('prepare', ['commands.json'])
    for model in ('tmp105', 'lsm303dlhc_mag', 'mpu6050'):
        add('registers', [model + '-compile.json', model + '-compile.log'])
    add('registers', ['registers.json'])
    for target in ('native', 'qemu'):
        add('build-' + target, ['001-build-inputs.json', '001-build.jsonl', 'jobs.json', 'metrics.json'])
    for n in range(1, 11):
        app = f'eval_cycle_{n:02d}'
        for index, action in ((3*n-2, 'create'), (3*n-1, 'build'), (3*n, 'delete')):
            stem = f'{index:03d}-{action}-{app}'
            logs('cycles-native', stem)
            if action == 'build':
                add('cycles-native', [stem + '-build-inputs.json'])
    logs('cycles-native', '031-restore-base-mission')
    add('cycles-native', ['031-restore-base-mission-build-inputs.json', 'commands.json', 'metrics.json', 'sources-after-cycles.json'])
    for target in TARGETS:
        add('starts-' + target, ['catalog.json', 'downlink.jsonl', 'jobs.json', 'metrics.json'])
        for n in range(1, 11):
            add('starts-' + target, [f'{2*n-1:03d}-run.jsonl'])
            if n < 10:
                add('starts-' + target, [f'{2*n:03d}-stop.jsonl'])
        add(target, ['artifacts.json', 'catalog.json', 'commands.json', 'downlink.jsonl', 'sensors.json', 'target.json'])
    add('native', ['dropout.json'])
    add('qemu', ['tmp105-configuration.json'])
    for n in range(1, 6):
        add('boots-qemu', [f'{4*n-3:03d}-boot.jsonl', f'{4*n-2:03d}-run.jsonl'])
        if n < 5:
            add('boots-qemu', [f'{4*n-1:03d}-stop.jsonl', f'{4*n:03d}-shutdown.jsonl'])
    add('boots-qemu', ['catalog.json', 'downlink.jsonl', 'jobs.json', 'metrics.json'])
    add('first-boot-qemu', ['001-boot.jsonl', '002-shutdown.jsonl', 'jobs.json', 'provision.json'])
    add('between-qemu-series', ['001-stop.jsonl', 'jobs.json'])
    add('before-physical-series', ['001-stop.jsonl', '002-shutdown.jsonl', 'jobs.json'])
    add('after-physical-series', ['001-stop.jsonl', 'jobs.json', 'final-state.json'])
    add('setup-physical-final', ['preconditions.json'])
    logs('setup-builder', '001-prepare-cfs-builder')
    add('setup-builder', ['001-prepare-cfs-builder-build-inputs.json', 'commands.json', 'setup.json'])
    logs('setup-qemu-final', '001-prepare-emulator-key')
    logs('setup-qemu-final', '002-qemu-version')
    add('setup-qemu-final', ['commands.json', 'setup.json'])
    logs('setup-qemu-image-final', '001-prepare-evaluation-image')
    add('setup-qemu-image-final', ['commands.json', 'setup.json'])
    assert len(paths) == len(set(paths)), 'Duplicate raw allowlist entry'
    return sorted(paths)


def plan(campaign, tables):
    entries = [('campaign', p, 'raw/' + p, campaign/p) for p in raw_paths()]
    entries += [('tables', p, 'tables/' + p, tables/p) for p in TABLES]
    entries += [('campaign', 'procedure/' + p, 'procedure/' + p, campaign/'procedure'/p) for p in PROCEDURES]
    illustrations = ['ground-prerequisite-checks.json', 'ground-capture-cleanup.json', 'ground-qemu/capture.json', 'ground-qemu/ground-qemu-overview.png']
    for app in ('eval_temp', 'eval_mag', 'eval_mpu'):
        illustrations += [f'ground-qemu/ground-qemu-{app}.png', f'ground-qemu/ground-qemu-{app}-telemetry.png']
    entries += [('campaign', 'illustrations/' + p, 'illustrations/' + p, campaign/'illustrations'/p) for p in illustrations]
    entries += [('packager', Path(__file__).name, 'procedure/package-final.py', Path(__file__).resolve())]
    assert len(entries) == len({e[2] for e in entries}), 'Duplicate output path'
    return entries


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_file(path, boundary):
    require(path.is_file() and not path.is_symlink(), 'Not a regular allowed file: ' + path.name)
    resolved = path.resolve()
    require(resolved.is_relative_to(boundary), 'Source escapes its boundary: ' + path.name)
    for parent in path.parents:
        require(not parent.is_symlink(), 'Symlink in source ancestry: ' + path.name)
        if parent == boundary:
            break
    require(stat.S_ISREG(path.stat().st_mode), 'Source is not regular: ' + path.name)


def private_patterns(campaign):
    # Read only the local connection record to detect accidental endpoint export.
    # Its values are never printed, copied, hashed into the public manifest or changed.
    database = campaign/'flight/hardware/.runtime/runtime.sqlite3'
    require(database.is_file(), 'Private-endpoint audit requires the local runtime database')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute("SELECT value FROM records WHERE name='connection'").fetchone()
    connection = json.loads(row[0]) if row and row[0] else {}
    require(connection.get('host') and connection.get('identity_file'), 'Configured private endpoint missing for publication audit')
    result = {
        'private-key-material': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----',
        'session-launch-key': rb'[?&]t=[A-Za-z0-9_-]{20,}',
        'github-credential': rb'\b(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{30,})',
        'ssh-public-key-material': rb'\bssh-(?:ed25519|rsa)\s+[A-Za-z0-9+/=]{30,}',
    }
    for key in ('host', 'identity_file'):
        result['configured-' + key] = re.escape(str(connection[key]).encode())
    if connection.get('user'):
        result['configured-user-home'] = re.escape(('/home/' + str(connection['user'])).encode())
    return {label: re.compile(pattern) for label, pattern in result.items()}


def scalar_keys(value, path='$'):
    private = {'password', 'passwd', 'secret', 'token', 'access_token', 'refresh_token',
               'api_key', 'private_key', 'client_secret', 'identity_file', 'hostname',
               'host', 'user', 'username', 'connection'}
    if isinstance(value, dict):
        for key, child in value.items():
            require(not (key.lower() in private and isinstance(child, str) and child),
                    'Potential private scalar key at ' + path + '.' + key)
            if isinstance(child, (dict, list)):
                scalar_keys(child, path + '.' + key)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                scalar_keys(child, path + '[*]')


def validate_complete(campaign, tables, repo):
    statuses = ['prepare.json', 'registers/registers.json', 'qemu-orchestration.json',
                'physical-orchestration.json', 'build-native/metrics.json', 'build-qemu/metrics.json',
                'cycles-native/metrics.json', 'boots-qemu/metrics.json', 'first-boot-qemu/provision.json',
                'setup-builder/setup.json', 'setup-qemu-final/setup.json', 'setup-qemu-image-final/setup.json']
    statuses += [f'{target}/target.json' for target in TARGETS]
    statuses += [f'starts-{target}/metrics.json' for target in TARGETS]
    for relative in statuses:
        require(load(campaign/relative).get('status') == 'passed', 'Final stage not passed: ' + relative)
    preservation = load(campaign/'nasa-preservation.json')
    require(preservation.get('status') == 'passed' or preservation.get('passed') is True, 'NASA preservation not passed')
    require(load(campaign/'nasa-before.json') == load(campaign/'nasa-after.json'), 'NASA before/after manifests differ')
    require(load(campaign/'prepare.json')['platform_commit'] == FROZEN_COMMIT, 'Unexpected frozen measurement revision')
    summary = load(tables/'summary.json')
    require(summary.get('status') == 'final' and summary.get('publishable') is True and summary.get('complete') is True and not summary.get('issues'), 'Table export is not complete and publishable')
    require(sha((repo/'validation/summarize.py').read_bytes()) == summary['analysis_sha256'], 'Table-analysis code differs from current repository file')
    capture = load(campaign/'illustrations/ground-qemu/capture.json')
    require(capture.get('passed') is True and not capture.get('page_errors') and not capture.get('blocked_requests'), 'Ground capture is incomplete')
    require(load(campaign/'illustrations/ground-capture-cleanup.json').get('server_stopped') is True, 'Capture server is not confirmed stopped')
    return summary, capture


def execute(args, entries):
    campaign, tables, repo, destination = args.campaign, args.tables, args.repo, args.destination
    require(not destination.exists(), 'Destination already exists; no overwrite or merge is performed')
    summary, capture = validate_complete(campaign, tables, repo)
    patterns = private_patterns(campaign)
    records = []; snapshots = {}
    # All validation and scanning completes before any destination directory is made.
    for source_kind, source_name, target, source in entries:
        boundary = campaign if source_kind == 'campaign' else tables if source_kind == 'tables' else source.parent
        check_file(source, boundary)
        before = source.stat(); data = source.read_bytes(); after = source.stat()
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'Source changed during inspection: ' + source_name)
        if source.suffix in ('.json', '.jsonl', '.log', '.py', '.cjs', '.sha256', '.csv'):
            for label, pattern in patterns.items():
                require(not pattern.search(data), 'Private-data pattern ' + label + ' in ' + source_name)
            if source.suffix == '.json':
                try:
                    scalar_keys(json.loads(data))
                except ValueError as error:
                    raise ValueError(source_name + ': ' + str(error)) from None
        record = {'source_kind': source_kind, 'source_path': source_name, 'path': target,
                  'bytes': len(data), 'sha256': sha(data), 'source_mtime_ns': before.st_mtime_ns}
        records.append(record); snapshots[target] = (before.st_size, before.st_mtime_ns)
    by_path = {row['path']: row for row in records}
    for row in summary['inputs']:
        copied = by_path.get('raw/' + row['path'])
        require(copied and copied['sha256'] == row['sha256'] and copied['bytes'] == row['bytes'], 'Raw evidence differs from final table input: ' + row['path'])
    for name, row in summary['tables'].items():
        require(by_path.get('tables/' + name, {}).get('sha256') == row['sha256'], 'CSV differs from summary: ' + name)
    for row in capture['screenshots']:
        require(by_path.get('illustrations/ground-qemu/' + row['file'], {}).get('sha256') == row['sha256'], 'Screenshot differs from capture receipt: ' + row['file'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + destination.name + '-staging-', dir=destination.parent))
    try:
        for source_kind, source_name, target, source in entries:
            now = source.stat(); require((now.st_size, now.st_mtime_ns) == snapshots[target], 'Source changed before copy: ' + source_name)
            output = staging/target; output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output, follow_symlinks=False)
            require(sha(output.read_bytes()) == by_path[target]['sha256'], 'Copy hash mismatch: ' + target)
        manifest = {
            'schema': 1, 'status': 'complete', 'packaged_utc': datetime.now(timezone.utc).isoformat(),
            'measurement_commit': FROZEN_COMMIT, 'campaign_name': campaign.name,
            'copy_policy': 'Exact bytes and file modification times preserved; no measurement rewriting or redaction during packaging.',
            'analysis': {'repository_path': 'validation/summarize.py', 'sha256': summary['analysis_sha256'],
                         'invocation': 'python3 -B -m validation.summarize --campaign validation/results/final/raw --output NEW_DIRECTORY'},
            'privacy_check': {'passed': True, 'pattern_names': sorted(patterns), 'private_scalar_keys_checked': True,
                              'note': 'Configured private endpoint values were used only in memory and are not exported. Public upstream banners and systemd unit names remain intact.'},
            'selection': 'Finite allowlist declared in procedure/package-final.py; unlisted files are not copied.',
            'excluded_source_paths': EXCLUSIONS, 'files': records,
        }
        (staging/'procedure/package-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        staging.rename(destination)
    except BaseException:
        # Preserve a partially written staging directory for inspection; never delete source evidence.
        print('Packaging stopped; staging retained at ' + str(staging), file=sys.stderr)
        raise
    print(json.dumps({'status': 'complete', 'destination': str(destination), 'files': len(records), 'bytes': sum(r['bytes'] for r in records)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument('--tables', type=Path, default=DEFAULT_TABLES)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--execute', action='store_true', help='Validate and copy the final completed campaign; default only lists exact paths.')
    args = parser.parse_args()
    args.campaign = args.campaign.resolve(); args.tables = args.tables.resolve(); args.repo = args.repo.resolve()
    args.destination = (args.destination or args.repo/'validation/results/final').absolute()
    require(not args.destination.is_symlink(), 'Destination cannot be a symlink')
    entries = plan(args.campaign, args.tables)
    if not args.execute:
        print(json.dumps({'mode': 'plan only; no files copied or hashes computed', 'destination': str(args.destination),
                          'files': [{'source_kind': kind, 'source_path': name, 'path': target} for kind, name, target, source in entries],
                          'exclusions': EXCLUSIONS}, ensure_ascii=False, indent=2))
        return
    execute(args, entries)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        raise SystemExit('Packaging refused: ' + str(error))
