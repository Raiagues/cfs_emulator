"""First-contact receipts for one ground receiver and its compiled flight catalog."""
import re


class FirstEvent:
    def __init__(self, catalog=None, destination=None, authored=None, information_ids=None):
        catalog = catalog or {}
        self.authored = authored
        self.information_ids = information_ids or {}
        self.noops = {}
        self.enable = None
        self.destination = destination
        self.information = catalog.get('transport', {}).get('evs_information')
        self.downlink = self.event = self.answer = None
        self.enable_send = self.downlink_receipt = None
        self.pending = None
        self.counter = {}
        self.hk_fields = {}
        self.counter_modulus = {}
        for command in catalog.get('commands', []):
            if command['app'] == 'to_lab' and command['id'].endswith('_OUTPUT_ENABLE_CC'):
                self.enable = command['id']
            if not command['id'].endswith('_NOOP_CC'):
                continue
            # The installed compiler catalog already limits this to active apps.
            # User apps now live under cFS/apps beside NASA's modules.
            self.noops[command['id']] = command['app']
        for packet in catalog.get('packets', []):
            if packet['app'] not in (authored if authored is not None else self.noops).values() or 'HK' not in packet['id'].upper():
                continue
            for field in packet['fields']:
                if field['name'].split('.')[-1] == 'CommandCounter':
                    self.hk_fields[packet['mid']] = field['name']
                    if field.get('format') in ('B', 'H', 'I', 'Q') and field.get('size') in (1, 2, 4, 8):
                        self.counter_modulus[packet['app']] = 1 << (8 * field['size'])

    def sent(self, command):
        if command['id'] == self.enable and not command.get('automatic'):
            self.enable_send = command['event_id']
            self.downlink_receipt = None
        watched = self.noops if self.authored is None else self.authored
        app = watched.get(command['id'])
        if app and not command.get('automatic'):
            # Receipts describe this transmission; completed tutorial evidence is
            # retained separately in Journey, not by freezing the live receiver.
            self.event = self.answer = None
            self.pending = {'app': app, 'send_id': command['event_id'], 'sent_at': command.get('sent_at'), 'baseline': self.counter.get(app), 'command': command['id'],
                            'reply': None, 'increase': None}

    def received(self, packet):
        if packet['errors'] or not packet['app']:
            return
        values = packet['values']
        if not self.downlink:
            self.downlink = packet['received_at']
        if self.enable_send is not None and not self.downlink_receipt and packet['event_id'] > self.enable_send:
            self.downlink_receipt = {'send_id': self.enable_send, 'mid': packet['mid'],
                                         'sequence': packet.get('sequence'), 'received_at': packet['received_at']}
        field = self.hk_fields.get(packet['mid'])
        count = values.get(field)
        if field and type(count) is int:
            self.counter[packet['app']] = count
        attempt = self.pending
        if self.answer is not None or not attempt or packet['event_id'] <= attempt['send_id']:
            return
        if self.matches_event(packet, attempt['command'], attempt['app']):
            if not attempt['reply']:
                attempt.update(reply=packet['event_id'], message=values['Message'], event_mid=packet['mid'])
            self.event = self.event or packet['received_at']
        if (packet['app'] == attempt['app'] and field and type(count) is int
                and attempt['baseline'] is not None and count == self.next_count(attempt['app'], attempt['baseline'])):
            if not attempt['increase']:
                attempt.update(increase=packet['event_id'], count=count)
        if attempt['reply'] and attempt['increase']:
            self.answer = packet['received_at']

    def next_count(self, app, baseline):
        value = baseline + 1
        modulus = self.counter_modulus.get(app)
        return value % modulus if modulus else value

    def matches_event(self, packet, command, app):
        values = packet['values']
        event_id = values.get('PacketID.EventID')
        declared = self.information_ids.get(command)
        return (not packet['errors'] and packet['app'] == 'cfe_evs' and event_id is not None
                and (event_id in (declared or ()) if self.authored is not None else not declared or event_id in declared)
                and self.information is not None and values.get('PacketID.EventType') == self.information
                and str(values.get('PacketID.AppName', '')).casefold() == app.casefold()
                and (self.authored is not None or re.search(r'\bno[ -]?op\b', str(values.get('Message', '')), re.I)))

    def snapshot(self, automatic=False):
        standard = next((key for key, app in self.noops.items() if app == 'sample_app'), None)
        return {'telemetry': bool(self.downlink), 'event': bool(self.event), 'answer': bool(self.answer),
                'event_at': self.event, 'answer_at': self.answer, 'return_host': self.destination,
                'enable_command': self.enable, 'noop_command': standard or next(iter(self.noops), None),
                'baseline_apps': sorted(self.counter), 'counters': dict(self.counter),
                'downlink_receipt': self.downlink_receipt,
                'app': self.pending['app'] if self.pending else self.noops.get(standard),
                'automatic': automatic, 'receipt': dict(self.pending) if self.pending else None}
