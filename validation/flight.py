"""Observe real command/HK/sensor downlink through the shared backend, without HTTP."""
import json
import os
from pathlib import Path
import re
import shlex
import threading
import time

from jobs.service import Laboratory
from project.model import board_catalog, load_config
from project.sensor_models import burst, display_units, identity_bytes, load, model_paths
from sensors.observations import fields
from .common import checked_workspace, environment, save, sha256, utc, input_manifest
from .protocol import LEVELS, SENSORS


def field(packet, name):
    values = packet['values']
    if name in values:
        return values[name]
    candidates = [value for key, value in values.items() if key.endswith('.' + name)]
    if len(candidates) != 1:
        raise ValueError('Ambiguous or missing telemetry field ' + name)
    return candidates[0]


def sequence_after(sequence, baseline):
    return isinstance(sequence, int) and isinstance(baseline, int) and 0 < ((sequence-baseline) & 0x3fff) < 0x2000


def sequence_baselines(packets):
    """Retain forward CCSDS progress; a late delivery must not move an anchor back."""
    latest = {}
    for packet in packets:
        if packet['errors']:
            continue
        previous = latest.get(packet['mid'])
        if previous is None or sequence_after(packet['sequence'], previous['sequence']):
            latest[packet['mid']] = packet
    return latest


def fresh(packet, sent, baseline=None):
    return (packet['event_id'] > sent['event_id'] and packet['received_at'] >= sent['sent_at'] and not packet['errors']
            and (baseline is None or packet['mid'] == baseline['mid'] and sequence_after(packet['sequence'], baseline['sequence'])))


