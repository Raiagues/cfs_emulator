#!/usr/bin/env python3
"""Local Flight Studio. Start with: python3 interface/server.py."""
import argparse
from copy import deepcopy
import json
import secrets
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from interface.backend.workspace import Workspace
from interface.backend import first_boot
from hardware.targets import selected_target
from journey import mission as evidence
from interface.backend.terminal import Shells
from interface.backend.hardware_settings import device_settings, update_device
from hardware.manager import HardwareManager
from hardware import infrastructure
from hardware.ground_link import resolve_ground_link
from sensors.orbit import preview as orbit_preview
from ground_station.station import GroundStation
from ground_station.catalog import apply_overrides, CATALOG_VERSION

# Infrastructure opens at /; the editor and diagrams open at /studio.
STATIC_ROOT = ROOT / 'interface/static'
ASSET_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
               '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png'}
CONTENT_SECURITY_POLICY = ("default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                           "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")


class Studio:
    ACTIONS = {'first-boot', 'clone-cfs', 'model-test', 'sensor-test', 'connect', 'probe', 'logs', 'simulate', 'setup', 'build', 'boot',
               'run', 'stop', 'shutdown', 'values', 'simulate-preview'}
    BACKGROUND = {'logs', 'simulate', 'simulate-preview'}

    def __init__(self, root=ROOT):
        self.workspace = Workspace(root)
        self.shells = Shells(root)
        self.hardware = HardwareManager(root)
        self.ground = GroundStation(root)
        self.token = secrets.token_urlsafe(32)
        self.jobs = {}
        self.lock = threading.Lock()
        self.operation = threading.Lock()
        self.ground_target = None
        self.closing = False

    def exclusive(self, operation, *args, wait=0, **kwargs):
        if not self.operation.acquire(timeout=wait):
            raise ValueError('Operation in progress. Try again when it finishes.')
        try:
            return operation(*args, **kwargs)
        finally:
            self.operation.release()

    def job(self, action, options):
        options, kind, script, connection = self._job_request(action, options)
        journal_instance = None
        if action == 'logs' and kind == 'current-flight' and options['target'] != 'native':
            target = options['target']
            receipt = self.hardware._load('operational-' + target + '.json', {})
            current = self.hardware.observed_flight(target, connection)
            journal_instance = receipt.get('instance')
            if not journal_instance or current.get('instance') != journal_instance or current['service'] != 'active':
                raise ValueError('The cFS service invocation changed.')

        target = options['target']
        exclusive = action not in self.BACKGROUND
        with self.lock:
            if self.closing:
                raise ValueError('The server is shutting down.')
            destination = tuple(sorted(connection.items())) if connection else None
            key = (action, target, kind, destination, options.get('device'), options.get('model'), options.get('scenario'), journal_instance)
            if journal_instance:
                for prior in reversed(self.jobs.values()):
                    if prior['key'] == key and (prior['status'] == 'running' or time.time() - prior.get('ended', 0) < 30):
                        return {'id': prior['id'], 'existing': True}
            existing = None if exclusive else self._running_reader(action, key, target, kind, connection)
            if existing:
                return {'id': existing['id'], 'existing': True}
            if exclusive and not self.operation.acquire(blocking=False):
                raise ValueError('An operation is already running. Follow its progress in the terminal.')
            ident = secrets.token_hex(6)
            record = {'id': ident, 'action': action, 'target': target, 'connection': connection,
                      'device': options.get('device'), 'scenario': options.get('scenario'), 'script': script, 'retry': bool(options.get('retry')),
                      'kind': kind, 'status': 'running', 'key': key,
                      'streaming': action in self.BACKGROUND, 'operation_complete': False,
                      'lines': deque(maxlen=3000), 'line_count': 0, 'started': time.time(), 'exit_code': None,
                      'cancel': threading.Event()}
            if journal_instance:
                record['journal_instance'] = journal_instance
                record['journal_apps'] = {}
                def check_invocation(current):
                    if current != journal_instance:
                        raise ValueError('The cFS service invocation changed.')
                options.update(kind='current-flight', on_invocation=check_invocation)
            record['thread'] = threading.Thread(target=self._run_job, args=(record, options), daemon=True)
            self.jobs[ident] = record
            for old in list(self.jobs)[:-30]:
                if self.jobs[old]['status'] != 'running':
                    del self.jobs[old]
        try:
            record['thread'].start()
        except BaseException:
            with self.lock:
                del self.jobs[ident]
            if exclusive:
                self.operation.release()
            raise
        return {'id': ident}

    def _running_reader(self, action, key, target, kind, connection):
        """A running job that already streams what this reader would open; called with self.lock held."""
        for existing in self.jobs.values():
            if existing['status'] != 'running' or existing['cancel'].is_set():
                continue
            if existing['key'] == key:
                return existing
            # A boot or run job keeps streaming the log this reader would open.
            same_log = existing['kind'] == kind and existing['target'] == target and existing['connection'] == connection
            if action == 'logs' and existing['action'] in {'boot', 'run', 'first-boot'} and same_log:
                return existing
        return None

    def _job_request(self, action, options):
        """Validate a job request: (options with target, log kind, sensor script, SSH connection)."""
        if not isinstance(action, str) or action not in self.ACTIONS or not isinstance(options, dict):
            raise ValueError('Invalid operation')
        if set(options) - {'target', 'connection', 'sensorless', 'kind', 'board', 'os', 'device', 'model', 'retry', 'scenario'}:
            raise ValueError('Invalid operation parameters')
        if options.get('target', self.hardware.default_target()) not in ('native', 'qemu', 'physical'):
            raise ValueError('Invalid target')
        if 'scenario' in options:
            from sensors.scenarios import SCENARIOS
            if (action != 'simulate-preview' or options['scenario'] not in SCENARIOS
                    or not options.get('device') or 'model' in options):
                raise ValueError('Select a local sensor scenario')
        if 'sensorless' in options and type(options['sensorless']) is not bool:
            raise ValueError('Invalid sensor profile')
        if 'retry' in options and (type(options['retry']) is not bool or action != 'boot' or options.get('target', 'qemu') != 'qemu'):
            raise ValueError('Retry applies only to QEMU startup')
        if 'connection' in options and not isinstance(options['connection'], dict):
            raise ValueError('Invalid connection')
        if options.get('kind', 'flight') not in (('boot', 'flight', 'current-flight') if action == 'logs' else ('boot', 'flight')):
            raise ValueError('Invalid log type')
        if any(key in options and options[key] is not None and (not isinstance(options[key], str) or not options[key]) for key in ('board', 'os')):
            raise ValueError('Invalid board or operating system')
        options = dict(options)
        target = options.setdefault('target', self.hardware.default_target())
        kind = 'boot' if action == 'boot' else options.get('kind', 'flight')
        script = None
        if action in {'simulate', 'simulate-preview'}:
            if action == 'simulate' and target != 'qemu':
                raise ValueError('Synthetic data is only available in QEMU emulation.')
            if 'device' in options and not isinstance(options['device'], str):
                raise ValueError('Invalid sensor selection')
            if 'model' in options:
                from sensors.simulator import simulation_scripts
                scripts = simulation_scripts(self.workspace.root)
                model = options['model']
                known = isinstance(model, str) and model in scripts
                if action != 'simulate-preview' or options.get('device') or not known:
                    raise ValueError('Select one Python sensor model to preview')
                script = scripts[model]
            elif not options.get('device'):
                session = self.workspace.simulation_snapshot()
                if not any(sensor['enabled'] for sensor in session['settings']['sensors']):
                    raise ValueError('Select at least one sensor in Synthetic data')
            if script is None:
                script = self.hardware.simulation_script(options.get('device'))
        elif action in {'sensor-test', 'model-test'}:
            if not isinstance(options.get('device'), str) or not options['device'] or 'model' in options:
                raise ValueError('Select a sensor on the workbench.')
        elif 'device' in options or 'model' in options:
            raise ValueError('A device can only be selected for synthetic data.')
        connection = None
        if target == 'physical' and action in {'first-boot', 'sensor-test', 'logs', 'boot', 'run', 'stop', 'shutdown', 'connect', 'probe', 'setup'}:
            connection = self.hardware.connection(options.get('connection'))
            options['connection'] = connection
        return options, kind, script, connection

    def _emit(self, record, line):
        with self.lock:
            if str(line).startswith('@cfs-instance '):
                record['instance'] = line.split()[1]
                return
            first_boot.observe(self.hardware, record, str(line))
            if record['action'] == 'values' and str(line).startswith('@qmp-write '):
                receipt = json.loads(line[len('@qmp-write '):])
                write = {receipt['device']: receipt['confirmed_at']}
                record['qmp_writes'] = {**record.get('qmp_writes', {}), **write}
                evidence.record_writes(self.hardware.root, record['target'], write)
                line = f"qom-set {receipt['device']}.{receipt['property']} = {receipt['value']} · OK"
            if record.get('scenario') and str(line).startswith('@scenario '):
                record['scenario_result'] = json.loads(line[len('@scenario '):])
                return
            if record['action'] in {'simulate', 'simulate-preview'} and str(line).startswith('@sensor '):
                try:
                    samples = json.loads(str(line)[8:])
                except ValueError:
                    samples = None
                if isinstance(samples, dict):
                    record['samples'] = dict(samples, received_at=time.time())
                    evidence.record_signal(self.hardware.root, record)
                    return
            if record['action'] == 'boot' and record['target'] == 'qemu':
                output = str(line)
                stage = record.get('boot_stage', 0)
                if output.startswith('[emulator] Image ready'):
                    stage = 1
                elif output.startswith('[emulator] Disk copied'):
                    stage = 2
                elif output.startswith('[emulator] Disk ready') or 'Booting Linux on physical CPU' in output:
                    stage = 3
                elif ' login:' in output or ('Started' in output and 'OpenBSD Secure Shell server' in output):
                    stage = 4
                record['boot_stage'] = max(stage, record.get('boot_stage', 0))
            if 'journal_apps' in record:
                fact = first_boot.parse_boot_line(str(line))
                if fact and 'app' in fact:
                    record['journal_apps'].setdefault(fact['app'], fact)
            record['lines'].append(str(line))
            record['line_count'] += 1

    def _cancel_readers(self, target, connection, kind=None, elsewhere=False):
        """Cancel streaming jobs of this destination, or only its log followers of one kind.

        With ``elsewhere``, streaming jobs of every other target or connection stop too.
        """
        with self.lock:
            for other in self.jobs.values():
                here = other['target'] == target and other['connection'] == connection
                follows = kind is None or other['action'] in {'first-boot', 'logs', 'boot', 'run'} and other['kind'] == kind
                if other['streaming'] and (here and follows or elsewhere and not here):
                    other['cancel'].set()

    def _run_job(self, record, options):
        """Job thread. An exclusive job holds self.operation until its operation ends."""
        owns_operation = record['action'] not in self.BACKGROUND
        emit = lambda line: self._emit(record, line)
        try:
            if record['cancel'].is_set():
                return
            result = self._execute_job(record, options, emit)
            with self.lock:
                record['result'] = result
                record['operation_complete'] = True
                record['ready_at'] = time.time()
                record['exit_code'] = 0
                record['status'] = 'succeeded'
        except Exception as error:
            message = ('Log reader stopped: ' if record['operation_complete'] else '') + str(error)
            if not record['cancel'].is_set():
                emit(message)
            with self.lock:
                record['error'] = message
                record['exit_code'] = getattr(error, 'returncode', None)
                record['status'] = 'failed'
        finally:
            with self.lock:
                if record['cancel'].is_set():
                    record['status'] = 'cancelled'
                record['ended'] = time.time()
                if record['action'] == 'simulate-preview':
                    evidence.record_signal(self.hardware.root, record)
            if owns_operation:
                self.operation.release()

    def _execute_job(self, record, options, emit):
        action, target, kind, connection = record['action'], record['target'], record['kind'], record['connection']
        if action == 'first-boot':
            return first_boot.execute(self, record, options, emit)
        if action == 'clone-cfs':
            self.hardware._stream([str(self.workspace.root / 'scripts/install-cfs.sh')], emit,
                                  cancel=record['cancel'], cwd=self.workspace.root)
            return infrastructure.source_status(self.workspace.root)
        if action == 'boot' and target == 'qemu':
            # Refuse an impossible boot before disconnecting anything.
            self.hardware.assert_can_boot(options.get('retry', False))
        def replace_readers():
            self.ground.stop()
            self._cancel_readers(target, connection, kind=kind, elsewhere=True)
        if action == 'boot':
            replace_readers()
        elif action in {'build', 'stop', 'shutdown'}:
            self.ground.stop()
        if action == 'shutdown':
            # Stop readers/writers before SSH and QMP disappear normally.
            self._cancel_readers(target, connection)
        # A run replaces the readers only once its build and target checks pass.
        on_start = replace_readers if action == 'run' else None
        result = self.hardware.execute(action, emit, cancel=record['cancel'], on_start=on_start, **options)
        if action in {'stop', 'shutdown'}:
            # Readers opened meanwhile would follow software that no longer runs.
            self._cancel_readers(target, connection, kind='flight' if action == 'stop' else None)
        if action == 'build' and isinstance(result, dict) and result.get('fingerprint') and not record['cancel'].is_set():
            emit('Preparing the communication catalog for this build...')
            try:
                self.freeze_catalog(result, bool(result.get('sensorless')))
            except (ValueError, OSError, RuntimeError) as error:
                emit('Catalog unavailable: ' + str(error))
        return result

    def boot_journal_snapshot(self, target, connection, instance):
        """Read an existing invocation's log buffer without creating or cancelling readers."""
        if instance:
            with self.lock:
                for reader in reversed(self.jobs.values()):
                    if (reader.get('journal_instance') == instance and reader['target'] == target
                            and reader['connection'] == connection):
                        return list(reader['lines'])[-300:], dict(reader['journal_apps'])
        return [], {}

    def cancel(self, ident):
        with self.lock:
            record = self.jobs.get(ident)
            if record is None:
                raise ValueError('Operation not found')
            if record['status'] == 'running':
                record['cancel'].set()
            return {'id': ident, 'status': record['status'], 'cancel_requested': record['cancel'].is_set()}

    def jobs_snapshot(self, *, boot_trace=False):
        jobs = []
        with self.lock:
            for job in self.jobs.values():
                public = {key: value for key, value in job.items() if key not in ('cancel', 'thread', 'key', 'lines', 'boot_trace', 'journal_apps')}
                if boot_trace and 'boot_trace' in job:
                    public['boot_trace'] = list(job['boot_trace'])
                if 'flight' in job:
                    public['flight'] = deepcopy(job['flight'])
                public['lines'] = list(job['lines'])
                jobs.append(public)
        return jobs + self.shells.snapshots()

    def freeze_catalog(self, state, sensorless=False, *, persist=True):
        """Catalog of one build, saved per build fingerprint.

        Packet layouts come from that build's compiler output, so later source
        edits do not change how its telemetry is decoded.
        """
        fingerprint = state.get('fingerprint', '')
        if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise ValueError('Invalid build identifier')
        target = state.get('target', self.hardware.default_target())
        profile = 'native' if target == 'native' else 'flight'
        filename = 'catalog-' + profile + '-' + fingerprint + ('-sensorless' if sensorless else '') + '.json'
        cached = self.hardware._load(filename)
        if cached and cached.get('catalog_version') == CATALOG_VERSION:
            # Board and emulator share ARM layouts. Receipts belong to this deployment.
            return dict(cached, build_target=target)
        build_root, _, build_state = self.hardware._require_build(sensorless, target=target)
        if build_state.get('fingerprint') != fingerprint:
            raise ValueError('The target uses a different build. Build and run before reconnecting.')
        build_dir = build_root / self.hardware.build_directory(target)
        catalog = self.ground.catalog(refresh=True, build_root=build_root, build_dir=build_dir)
        # An external editor can bypass the UI lock while the compiler inspects headers.
        self.hardware._require_build(sensorless, target=target)
        if not catalog.get('transport'):
            raise ValueError('; '.join(catalog.get('errors', [])) or 'No transport in the catalog')
        catalog['build_fingerprint'] = fingerprint
        catalog['sensorless'] = sensorless
        catalog['build_target'] = target
        if persist:
            self.hardware._save(filename, catalog)
        return catalog

    def ground_catalog(self, target=None):
        target = target or self.hardware.default_target()
        if target not in ('native', 'qemu', 'physical'):
            raise ValueError('Invalid target')
        deployment = self.hardware._load('deployed.json', {}).get(target)
        active = deployment if deployment and not deployment.get('stopped_at') else None
        sensorless = bool(active and active.get('sensorless'))
        state = active or self.hardware.build_state(target)
        if not state:
            return {'packets': [], 'commands': [], 'transport': {},
                    'errors': ['Build and run the flight software to prepare the catalog.']}
        return apply_overrides(self.freeze_catalog(dict(state, target=target), sensorless, persist=False), self.workspace.root)

    def ground_start(self, options):
        if set(options) - {'target', 'connection'}:
            raise ValueError('Invalid ground station configuration')
        if 'connection' in options and not isinstance(options['connection'], dict):
            raise ValueError('Invalid connection')
        target = options.get('target', self.hardware.default_target())
        deployment = self.hardware._load('deployed.json', {}).get(target)
        if not deployment:
            raise ValueError('Build and run cFS on this target before connecting the ground station.')
        hardware = self.hardware.status()
        if target == 'physical':
            probe = self.hardware.probe(options.get('connection'))
            running = probe.get('service') == 'active'
        elif target == 'native':
            running = hardware['native'].get('running')
        else:
            running = hardware['qemu'].get('flight_running')
        if not running:
            raise ValueError('cFS is not available on this target. Run it from the workbench before connecting the ground station.')
        if target == 'physical':
            current = self.hardware.connection(options.get('connection'))
            prior = deployment.get('connection') or {}
            if not self.hardware.same_board(current, prior):
                raise ValueError('Run cFS on the selected board to deploy this mission there.')
        catalog = apply_overrides(self.freeze_catalog(deployment, bool(deployment.get('sensorless'))), self.workspace.root)
        if target == 'native':
            instance = deployment.get('instance') if deployment.get('pid') in hardware['native']['pids'] else None
        else:
            argv = self.hardware.ssh_argv(target, options.get('connection'))
            service = 'cfs-studio.service' if target == 'physical' else 'cfs.service'
            command = f'systemctl show --property=InvocationID --value {service}'
            code, instance = self.hardware._capture(argv + [command], 5)
            if code or len(instance) != 32 or any(c not in '0123456789abcdef' for c in instance):
                instance = None
        link = resolve_ground_link(self.hardware, target, catalog, options.get('connection'))
        result = self.ground.start(**link, catalog=catalog, service_instance=instance,
                                   journey_reset_at=self.hardware.journey.snapshot(target)['reset_at'])
        self.ground_target = target
        return dict(result, target=target)

    def ground_snapshot(self):
        return dict(self.ground.snapshot(), target=self.ground_target)

    def ground_source(self, query):
        catalog = self.ground_catalog(query.get('target'))
        category = 'commands' if query.get('kind') == 'command' else 'packets'
        packet = next((packet for packet in catalog[category] if packet['id'] == query.get('id')), None)
        if packet is None:
            raise ValueError('Definition not found in this build.')
        from ground_station.catalog import source_locations
        app = packet['app']
        from project.flight_sources import module_directory
        appdir = (self.workspace.root / 'cFS/cfe/modules' / app[4:] if app.startswith('cfe_')
                  else module_directory(self.workspace.root, 'apps', app))
        # Resolve again against the current workspace so added comments cannot shift navigation.
        locations = source_locations(self.workspace.root, appdir, packet)
        kind = query.get('section') or ('dispatch' if category == 'commands' else 'packet')
        location = locations.get(kind) or locations.get('identifier') or locations.get('packet')
        if location is None and packet.get('source', '').endswith(('.c', '.h')):
            location = {'path': packet['source'], 'line': 1, 'end_line': 1, 'symbol': packet['id']}
        if location is None:
            raise ValueError('This packet has no C source location in this workspace.')
        self.workspace.path(location['path'])
        return location

    def ground_send(self, body):
        if set(body) - {'command_id', 'values', 'target', 'test_id'}:
            raise ValueError('Invalid command parameters')
        if body.get('target', self.ground_target) != self.ground_target:
            raise ValueError('Connect the ground station to the selected target before sending commands.')
        if not isinstance(body.get('values', {}), dict):
            raise ValueError('Command values must be an object')
        return self.ground.send(body['command_id'], body.get('values', {}), test_id=body.get('test_id'))

    def ground_plan(self, body):
        return self.ground.plans.save(body, self.ground_catalog(body.get('target')) if not body.get('delete') else {})

    def close(self):
        self.shells.close()
        with self.lock:
            self.closing = True
            jobs = list(self.jobs.values())
            for job in jobs:
                job['cancel'].set()
        self.ground.stop()
        deadline = time.monotonic() + 6
        for job in jobs:
            # A job registered just before closing may not have started its thread.
            if job['thread'].is_alive():
                job['thread'].join(max(0, deadline - time.monotonic()))


class Handler(BaseHTTPRequestHandler):
    server_version = 'FlightStudio/1'

    def log_message(self, *_):
        pass

    def reply(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def stream_checks(self, hardware, target):
        snapshots = infrastructure.check_progress(hardware, target)
        first = next(snapshots)  # Validate the target and load its settings before committing HTTP 200.
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

        def publish(snapshot):
            self.wfile.write((json.dumps(snapshot, ensure_ascii=False) + '\n').encode('utf-8'))
            self.wfile.flush()

        try:
            publish(first)
            for snapshot in snapshots:
                publish(snapshot)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # A tab can close or switch targets while a probe is running.
        except Exception:
            traceback.print_exc()
            publish({'error': 'Setup verification was interrupted.'})
        finally:
            snapshots.close()

    def do_GET(self):
        try:
            if not self.valid_host():
                return self.reply({'error': 'Invalid host'}, 403)
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            app = self.server.studio
            routes = {
                '/api/journey': lambda: app.hardware.journey.snapshot(
                    (app.hardware._load('target.json', {}).get('journey_origin') if query.get('view') == 'board' else None)
                    or query.get('target') or selected_target(app.hardware.root)),
                '/api/session': lambda: {'token': app.token},
                '/api/workspace': lambda: {**app.workspace.snapshot(), 'builds': app.hardware.builds_status()},
                '/api/tree': lambda: app.workspace.tree(query.get('path', '')),
                '/api/files/search': lambda: app.workspace.search_files(query.get('root', 'cFS'), query.get('q', '')),
                '/api/file': lambda: app.workspace.read_file(query['path']),
                '/api/hardware': app.hardware.status,
                '/api/first-boot': lambda: first_boot.snapshot(app, query.get('target', app.hardware.default_target()), journal=app.boot_journal_snapshot),
                '/api/infrastructure': lambda: infrastructure.snapshot(app.hardware, verify_source=query.get('verify_source') == '1'),
                '/api/simulation': app.workspace.simulation_snapshot,
                '/api/simulation/orbit': lambda: orbit_preview(json.loads(query['parameters'])),
                '/api/hardware/device': lambda: device_settings(app.workspace, query.get('id')),
                '/api/jobs': app.jobs_snapshot,
                '/api/ground/catalog': lambda: app.exclusive(app.ground_catalog, query.get('target'), wait=3),
                '/api/ground/tests': app.ground.plans.read,
                '/api/ground': app.ground_snapshot,
                '/api/ground/source': lambda: app.exclusive(app.ground_source, query, wait=3),
            }
            if url.path in routes:
                return self.reply(routes[url.path]())
            if url.path == '/':
                name = 'infrastructure.html'
            elif url.path in {'/studio', '/studio/'}:
                if not infrastructure.sources_ready(app.workspace.root):
                    target = query.get('target')
                    destination = '/?target=' + target if target in {'native', 'qemu', 'physical'} else '/'
                    self.send_response(302)
                    self.send_header('Location', destination + '#target')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    return
                name = 'index.html'
            elif url.path == '/emulator-guide.html':
                name = 'emulator-guide.html'
            else:
                name = url.path.removeprefix('/')
                if Path(name).suffix not in ASSET_TYPES:
                    return self.reply({'error': 'Not found'}, 404)
            asset = (STATIC_ROOT / name).resolve()
            if not asset.is_relative_to(STATIC_ROOT) or not asset.is_file():
                return self.reply({'error': 'Not found'}, 404)
            data = asset.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', ASSET_TYPES.get(asset.suffix, 'text/html; charset=utf-8'))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', CONTENT_SECURITY_POLICY)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, KeyError, OSError, RuntimeError) as error:
            self.reply({'error': str(error)}, 400)
        except Exception as error:
            traceback.print_exc()
            self.reply({'error': str(error)}, 500)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_POST(self):
        app = self.server.studio
        origin = self.headers.get('Origin')
        allowed_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        token = self.headers.get('X-Studio-Token', '')
        if not self.valid_host() or (origin and origin not in allowed_origins) or not secrets.compare_digest(token, app.token):
            return self.reply({'error': 'Invalid session. Reload the page.'}, 403)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 2_000_000:
                raise ValueError('Invalid request size')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Send application/json')
            self.connection.settimeout(15)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Request body must be an object')
            path = urlparse(self.path).path
            if path == '/api/journey/reset':
                result = app.ground.reset_journey(body.get('target') or selected_target(app.hardware.root))
            elif path == '/api/file':
                result = app.exclusive(app.workspace.write_file, body['path'], body['content'], body.get('expected_hash'))
            elif path == '/api/infrastructure':
                result = app.exclusive(infrastructure.save, app, body)
            elif path == '/api/infrastructure/check':
                if 'label' in body:
                    return self.reply(infrastructure.check_one(app.hardware, body.get('target'), body['label']))
                if 'application/x-ndjson' in self.headers.get('Accept', ''):
                    return self.stream_checks(app.hardware, body.get('target'))
                result = infrastructure.check(app.hardware, body.get('target'))
            elif path == '/api/mutate':
                result = app.exclusive(app.workspace.mutate, body['action'], body.get('payload', {}), body.get('expected_hash'))
            elif path == '/api/mission/app':
                if body.get('action') == 'delete':
                    result = app.exclusive(app.workspace.delete_app, body.get('name'), body.get('expected_hash'))
                else:
                    result = app.exclusive(app.workspace.mission_app, body.get('action'), body.get('name'), body.get('expected_hash'))
            elif path == '/api/mission/library':
                result = app.exclusive(app.workspace.mission_library, body.get('action'), body.get('name'), body.get('expected_hash'))
            elif path == '/api/mission/rename':
                result = app.exclusive(app.workspace.rename_module, body.get('kind'), body.get('name'),
                                       body.get('new_name'), body.get('expected_hash'))
            elif path == '/api/mission/draft':
                draft = (body.get('kind'), body.get('name'), body.get('settings'), body.get('expected_hash'))
                result = app.exclusive(app.workspace.mission_draft, *draft, body.get('mode', 'create'))
            elif path == '/api/mission/save':
                draft = (body.get('kind'), body.get('name'), body.get('settings'), body.get('expected_hash'))
                result = app.exclusive(app.workspace.save_mission_draft, *draft, body.get('plan_hash'), body.get('mode', 'create'))
            elif path == '/api/mission/profile':
                result = app.exclusive(app.workspace.select_profile, body.get('board'), body.get('os'),
                                       body.get('expected_hash'), app.hardware)
            elif path == '/api/simulation/orbit':
                result = orbit_preview(body)
            elif path == '/api/simulation':
                if any(job['action'] in {'simulate', 'simulate-preview'} and job['status'] == 'running' for job in app.jobs_snapshot()):
                    raise ValueError('Stop synthetic data before changing its session settings')
                result = app.exclusive(app.workspace.save_simulation, body.get('settings'), body.get('expected_hash'))
            elif path == '/api/hardware/target':
                result = app.exclusive(app.hardware.select_target, body.get('target'), board_visit=body.get('use_board') is True)
            elif path == '/api/hardware/model':
                from project.sensor_models import register
                result = app.exclusive(register, app.workspace.root, body)
            elif path == '/api/hardware/device':
                result = app.exclusive(update_device, app.workspace, body)
            elif path == '/api/job':
                result = app.job(body['action'], body.get('options', {}))
            elif path == '/api/job/cancel':
                result = app.cancel(body['id'])
            elif path == '/api/terminal/create':
                result = app.shells.create(body.get('rows', 24), body.get('cols', 80),
                                           body.get('setup_action'), body.get('target'))
            elif path == '/api/terminal/read':
                result = app.shells.get(body['id']).read(body.get('cursor', 0))
            elif path == '/api/terminal/input':
                result = app.shells.get(body['id']).write(body['data'])
            elif path == '/api/terminal/resize':
                result = app.shells.get(body['id']).resize(body['rows'], body['cols'])
            elif path == '/api/terminal/close':
                result = app.shells.get(body['id']).close()
            elif path == '/api/ground/start':
                result = app.exclusive(app.ground_start, body)
            elif path == '/api/ground/stop':
                result = app.exclusive(app.ground.stop)
            elif path == '/api/ground/send':
                result = app.exclusive(app.ground_send, body)
            elif path == '/api/ground/tests':
                result = app.exclusive(app.ground_plan, body)
            elif path == '/api/ground/tests/cancel':
                if body.get('target') != app.ground_target or body.get('session') != app.ground_snapshot()['communication']['since']:
                    raise ValueError('The ground session has changed.')
                result = app.ground.cancel_test(body.get('id'))
            else:
                return self.reply({'error': 'Not found'}, 404)
            self.reply(result or {'ok': True})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, KeyError, OSError, RuntimeError) as error:
            self.reply({'error': str(error)}, 400)
        except Exception as error:
            traceback.print_exc()
            self.reply({'error': str(error)}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    server.studio = Studio()
    print(f'Flight Studio: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.studio.close()
        server.server_close()

if __name__ == '__main__':
    main()
