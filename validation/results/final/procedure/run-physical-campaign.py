"""Coordinate the physical phase using the frozen, already-built evaluation workspace.

No compilation, physical-board power-off, or private connection export is performed.
Run only after the QEMU interface capture and its browser/server are closed.
"""
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent if HERE.name == 'procedure' else HERE
ROOT = CAMPAIGN / 'flight'
sys.path.insert(0, str(ROOT))
from validation.common import environment, save, sha256, utc
from validation.flight import Flight, run as observe_target
from validation.metrics import starts
from hardware.state import RuntimeState

os.environ.update(environment(ROOT))
STATE = CAMPAIGN / 'physical-orchestration.json'
EXPECTED_FINGERPRINT = '28c867ab6b73c3de4093fddae2adcdc6f26d73ab60ea0cb7b31497e620a13ded'
OUTPUTS = {
    'stop-and-shutdown-isolated-qemu': 'before-physical-series',
    'physical-preconditions-and-arm-payload': 'setup-physical-final',
    'ten-cfs-starts': 'starts-physical',
    'commands-sensors-portability': 'physical',
    'stop-physical-cfs-service': 'after-physical-series',
}
if STATE.exists() or any((CAMPAIGN / output).exists() for output in OUTPUTS.values()):
    raise SystemExit('Physical campaign output already exists; preserve previous evidence')

state = {
    'status': 'running', 'started_utc': utc(), 'pid': os.getpid(),
    'harness_revision': '64add2472dbf6869563612cf6b2c427b181dba5d',
    'coordinator_sha256': sha256(Path(__file__)),
    'launch': 'detached process session; frozen validation functions',
    'build_jobs': 1, 'recompile': False, 'physical_poweroff': False,
    'stationary_reported_by_operator': True, 'mounting': 'no chão',
    'orientation_controlled': False, 'completed': [], 'phases': [],
}
connection = RuntimeState(ROOT).read('connection.json', {})
private = [str(connection[k]) for k in ('host', 'identity_file') if connection.get(k)]
if connection.get('user'):
    private.append('/home/' + connection['user'])

def redact(value):
    for secret in sorted(private, key=len, reverse=True):
        value = value.replace(secret, '[private-endpoint]')
    return value

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

try:
    for name in ('native', 'qemu'):
        previous = json.loads((CAMPAIGN / name / 'target.json').read_text())
        if previous['status'] != 'passed':
            raise RuntimeError(name + ' evaluation prerequisite is not complete')
    reference = json.loads((CAMPAIGN / 'qemu/artifacts.json').read_text())
    if not reference['passed'] or reference['build_fingerprint'] != EXPECTED_FINGERPRINT:
        raise RuntimeError('QEMU ARM artifact prerequisite does not match the frozen build')

    phase('stop-and-shutdown-isolated-qemu')
    maintenance = Flight(ROOT, CAMPAIGN / OUTPUTS[state['phase']], 'qemu')
    try:
        maintenance.job('stop')
        maintenance.job('shutdown')
        if maintenance.lab.hardware._qemu_running():
            raise RuntimeError('Isolated QEMU guest remained running')
    finally:
        maintenance.close()
    completed('stop-and-shutdown-isolated-qemu')

    phase('physical-preconditions-and-arm-payload')
    preflight = Flight(ROOT, CAMPAIGN / OUTPUTS[state['phase']], 'physical')
    try:
        _, payload, build = preflight.lab.hardware._require_build(target='physical')
        current = {p.relative_to(payload).as_posix(): sha256(p)
            for p in sorted(payload.rglob('*')) if p.is_file() and not p.is_symlink()}
        if build['fingerprint'] != EXPECTED_FINGERPRINT or current != reference['local']:
            raise RuntimeError('Physical deployment must reuse the exact QEMU ARM payload without recompilation')
        board = preflight.lab.hardware.probe(None, lambda line: None, None)
        safe = {key: board.get(key) for key in ('model', 'arch', 'os', 'glibc', 'i2c',
            'raspios', 'authorized', 'service_installed', 'service', 'ready')}
        safe.update(recorded_utc=utc(), build_fingerprint=build['fingerprint'],
            local_payload_files=len(current), matches_qemu_payload=True, recompiled=False)
        save(preflight.output / 'preconditions.json', safe)
        if not board.get('ready') or board.get('service') != 'inactive':
            raise RuntimeError('Physical cFS service must be ready and inactive before timings')
    finally:
        preflight.close()
    completed('physical-preconditions-and-arm-payload')

    phase('ten-cfs-starts')
    starts(ROOT, CAMPAIGN / 'starts-physical', 'physical', repetitions=10, leave_running=True)
    completed('ten-cfs-starts')

    phase('commands-sensors-portability')
    result = observe_target(ROOT, CAMPAIGN / 'physical', 'physical', repetitions=3, samples=5)
    if result['artifacts']['local'] != reference['local']:
        raise RuntimeError('Physical observation payload differs from the measured QEMU payload')
    completed('commands-sensors-portability')

    phase('stop-physical-cfs-service')
    maintenance = Flight(ROOT, CAMPAIGN / OUTPUTS[state['phase']], 'physical')
    try:
        maintenance.job('stop')
        board = maintenance.lab.hardware.probe(None, lambda line: None, None)
        if board.get('service') != 'inactive':
            raise RuntimeError('Physical cFS service remained active after the evaluation')
        save(maintenance.output / 'final-state.json', {'service': board['service'],
            'ssh_responded': True, 'physical_poweroff_requested': False, 'recorded_utc': utc()})
    finally:
        maintenance.close()
    completed('stop-physical-cfs-service')
    state.update(status='passed', ended_utc=utc(), physical_cfs_stopped=True,
        physical_linux_left_running=True, isolated_qemu_stopped=True)
except BaseException as error:
    state.update(status='failed', ended_utc=utc(), error=redact(f'{type(error).__name__}: {error}'))
    if state['phases'] and state['phases'][-1]['status'] == 'running':
        state['phases'][-1].update(status='failed', ended_utc=state['ended_utc'], error=state['error'])
    print(json.dumps({'error': state['error']}), flush=True)
finally:
    save(STATE, state)
    print(json.dumps({'status': state['status'], 'phase': state.get('phase')}), flush=True)
if state['status'] != 'passed':
    raise SystemExit(1)
