"""Web session state around the official cFS-GroundSystem UDP tools."""
import copy
import hashlib
import json
import re
import socket
import sys
import threading
import time
import tempfile
from collections import deque
from pathlib import Path

from .catalog import build_catalog, apply_overrides
from .first_event import FirstEvent
from journey import Store
from .round_trip import PassedTests, RoundTrips, TestPlans


class GroundStation:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._catalog = None
        self._build_root = self.root
        self._build_dir = None
        self._definitions = {}
        self._active_catalog = None
        self._lock = threading.RLock()
        self._updates = threading.Condition(self._lock)
        self._catalog_lock = threading.Lock()
        self._receiver = None
        self._definitions_files = None
        self._official = None
        self._socket = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._latest = {}
        self._history = deque(maxlen=256)
        self._events = deque(maxlen=256)
        self._commands = deque(maxlen=100)
        self.plans = TestPlans(self.root)
        self.receipts = PassedTests(self.root)
        self.trips = RoundTrips()
        self._communication = {}
        self._session_started = None
        self._event_sequence = 0
        self._error = None
        self._failure = None
        self._transport = None
        self._received = 0
        self._malformed = 0
        self._last_received = None
        self.journey = Store(self.root)
        self.first_contact = FirstEvent()
        self.command_reply = FirstEvent(authored={})
        self._learned_targets = {}
        self._target = None
        self._auto_enable = False
        self._subscriptions_due = self._subscription_thread = None
        self._subscription_errors = []
        self._subscription_cache = {}
        self._subscription_file = self.root / 'ground_station/.runtime/subscriptions.json'
        try:
            saved = json.loads(self._subscription_file.read_text())
            if isinstance(saved, dict):
                self._subscription_cache = {key: mids for key, mids in saved.items()
                                            if isinstance(mids, list) and all(type(mid) is int and 0 < mid <= 0xffff for mid in mids)}
        except (OSError, ValueError):
            pass

    def catalog(self, refresh=False, build_root=None, build_dir=None):
        with self._catalog_lock:
            if build_root is not None and Path(build_root).resolve() != self._build_root:
                self._build_root = Path(build_root).resolve()
                refresh = True
            if build_dir != self._build_dir:
                self._build_dir = build_dir
                refresh = True
            if self._catalog is None or refresh:
                catalog = build_catalog(self._build_root, overrides_root=self.root, build_dir=self._build_dir)
                with self._lock:
                    self._catalog = catalog
            return copy.deepcopy(self._catalog)

    def start(self, host, listen_host='0.0.0.0', return_host=None, build_root=None, catalog=None,
              service_instance=None, build_dir=None, journey_reset_at=0):
        if type(journey_reset_at) not in (int, float) or not 0 <= journey_reset_at < float('inf'):
            raise ValueError('Invalid journey reset time')
        # The Studio may serve a different project from the installation of its
        # Python package. Load GroundSystem from the mission's verified checkout.
        tools = self.root / 'cFS/tools/cFS-GroundSystem'
        for directory in (tools, tools / 'Subsystems/cmdGui', tools / 'Subsystems/tlmGUI'):
            if directory.is_dir() and str(directory) not in sys.path:
                sys.path.insert(0, str(directory))
        from . import official
        self.stop()
        self._official = official
        catalog = copy.deepcopy(catalog) if catalog is not None else self.catalog(refresh=True, build_root=build_root, build_dir=build_dir)
        catalog = apply_overrides(catalog, self.root)
        if not catalog['transport']:
            raise ValueError('Catalog unavailable: ' + '; '.join(catalog['errors']))
        enable = next((c for c in catalog['commands'] if c['id'] == 'TO_LAB_OUTPUT_ENABLE_CC'), None)
        if not enable:
            raise ValueError('TO_LAB output enable command not found in the current build')
        ports = catalog['transport']
        for command in catalog['commands']:
            command['header_size'] = ports['command_header_size']
        target_ip = socket.gethostbyname(host)
        directory = self.root / 'ground_station/.runtime/definitions' / (catalog.get('build_fingerprint') or 'current')
        definitions = official.Definitions(directory, catalog, target_ip)
        try:
            with self._lock:
                self._active_catalog = catalog
                self._definitions = {packet['mid']: packet for packet in catalog['packets']}
                self._definitions_files = definitions
                self._latest.clear()
                self._history.clear()
                self._events.clear()
                self._commands.clear()
                self.trips = RoundTrips()
                self._communication.clear()
                self._session_started = time.time()
                self._event_sequence = 0
                self._received = self._malformed = 0
                self._last_received = None
                self._error = self._failure = None
                self._subscription_errors = []
                self._target = (catalog.get('build_target'), target_ip, ports['command_port'])
                self._auto_enable = self._learned_targets.get(self._target, 0) > journey_reset_at
                self._start_observations(catalog, return_host or listen_host)
                self._subscriptions_due = ([target_ip, ports['command_port']], service_instance)
                self._stop = threading.Event()
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.bind((listen_host, 0))
                self._transport = 'udp'
                self._receiver = official.Receiver(target_ip, listen_host, ports['telemetry_port'], self._accept, self._transport_failed)
                self._ready = self._receiver.ready
                self._receiver.start()
            deadline = time.monotonic() + 10
            while not self._ready.wait(.1):
                if self._failure or time.monotonic() >= deadline:
                    raise ValueError(self._failure or 'The official telemetry receiver did not become ready.')
            if not self._connected():
                raise ValueError(self._failure or 'The telemetry receiver stopped.')
            if self._auto_enable:
                self._enable_downlink(enable['id'], return_host or listen_host)
        except Exception:
            self.stop()
            raise
        return self.snapshot()

    def _start_observations(self, catalog, destination):
        target = catalog.get('build_target')
        self._journey_cutoff = self.journey.snapshot(target)['reset_at']
        commands = {ref['command']: ref['app'] for ref in self.journey.references(target, 'command')
                    if ref['build'] == catalog.get('build_fingerprint')}
        self.first_contact = FirstEvent(catalog, destination)
        self.command_reply = FirstEvent(catalog, destination, authored=commands)

    def reset_journey(self, target):
        with self._lock:
            state = self.journey.reset(target)
            if self._target and self._target[0] == target:
                self._start_observations(self._active_catalog, self.first_contact.destination)
            return state

    def _observe_reply(self, packet, tracker, step):
        previous = tracker.answer
        tracker.received(packet)
        if not previous and tracker.answer and self._target and self._target[0]:
            ref = tracker.pending
            if step == 'event' and (ref['app'] != 'sample_app' or not tracker.downlink_receipt):
                return
            self.journey.observe(self._target[0], step, dict(ref, session=self._session_started), tracker.answer)

    def _enable_downlink(self, command, destination):
        """CI_LAB can start after the OS process. The output destination is safe to reapply."""
        with self._updates:
            for _ in range(5):
                self.send(command, {'dest_IP': destination}, automatic=True)
                self._updates.wait_for(lambda: self._received or not self._connected(), timeout=2)
                if not self._connected():
                    raise ValueError(self._failure or 'Telemetry link closed during setup.')
                if self._received:
                    return
        # A quiet mission may first need a subscription. Its EVS reply is checked
        # by _subscribe_catalog before the subscription is considered active.

    def _subscribe_catalog(self, connection, service_instance):
        """Complete the compiled TO table, recording only flight-confirmed additions."""
        catalog = self._active_catalog
        config = catalog['transport']
        if 'subscriptions' not in config:
            return
        command = next((c for c in catalog['commands'] if c['id'] == 'TO_LAB_ADD_PKT_CC'), None)
        if not command:
            self._subscription_errors.append('TO_LAB does not provide a packet subscription command.')
            return
        key = hashlib.sha256(json.dumps([connection, catalog.get('build_fingerprint'), service_instance],
                                        sort_keys=True).encode()).hexdigest() if service_instance else None
        confirmed = set(self._subscription_cache.get(key, [])) if key else set()
        baseline = {entry['mid'] for entry in config['subscriptions']}
        desired = {packet['mid'] for packet in catalog['packets']}
        if len(baseline | confirmed | desired) > config['max_subscriptions']:
            self._subscription_errors.append('The catalog exceeds the TO_LAB subscription table capacity.')
            return
        defaults = config['subscription_defaults']
        for mid in sorted(desired - baseline - confirmed):
            if self._stop.is_set():
                return
            try:
                fields = {'Stream': mid, 'Stream.Value': mid, 'Flags.Priority': defaults['priority'],
                          'Flags.Reliability': defaults['reliability'], 'BufLimit': defaults['buffer_limit']}
                values = {field['name']: fields[field['name']] for field in command['fields'] if field['name'] in fields}
                sent = self.send(command['id'], values, automatic=True)
                self._wait_subscription(mid, sent['sent_at'], config)
                confirmed.add(mid)
                if key:
                    self._subscription_cache[key] = sorted(confirmed)
                    self._subscription_file.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(mode='w', dir=self._subscription_file.parent, delete=False) as file:
                        json.dump(dict(list(self._subscription_cache.items())[-32:]), file)
                        temporary = Path(file.name)
                    temporary.replace(self._subscription_file)
            except (ValueError, OSError) as error:
                self._subscription_errors.append(f'Subscription 0x{mid:04X}: {error}')
                break

    def _wait_subscription(self, mid, since, config):
        events = config['subscription_events']
        expected = {events['added'], events['exists'], *events['errors']}
        deadline = time.monotonic() + 8
        with self._updates:
            while self._connected():
                for packet in self._history:
                    values = packet['values']
                    if (packet['received_at'] < since or values.get('PacketID.AppName') != config['subscription_app'] or
                            values.get('PacketID.EventID') not in expected or
                            not re.search(r'\b0x0*' + format(mid, 'x') + r'\b', str(values.get('Message', '')), re.I)):
                        continue
                    if values['PacketID.EventID'] in events['errors']:
                        raise ValueError(values['Message'])
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('TO_LAB did not confirm the subscription in the event stream.')
                self._updates.wait(remaining)
        raise ValueError(self._failure or 'Telemetry link closed')

    def _connected(self):
        return bool(self._receiver and self._receiver.connected() and not self._failure and not self._stop.is_set())

    def _transport_failed(self, message):
        with self._updates:
            self._error = self._failure = str(message)
            self.trips.finish('disconnected')
            self._updates.notify_all()

    def _record_communication(self, app, kind, size, timestamp):
        """Count observed UDP traffic independently of the bounded message history."""
        counters = self._communication.setdefault(app or '', {
            'app': app, 'telemetry_received': 0, 'commands_sent': 0,
            'telemetry_bytes': 0, 'command_bytes': 0,
            'last_received': None, 'last_sent': None,
        })
        if kind == 'telemetry':
            counters['telemetry_received'] += 1
            counters['telemetry_bytes'] += size
            counters['last_received'] = timestamp
        else:
            counters['commands_sent'] += 1
            counters['command_bytes'] += size
            counters['last_sent'] = timestamp
        self._event_sequence += 1
        return self._event_sequence

    def _accept(self, data):
        with self._lock:
            if len(data) < 6 or data[0] >> 5 or int.from_bytes(data[4:6], 'big') + 7 != len(data):
                self._malformed += 1
                self._error = 'Invalid CCSDS version or packet size'
                return
            mid = int(self._official.RoutingService.get_pkt_id(data), 16)
            definition = self._definitions.get(mid)
            page = self._definitions_files.pages.get(mid)
            values, errors = page.read(data) if page else ({}, [])
            packet = {'mid': mid, 'sequence': int.from_bytes(data[2:4], 'big') & 0x3fff,
                      'bytes': len(data), 'name': definition['name'] if definition else hex(mid),
                      'app': definition['app'] if definition else None,
                      'source': definition.get('source') if definition else None,
                      'values': values, 'errors': errors, 'hex': data.hex(), 'received_at': time.time()}
            self._received += 1
            self._last_received = packet['received_at']
            previous = self._latest.get(mid)
            packet['count'] = (previous['count'] if previous else 0) + 1
            packet['event_id'] = self._record_communication(packet['app'], 'telemetry', len(data), packet['received_at'])
            self._latest[mid] = packet
            if not any(p['mid'] == mid and p['sequence'] == packet['sequence'] and
                       p['hex'] == packet['hex'] for p in reversed(self._history)):
                self._observe_reply(packet, self.first_contact, 'event')
                self._observe_reply(packet, self.command_reply, 'send')
                if self.first_contact.event:
                    self._learned_targets[self._target] = self.first_contact.event
                if self.trips.active:
                    active = self.trips.active
                    self.trips.observe(packet)
                    if active['status'] == 'passed':
                        try:
                            self.receipts.record(active, self._active_catalog)
                        except (OSError, ValueError) as error:
                            self._error = 'Could not save flight receipt: ' + str(error)
            if self.first_contact.downlink and self._subscriptions_due and not self._stop.is_set():
                # An EVS acknowledgment cannot arrive on a closed downlink. Complete
                # subscriptions from a worker so the receiver can deliver the reply.
                self._subscription_thread = threading.Thread(target=self._subscribe_catalog,
                                                            args=self._subscriptions_due, daemon=True)
                self._subscriptions_due = None
                self._subscription_thread.start()
            self._history.append(packet)
            if "Message" in values and "PacketID.AppName" in values:
                self._events.append(packet)
            self._updates.notify_all()

    def send(self, command_id, values=None, *, automatic=False, test_id=None):
        with self._lock:
            if not self._connected():
                detail = self._failure
                raise ValueError('Connect the ground station before sending commands' + (': ' + detail if detail else ''))
            command = next((c for c in self._active_catalog['commands'] if c['id'] == command_id), None)
            if not command:
                raise ValueError('Command does not exist in the connected catalog')
            self.trips.expire()
            if self.trips.active and not automatic:
                raise ValueError('Wait for the active test or stop it before sending another command.')
            prepared = None
            if test_id is not None:
                plan = next((p for p in self.plans.read()['plans'] if p['id'] == test_id), None)
                if not plan or plan['command'] != command_id:
                    raise ValueError('Choose a saved test for this command.')
                prepared = self.trips.prepare(plan, self._active_catalog, self._latest)
            try:
                sender = self._definitions_files.sender(command_id, values or {}, self._socket)
                size = sender.send()
            except OSError as error:
                self._transport_failed('Official command sender failed: ' + str(error))
                raise ValueError(self._failure) from error
            event = {'id': command_id, 'app': command['app'], 'mid': command['mid'], 'code': command['code'],
                     'values': copy.deepcopy(values or {}), 'sent_at': time.time(), 'bytes': size, 'status': 'sent',
                     'hex': bytes(sender.packet).hex(),
                     'automatic': automatic}
            event['event_id'] = self._record_communication(event['app'], 'command', size, event['sent_at'])
            self._commands.append(event)
            cutoff = self.journey.snapshot(self._target[0])['reset_at']
            if cutoff != self._journey_cutoff:
                self._start_observations(self._active_catalog, self.first_contact.destination)
            self.first_contact.sent(event)
            self.command_reply.sent(event)
            if prepared:
                self.trips.start(prepared, event, test_id)
            return event

    def cancel_test(self, ident):
        with self._lock:
            self.trips.expire()
            if self.trips.active and self.trips.active['id'] == ident:
                self.trips.finish('cancelled')
            return self.snapshot()

    def passed_tests(self, target):
        return self.receipts.read(target)

    def stop(self):
        self._stop.set()
        with self._updates:
            self.trips.finish('disconnected')
            self._updates.notify_all()
        if self._receiver:
            self._receiver.stop()
        if self._subscription_thread:
            self._subscription_thread.join()
        self._subscriptions_due = self._subscription_thread = None
        if self._socket:
            self._socket.close()
        self._receiver = self._socket = None
        self._ready.clear()
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            self.trips.expire()
            connected = bool(self._connected())
            return copy.deepcopy({'connected': connected,
                                  'build_fingerprint': (self._active_catalog or {}).get('build_fingerprint'),
                                  'receiving': connected and self._last_received is not None and time.time() - self._last_received < 10,
                                  'transport': self._transport, 'backend': 'cFS-GroundSystem', 'error': self._error,
                                  'subscription_errors': list(self._subscription_errors),
                                  'first_flight': self.first_contact.snapshot(self._auto_enable),
                                  'received': self._received, 'malformed': self._malformed,
                                  'last_received': self._last_received,
                                  'communication': {'since': self._session_started,
                                                    'apps': list(self._communication.values())},
                                  'events': list(self._events), 'packets': list(self._latest.values()), 'history': list(self._history),
                                  'commands': list(self._commands), 'runs': list(self.trips.runs)})
