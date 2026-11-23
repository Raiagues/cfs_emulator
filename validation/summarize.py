"""Post-collection tables; never starts a target or changes the frozen harness.

python3 -B -m validation.summarize --campaign DIR --output NEW_DIR
--partial is a local diagnostic export, always marked non-publishable.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

from .protocol import LEVELS

TARGETS = ('native', 'qemu', 'physical')
MODELS = ('tmp105', 'lsm303dlhc_mag', 'mpu6050')
APPS = ('sample_app', 'eval_temp', 'eval_mag', 'eval_mpu')
MODEL_APPS = dict(zip(MODELS, APPS[1:]))
REQUIRED = ['prepare.json', 'registers/registers.json', 'build-native/metrics.json',
            'build-qemu/metrics.json', 'cycles-native/metrics.json', 'boots-qemu/metrics.json'] + [
    f'{target}/{name}.json' for target in TARGETS for name in ('target', 'commands', 'sensors', 'artifacts')
] + [f'starts-{target}/metrics.json' for target in TARGETS] + ['native/dropout.json']
HEADERS = {
    'q1_commands': ['target', 'app', 'command', 'sent', 'confirmed', 'failures'],
    'q1_attempts': ['target', 'app', 'repetition', 'step', 'command', 'mid', 'function_code', 'send_id',
                    'event_id', 'event_sequence', 'hk_event_id', 'baseline_sequence', 'hk_sequence',
                    'baseline_counter', 'command_counter', 'error_counter', 'confirmed'],
    'q2_errors': ['environment', 'target', 'model', 'channel', 'n', 'max_abs_error_scaled',
                   'max_tolerance_scaled', 'max_abs_error', 'max_tolerance', 'unit'],
    'q2_samples': ['environment', 'target', 'model', 'scenario', 'repetition', 'level', 'sample_index',
                    'channel', 'input_scaled', 'read_scaled', 'abs_error_scaled', 'tolerance_scaled',
                    'input', 'read', 'abs_error', 'tolerance', 'unit', 'valid'],
    'physical_readings': ['model', 'channel', 'n', 'min', 'median', 'max', 'unit', 'valid_expected'],
    'q3_interruptions': ['environment', 'target', 'model', 'repetition', 'episodes', 'expected_invalid',
                         'observed_invalid', 'recovery_observations', 'recovery_s', 'recovery_bound_s',
                         'first_causal_read_valid', 'passed'],
    'q3_hal_samples': ['model', 'repetition', 'sample_index', 'disconnected', 'status', 'valid', 'first_recovery'],
    'q3_recovery': ['target', 'model', 'sample_index', 'sequence', 'received_after_restore_s', 'valid', 'status'],
    'q4_artifacts': ['path', 'category', 'qemu_sha256', 'physical_sha256', 'identical'],
    'q5_timings': ['kind', 'target', 'repetition', 'stage', 'seconds'],
    'q5_statistics': ['kind', 'target', 'stage', 'n', 'min', 'q1', 'median', 'q3', 'iqr', 'max'],
}


class CampaignError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CampaignError(message)


def number(value, label='value', minimum=None):
    require(type(value) in (int, float) and math.isfinite(value), label + ': expected a finite number')
    require(minimum is None or value >= minimum, label + ': outside the allowed range')
    return value


def stats(values):
    values = [number(value) for value in values]
    if not values:
        return {'n': 0}
    result = dict(n=len(values), min=min(values), median=statistics.median(values), max=max(values))
    if len(values) > 1:
        q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
        result.update(q1=q1, q3=q3, iqr=q3-q1)
    return result


def value(packet, name):
    fields = packet['values']
    if name in fields:
        return fields[name]
    candidates = [v for k, v in fields.items() if k.endswith('.' + name)]
    require(len(candidates) == 1, 'missing or ambiguous telemetry field ' + name)
    return candidates[0]


def sequence_after(new, previous):
    return type(new) is int and type(previous) is int and 0 <= new < 16384 and 0 <= previous < 16384 and 0 < ((new-previous) & 16383) < 8192


def newer(packet, sent, baseline=None):
    return (not packet['errors'] and packet['event_id'] > sent['event_id'] and packet['received_at'] >= sent['sent_at']
            and (baseline is None or packet['mid'] == baseline['mid'] and sequence_after(packet['sequence'], baseline['sequence'])))


def successful(report, label):
    require(report.get('status') == 'passed', label + ': status is not passed')


def exact_keys(actual, expected, label):
    require(Counter(list(actual)) == Counter(list(expected)), label + ': missing, duplicate or unexpected cases')


def repetitions(rows, expected, label):
    exact_keys([row['repetition'] for row in rows], range(1, expected+1), label)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_packet(packet):
    # Only public wire facts, never connection metadata, paths or event text.
    return {key: packet[key] for key in ('id', 'app', 'mid', 'code', 'hex', 'sequence', 'event_id', 'received_at', 'sent_at') if key in packet}


class Analysis:
    def __init__(self, campaign):
        self.campaign = Path(campaign).resolve()
        self.inputs, self.data, self.issues = [], {}, []
        self.tables = {name: [] for name in HEADERS}
        self.examples, self.scales = {}, {}
        self.provenance = {}
        for relative in REQUIRED:
            path = self.campaign / relative
            try:
                require(path.resolve().is_relative_to(self.campaign), 'input escapes campaign directory')
                raw = path.read_bytes()
                self.data[relative] = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                self.inputs.append({'path': relative, 'sha256': digest(raw), 'bytes': len(raw)})
            except (OSError, ValueError) as error:
                self.issues.append(relative + ': ' + ('missing or unreadable input' if isinstance(error, OSError) else 'invalid JSON input'))

    def section(self, label, function):
        try:
            function()
        except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError, AttributeError) as error:
            self.issues.append(label + ': ' + str(error))

    def prepare(self):
        report = self.data['prepare.json']; successful(report, 'prepare')
        require(report.get('nasa_originals_unchanged') is True, 'NASA original preservation is unconfirmed')
        for key in ('platform_commit', 'nasa_commit'):
            require(isinstance(report.get(key), str) and len(report[key]) == 40 and all(c in '0123456789abcdef' for c in report[key]), key + ': missing full revision')
        require(report.get('protocol') == 'final-technical-v1', 'unrecognized frozen protocol')
        exact_keys([row['app'] for row in report['sensors']], APPS[1:], 'prepared sensor apps')
        self.provenance = {key: report[key] for key in ('platform_commit', 'nasa_commit', 'protocol', 'source_method', 'nasa_originals_unchanged') if key in report}

    def command_cases(self, target):
        report = self.data[f'{target}/target.json']; successful(report, target)
        require(report['target'] == target and report['command_repetitions'] == 3, 'wrong target or Q1 repetition count')
        rows = self.data[f'{target}/commands.json']
        require(len(rows) == 36 and report['commands'] == 36, 'Q1 requires 36 command attempts per target')
        expected = [(app, rep, kind) for app in APPS for rep in range(1, 4) for kind in ('NOOP_CC', 'RESET_COUNTERS_CC', 'NOOP_CC')]
        require([(row['app'], row['repetition'], row['command'].removeprefix(row['app'].upper()+'_')) for row in rows] == expected,
                'Q1 command sequence differs from NOOP/RESET/NOOP × 3 × 4 apps')
        counts = defaultdict(lambda: [0, 0])
        used_sends = set()
        for index, row in enumerate(rows):
            successful(row, 'Q1 attempt'); require(row.get('passed') is True, 'Q1 attempt did not pass')
            sent, event, baseline, hk = (row[key] for key in ('sent', 'event', 'baseline', 'housekeeping'))
            app, kind = expected[index][0], expected[index][2]
            require(sent['id'] == row['command'] and sent['app'] == app, 'Q1 sent command does not match the attempt')
            require(sent['event_id'] not in used_sends, 'Q1 reused a send ID'); used_sends.add(sent['event_id'])
            anchor = row['event_baselines'].get(str(event['mid']))
            require(anchor is not None and newer(event, sent, anchor), 'Q1 EVS is old, duplicate or malformed')
            require(value(event, 'PacketID.AppName') == app.upper() and ('RESET' if kind.startswith('RESET') else 'NOOP') in value(event, 'Message').upper(), 'Q1 EVS belongs to another app/command')
            require(newer(hk, sent, baseline), 'Q1 HK is old, duplicate or malformed')
            reset = kind == 'RESET_COUNTERS_CC'
            expected_count = 0 if reset else (int(value(baseline, 'CommandCounter'))+1) % 256
            expected_errors = 0 if reset else value(baseline, 'CommandErrorCounter')
            require(value(hk, 'CommandCounter') == expected_count == row['expected_counter'], 'Q1 command counter mismatch')
            require(value(hk, 'CommandErrorCounter') == expected_errors == row['expected_error_counter'], 'Q1 error counter mismatch')
            require(index % 3 != 2 or expected_count == 1, 'Q1 NOOP after RESET must produce one')
            if index+1 < len(rows):
                require(max(event['event_id'], hk['event_id']) < rows[index+1]['sent']['event_id'], 'Q1 responses overlap the next send')
            counts[(app, kind)][0] += 1; counts[(app, kind)][1] += 1
            self.tables['q1_attempts'].append(dict(target=target, app=app, repetition=row['repetition'], step=index%3+1,
                command=kind, mid=sent['mid'], function_code=sent['code'], send_id=sent['event_id'], event_id=event['event_id'],
                event_sequence=event['sequence'], hk_event_id=hk['event_id'], baseline_sequence=baseline['sequence'],
                hk_sequence=hk['sequence'], baseline_counter=value(baseline, 'CommandCounter'),
                command_counter=value(hk, 'CommandCounter'), error_counter=value(hk, 'CommandErrorCounter'), confirmed=1))
            if 'command' not in self.examples:
                self.examples['command'] = {'target': target, 'app': app, 'sent': safe_packet(sent), 'event': safe_packet(event),
                    'housekeeping': safe_packet(hk), 'counter_before': value(baseline, 'CommandCounter'), 'counter_after': value(hk, 'CommandCounter')}
        for (app, kind), (sent, confirmed) in counts.items():
            self.tables['q1_commands'].append(dict(target=target, app=app, command=kind, sent=sent, confirmed=confirmed, failures=sent-confirmed))

    def register_cases(self):
        report = self.data['registers/registers.json']; successful(report, 'register HAL')
        require(report['repetitions'] == 3 and report['samples'] == 405, 'HAL requires 3 repetitions and 405 samples')
        rows = report['runs']
        exact_keys([(row['model'], row['scenario'], row['repetition']) for row in rows],
                   [(model, scenario, rep) for model in MODELS for rep in range(1, 4) for scenario in ('constant', 'step', 'dropout')], 'HAL cases')
        for row in rows:
            require(row.get('passed') is True and all(row['checks'].values()), 'HAL case failed')
            points = row['samples']; require([p['index'] for p in points] == list(range(15)), 'HAL sample indices are incomplete')
            expected_bad = list(range(5, 10)) if row['scenario'] == 'dropout' else []
            require([p['index'] for p in points if p['disconnected']] == expected_bad, 'HAL interruption indices differ')
            for point in points:
                expected_input = LEVELS[row['model']][point['index']//5 if row['scenario']=='step' else 0]
                require(point['input_scaled'] == expected_input, 'HAL inputs differ from the frozen protocol')
                require(isinstance(point['register_hex'], str) and len(bytes.fromhex(point['register_hex'])) == 256, 'HAL raw register dump incomplete')
                if row['scenario'] == 'dropout':
                    self.tables['q3_hal_samples'].append(dict(model=row['model'], repetition=row['repetition'], sample_index=point['index'],
                        disconnected=int(point['disconnected']), status=point['status'], valid=int(point['status']==0), first_recovery=int(point['index']==10)))
                if point['disconnected']:
                    require(point['status'] != 0 and not point['read'] and not point['read_scaled'], 'HAL interrupted read presented as valid')
                    continue
                require(point['status'] == 0, 'HAL read failed outside interruption')
                for channel, expected_scaled in point['input_scaled'].items():
                    expected, observed = number(point['input'][channel]), number(point['read'][channel])
                    tolerance = number(point['tolerance'][channel], minimum=0)
                    require(abs(observed-expected) <= tolerance+1e-12, 'HAL reading exceeds recorded tolerance')
                    if expected:
                        scale = number(expected_scaled)/expected
                        require(scale > 0, 'HAL scale must be positive')
                        previous = self.scales.setdefault((row['model'], channel), scale)
                        require(math.isclose(scale, previous, rel_tol=1e-9), 'inconsistent recorded channel scaling')
                    else:
                        scale = self.scales.get((row['model'], channel))
                    require(scale is not None, 'cannot infer scaled units from recorded inputs')
                    self.sample('register_hal', 'memory_bus', row['model'], row['scenario'], row['repetition'], '', point['index'],
                                channel, expected_scaled, point['read_scaled'][channel], tolerance*scale, scale, row['units'][channel])
            if row['scenario'] == 'dropout':
                require(points[10]['status'] == 0, 'HAL first causal recovery read failed')
                self.tables['q3_interruptions'].append(dict(environment='register_hal', target='memory_bus', model=row['model'],
                    repetition=row['repetition'], episodes=1, expected_invalid=5, observed_invalid=sum(p['status'] != 0 for p in points[5:10]),
                    recovery_observations=1, recovery_s='', recovery_bound_s='', first_causal_read_valid=1, passed=1))

    def sample(self, environment, target, model, scenario, repetition, level, index, channel, expected, observed, tolerance, scale, unit):
        expected, observed, tolerance = number(expected), number(observed), number(tolerance, minimum=0)
        require(number(scale) > 0 and isinstance(unit, str) and bool(unit), 'sample scale/unit missing')
        error = abs(observed-expected)
        require(error <= tolerance+1e-9, f'{target}/{model}/{channel}: error exceeds tolerance')
        self.tables['q2_samples'].append(dict(environment=environment, target=target, model=model, scenario=scenario,
            repetition=repetition, level=level, sample_index=index, channel=channel, input_scaled=expected, read_scaled=observed,
            abs_error_scaled=error, tolerance_scaled=tolerance, input=expected/scale, read=observed/scale,
            abs_error=error/scale, tolerance=tolerance/scale, unit=unit, valid=1))

    def sensor_cases(self, target):
        report = self.data[f'{target}/target.json']; successful(report, target)
        require(report['sensor_samples_per_level'] == 5, 'Q2 requires five packets per level')
        rows = self.data[f'{target}/sensors.json']; levels = 1 if target == 'physical' else 3
        exact_keys([(row['model'], row['level']) for row in rows], [(model, level) for level in range(levels) for model in MODELS], 'sensor cases')
        require(report['sensor_cases'] == len(rows), 'sensor case count differs from report')
        for row in rows:
            successful(row, 'sensor case'); require(row.get('passed') is True, 'sensor case failed')
            model = row['model']; require(row['app'] == MODEL_APPS[model], 'sensor app/model mismatch')
            exact_keys(row['field_mapping'], LEVELS[model][0], 'sensor channels')
            if target != 'physical': require(row['expected_scaled'] == LEVELS[model][row['level']], 'sensor inputs differ from frozen levels')
            packets = row['packets']; require(len(packets) == 5 and len({p['sequence'] for p in packets}) == 5, 'sensor packet count/sequence incomplete')
            valid = target != 'physical' or model == 'mpu6050'
            require(row['valid_expected'] is valid, 'unexpected physical sensor presence assumption')
            if valid:
                require(row['raw_registers']['status'] == 'read', 'required raw register dump missing')
            for packet in packets:
                require(packet['mid'] == row['mid'] and not packet['errors'], 'wrong MID or decoder failure in sensor evidence')
                require(bool(value(packet, 'Valid')) == valid and (value(packet, 'Status') == 0) == valid, 'sensor validity/status differs from protocol')
                require(packet['received_at'] > row['input_applied_at'], 'sensor packet predates the input boundary')
            if target == 'physical':
                require(row['expected_scaled'] is None, 'physical readings cannot claim synthetic reference accuracy')
                for channel, field in row['field_mapping'].items():
                    scale = self.scales[(model, channel)]
                    readings = [number(value(p, field))/scale for p in packets] if valid else []
                    self.tables['physical_readings'].append(dict(model=model, channel=channel, unit=row['units'][channel],
                        valid_expected=int(valid), **stats(readings)))
                if not valid:
                    self.tables['q3_interruptions'].append(dict(environment='physical_absence', target=target, model=model,
                        repetition=1, episodes=0, expected_invalid=5, observed_invalid=5, recovery_observations=0,
                        recovery_s='', recovery_bound_s='', first_causal_read_valid='', passed=1))
            else:
                for index, packet in enumerate(packets):
                    for channel, expected in row['expected_scaled'].items():
                        self.sample('flight_telemetry', target, model, 'fixed_level', 1, row['level'], index, channel,
                            expected, value(packet, row['field_mapping'][channel]), row['tolerance_scaled'][channel],
                            self.scales[(model, channel)], row['units'][channel])
            if target == 'qemu' and model == 'mpu6050' and 'registers' not in self.examples:
                raw = row['raw_registers']
                self.examples['registers'] = {'target': target, 'model': model,
                    **{key: raw[key] for key in ('operation', 'implementation', 'bus', 'address', 'blocks', 'status', 'at') if key in raw},
                    'public_command': "python3 - \"$ALVO_SSH\" \"$BUS\" \"$ADDRESS\" \"$BLOCKS_JSON\" <<'PYTHON'\nimport shlex, subprocess, sys\nfrom hardware.sensor_probe import READ_REGISTERS\ncommand = shlex.join(['python3', '-c', READ_REGISTERS, *sys.argv[2:]])\nsubprocess.run(['ssh', sys.argv[1], command], check=True)\nPYTHON",
                    'command_note': 'Replace placeholders locally; the acquisition used the recorded bus, address and blocks. No endpoint or key is exported.'}

    def dropout_cases(self):
        rows = self.data['native/dropout.json']
        exact_keys([row['model'] for row in rows], MODELS, 'Native dropout cases')
        require(self.data['native/target.json']['dropout_cases'] == 3, 'Native dropout count differs')
        for row in rows:
            successful(row, 'Native dropout'); require(row.get('passed') is True, 'Native dropout did not pass')
            require(value(row['before'], 'Valid') == 1 and value(row['before'], 'Status') == 0, 'Native dropout baseline invalid')
            invalid = row['invalid']; require(len(invalid) == 5 and len({p['sequence'] for p in invalid}) == 5, 'Native requires five distinct outage packets')
            require(all(not p['errors'] and value(p, 'Valid') == 0 and value(p, 'Status') != 0 and p['received_at'] > row['removed_at'] for p in invalid), 'Native outage contains a valid/old/malformed sample')
            recovery = row['recovery_observations']; require(bool(recovery), 'Native recovery evidence missing')
            require(len({p['sequence'] for p in recovery}) == len(recovery), 'duplicate Native recovery packet')
            for index, packet in enumerate(recovery):
                delay = number(packet['received_at']-row['restored_at'], minimum=0)
                require(not packet['errors'], 'Native recovery decode failure')
                valid = value(packet, 'Valid') == 1 and value(packet, 'Status') == 0
                require(valid == (index == len(recovery)-1), 'Native recovery should stop at first valid observation')
                self.tables['q3_recovery'].append(dict(target='native', model=row['model'], sample_index=index,
                    sequence=packet['sequence'], received_after_restore_s=delay, valid=int(valid), status=value(packet, 'Status')))
            latency = number(row['recovery_latency_s'], minimum=0); bound = number(row['recovery_bound_s'], minimum=0)
            require(latency <= bound+1e-6 and math.isclose(latency, recovery[-1]['received_at']-row['restored_at'], abs_tol=1e-6), 'Native recovery is outside the declared bound')
            self.tables['q3_interruptions'].append(dict(environment='flight_telemetry', target='native', model=row['model'],
                repetition=1, episodes=1, expected_invalid=5, observed_invalid=5, recovery_observations=len(recovery),
                recovery_s=latency, recovery_bound_s=bound, first_causal_read_valid='', passed=1))

    def artifact_cases(self):
        reports = {target: self.data[f'{target}/artifacts.json'] for target in TARGETS}
        for target, report in reports.items():
            require(report.get('passed') is True and report['local'], target + ': artifacts unconfirmed')
            for name, sha in report['local'].items():
                require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'unsafe artifact path')
                require(isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha), 'invalid artifact SHA-256')
            if target != 'native':
                require(report['local'] == report['installed'] and not report['differences'], target + ': installed payload differs')
        qemu, board = reports['qemu'], reports['physical']
        require(qemu['build_fingerprint'] == board['build_fingerprint'], 'QEMU/physical build fingerprints differ')
        expected = self.data['build-qemu/metrics.json']['measurement']['result']['fingerprint']
        require(qemu['build_fingerprint'] == expected, 'ARM payload does not match measured build')
        require(qemu['local'] == board['local'], 'ARM local files differ between QEMU and physical')
        for name, sha in sorted(qemu['installed'].items()):
            category = ('executable' if Path(name).name == 'core-cpu1' else 'table' if name.endswith('.tbl') else
                        'startup' if name.endswith('cfe_es_startup.scr') else 'loadable_module' if name.endswith('.so') else 'other')
            self.tables['q4_artifacts'].append(dict(path=name, category=category, qemu_sha256=sha,
                physical_sha256=board['installed'][name], identical=int(sha == board['installed'][name])))

    def timing(self, kind, target, repetition, stage, seconds):
        self.tables['q5_timings'].append(dict(kind=kind, target=target, repetition=repetition, stage=stage,
                                              seconds=number(seconds, stage, minimum=0)))

    def metric_cases(self, relative, kind, target, count):
        report = self.data[relative]; successful(report, relative)
        require(report['kind'] == kind and report['target'] == target, 'wrong metrics kind/target')
        if kind == 'full_build':
            require(report['n'] == 1 and report['measurement']['status'] == 'succeeded', 'full build evidence incomplete')
            self.timing(kind, target, 1, 'elapsed_s', report['measurement']['elapsed_s']); return
        require(report['planned_n'] == count, 'metric repetition plan differs from frozen protocol')
        if kind == 'development_cycles':
            repetitions(report['cycles'], count, 'development cycles')
            require(report['restoration_build']['exit_code'] == 0, 'base mission restoration failed')
            for row in report['cycles']:
                for stage in ('create_s', 'build_s', 'delete_s'):
                    self.timing(kind, target, row['repetition'], stage, row[stage])
            return
        repetitions(report['runs'], count, kind)
        for row in report['runs']:
            operation = row['run_to_operational']; require(operation['status'] == 'succeeded', 'run job failed')
            require(0 <= number(operation['operational_observed_s']) <= number(operation['elapsed_s']), 'OPERATIONAL timing outside run interval')
            stages = dict(run_total_s=operation['elapsed_s'], operational_observed_s=operation['operational_observed_s'],
                          ground_to_first_hk_s=row['ground_to_first_hk']['elapsed_s'], total_to_first_hk_s=row['total_to_first_hk_s'])
            contact = row['ground_to_first_hk']; require(newer(contact['first_hk'], contact['enable']), 'timing lacks fresh HK after ENABLE_OUTPUT')
            total = operation['elapsed_s']+contact['elapsed_s']
            if kind == 'guest_boots':
                boot = row['guest_boot_to_ssh']; require(boot['status'] == 'succeeded', 'guest boot failed')
                stages['guest_boot_total_s'] = boot['elapsed_s']; total += boot['elapsed_s']
                if 'guest_ssh_ready_observed_s' in boot:
                    require(0 <= boot['guest_ssh_ready_observed_s'] <= boot['elapsed_s'], 'SSH observation outside guest boot interval')
                    stages['guest_ssh_ready_observed_s'] = boot['guest_ssh_ready_observed_s']
            require(row['total_to_first_hk_s']+1e-6 >= total, 'total to HK is shorter than its measured stages')
            for stage, seconds in stages.items(): self.timing(kind, target, row['repetition'], stage, seconds)
            transfers = [p for p in operation.get('phases', []) if p['phase'] == 'payload_transfer']
            if target != 'native': require(len(transfers) == 1, 'remote run must record one payload transfer')
            for phase in transfers:
                require(0 <= phase['start_s'] <= phase['end_s'] <= operation['elapsed_s'] and phase['elapsed_s'] >= 0, 'transfer outside run interval')
                self.timing(kind, target, row['repetition'], 'payload_transfer', phase['elapsed_s'])

    def aggregate(self):
        errors = defaultdict(list)
        for row in self.tables['q2_samples']: errors[tuple(row[key] for key in ('environment', 'target', 'model', 'channel', 'unit'))].append(row)
        for (environment, target, model, channel, unit), rows in sorted(errors.items()):
            self.tables['q2_errors'].append(dict(environment=environment, target=target, model=model, channel=channel, n=len(rows),
                max_abs_error_scaled=max(r['abs_error_scaled'] for r in rows), max_tolerance_scaled=max(r['tolerance_scaled'] for r in rows),
                max_abs_error=max(r['abs_error'] for r in rows), max_tolerance=max(r['tolerance'] for r in rows), unit=unit))
        timings = defaultdict(list)
        for row in self.tables['q5_timings']: timings[(row['kind'], row['target'], row['stage'])].append(row['seconds'])
        for (kind, target, stage), seconds in sorted(timings.items()):
            self.tables['q5_statistics'].append(dict(kind=kind, target=target, stage=stage, **stats(seconds)))

    def run(self):
        self.section('prepare', self.prepare)
        self.section('registers', self.register_cases)
        for target in TARGETS:
            self.section('Q1 '+target, lambda t=target: self.command_cases(t))
            self.section('Q2 '+target, lambda t=target: self.sensor_cases(t))
        self.section('Q3 Native', self.dropout_cases)
        self.section('Q4 ARM identity', self.artifact_cases)
        for target in ('native', 'qemu'):
            self.section('build '+target, lambda t=target: self.metric_cases(f'build-{t}/metrics.json', 'full_build', t, 1))
        self.section('cycles Native', lambda: self.metric_cases('cycles-native/metrics.json', 'development_cycles', 'native', 10))
        for target in TARGETS:
            self.section('starts '+target, lambda t=target: self.metric_cases(f'starts-{t}/metrics.json', 'cfs_starts', t, 10))
        self.section('boots QEMU', lambda: self.metric_cases('boots-qemu/metrics.json', 'guest_boots', 'qemu', 5))
        self.aggregate()
        return self


def summarize(campaign, output, partial=False):
    output = Path(output).resolve()
    require(not output.exists(), 'output directory must be new')
    require(not partial or 'final' not in output.parts and not {'validation', 'results'}.issubset(output.parts), 'partial exports must stay outside publication/final directories')
    analysis = Analysis(campaign).run()
    if analysis.issues and not partial:
        raise CampaignError('Campaign is incomplete or inconsistent; no final output written:\n' + '\n'.join(analysis.issues))
    output.mkdir(parents=True, exist_ok=False)
    for name, fields in HEADERS.items():
        with (output / (name+'.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(analysis.tables[name])
    summary = {'schema': 1, 'status': 'partial' if partial else 'final', 'publishable': not partial,
        'complete': not analysis.issues, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'analysis_sha256': digest(Path(__file__).read_bytes()), 'provenance': analysis.provenance,
        'quartile_method': 'inclusive', 'issues': analysis.issues, 'inputs': analysis.inputs,
        'tables': {name+'.csv': {'rows': len(rows), 'columns': HEADERS[name], 'sha256': digest((output/(name+'.csv')).read_bytes())} for name, rows in analysis.tables.items()},
        'q1': {'confirmed': sum(row['confirmed'] for row in analysis.tables['q1_commands']), 'expected_final': 108, 'by_target_app_command': analysis.tables['q1_commands']},
        'q2': {'errors': analysis.tables['q2_errors'], 'physical_descriptive': analysis.tables['physical_readings']},
        'q3': {environment: {'episodes': sum(row['episodes'] for row in analysis.tables['q3_interruptions'] if row['environment']==environment),
                 'invalid_readings': sum(row['observed_invalid'] for row in analysis.tables['q3_interruptions'] if row['environment']==environment)}
               for environment in ('register_hal', 'flight_telemetry', 'physical_absence')},
        'q4': {'arm_files': len(analysis.tables['q4_artifacts']), 'categories': dict(Counter(row['category'] for row in analysis.tables['q4_artifacts'])),
               'identical': bool(analysis.tables['q4_artifacts']) and all(row['identical'] for row in analysis.tables['q4_artifacts'])},
        'q5': {'statistics': analysis.tables['q5_statistics']},
        'notes': ['Physical readings are descriptive; no synthetic reference or accuracy claim.',
                  'Register samples use indices, not measured time.', 'UDP recovery is an observed bounded transition, not the first causal C call.',
                  'Full builds have N=1; restoration build is outside development-cycle statistics.',
                  'Durations and first-observation markers retain the frozen harness stage names.']}
    for name, document in (('summary.json', summary), ('examples.json', analysis.examples)):
        (output/name).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--partial', action='store_true', help='Diagnostic local export, always non-publishable')
    args = parser.parse_args()
    try:
        result = summarize(args.campaign, args.output, args.partial)
    except (CampaignError, OSError) as error:
        parser.exit(1, str(error)+'\n')
    print(json.dumps({'status': result['status'], 'publishable': result['publishable'], 'complete': result['complete'], 'issues': len(result['issues'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