class Flight:
    def __init__(self, root, output, target, timeout=60):
        self.root = checked_workspace(root)
        self.output = Path(output).resolve(); self.output.mkdir(parents=True, exist_ok=False)
        os.environ.update({key:value for key,value in environment(root).items() if key.startswith('FLIGHT_STUDIO_') or key in ('BUILD_JOBS', 'CMAKE_BUILD_PARALLEL_LEVEL')})
        self.lab = Laboratory(self.root)
        self.target, self.timeout = target, timeout
        self.catalog = None
        self.cursor = 0
        self._stop = threading.Event()
        self._observer = None
        self.jobs = []
        # Connection metadata is consumed internally; it is never serialized.
        connection = self.lab.hardware.state.read('connection.json', {})
        self.private = [str(connection[key]) for key in ('host', 'identity_file') if connection.get(key)]
        if connection.get('user'):
            self.private.append('/home/' + connection['user'])

    def redact(self, text):
        for value in sorted(self.private, key=len, reverse=True):
            text = text.replace(value, '[private-endpoint]')
        return text

    def close(self):
        self._stop.set()
        if self._observer:
            self._observer.join(timeout=3)
        self.lab.close()

    def job(self, action):
        record = {'action': action, 'target': self.target, 'started_utc': utc(), 'phases': []}
        index = len(self.jobs) + 1
        if action == 'build':
            save(self.output / f'{index:03d}-build-inputs.json', input_manifest(self.root))
        start = time.monotonic()
        self.jobs.append(record)
        original = self.lab.hardware.upload
        def upload(*args, **kwargs):
            begun = time.monotonic()
            try:
                return original(*args, **kwargs)
            finally:
                record['phases'].append({'phase': 'payload_transfer', 'start_s': begun-start,
                                         'end_s': time.monotonic()-start, 'elapsed_s': time.monotonic()-begun})
        self.lab.hardware.upload = upload
        try:
            ident = self.lab.job(action, {'target': self.target})['id']
            with (self.output / f'{index:03d}-{action}.jsonl').open('w') as log:
                for frame in self.lab.job_updates(ident):
                    for line in frame['lines']:
                        at = time.monotonic()-start
                        log.write(json.dumps({'elapsed_s': at, 'line': self.redact(line)}, ensure_ascii=False) + '\n'); log.flush()
                        if '[emulator] Linux SSH ready.' in line:
                            record.setdefault('guest_ssh_ready_observed_s', at)
                        if 'CFE_ES_Main entering OPERATIONAL state' in line:
                            record.setdefault('operational_observed_s', at)
                    if frame['status'] != 'running':
                        record['status'] = frame['status']
                if frame['status'] != 'succeeded':
                    raise RuntimeError(self.redact(frame.get('error') or frame['status']))
                result = frame.get('result') or {}
                record['result'] = {key: result[key] for key in ('fingerprint', 'installed_sha256', 'pid', 'instance',
                                    'built_at', 'deployed_at', 'stopped', 'linux_ready') if key in result}
            return record
        except BaseException as error:
            record['status'] = 'failed'; record['error'] = self.redact(f'{type(error).__name__}: {error}')
            raise
        finally:
            self.lab.hardware.upload = original
            record.update(elapsed_s=time.monotonic()-start, ended_utc=utc())
            save(self.output / 'jobs.json', self.jobs)

    def _observe(self):
        with (self.output / 'downlink.jsonl').open('a') as log:
            while not self._stop.wait(.05):
                for packet in self.lab.ground_snapshot()['history']:
                    if packet['event_id'] > self.cursor:
                        log.write(json.dumps(packet, ensure_ascii=False) + '\n')
                        self.cursor = packet['event_id']
                log.flush()

    def connect(self):
        begun = time.monotonic()
        if self._observer:
            self._stop.set(); self._observer.join(timeout=3)
            self._observer = None; self._stop = threading.Event()
        self.cursor = 0
        session = self.lab.ground_start({'target': self.target})
        self.catalog = self.lab.ground_catalog(self.target)
        save(self.output / 'catalog.json', self.catalog)
        if not self._observer:
            self._observer = threading.Thread(target=self._observe, daemon=True); self._observer.start()
        contact = session['first_flight']
        sent = self.lab.ground_send({'target': self.target, 'command_id': contact['enable_command'],
                                     'values': {'dest_IP': contact['return_host']}})
        packet = self.wait(lambda s: next((p for p in s['history'] if fresh(p, sent)), None), 'first downlink')
        hk = self.hk('sample_app')
        first_hk = self.wait(lambda s: next((p for p in s['history'] if p['mid'] == hk['mid'] and fresh(p, sent)), None), 'first housekeeping')
        return {'elapsed_s': time.monotonic()-begun, 'enable': sent, 'first_packet': packet, 'first_hk': first_hk}

    def wait(self, predicate, description):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            state = self.lab.ground_snapshot()
            if result := predicate(state):
                return result
            if not state['connected']:
                raise RuntimeError('Ground disconnected: ' + str(state.get('error')))
            time.sleep(.05)
        raise RuntimeError('Timed out waiting for ' + description)

    def hk(self, app):
        matches = [p for p in self.catalog['packets'] if p['app'] == app and 'HK' in p['id'].upper()
                   and any(f['name'].split('.')[-1] == 'CommandCounter' for f in p.get('fields', []))]
        if len(matches) != 1:
            raise ValueError('No unique real housekeeping definition for ' + app)
        return matches[0]

    def commands(self, repetitions=3):
        if repetitions < 1:
            raise ValueError('Choose a positive command repetition count')
        results = []
        save(self.output / 'commands.json', results)
        for app in ('sample_app', *(s['app'] for s in SENSORS)):
            hk = self.hk(app)
            for repetition in range(1, repetitions + 1):
                for suffix, signature in (('NOOP_CC', 'NOOP'), ('RESET_COUNTERS_CC', 'RESET'), ('NOOP_CC', 'NOOP')):
                    baseline = self.wait(lambda state: sequence_baselines([*state['history'], *state['packets']]).get(hk['mid']), app + ' HK baseline')
                    # EVS has its own sequence stream. A retransmitted old event can
                    # receive a new host ID/time, so retain the pre-send CCSDS anchor.
                    events = self.wait(lambda state: state['events'], 'EVS sequence baseline')
                    event_baselines = sequence_baselines(events)
                    reset = suffix == 'RESET_COUNTERS_CC'
                    expected = 0 if reset else (int(field(baseline, 'CommandCounter')) + 1) % 256
                    error_expected = 0 if reset else field(baseline, 'CommandErrorCounter')
                    attempt = {'app': app, 'repetition': repetition, 'command': app.upper() + '_' + suffix,
                               'baseline': baseline, 'event_baselines': event_baselines, 'expected_counter': expected,
                               'expected_error_counter': error_expected, 'status': 'running', 'passed': False}
                    results.append(attempt); save(self.output / 'commands.json', results)
                    try:
                        sent = self.lab.ground_send({'target': self.target, 'command_id': attempt['command'], 'values': {}})
                        attempt['sent'] = sent; save(self.output / 'commands.json', results)
                        event = self.wait(lambda state: next((p for p in state['events'] if p['mid'] in event_baselines
                            and fresh(p, sent, event_baselines[p['mid']]) and p['values'].get('PacketID.AppName') == app.upper()
                            and signature in p['values'].get('Message', '').upper()), None), app + ' ' + signature + ' EVS')
                        attempt['event'] = event; save(self.output / 'commands.json', results)
                        observed = self.wait(lambda state: next((p for p in state['history'] if p['mid'] == hk['mid'] and fresh(p, sent, baseline)
                            and field(p, 'CommandCounter') == expected and field(p, 'CommandErrorCounter') == error_expected), None), app + ' command counter')
                        attempt.update(housekeeping=observed, passed=True, status='passed')
                    except BaseException as error:
                        attempt.update(status='failed', error=self.redact(str(error)))
                        raise
                    finally:
                        save(self.output / 'commands.json', results)
        return results

    def collect(self, mid, count, after, predicate=None, timeout=None):
        records, sequences = [], set()
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while len(records) < count and time.monotonic() < deadline:
            for packet in self.lab.ground_snapshot()['history']:
                if packet['mid'] != mid or packet['received_at'] <= after or packet['sequence'] in sequences:
                    continue
                if packet['errors']:
                    raise ValueError('Telemetry decoder failed: ' + str(packet['errors']))
                if predicate and not predicate(packet):
                    continue
                records.append(packet); sequences.add(packet['sequence'])
                if len(records) == count:
                    break
            time.sleep(.05)
        if len(records) != count:
            raise RuntimeError(f'Expected {count} distinct packets for MID {mid:#x}; received {len(records)}')
        return records

    def raw_registers(self, sensor, spec):
        from sensors.registers import register_file
        config = load_config(self.root); catalog = board_catalog(config['board'], self.root)
        device = next(d for d in config['devices'] if d['id'] == sensor['device'])
        if self.target == 'native':
            path = register_file(self.root, device, catalog)
            return {'at': time.time(), 'status': 'read', 'hex': path.read_bytes().hex(),
                    'operation': 'read_native_register_image', 'path': path.relative_to(self.root).as_posix()}
        from hardware.sensor_probe import READ_REGISTERS
        first, size = burst(spec)
        blocks = [[first, size]] + [[c['register'], 1] for c in spec['controls']]
        identity = identity_bytes(spec)
        if identity:
            blocks.append([spec['id_register'], len(identity)])
        bus = catalog['buses'][device['bus']]['device'].split('-')[-1]
        command = shlex.join(['python3', '-c', READ_REGISTERS, bus, str(device['address']), json.dumps(blocks)])
        operation = {'operation': 'linux_i2c_rdwr', 'implementation': 'hardware/sensor_probe.py:READ_REGISTERS',
                     'bus': int(bus), 'address': device['address'], 'blocks': blocks}
        code, output = self.lab.hardware._capture(self.lab.hardware.ssh_argv(self.target) + [command], 30)
        if code:
            return {**operation, 'at': time.time(), 'status': 'unavailable', 'error': self.redact(output)}
        data = json.loads(output.splitlines()[0])
        if [len(bytes.fromhex(value)) for value in data] != [size for _,size in blocks]:
            raise ValueError('Incomplete raw register read')
        return {**operation, 'at': time.time(), 'status': 'read', 'blocks': [{'register': block[0], 'size': block[1], 'hex': value} for block,value in zip(blocks, data)]}

    def sensors(self, samples=5):
        if samples < 1:
            raise ValueError('Choose a positive sensor sample count')
        from sensors.registers import register_file, write, initial_registers, encode_values
        from sensors.runtime import connect_board, check_live
        config = load_config(self.root); catalog = board_catalog(config['board'], self.root)
        results = []
        for level in range(1 if self.target == 'physical' else 3):
            written = {}
            if self.target == 'qemu':
                with connect_board(self.root) as qmp:
                    check_live(config, qmp)
                    for sensor in SENSORS:
                        values = LEVELS[sensor['model']][level]
                        for name, value in values.items():
                            qmp.execute('qom-set', {'path': '/machine/peripheral/' + sensor['device'], 'property': name, 'value': value})
                        written[sensor['device']] = time.time()
            elif self.target == 'native':
                for sensor in SENSORS:
                    spec = load(model_paths(self.root)[sensor['model']])
                    device = next(d for d in config['devices'] if d['id'] == sensor['device'])
                    write(register_file(self.root, device, catalog), spec, LEVELS[sensor['model']][level])
                    written[sensor['device']] = time.time()
            for sensor in SENSORS:
                spec = load(model_paths(self.root)[sensor['model']]); mapping = fields(spec)
                descriptor = json.loads((self.root / 'project/apps' / (sensor['app'] + '.json')).read_text())
                mid = next(s['tlm_mid'] for s in descriptor['sensors'] if s['name'] == 'sample')
                expected = None if self.target == 'physical' else LEVELS[sensor['model']][level]
                raw = self.raw_registers(sensor, spec)
                tolerance = encode_values(initial_registers(spec), spec, expected or LEVELS[sensor['model']][0])
                if self.target == 'qemu':
                    # QEMU TMP105 powers up at 9 bits and truncates; other models also
                    # truncate to one LSB. Include one scaled-integer output rounding.
                    tolerance = {o['name']: (500 + 1 if sensor['model'] == 'tmp105' else 2 * (tolerance[o['name']] - 1) + 1)
                                 for o in spec['outputs']}
                valid = self.target != 'physical' or sensor['model'] == 'mpu6050'
                def matches(packet):
                    return bool(field(packet, 'Valid')) == valid and (field(packet, 'Status') == 0) == valid and (
                        expected is None or all(abs(field(packet, mapping[key])-value) <= tolerance[key] for key,value in expected.items()))
                after = written.get(sensor['device'], time.time())
                # Locate the first matching sample after a changed input, then retain
                # the following distinct samples without filtering incorrect values.
                record = {'model': sensor['model'], 'app': sensor['app'], 'level': level, 'mid': mid,
                          'expected_scaled': expected, 'tolerance_scaled': tolerance if expected else None,
                          'units': {o['name']: display_units(o['unit'])[1] for o in spec['outputs']},
                          'field_mapping': mapping, 'raw_registers': raw, 'packets': [],
                          'passed': False, 'status': 'running', 'valid_expected': valid, 'input_applied_at': after}
                results.append(record); save(self.output / 'sensors.json', results)
                try:
                    if valid and raw.get('status') != 'read':
                        raise ValueError('Required raw register dump was unavailable: ' + sensor['model'])
                    first = self.collect(mid, 1, after, matches)[0]
                    packets = [first] + (self.collect(mid, samples-1, first['received_at']) if samples > 1 else [])
                    record.update(packets=packets, passed=all(matches(packet) for packet in packets), status='passed')
                    if not record['passed']:
                        raise ValueError('Sensor samples did not match the fixed protocol: ' + sensor['model'])
                except BaseException as error:
                    record.update(status='failed', error=self.redact(str(error)))
                    raise
                finally:
                    save(self.output / 'sensors.json', results)
        return results

    def dropout(self, samples=5):
        if self.target != 'native':
            raise ValueError('Controlled mission interruption is only defined for the Native register transport')
        from sensors.registers import register_file
        config = load_config(self.root); catalog = board_catalog(config['board'], self.root)
        results = []
        for sensor in SENSORS:
            device = next(d for d in config['devices'] if d['id'] == sensor['device'])
            path = register_file(self.root, device, catalog); backup = path.with_suffix('.evaluation-disconnected')
            if backup.exists():
                raise ValueError('A previous interruption needs recovery before running another')
            descriptor = json.loads((self.root / 'project/apps' / (sensor['app'] + '.json')).read_text())
            mid = next(s['tlm_mid'] for s in descriptor['sensors'] if s['name'] == 'sample')
            before = self.collect(mid, 1, time.time(), lambda p: field(p, 'Valid') == 1)[0]
            schedule = self.lab.workspace.mission.schedule_config()
            tick_hz = schedule.get('tick_hz')
            period = descriptor['period_ticks'] / tick_hz if tick_hz else None
            bound = min(self.timeout, max(5.0, 3 * period + 2.0)) if period else self.timeout
            record = {'model': sensor['model'], 'before': before, 'status': 'running', 'passed': False,
                      'acquisition_period_s': period, 'period_ticks': descriptor['period_ticks'], 'schedule': schedule,
                      'recovery_bound_s': bound, 'criterion': 'first valid downlink within host observation bound; not first causal C acquisition'}
            results.append(record)
            try:
                path.rename(backup); record['removed_at'] = time.time()
                save(self.output / 'dropout.json', results)
                try:
                    first = self.collect(mid, 1, record['removed_at'], lambda p: field(p, 'Valid') == 0)[0]
                    invalid = [first] + (self.collect(mid, samples-1, first['received_at']) if samples > 1 else [])
                    record['invalid'] = invalid
                    if any(field(p, 'Valid') != 0 or field(p, 'Status') == 0 for p in invalid):
                        raise ValueError('Valid or successful samples interleaved during the outage')
                finally:
                    backup.rename(path)
                    record['restored_at'] = time.time()
                    save(self.output / 'dropout.json', results)
                record['recovery_observations'] = []
                deadline = time.monotonic() + bound
                after = record['restored_at']
                while time.monotonic() < deadline:
                    recovered = self.collect(mid, 1, after, timeout=max(.001, deadline-time.monotonic()))[0]
                    record['recovery_observations'].append(recovered)
                    save(self.output / 'dropout.json', results)
                    if field(recovered, 'Valid') == 1 and field(recovered, 'Status') == 0:
                        record.update(passed=True, status='passed', recovery_latency_s=recovered['received_at']-record['restored_at'])
                        break
                    after = recovered['received_at']
                save(self.output / 'dropout.json', results)
                if not record['passed']:
                    raise ValueError('No valid Native sensor downlink within recovery observation bound')
            except BaseException as error:
                record.update(status='failed', error=self.redact(str(error)))
                raise
            finally:
                save(self.output / 'dropout.json', results)
        return results

    def artifacts(self):
        _, payload, state = self.lab.hardware._require_build(target=self.target)
        local = {p.relative_to(payload).as_posix(): sha256(p) for p in sorted(payload.rglob('*')) if p.is_file() and not p.is_symlink()}
        result = {'build_fingerprint': state['fingerprint'], 'local': local}
        if self.target in ('qemu', 'physical'):
            deployment = self.lab.hardware.state.read('deployed.json', {})[self.target]
            if self.target == 'physical':
                directory = deployment['release'] + '/cpu1'
            else:
                directory = re.search(r'^WorkingDirectory=(.+)$', (self.root / 'cfs.service').read_text(), re.M)[1]
            script = "import hashlib,json,pathlib,sys; root=pathlib.Path(sys.argv[1]); print(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in json.loads(sys.argv[2])}))"
            command = shlex.join(['python3', '-c', script, directory, json.dumps(list(local))])
            code, output = self.lab.hardware._capture(self.lab.hardware.ssh_argv(self.target) + [command], 60)
            if code:
                raise RuntimeError('Could not hash installed payload: ' + self.redact(output))
            result['installed'] = json.loads(output.splitlines()[0])
            result['differences'] = [name for name in local if result['installed'].get(name) != local[name]]
            result['passed'] = not result['differences']
        else:
            result['passed'] = True
        save(self.output / 'artifacts.json', result)
        if not result['passed']:
            raise ValueError('Installed payload differs from the recorded local build')
        return result


def run(root, output, target, repetitions=3, samples=5, timeout=60):
    flight = Flight(root, output, target, timeout)
    report = {'schema': 1, 'target': target, 'started_utc': utc(), 'status': 'running',
              'command_repetitions': repetitions, 'sensor_samples_per_level': samples,
              'stationary_reported_by_operator': target == 'physical',
              'mounting': 'on the floor' if target == 'physical' else None, 'orientation_controlled': False}
    try:
        report['contact'] = flight.connect()
        report['commands'] = len(flight.commands(repetitions))
        report['sensor_cases'] = len(flight.sensors(samples))
        if target == 'native':
            report['dropout_cases'] = len(flight.dropout(samples))
        report['artifacts'] = flight.artifacts()
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'; report['error'] = flight.redact(f'{type(error).__name__}: {error}')
        raise
    finally:
        report['ended_utc'] = utc(); save(flight.output / 'target.json', report); flight.close()
    return report
