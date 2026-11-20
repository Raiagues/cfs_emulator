#!/usr/bin/env python3
"""Local Flight Studio. Start with: python3 interface/server.py."""
import argparse
import json
import secrets
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ground_station.catalog import CATALOG_VERSION
from hardware import infrastructure
from hardware.device_settings import device_settings, update_device
from hardware.targets import selected_target
from jobs.service import Laboratory
from journey import first_boot
from sensors.orbit import preview as orbit_preview

# Infrastructure opens at /; the editor and diagrams open at /studio.
STATIC_ROOT = ROOT / 'interface/static'
ASSET_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
               '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png'}
CONTENT_SECURITY_POLICY = ("default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                           "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")


class Studio(Laboratory):
    """Attach an HTTP session token to the shared lab operations."""

    def __init__(self, root=ROOT):
        super().__init__(root)
        self.token = secrets.token_urlsafe(32)


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
        return self.stream_records(infrastructure.check_progress(hardware, target))

    def stream_records(self, snapshots):
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
            publish({'error': 'Stream interrupted.'})
        finally:
            snapshots.close()

    def do_GET(self):
        try:
            if not self.valid_host():
                return self.reply({'error': 'Invalid host'}, 403)
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            app = self.server.studio
            if url.path == '/api/jobs/stream':
                return self.stream_records(app.job_updates(query.get('id'), int(query.get('cursor', 0))))
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
                '/api/first-boot': lambda: first_boot.snapshot(app, query.get('target') or selected_target(app.hardware.root), journal=app.boot_journal_snapshot),
                '/api/infrastructure': lambda: infrastructure.snapshot(app.hardware, verify_source=query.get('verify_source') == '1'),
                '/api/simulation': app.workspace.simulation_snapshot,
                '/api/simulation/orbit': lambda: orbit_preview(json.loads(query['parameters'])),
                '/api/hardware/device': lambda: device_settings(app.workspace, query.get('id')),
                '/api/jobs': lambda: app.jobs_snapshot(include_lines=query.get('lines') != '0'),
                '/api/ground/catalog': lambda: app.ground_catalog(query.get('target')),
                '/api/ground/tests': app.ground.plans.read,
                '/api/ground': app.ground_snapshot,
                '/api/ground/source': lambda: app.ground_source(query),
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
                result = app.workspace.write_file(body['path'], body['content'], body.get('expected_hash'))
            elif path == '/api/infrastructure':
                result = infrastructure.save(app.hardware, body)
            elif path == '/api/infrastructure/check':
                if 'label' in body:
                    return self.reply(infrastructure.check_one(app.hardware, body.get('target'), body['label']))
                if 'application/x-ndjson' in self.headers.get('Accept', ''):
                    return self.stream_checks(app.hardware, body.get('target'))
                result = infrastructure.check(app.hardware, body.get('target'))
            elif path == '/api/mutate':
                result = app.workspace.mutate(body['action'], body.get('payload', {}), body.get('expected_hash'))
            elif path == '/api/mission/app':
                if body.get('action') == 'delete':
                    result = app.workspace.delete_app(body.get('name'), body.get('expected_hash'))
                else:
                    result = app.workspace.mission_app(body.get('action'), body.get('name'), body.get('expected_hash'))
            elif path == '/api/mission/library':
                result = app.workspace.mission_library(body.get('action'), body.get('name'), body.get('expected_hash'))
            elif path == '/api/mission/rename':
                result = app.workspace.rename_module(body.get('kind'), body.get('name'),
                                       body.get('new_name'), body.get('expected_hash'))
            elif path == '/api/mission/draft':
                draft = (body.get('kind'), body.get('name'), body.get('settings'), body.get('expected_hash'))
                result = app.workspace.mission_draft(*draft, body.get('mode', 'create'))
            elif path == '/api/mission/save':
                draft = (body.get('kind'), body.get('name'), body.get('settings'), body.get('expected_hash'))
                result = app.workspace.save_mission_draft(*draft, body.get('plan_hash'), body.get('mode', 'create'))
            elif path == '/api/mission/profile':
                result = app.workspace.select_profile(body.get('board'), body.get('os'),
                                       body.get('expected_hash'), app.hardware)
            elif path == '/api/simulation/orbit':
                result = orbit_preview(body)
            elif path == '/api/simulation':
                if any(job['action'] in {'simulate', 'simulate-preview'} and job['status'] == 'running' for job in app.jobs_snapshot()):
                    raise ValueError('Stop synthetic data before changing its session settings')
                result = app.workspace.save_simulation(body.get('settings'), body.get('expected_hash'))
            elif path == '/api/hardware/target':
                result = app.hardware.select_target(body.get('target'), board_visit=body.get('use_board') is True)
            elif path == '/api/hardware/model':
                from project.sensor_models import register
                result = register(app.workspace.root, body)
            elif path == '/api/hardware/device':
                result = update_device(app.workspace, body)
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
                result = app.ground_start(body)
            elif path == '/api/ground/stop':
                result = app.ground.stop()
            elif path == '/api/ground/send':
                result = app.ground_send(body)
            elif path == '/api/ground/tests':
                result = app.ground_plan(body)
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
