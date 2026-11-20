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
def lab(root):
    if not (root / 'cFS/cfe/CMakeLists.txt').is_file():
        raise RuntimeError('Install NASA cFS before running the browser inventory')
    with tempfile.TemporaryDirectory(prefix='flight-browser-') as temp:
        mission_root = Path(temp)
        ignore = shutil.ignore_patterns('__pycache__', '.runtime', '.state', 'build-native', 'build-flight', '.prepare*')
        for folder in ('cFS', 'mission', 'project', 'hardware', 'journey', 'ground_station', 'sensors', 'config', 'scripts'):
            shutil.copytree(root / folder, mission_root / folder, ignore=ignore, symlinks=True)
        shutil.copy2(root / 'Dockerfile', mission_root)
        prepare_mission(mission_root)
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            server.daemon_threads = True
            server.studio = Studio(mission_root)
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}'
            finally:
                server.shutdown()
                worker.join()
                server.studio.close()
