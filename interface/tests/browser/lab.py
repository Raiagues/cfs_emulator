"""Serve the real HTTP adapters with an isolated mission for browser checks."""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading

from interface.server import Handler, Studio
from project.flight_sources import prepare_mission


@contextmanager
def lab(root, *, completed=False):
    if not (root / 'cFS/cfe/CMakeLists.txt').is_file():
        raise RuntimeError('Install NASA cFS before running the browser inventory')
    with tempfile.TemporaryDirectory(prefix='flight-browser-') as temp:
        mission_root = Path(temp)
        ignore = shutil.ignore_patterns('__pycache__', '.runtime', '.state', 'build-native', 'build-flight', '.prepare*')
        for folder in ('cFS', 'mission', 'project', 'hardware', 'jobs', 'journey', 'ground_station', 'sensors', 'config', 'scripts'):
            shutil.copytree(root / folder, mission_root / folder, ignore=ignore, symlinks=True)
        for name in ('Dockerfile', 'start', 'boot.sh', 'logs.sh', 'stop.sh'):
            shutil.copy2(root / name, mission_root)
        prepare_mission(mission_root)
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            server.daemon_threads = False
            server.studio = Studio(mission_root)
            if completed:
                from journey import STEPS
                server.studio.hardware.select_target('native')
                workspace = server.studio.workspace
                app = 'nav_demo'
                workspace.mutate('add-app', {'name': app})
                workspace.mutate('link-hal', {'app': app, 'name': 'temp', 'device': 'temp'})
                view = workspace.command_lesson('native', app)
                for stage in range(5):
                    view = workspace.mutate('command-step', {'app': app, 'target': 'native', 'stage': stage,
                                             'source_hash': view['source_hash']}, view['expected_hash'])
                workspace.save_command_line('native', app, view['path'], view['content'].replace(view['stub'], view['ghost']),
                                            view['file_hash'])
                for index, step in enumerate(STEPS[:-1], 1):
                    server.studio.hardware.journey.observe('native', step, {'fixture': step, 'app': app,
                        'command': 'NAV_DEMO_SET_RATE_CC', 'device': 'temp'}, index)
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}'
            finally:
                server.shutdown()
                worker.join()
                server.studio.changes.close()
                server.server_close()
                server.studio.close()
