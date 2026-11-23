"""Ground sessions for CI_LAB commands and TO_LAB telemetry."""
import copy
import socket
import threading
import time
from collections import Counter, deque
from pathlib import Path

from .catalog import build_catalog, apply_overrides
from . import official
from .first_event import FirstEvent
from journey import Store
from project.defaults import sensor_timeout
from sensors.observations import SensorTelemetry
from .round_trip import PassedTests, RoundTrips, TestPlans


class GroundStation:
    def __init__(self, root, on_change=lambda: None):
        self.on_change = on_change
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
        self._lifecycle = threading.RLock()
        self._socket = None
        self._stop = threading.Event()
        self._latest = {}
        self._history = deque(maxlen=256)
        self._events = deque(maxlen=256)
        self._commands = deque(maxlen=100)
        self._command_counts = Counter()
        self.plans = TestPlans(self.root)
        self.receipts = PassedTests(self.root)
        self.trips = RoundTrips()
        self._communication = {}
        self._traffic_seconds = {}
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
        self._target = None

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

    def start(self, host, listen_host, return_host=None, build_root=None, catalog=None, build_dir=None,
              command_port=None, receiver_container=None):
        with self._lifecycle:
            self.stop()
            return self._start(host, listen_host, return_host, build_root, catalog, build_dir, command_port, receiver_container)

    def _start(self, host, listen_host, return_host, build_root, catalog, build_dir, command_port, receiver_container):
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
        try:
            with self._lock:
                self._active_catalog = catalog
                self._definitions = {packet['mid']: packet for packet in catalog['packets']}
                self._latest.clear()
                self._history.clear()
                self._events.clear()
                self._commands.clear()
                self._command_counts.clear()
                self.trips = RoundTrips()
                self._communication.clear()
                self._traffic_seconds.clear()
                self._session_started = time.time()
                self._event_sequence = 0
                self._received = self._malformed = 0
                self._last_received = None
                self._error = self._failure = None
                self._target = (catalog.get('build_target'), target_ip, command_port or ports['command_port'])
                self._start_observations(catalog, return_host or listen_host)
                self._stop = threading.Event()
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.bind((listen_host, 0))
                self._transport = 'udp'
                if receiver_container:
                    from .emulator import EmulatorReceiver
                    self._receiver = EmulatorReceiver(receiver_container, ports['telemetry_port'], self._accept, self._transport_failed)
                else:
                    self._receiver = official.Receiver(target_ip, listen_host, ports['telemetry_port'],
                                                       self._accept, self._transport_failed)
                self._receiver.start()
        except Exception:
            self.stop()
            raise
        return self.snapshot()

    def _start_observations(self, catalog, destination):
        target = catalog.get('build_target')
        self._journey_cutoff = self.journey.snapshot(target)['reset_at']
        self.sensor_telemetry = SensorTelemetry(self.root, target)
        compiled = [ref for ref in self.journey.references(target, 'command')
                    if ref.get('build') == catalog.get('build_fingerprint') and 'command' in ref]
        commands = {ref['command']: ref['app'] for ref in compiled}
        information_ids = {ref['command']: ref['information_ids'] for ref in compiled if ref.get('information_ids')}
        self.first_contact = FirstEvent(catalog, destination)
        self.command_reply = FirstEvent(catalog, destination, authored=commands, information_ids=information_ids)

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

    def _connected(self):
        return bool(self._receiver and self._receiver.connected() and not self._failure and not self._stop.is_set())

    def _transport_failed(self, message):
        with self._updates:
            self._error = self._failure = str(message)
            self.trips.finish('disconnected')
            self._updates.notify_all()
            self.on_change()

    def _record_communication(self, app, kind, size, timestamp):
        """Count observed UDP traffic independently of the bounded message history."""
        bins = self._traffic_seconds.setdefault((app or '', kind), deque(maxlen=30))
        second = int(timestamp)
        if bins and bins[-1][0] == second:
            bins[-1][1] += 1
        else:
            bins.append([second, 1])
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
            mid = int.from_bytes(data[:2], 'big')
            definition = self._definitions.get(mid)
            values, errors = official.decode(definition, data, self._active_catalog['byte_order']) if definition else ({}, [])
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
                self.sensor_telemetry.received(packet)
                self._observe_reply(packet, self.first_contact, 'event')
                self._observe_reply(packet, self.command_reply, 'send')
                if self.trips.active:
                    active = self.trips.active
                    self.trips.observe(packet)
                    if active['status'] == 'passed':
                        try:
                            self.receipts.record(active, self._active_catalog)
                        except (OSError, ValueError) as error:
                            self._error = 'Could not save flight receipt: ' + str(error)
            self._history.append(packet)
            if "Message" in values and "PacketID.AppName" in values:
                self._events.append(packet)
            self._updates.notify_all()
            self.on_change()

    def send(self, command_id, values=None, *, test_id=None):
        with self._lock:
            if not self._connected():
                detail = self._failure
                raise ValueError('Connect the ground station before sending commands' + (': ' + detail if detail else ''))
            command = next((c for c in self._active_catalog['commands'] if c['id'] == command_id), None)
            if not command:
                raise ValueError('Command does not exist in the connected catalog')
            self.trips.expire()
            if self.trips.active:
                raise ValueError('Wait for the active test or stop it before sending another command.')
            prepared = None
            if test_id is not None:
                plan = next((p for p in self.plans.read()['plans'] if p['id'] == test_id), None)
                if not plan or plan['command'] != command_id:
                    raise ValueError('Choose a saved test for this command.')
                prepared = self.trips.prepare(plan, self._active_catalog, self._latest)
            try:
                packet = official.encode(command, values or {}, self._active_catalog['byte_order'])
                size = self._socket.sendto(packet, self._target[1:])
            except OSError as error:
                self._transport_failed('UDP command send failed: ' + str(error))
                raise ValueError(self._failure) from error
            event = {'id': command_id, 'app': command['app'], 'mid': command['mid'], 'code': command['code'],
                     'values': copy.deepcopy(values or {}), 'sent_at': time.time(), 'bytes': size, 'status': 'sent',
                     'hex': packet.hex()}
            event['event_id'] = self._record_communication(event['app'], 'command', size, event['sent_at'])
            self._commands.append(event)
            self._command_counts[command_id] += 1
            cutoff = self.journey.snapshot(self._target[0])['reset_at']
            if cutoff != self._journey_cutoff:
                self._start_observations(self._active_catalog, self.first_contact.destination)
            self.first_contact.sent(event)
            self.command_reply.sent(event)
            if prepared:
                self.trips.start(prepared, event, test_id)
            return event

    def resolve_command(self, app, name):
        from .commands import command_for
        with self._lock:
            if not self._connected():
                raise ValueError('Connect the ground station before selecting a command')
            return command_for(self._active_catalog['commands'], app, name)

    def send_observed(self, app, name, arguments, timeout):
        """Send once. Wait for real downlink when this command has a known reply."""
        from .commands import noop_event
        with self._updates:
            command = self.resolve_command(app, name)
            noop = command['id'].endswith('_NOOP_CC')
            enable = command['id'] == self.first_contact.enable
            authored = command['id'] in self.command_reply.authored
            counter = (self.command_reply if authored else self.first_contact).counter
            needs_counter = authored or noop and app == 'sample_app'
            if needs_counter:
                self.wait_for(lambda: app in counter, timeout, app + ' housekeeping')
            before = counter.get(app)
            uplink = self.send(command['id'], arguments)
            if enable:
                self.wait_for(lambda: any(p['event_id'] > uplink['event_id'] for p in self._history),
                              timeout, 'TO_LAB telemetry')
            if not (noop or authored):
                return {'sent': uplink, 'telemetry': enable}

            def reply():
                return next((packet for packet in self._events if packet['event_id'] > uplink['event_id']
                             and (self.command_reply.matches_event(packet, command['id'], app)
                                  if authored else noop_event(packet, app))), None)

            packet = self.wait_for(reply, timeout, app + ' ' + name + ' event')
            result = {'sent': uplink, 'event': packet['values']['Message']}
            if needs_counter:
                self.wait_for(lambda: counter.get(app) == before + 1, timeout, 'CommandCounter increase')
                result.update(before=before, after=counter[app])
            return result

    def wait_for(self, predicate, timeout, observation):
        """Wait for an observation or a closed receiver. Caller may already hold the condition."""
        with self._updates:
            arrived = self._updates.wait_for(lambda: predicate() or not self._connected(), timeout)
            if not self._connected():
                raise ValueError(self._failure or 'Ground receiver disconnected')
            if not arrived:
                raise ValueError('Timed out waiting for ' + observation)
            return arrived

    def observations_since(self, cursor, events, timeout):
        with self._updates:
            source = self._events if events else self._history
            return self.wait_for(lambda: [packet for packet in source if packet['event_id'] > cursor],
                                 timeout, 'a flight event' if events else 'flight telemetry')

    def noops(self):
        with self._lock:
            if not self._connected():
                raise ValueError('Connect the ground station before running NOOP tests')
            return [(row['app'], row['id']) for row in self._active_catalog['commands']
                    if row['id'].endswith('_NOOP_CC') and not row['fields']]

    def cancel_test(self, ident):
        with self._lock:
            self.trips.expire()
            if self.trips.active and self.trips.active['id'] == ident:
                self.trips.finish('cancelled')
            return self.snapshot()

    def passed_tests(self, target):
        return self.receipts.read(target)

    def stop(self):
        with self._lifecycle:
            return self._stop_receiver()

    def _stop_receiver(self):
        self._stop.set()
        with self._updates:
            self.trips.finish('disconnected')
            self._updates.notify_all()
            self.on_change()
        if self._receiver:
            self._receiver.stop()
        if self._socket:
            self._socket.close()
        self._receiver = self._socket = None
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            self.trips.expire()
            connected = bool(self._connected())
            start = int(time.time()) - 29
            recent = []
            for (app, kind), bins in self._traffic_seconds.items():
                activity = dict(bins)
                series = [activity.get(start + index, 0) for index in range(30)]
                if connected and sum(series):
                    recent.append({'app': app, 'kind': kind, 'bins': series, 'rate': sum(series) / len(series)})
            return copy.deepcopy({'connected': connected,
                                  'build_fingerprint': (self._active_catalog or {}).get('build_fingerprint'),
                                  'receiving': connected and self._last_received is not None and time.time() - self._last_received < 10,
                                  'transport': self._transport, 'backend': 'CI_LAB / TO_LAB', 'error': self._error,
                                  'first_flight': self.first_contact.snapshot(), 'authored_reply': self.command_reply.snapshot(),
                                  'reply_timeout': sensor_timeout(),
                                  'received': self._received, 'malformed': self._malformed,
                                  'last_received': self._last_received,
                                  'communication': {'since': self._session_started, 'recent': recent,
                                                    'totals': {'commands_sent': sum(self._command_counts.values()),
                                                               'telemetry_received': self._received,
                                                               'malformed': self._malformed},
                                                    'commands': dict(self._command_counts),
                                                    'apps': list(self._communication.values())},
                                  'events': list(self._events), 'packets': list(self._latest.values()), 'history': list(self._history),
                                  'commands': list(self._commands), 'runs': list(self.trips.runs)})
