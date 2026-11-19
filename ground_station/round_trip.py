"""Ordered assertions on actual decoded downlink packets following a single uplink."""
from collections import deque
import copy
import hashlib
import json
import math
from pathlib import Path
import secrets
import tempfile
import time


def _text(value, name, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'Enter a valid {name}.')
    return value.strip()


def validate_plan(plan, catalog):
    if not isinstance(plan, dict):
        raise ValueError('Choose a test definition.')
    command = next((c for c in catalog['commands'] if c['id'] == plan.get('command')), None)
    if command is None:
        raise ValueError('The selected command is unavailable in this build.')
    name = _text(plan.get('name'), 'test name', 80)
    duration = plan.get('timeout', 15)
    if type(duration) is not int or not 1 <= duration <= 300:
        raise ValueError('Choose a timeout between 1 and 300 seconds.')
    steps = plan.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 16:
        raise ValueError('Add between 1 and 16 observations.')
    packets = {packet['id']: packet for packet in catalog['packets']}
    clean = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError('Invalid observation.')
        if step.get('kind') == 'event':
            app = _text(step.get('app'), 'EVS origin', 64)
            event_id = step.get('event_id')
            if event_id is not None and (type(event_id) is not int or not 0 <= event_id <= 65535):
                raise ValueError('Event ID must be a 16-bit unsigned integer.')
            message = step.get('message', '')
            if not isinstance(message, str) or len(message) > 160 or (event_id is None and not message.strip()):
                raise ValueError('Specify the event ID or text to match.')
            clean.append({'kind': 'event', 'app': app, 'event_id': event_id, 'message': message.strip()})
        elif step.get('kind') == 'packet':
            packet = packets.get(step.get('packet'))
            if not packet:
                raise ValueError('The telemetry packet is unavailable in this build.')
            op = step.get('op', 'received')
            rule = {'kind': 'packet', 'packet': packet['id'], 'op': op}
            if op not in ('received', 'equals', 'changed', 'increased'):
                raise ValueError('Unknown field comparison.')
            if op != 'received':
                field = next((f for f in packet['fields'] if f['name'] == step.get('field')), None)
                if not field:
                    raise ValueError('Choose a field in the selected packet.')
                rule['field'] = field['name']
                if op == 'equals':
                    value = step.get('value')
                    if not isinstance(value, (str, bool, int, float)) or isinstance(value, float) and not math.isfinite(value):
                        raise ValueError('Enter a field value.')
                    rule['value'] = value
            clean.append(rule)
        else:
            raise ValueError('Unknown observation type.')
    return {'name': name, 'command': command['id'], 'timeout': duration, 'steps': clean}


class TestPlans:
    """Project-local definitions, independent of the mission and flight build."""
    def __init__(self, root):
        self.path = Path(root) / 'ground_station/test-plans.json'

    def read(self):
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            content = b'[]'
        return {'plans': json.loads(content), 'revision': hashlib.sha256(content).hexdigest()}

    def save(self, body, catalog):
        import fcntl
        lock_path = self.path.parent / '.runtime/test-plans.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            saved = self.read()
            if saved['revision'] != body.get('revision'):
                raise ValueError('Tests changed. Reopen the editor to use the latest revision.')
            plans = saved['plans']
            ident = body.get('id')
            index = next((i for i, p in enumerate(plans) if p['id'] == ident), None)
            if ident is not None and index is None:
                raise ValueError('Test definition no longer exists.')
            if body.get('delete') is True:
                if index is None:
                    raise ValueError('Select a saved test.')
                del plans[index]
            else:
                item = validate_plan(body.get('plan'), catalog)
                ident = ident or secrets.token_hex(8)
                item['id'] = ident
                if index is None:
                    plans.append(item)
                else:
                    plans[index] = item
            with tempfile.NamedTemporaryFile(dir=self.path.parent, mode='w', delete=False) as output:
                json.dump(plans, output, indent=2, ensure_ascii=False)
                output.write('\n')
            Path(output.name).replace(self.path)
            return dict(self.read(), id=ident)


class RoundTrips:
    """Access under the station lock. One observation can satisfy only one step."""
    def __init__(self):
        self.runs = deque(maxlen=64)
        self.active = None

    def finish(self, status):
        if self.active:
            self.active['status'] = status
            self.active['finished_at'] = time.time()
            self.active = None

    def expire(self):
        if self.active and time.monotonic() >= self.deadline:
            self.finish('timed_out')

    def prepare(self, plan, catalog, latest):
        self.expire()
        if self.active:
            raise ValueError('A test is waiting for flight observations.')
        rules = validate_plan(plan, catalog)
        packets = {p['id']: p for p in catalog['packets']}
        steps = []
        for step in rules['steps']:
            step = dict(step)
            if step['kind'] == 'packet':
                definition = packets[step['packet']]
                step['mid'] = definition['mid']
                if step['op'] in ('changed', 'increased'):
                    sample = latest.get(step['mid'], {})
                    values = sample.get('values', {})
                    if sample.get('errors') or step['field'] not in values:
                        raise ValueError(f"Wait for a baseline sample of {step['packet']}.{step['field']} before sending.")
                    step['baseline'] = copy.deepcopy(values[step['field']])
            steps.append(step)
        return dict(rules, steps=steps)

    def start(self, prepared, sent, test_id):
        self.active = dict(prepared, id=sent['event_id'], test_id=test_id, sent=sent, status='waiting', matched=0)
        self.deadline = time.monotonic() + prepared['timeout']
        self.runs.append(self.active)

    def observe(self, packet):
        self.expire()
        run = self.active
        if not run or packet['event_id'] <= run['id'] or packet['errors']:
            return
        step = run['steps'][run['matched']]
        values = packet['values']
        if step['kind'] == 'event':
            if (packet['app'] != 'cfe_evs' or str(values.get('PacketID.AppName', '')).casefold() != step['app'].casefold()
                    or 'PacketID.EventID' not in values
                    or step['event_id'] is not None and values['PacketID.EventID'] != step['event_id']
                    or step['message'].casefold() not in str(values.get('Message', '')).casefold()):
                return
            evidence = {k: values[k] for k in ('PacketID.AppName', 'PacketID.EventID', 'Message') if k in values}
        else:
            if packet['mid'] != step['mid']:
                return
            field, op = step.get('field'), step['op']
            value = values.get(field)
            if field and field not in values:
                return
            if op == 'equals' and value != step['value'] or op == 'changed' and value == step['baseline']:
                return
            if op == 'increased' and not (type(value) in (float, int) and type(step['baseline']) in (float, int) and value > step['baseline']):
                return
            evidence = {field: value} if field else {}
        step['observation'] = {k: packet[k] for k in ('event_id', 'mid', 'sequence', 'received_at', 'bytes', 'name', 'app')}
        step['observation']['values'] = evidence
        run['matched'] += 1
        if run['matched'] == len(run['steps']):
            self.finish('passed')
