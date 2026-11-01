"""Web session state around the official cFS-GroundSystem UDP tools."""
import copy
import hashlib
import json
import re
import socket
import threading
import time
import tempfile
from collections import deque
from pathlib import Path

from .catalog import build_catalog, apply_overrides


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
        self._commands = deque(maxlen=100)
        self._communication = {}
        self._session_started = None
        self._event_sequence = 0
        self._error = None
        self._failure = None
        self._transport = None
        self._received = 0
        self._malformed = 0
        self._last_received = None
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
              service_instance=None, build_dir=None):
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
                self._commands.clear()
                self._communication.clear()
                self._session_started = time.time()
                self._event_sequence = 0
                self._received = self._malformed = 0
                self._last_received = None
                self._error = self._failure = None
                self._subscription_errors = []
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
            self.send(enable['id'], {'dest_IP': return_host or listen_host}, automatic=True)
            self._subscribe_catalog([target_ip, ports['command_port']], service_instance)
        except Exception:
            self.stop()
            raise
        return self.snapshot()

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
            self._history.append(packet)
            self._updates.notify_all()

    def send(self, command_id, values=None, *, automatic=False):
        with self._lock:
            if not self._connected():
                detail = self._failure
                raise ValueError('Connect the ground station before sending commands' + (': ' + detail if detail else ''))
            command = next((c for c in self._active_catalog['commands'] if c['id'] == command_id), None)
            if not command:
                raise ValueError('Command does not exist in the connected catalog')
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
            return event

    def stop(self):
        self._stop.set()
        with self._updates:
            self._updates.notify_all()
        if self._receiver:
            self._receiver.stop()
        if self._socket:
            self._socket.close()
        self._receiver = self._socket = None
        self._ready.clear()
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            connected = bool(self._connected())
            return copy.deepcopy({'connected': connected,
                                  'receiving': connected and self._last_received is not None and time.time() - self._last_received < 10,
                                  'transport': self._transport, 'backend': 'cFS-GroundSystem', 'error': self._error,
                                  'subscription_errors': list(self._subscription_errors),
                                  'received': self._received, 'malformed': self._malformed,
                                  'last_received': self._last_received,
                                  'communication': {'since': self._session_started,
                                                    'apps': list(self._communication.values())},
                                  'packets': list(self._latest.values()), 'history': list(self._history),
                                  'commands': list(self._commands)})
