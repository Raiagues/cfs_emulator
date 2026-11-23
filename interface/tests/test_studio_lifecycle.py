"""Exercise real listeners without building or starting a flight target."""
import contextlib
import io
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from hardware.manager import HardwareManager
from interface import lifecycle, server


LEGACY_SERVER = '''from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
class Handler(BaseHTTPRequestHandler):
    server_version = 'FlightStudio/1'
    def log_message(self, *_): pass
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')
with ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), Handler) as http:
    print('ready', flush=True)
    try: http.serve_forever()
    except KeyboardInterrupt: pass
Path(__file__).with_suffix('.closed').write_text('closed')
'''


@unittest.skipUnless(sys.platform.startswith('linux'), 'Local listener ownership uses Linux procfs')
class StudioLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.root = self.base / 'first' / 'same name'
        (self.root / 'interface').mkdir(parents=True)

    def free_port(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            return listener.getsockname()[1]

    def launch(self, root=None, unrelated=False):
        root = root or self.root
        (root / 'interface').mkdir(parents=True, exist_ok=True)
        script = root / ('unrelated.py' if unrelated else 'interface/server.py')
        script.write_text(LEGACY_SERVER)
        port = self.free_port()
        # The unrelated program deliberately receives the expected path as data.
        command = [sys.executable, '-B', str(script), str(port)]
        if unrelated:
            command.append(str(root / 'interface/server.py'))
        process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        self.addCleanup(cleanup)
        self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'Listener did not start')
        self.assertEqual(process.stdout.readline(), b'ready\n')
        return process, port, script

    def test_repeated_start_reuses_legacy_server_without_creating_a_studio(self):
        process, port, _ = self.launch()
        with patch.object(server, 'ROOT', self.root), patch.object(server, 'Studio') as factory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(server.main(['--port', str(port)]), 0)
            factory.assert_not_called()
        self.assertIn(f'http://127.0.0.1:{port}/', output.getvalue())
        self.assertEqual(lifecycle.owner(self.root, '127.0.0.1', port).pid, process.pid)
        self.assertIsNone(process.poll())

    def test_stop_is_graceful_and_repeatable_without_ssh(self):
        process, port, script = self.launch()
        self.assertTrue(lifecycle.stop(self.root, '127.0.0.1', port))
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(script.with_suffix('.closed').read_text(), 'closed')
        self.assertFalse(lifecycle.stop(self.root, '127.0.0.1', port))

    def test_different_workspace_with_same_basename_is_not_reused_or_stopped(self):
        other = self.base / 'second' / self.root.name
        process, port, _ = self.launch(other)
        self.assertIsNone(lifecycle.running_url(self.root, '127.0.0.1', port))
        with self.assertRaisesRegex(RuntimeError, 'another service or workspace'):
            lifecycle.stop(self.root, '127.0.0.1', port)
        self.assertIsNone(process.poll())

    def test_unrelated_program_cannot_impersonate_studio_with_header_and_argument(self):
        process, port, _ = self.launch(unrelated=True)
        self.assertIsNone(lifecycle.running_url(self.root, '127.0.0.1', port))
        with patch.object(server, 'ROOT', self.root), patch.object(server, 'Studio') as factory:
            output = io.StringIO()
            with contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as raised:
                server.main(['--port', str(port)])
            self.assertEqual(raised.exception.code, 1)
            factory.assert_not_called()
        self.assertIn('already in use', output.getvalue())
        self.assertNotIn('Traceback', output.getvalue())
        with self.assertRaisesRegex(RuntimeError, 'another service or workspace'):
            lifecycle.stop(self.root, '127.0.0.1', port)
        self.assertIsNone(process.poll())

    def test_changed_listener_is_not_signaled(self):
        process, port, _ = self.launch()
        instance = lifecycle.owner(self.root, '127.0.0.1', port)
        with patch.object(lifecycle, 'owner', side_effect=[instance, None]), \
                patch.object(lifecycle.os, 'kill') as kill, \
                patch.object(lifecycle.signal, 'pidfd_send_signal', create=True) as send:
            with self.assertRaisesRegex(RuntimeError, 'listener changed'):
                lifecycle.stop(self.root, '127.0.0.1', port)
        kill.assert_not_called()
        send.assert_not_called()
        self.assertIsNone(process.poll())

    def test_failed_studio_initialization_releases_bound_socket(self):
        port = self.free_port()
        with patch.object(server, 'Studio', side_effect=RuntimeError('initialization failed')):
            with self.assertRaisesRegex(RuntimeError, 'initialization failed'):
                server.main(['--port', str(port)])
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))

    def test_second_interrupt_during_cleanup_does_not_abort_resource_release(self):
        script = """import os, signal
from unittest.mock import patch
from interface import server
class Studio:
    launch_key = 'test'
    def close(self):
        os.kill(os.getpid(), signal.SIGINT)
        print('cleanup-completed', flush=True)
with patch.object(server, 'Studio', Studio), patch.object(server.ThreadingHTTPServer, 'serve_forever', side_effect=KeyboardInterrupt):
    server.main(['--port', PORT])
""".replace('PORT', repr(str(self.free_port())))
        result = subprocess.run([sys.executable, '-B', '-c', script],
                                cwd=Path(server.__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('cleanup-completed', result.stdout)

    def test_python_flags_do_not_turn_script_arguments_into_a_server_identity(self):
        self.assertEqual(lifecycle.script_argument([b'-B', b'-X', b'dev', b'interface/server.py']), b'interface/server.py')
        self.assertEqual(lifecycle.script_argument([b'other.py', b'interface/server.py']), b'other.py')
        self.assertIsNone(lifecycle.script_argument([b'-m', b'http.server']))
        self.assertIsNone(lifecycle.script_argument([b'-c', b'code', b'interface/server.py']))

    def test_emulator_shutdown_uses_guest_poweroff_not_studio_stop_script(self):
        manager = HardwareManager(self.base)
        manager._qemu_running = Mock(return_value=True)
        manager._stream = Mock()
        manager._wait_qemu_stopped(Mock())
        self.assertEqual(manager._stream.call_args_list[0].args[0],
                         [sys.executable, '-m', 'hardware.emulator_ssh', 'ssh', 'systemctl', 'poweroff', '--no-block'])
        self.assertEqual(manager._stream.call_args_list[1].args[0][:2], ['docker', 'wait'])
