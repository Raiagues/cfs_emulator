#!/usr/bin/env python3
"""Local Flight Studio. Start with: python3 interface/server.py."""
import argparse
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
from interface.backend.terminal import Shells
from interface.backend.hardware_settings import device_settings, update_device
from hardware.manager import HardwareManager
from hardware import infrastructure
from hardware.ground_link import resolve_ground_link
from ground_station.station import GroundStation
from ground_station.catalog import apply_overrides, CATALOG_VERSION

# Infrastructure opens at /; the editor and diagrams open at /studio.
STATIC_FILES = {'app.js', 'style.css', 'prototype.css', 'panels.css', 'panels.js', 'board.js', 'board.css', 'ui.js',
                'layout.js', 'terminal.js', 'selectors.js', 'terminal.css', 'shell.js', 'architecture.js',
                'architecture.css', 'mission-diagram.js', 'mission-diagram.css', 'app-diagram.js', 'app-diagram.css',
                'communication.js', 'communication.css', 'simulation.js', 'simulation.css',
                'vendor/xterm.js', 'vendor/xterm.css', 'vendor/addon-fit.js', 'infrastructure.js', 'infrastructure.css'}
CONTENT_TYPES = {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8'}
CONTENT_SECURITY_POLICY = ("default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                           "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")


class Studio:
    ACTIONS = {'connect', 'probe', 'logs', 'simulate', 'setup', 'build', 'boot',
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

    def exclusive(self, operation, *args, **kwargs):
        if not self.operation.acquire(blocking=False):
            raise ValueError('Wait for the terminal operation to finish before editing files.')
        try:
            return operation(*args, **kwargs)
        finally:
            self.operation.release()

    def job(self, action, options):
        options, kind, script, connection = self._job_request(action, options)
        target = options['target']
        exclusive = action not in self.BACKGROUND
        with self.lock:
            if self.closing:
                raise ValueError('The server is shutting down.')
            destination = tuple(sorted(connection.items())) if connection else None
            key = (action, target, kind, destination, options.get('device'), options.get('model'))
            existing = None if exclusive else self._running_reader(action, key, target, kind, connection)
            if existing:
                return {'id': existing['id'], 'existing': True}
            if exclusive and not self.operation.acquire(blocking=False):
                raise ValueError('An operation is already running. Follow its progress in the terminal.')
            ident = secrets.token_hex(6)
            record = {'id': ident, 'action': action, 'target': target, 'connection': connection,
                      'device': options.get('device'), 'script': script, 'retry': bool(options.get('retry')),
                      'kind': kind, 'status': 'running', 'key': key,
                      'streaming': action in self.BACKGROUND, 'operation_complete': False,
                      'lines': deque(maxlen=3000), 'line_count': 0, 'started': time.time(), 'exit_code': None,
                      'cancel': threading.Event()}
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
            if action == 'logs' and existing['action'] in {'boot', 'run'} and same_log:
                return existing
        return None

    def _job_request(self, action, options):
        """Validate a job request: (options with target, log kind, sensor script, SSH connection)."""
        if not isinstance(action, str) or action not in self.ACTIONS or not isinstance(options, dict):
            raise ValueError('Invalid operation')
        if set(options) - {'target', 'connection', 'sensorless', 'kind', 'board', 'os', 'device', 'model', 'retry'}:
            raise ValueError('Invalid operation parameters')
        if options.get('target', self.hardware.default_target()) not in ('native', 'qemu', 'physical'):
            raise ValueError('Invalid target')
        if 'sensorless' in options and type(options['sensorless']) is not bool:
            raise ValueError('Invalid sensor profile')
        if 'retry' in options and (type(options['retry']) is not bool or action != 'boot' or options.get('target', 'qemu') != 'qemu'):
            raise ValueError('Retry applies only to QEMU startup')
        if 'connection' in options and not isinstance(options['connection'], dict):
            raise ValueError('Invalid connection')
        if options.get('kind', 'flight') not in ('boot', 'flight'):
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
        elif 'device' in options or 'model' in options:
            raise ValueError('A device can only be selected for synthetic data.')
        connection = None
        if target == 'physical' and action in {'logs', 'boot', 'run', 'stop', 'shutdown', 'connect', 'probe', 'setup'}:
            connection = self.hardware.connection(options.get('connection'))
            options['connection'] = connection
        return options, kind, script, connection

    def _emit(self, record, line):
        with self.lock:
            if record['action'] in {'simulate', 'simulate-preview'} and str(line).startswith('@sensor '):
                try:
                    samples = json.loads(str(line)[8:])
                except ValueError:
                    samples = None
                if isinstance(samples, dict):
                    record['samples'] = dict(samples, received_at=time.time())
                    return
            record['lines'].append(str(line))
            record['line_count'] += 1

    def _cancel_readers(self, target, connection, kind=None, elsewhere=False):
        """Cancel streaming jobs of this destination, or only its log followers of one kind.

        With ``elsewhere``, streaming jobs of every other target or connection stop too.
        """
        with self.lock:
            for other in self.jobs.values():
                here = other['target'] == target and other['connection'] == connection
                follows = kind is None or other['action'] in {'logs', 'boot', 'run'} and other['kind'] == kind
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
            if record['action'] in {'run', 'boot'} and not record['cancel'].is_set():
                # The same output continues after startup. Release the operation
                # lock so a long-running log tail never blocks Build/Run/Stop.
                with self.lock:
                    record['operation_complete'] = True
                    record['streaming'] = True
                    self.operation.release()
                    owns_operation = False
                self._follow_logs(record, emit)
            with self.lock:
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
            if owns_operation:
                self.operation.release()

    def _execute_job(self, record, options, emit):
        action, target, kind, connection = record['action'], record['target'], record['kind'], record['connection']
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

    def _follow_logs(self, record, emit):
        follow = {'target': record['target'], 'kind': record['kind']}
        if record['connection']:
            follow['connection'] = record['connection']
        if record['action'] == 'boot' and record['target'] == 'qemu':
            follow['tail'] = 0  # boot.sh already printed the serial history.
        if not record['cancel'].is_set():
            self.hardware.execute('logs', emit, cancel=record['cancel'], **follow)

    def cancel(self, ident):
        with self.lock:
            record = self.jobs.get(ident)
            if record is None:
                raise ValueError('Operation not found')
            if record['status'] == 'running':
                record['cancel'].set()
            return {'id': ident, 'status': record['status'], 'cancel_requested': record['cancel'].is_set()}

    def jobs_snapshot(self):
        jobs = []
        with self.lock:
            for job in self.jobs.values():
                public = {key: value for key, value in job.items() if key not in ('cancel', 'thread', 'key', 'lines')}
                public['lines'] = list(job['lines'])
                jobs.append(public)
        return jobs + self.shells.snapshots()

    def freeze_catalog(self, state, sensorless=False):
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
            return cached
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
        self.hardware._save(filename, catalog)
        return catalog

    def ground_catalog(self, target=None):
        target = target or self.hardware.default_target()
        if target not in ('native', 'qemu', 'physical'):
            raise ValueError('Invalid target')
        deployment = self.hardware._load('deployed.json', {}).get(target)
        sensorless = bool(deployment and deployment.get('sensorless'))
        state = deployment or self.hardware.build_state(target)
        if not state:
            return {'packets': [], 'commands': [], 'transport': {},
                    'errors': ['Build and run the flight software to prepare the catalog.']}
        return apply_overrides(self.freeze_catalog(state, sensorless), self.workspace.root)

    def ground_start(self, options):
        if set(options) - {'target', 'connection'}:
            raise ValueError('Invalid ground station configuration')
        if 'connection' in options and not isinstance(options['connection'], dict):
            raise ValueError('Invalid connection')
        target = options.get('target', self.hardware.default_target())
        deployment = self.hardware._load('deployed.json', {}).get(target)
        if not deployment:
            raise ValueError('Run the build on this target through the interface before connecting the ground station.')
        if target == 'physical' and self.hardware.connection(options.get('connection')) != deployment.get('connection'):
            raise ValueError('This SSH connection does not match the board used for the last deployment.')
        hardware = self.hardware.status()
        if target == 'physical':
            probe = hardware['physical'].get('last_probe') or {}
            running = probe.get('service') == 'active'
        elif target == 'native':
            running = hardware['native'].get('running')
        else:
            running = hardware['qemu'].get('flight_running')
        if not running:
            raise ValueError('cFS is not available on this target. Run it from the workbench before connecting the ground station.')
        catalog = self.ground_catalog(target)
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
        result = self.ground.start(**link, catalog=catalog, service_instance=instance)
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
        appdir = self.workspace.root / ('cFS/cfe/modules/' + app[4:] if app.startswith('cfe_') else 'cFS/apps/' + app)
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
        if set(body) - {'command_id', 'values', 'target'}:
            raise ValueError('Invalid command parameters')
        if body.get('target', self.ground_target) != self.ground_target:
            raise ValueError('Connect the ground station to the selected target before sending commands.')
        if not isinstance(body.get('values', {}), dict):
            raise ValueError('Command values must be an object')
        return self.ground.send(body['command_id'], body.get('values', {}))

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

    def do_GET(self):
        try:
            if not self.valid_host():
                return self.reply({'error': 'Invalid host'}, 403)
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            app = self.server.studio
            routes = {
                '/api/session': lambda: {'token': app.token},
                '/api/workspace': app.workspace.snapshot,
                '/api/tree': lambda: app.workspace.tree(query.get('path', '')),
                '/api/files/search': lambda: app.workspace.search_files(query.get('root', 'cFS'), query.get('q', '')),
                '/api/file': lambda: app.workspace.read_file(query['path']),
                '/api/hardware': app.hardware.status,
                '/api/infrastructure': lambda: infrastructure.snapshot(app.hardware),
                '/api/simulation': app.workspace.simulation_snapshot,
                '/api/hardware/device': lambda: device_settings(app.workspace, query.get('id')),
                '/api/jobs': app.jobs_snapshot,
                '/api/ground/catalog': lambda: app.exclusive(app.ground_catalog, query.get('target')),
                '/api/ground': app.ground_snapshot,
                '/api/ground/source': lambda: app.exclusive(app.ground_source, query),
            }
            if url.path in routes:
                return self.reply(routes[url.path]())
            if url.path == '/':
                name = 'infrastructure.html'
            elif url.path in {'/studio', '/studio/'}:
                name = 'index.html'
            elif url.path[1:] in STATIC_FILES:
                name = url.path[1:]
            else:
                return self.reply({'error': 'Not found'}, 404)
            data = (ROOT / 'interface/static' / name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPES[name.split('.')[-1]])
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
            if path == '/api/file':
                result = app.exclusive(app.workspace.write_file, body['path'], body['content'], body.get('expected_hash'))
            elif path == '/api/infrastructure':
                result = app.exclusive(infrastructure.save, app, body)
            elif path == '/api/infrastructure/check':
                result = app.exclusive(infrastructure.check, app.hardware, body.get('target'))
            elif path == '/api/mutate':
                result = app.exclusive(app.workspace.mutate, body['action'], body.get('payload', {}))
            elif path == '/api/mission/app':
                if body.get('action') == 'delete':
                    result = app.exclusive(app.workspace.delete_app, body.get('name'), body.get('expected_hash'))
                else:
                    result = app.exclusive(app.workspace.mission_app, body.get('action'), body.get('name'), body.get('expected_hash'))
            elif path == '/api/mission/library':
                result = app.exclusive(app.workspace.mission_library, body.get('action'), body.get('name'), body.get('expected_hash'))
            elif path == '/api/mission/draft':
                draft = (body.get('kind'), body.get('name'), body.get('settings'), body.get('expected_hash'))
                result = app.exclusive(app.workspace.mission_draft, *draft, body.get('mode', 'create'))
            elif path == '/api/mission/save':
                draft = (body.get('kind'), body.get('name'), body.get('settings'), body.get('expected_hash'))
                result = app.exclusive(app.workspace.save_mission_draft, *draft, body.get('plan_hash'), body.get('mode', 'create'))
            elif path == '/api/mission/profile':
                result = app.exclusive(app.workspace.select_profile, body.get('board'), body.get('os'), body.get('expected_hash'))
            elif path == '/api/simulation':
                if any(job['action'] == 'simulate' and job['status'] == 'running' for job in app.jobs_snapshot()):
                    raise ValueError('Stop synthetic data before changing its session settings')
                result = app.exclusive(app.workspace.save_simulation, body.get('settings'), body.get('expected_hash'))
            elif path == '/api/hardware/target':
                result = app.exclusive(app.hardware.select_target, body.get('target'))
            elif path == '/api/hardware/device':
                result = app.exclusive(update_device, app.workspace, body)
            elif path == '/api/job':
                result = app.job(body['action'], body.get('options', {}))
            elif path == '/api/job/cancel':
                result = app.cancel(body['id'])
            elif path == '/api/terminal/create':
                result = app.shells.create(body.get('rows', 24), body.get('cols', 80))
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
