"""Coordinate frozen evaluation functions; no measurements or evidence are synthesized."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

CAMPAIGN = Path(__file__).resolve().parent
ROOT = CAMPAIGN / 'flight'
sys.path.insert(0, str(ROOT))
from validation.common import Recorder, environment, save, sha256, utc
from validation.flight import Flight, run as observe_target
from validation.metrics import starts
from project.defaults import network
from project.qemu.generate import fingerprint

os.environ.update(environment(ROOT))
STATE = CAMPAIGN / 'qemu-orchestration.json'
state = {'status': 'running', 'started_utc': utc(), 'pid': os.getpid(),
         'harness_revision': '64add2472dbf6869563612cf6b2c427b181dba5d',
         'launch': 'detached process session; frozen validation functions', 'completed': [], 'phases': []}

OUTPUTS = {'setup-identity-and-versions': 'setup-qemu-final',
           'first-provisioning-boot': 'first-boot-qemu',
           'five-prepared-guest-boots': 'boots-qemu',
           'stop-cfs-with-guest-running': 'between-qemu-series',
           'ten-cfs-starts': 'starts-qemu',
           'commands-sensors-portability': 'qemu'}

def phase(name):
    state.update(phase=name, phase_started_utc=utc())
    state['phases'].append({'phase': name, 'status': 'running',
                            'started_utc': state['phase_started_utc'], 'output_directory': OUTPUTS[name]})
    save(STATE, state)
    print(json.dumps({'phase': name, 'started_utc': state['phase_started_utc']}), flush=True)

def completed(name):
    ended = utc()
    state['completed'].append({'phase': name, 'ended_utc': ended})
    state['phases'][-1].update(status='passed', ended_utc=ended)
    save(STATE, state)

def streaming_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

try:
    image_setup = json.loads((CAMPAIGN / 'setup-qemu-image-final/setup.json').read_text())
    if image_setup['status'] != 'passed':
        raise RuntimeError('Emulator image prerequisite is not complete')
    phase('setup-identity-and-versions')
    recorder = Recorder(ROOT, CAMPAIGN / 'setup-qemu-final')
    image = 'flight-studio-evaluation:' + fingerprint(ROOT)[:12]
    inspected = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]
    expected = fingerprint(ROOT)
    label = (inspected['Config'].get('Labels') or {}).get('org.flight-studio.register-models')
    if label != expected:
        raise RuntimeError('Emulator image does not match the frozen register models')
    disk = ROOT / 'board/raspios.qcow2'
    if disk.exists():
        raise RuntimeError('First provisioning requires the isolated guest disk to be absent')
    setup = {'status': 'running', 'started_utc': utc(), 'guest_disk_existed_before': False,
             'image': {'tag': image, 'id': inspected['Id'], 'architecture': inspected.get('Architecture'),
                       'register_models': label, 'expected_register_models': expected}}
    save(recorder.output / 'setup.json', setup)
    key = recorder.cli('prepare-emulator-key', 'emulator', 'key', '--json')
    key_output = recorder.output / key['stdout']
    json.loads(key_output.read_text())
    key_output.write_text(json.dumps({'identity': '[private-key-path]',
        'redacted': 'Identity filename; key material was never emitted'}) + '\n')
    setup['public_key_sha256'] = sha256(Path(network(ROOT).keys) / 'id_ed25519.pub')
    version = recorder.command('qemu-version', ['docker', 'run', '--rm', '--entrypoint',
        '/usr/bin/qemu-system-aarch64', image, '--version'])
    setup['qemu_version'] = (recorder.output / version['stdout']).read_text().strip()
    setup.update(status='passed', ended_utc=utc())
    save(recorder.output / 'setup.json', setup)
    completed('setup-identity-and-versions')

    phase('first-provisioning-boot')
    provision = Flight(ROOT, CAMPAIGN / 'first-boot-qemu', 'qemu')
    report = {'status': 'running', 'started_utc': utc(), 'guest_disk_existed_before': False,
              'scope': 'first disk provisioning and Linux/SSH boot; no cFS start; outside N=5'}
    save(provision.output / 'provision.json', report)
    try:
        report['boot'] = provision.job('boot')
        guest_probe = "import json,platform,pathlib; p=pathlib.Path('/etc/os-release'); pairs={k:v.strip(chr(34)) for k,v in (line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.startswith('#'))}; print(json.dumps({'kernel':platform.release(),'machine':platform.machine(),'os':{k:pairs.get(k) for k in ('ID','VERSION_ID','PRETTY_NAME','VERSION_CODENAME')}}))"
        argv = provision.lab.hardware.ssh_argv('qemu') + [shlex.join(['python3', '-c', guest_probe])]
        try:
            guest = subprocess.run(argv, capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Guest metadata probe timed out') from None
        if guest.returncode:
            raise RuntimeError(f'Guest metadata probe failed with exit code {guest.returncode}')
        report['guest'] = json.loads(guest.stdout)
        save(provision.output / 'provision.json', report)
        report['shutdown'] = provision.job('shutdown')
        if provision.lab.hardware._qemu_running():
            raise RuntimeError('Guest remained running before disk hashing')
        report['prepared_disk'] = {'path': 'board/raspios.qcow2', 'bytes': disk.stat().st_size,
                                  'sha256': streaming_sha256(disk), 'observed_utc': utc(),
                                  'guest_running_during_hash': False}
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=provision.redact(f'{type(error).__name__}: {error}'))
        raise
    finally:
        report['ended_utc'] = utc()
        save(provision.output / 'provision.json', report)
        provision.close()
    completed('first-provisioning-boot')

    phase('five-prepared-guest-boots')
    starts(ROOT, CAMPAIGN / 'boots-qemu', 'qemu', repetitions=5, guest_boots=True, leave_running=True)
    completed('five-prepared-guest-boots')

    phase('stop-cfs-with-guest-running')
    maintenance = Flight(ROOT, CAMPAIGN / 'between-qemu-series', 'qemu')
    try:
        maintenance.job('stop')
        if not maintenance.lab.hardware._qemu_running():
            raise RuntimeError('Guest must remain running for cFS-only start measurements')
    finally:
        maintenance.close()
    completed('stop-cfs-with-guest-running')

    phase('ten-cfs-starts')
    starts(ROOT, CAMPAIGN / 'starts-qemu', 'qemu', repetitions=10, leave_running=True)
    completed('ten-cfs-starts')

    phase('commands-sensors-portability')
    observe_target(ROOT, CAMPAIGN / 'qemu', 'qemu', repetitions=3, samples=5)
    completed('commands-sensors-portability')
    state.update(status='passed', ended_utc=utc(), guest_left_running_for_review=True)
except BaseException as error:
    state.update(status='failed', ended_utc=utc(), error=f'{type(error).__name__}: {error}')
    if state['phases'] and state['phases'][-1]['status'] == 'running':
        state['phases'][-1].update(status='failed', ended_utc=state['ended_utc'], error=state['error'])
    raise
finally:
    save(STATE, state)
    print(json.dumps({'status': state['status'], 'phase': state.get('phase')}), flush=True)
