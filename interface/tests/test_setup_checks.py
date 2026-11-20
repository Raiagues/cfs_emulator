"""The setup UI must receive real probe transitions while a slow host tool is still running."""
import json
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hardware import infrastructure
from hardware.manager import HardwareManager
from interface.server import Handler


class SetupChecksTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'config').mkdir()
        (root / 'config/image').write_text('studio:test')
        self.hardware = HardwareManager(root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.studio = SimpleNamespace(token='test-token', hardware=self.hardware)
        self.addCleanup(self.server.server_close)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)

    def request(self, target, stream=True, label=None):
        headers = {'Content-Type': 'application/json', 'X-Studio-Token': 'test-token'}
        if stream:
            headers['Accept'] = 'application/x-ndjson'
        url = f'http://127.0.0.1:{self.server.server_port}/api/infrastructure/check'
        body = {'target': target}
        if label is not None:
            body['label'] = label
        return urlopen(Request(url, json.dumps(body).encode(), headers), timeout=10)

    def test_live_probe_and_simultaneous_legacy_request(self):
        running = threading.Event()
        release = threading.Event()

        # This test exercises the HTTP stream and concurrent requests. Running
        # host tools here makes the synchronization depend on local startup time.
        def capture(command, **options):
            if command[1:3] == ('-m', 'project.nasa_source'):
                return subprocess.CompletedProcess(command, 1, '{"state":"missing"}')
            if command[:2] == ('docker', 'version'):
                running.set()
                if not release.wait(5):
                    raise RuntimeError('client did not receive the running state')
                return subprocess.CompletedProcess(command, 0, '28.0.0')
            return subprocess.CompletedProcess(command, 0, 'tool 1.0')

        with patch('hardware.infrastructure.subprocess.run', side_effect=capture), self.request('physical') as stream:
            self.assertEqual(stream.headers.get_content_type(), 'application/x-ndjson')
            first = json.loads(stream.readline())
            self.assertIsNone(first['ready'])
            self.assertTrue(all(row['status'] == 'pending' for row in first['checks']))
            try:
                for line in stream:
                    state = json.loads(line)
                    engine = next(row for row in state['checks'] if row['label'] == 'Docker engine ≥ 23')
                    if engine['status'] == 'running':
                        break
                else:
                    self.fail('stream completed before the engine check started')
                self.assertTrue(running.wait(4))
                self.assertIsNone(engine['ready'])
                self.assertIsNone(engine['duration_ms'])
                self.assertEqual(state['status'], 'running')
                # A slow Docker request must not hold the workspace operation lock.
                with self.request('native', stream=False) as native:
                    legacy = json.load(native)
                self.assertEqual(set(legacy), {'target', 'ready', 'checks'})
                self.assertEqual(legacy['target'], 'native')
                self.assertTrue(all(set(item) == {'label', 'ready', 'detail', 'command'} for item in legacy['checks']))
            finally:
                release.set()
            final = [json.loads(line) for line in stream][-1]
            self.assertEqual(final['status'], 'complete')
            self.assertFalse(final['ready'])  # Empty fixture has no NASA checkout.
            self.assertEqual(next(row['status'] for row in final['checks'] if row['label'] == 'Docker engine ≥ 23'), 'passed')
            self.assertTrue(all(row['duration_ms'] >= 0 for row in final['checks']))

    def test_target_settings_are_captured_and_failure_is_local(self):
        self.hardware._save('emulator.json', {'image': 'old:image', 'ssh_port': 24229})
        checks = infrastructure.check_progress(self.hardware, 'qemu')
        initial = next(checks)
        self.hardware._save('emulator.json', {'image': 'new:image', 'ssh_port': 24230})
        with patch('hardware.infrastructure.subprocess.run', side_effect=OSError('Docker unavailable')):
            frames = list(checks)
        final = {item['label']: item for item in frames[-1]['checks']}
        self.assertEqual(final['Emulator image']['status'], 'failed')
        self.assertEqual(final['Emulator image']['detail'], 'Docker unavailable')
        self.assertIn('Emulator SSH identity', final)
        self.assertTrue(all(item['status'] == 'pending' for item in initial['checks']))
        self.assertIsNone(final['Emulator image']['exit_code'])
        self.assertIn('old:image', final['Emulator image']['probe'])
        self.assertTrue(final['Local SSH port']['probe'].endswith('24229'))

    def test_plan_is_passive_and_one_click_executes_only_its_command(self):
        project = self.hardware.root / 'project'
        project.mkdir()
        (project / 'config.json').write_text('{"board": null, "os": null}')
        checkout = self.hardware.root / 'cFS'
        for path in ('.git', 'sample_defs', 'cfe'):
            (checkout / path).mkdir(parents=True)
        (checkout / 'sample_defs/targets.cmake').touch()
        (checkout / 'cfe/CMakeLists.txt').touch()
        with patch('hardware.infrastructure.subprocess.run', side_effect=AssertionError('unexpected probe')):
            settings = infrastructure.snapshot(self.hardware)
        self.assertEqual(settings['source']['state'], 'installed')
        self.assertIsNone(settings['source']['revision'])
        self.assertEqual(infrastructure.snapshot(self.hardware, verify_source=True)['source']['state'], 'occupied')
        planned = settings['check_plan']
        self.assertTrue(all(set(item) == {'label', 'probe'} for plan in planned.values() for item in plan))
        self.assertNotIn('docker', [item['label'] for item in planned['native']])
        fixture = self.hardware.root / 'bin'
        fixture.mkdir()
        git = fixture / 'git'
        git.write_text('#!/bin/sh\ntest "$1" = "--version" || exit 99\necho broken-git-on-path >&2\nexit 17\n')
        git.chmod(0o755)
        with patch.dict(os.environ, PATH=str(fixture)):
            with self.request('native', stream=False, label='git') as response:
                failed = json.load(response)
            with self.request('native', stream=False, label='make') as response:
                missing = json.load(response)
            git.write_text('#!/bin/sh\nexit 0\n')
            with self.request('native', stream=False, label='git') as response:
                no_version = json.load(response)
        self.assertEqual(failed['probe'], 'git --version')
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['exit_code'], 17)
        self.assertIn('broken-git-on-path', failed['detail'])
        self.assertIsNone(missing['exit_code'])
        self.assertEqual(no_version['exit_code'], 0)
        self.assertEqual(no_version['status'], 'failed')
        self.assertIn('version', no_version['detail'].lower())
        with self.assertRaises(HTTPError) as failure:
            self.request('native', label='docker')
        self.assertEqual(failure.exception.code, 400)

    def test_invalid_target_returns_json_before_starting_stream(self):
        with self.assertRaises(HTTPError) as failure:
            self.request('unknown')
        with failure.exception as response:
            self.assertEqual(response.code, 400)
            self.assertEqual(response.headers.get_content_type(), 'application/json')
            self.assertIn('error', json.load(response))


if __name__ == '__main__':
    unittest.main()
