"""Board probe over SSH: the remote script's protocol and how its answers are judged.

No Raspberry Pi is needed. The script runs locally with stub sudo/systemctl
commands, and SSH answers are replaced unless a test says otherwise.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from hardware.manager import PROBE_FIELDS, HardwareError, HardwareManager


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'hardware/board_probe.py'
BOARD = {'host': 'raspberrypi4.local', 'user': 'pi', 'port': 22}
PI = {'arch': 'aarch64', 'model': 'Raspberry Pi 4 Model B Rev 1.5', 'home': '/home/pi', 'hostname': 'raspberrypi4',
      'i2c': ['/dev/i2c-1'], 'sudo': False, 'authorized': True, 'shutdown_authorized': True,
      'service_installed': True, 'service': 'inactive', 'systemd': True,
      'os': 'Debian GNU/Linux 12 (bookworm)', 'raspios': True}


def temporary_manager(test):
    """A manager whose saved probe and connection go to a temporary runtime."""
    runtime = tempfile.TemporaryDirectory(prefix='runtime-')
    test.addCleanup(runtime.cleanup)
    manager = HardwareManager(ROOT)
    manager.runtime = Path(runtime.name)
    manager._last_probe = None
    return manager


def stub(directory, name, body):
    path = Path(directory) / name
    path.write_text('#!/bin/sh\n' + body + '\n')
    path.chmod(0o755)


class ProbeScriptTest(unittest.TestCase):
    def run_script(self, sudo_status):
        with tempfile.TemporaryDirectory(prefix='probe-') as directory:
            stub(directory, 'sudo', 'exit ' + str(sudo_status))
            stub(directory, 'systemctl', 'echo inactive; exit 3')
            stub(directory, 'systemd-run', 'exit 0')
            environment = {'PATH': directory, 'HOME': directory}
            # The same transport as probe(): the script on the standard input of `python3 -`.
            completed = subprocess.run([sys.executable, '-'], input=SCRIPT.read_text(), capture_output=True, text=True, env=environment, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    def test_reports_every_protocol_field_with_its_type(self):
        report = json.loads(self.run_script(sudo_status=1).splitlines()[-1])
        self.assertEqual(set(report), set(PROBE_FIELDS))
        for field, kind in PROBE_FIELDS.items():
            self.assertIsInstance(report[field], kind, field)
        self.assertEqual((report['sudo'], report['authorized'], report['shutdown_authorized']), (False, False, False))
        self.assertEqual((report['service'], report['systemd']), ('inactive', True))

    def test_sudo_permissions_are_reported_as_they_are(self):
        report = json.loads(self.run_script(sudo_status=0).splitlines()[-1])
        self.assertEqual((report['sudo'], report['authorized'], report['shutdown_authorized']), (True, True, True))

    def test_this_computer_is_rejected_as_a_board(self):
        output = self.run_script(sudo_status=1)
        report = json.loads(output.splitlines()[-1])
        if 'Raspberry Pi 4 Model B' in report['model'] and report['arch'] == 'aarch64' and report['raspios']:
            self.skipTest('the tests are running on a supported board')
        manager = temporary_manager(self)
        with mock.patch.object(HardwareManager, '_capture', return_value=(0, output)):
            with self.assertRaisesRegex(HardwareError, 'supports Raspberry Pi 4B'):
                manager.probe(BOARD)
        self.assertFalse((manager.runtime / 'probe.json').exists())


class ProbeTest(unittest.TestCase):
    def answer(self, code, output):
        manager = temporary_manager(self)
        capture = mock.patch.object(HardwareManager, '_capture', return_value=(code, output))
        with capture as captured:
            try:
                return manager, manager.probe(BOARD), captured
            except HardwareError as error:
                self.assertIsNone(manager._last_probe)
                self.assertFalse((manager.runtime / 'probe.json').exists())
                self.assertFalse((manager.runtime / 'connection.json').exists())
                return manager, error, captured

    def test_valid_board_answer_after_shell_noise(self):
        manager, result, captured = self.answer(0, 'Welcome to the board\n' + json.dumps(PI))
        self.assertEqual((result['connected'], result['ready'], result['service_ready']), (True, True, True))
        self.assertEqual(json.loads((manager.runtime / 'probe.json').read_text())['model'], PI['model'])
        self.assertEqual(json.loads((manager.runtime / 'connection.json').read_text()), BOARD)
        argv, timeout = captured.call_args.args
        # The command line stays constant; the script itself is the standard input.
        self.assertEqual((argv[-1], timeout), ('python3 -', 20))
        self.assertEqual(captured.call_args.kwargs['input'], SCRIPT.read_text())

    def test_missing_authorization_is_not_ready(self):
        _, result, _ = self.answer(0, json.dumps(dict(PI, authorized=False)))
        self.assertEqual((result['connected'], result['ready']), (True, False))

    def test_invalid_answers(self):
        cases = {'no JSON': 'Linux raspberrypi4 6.6.51', 'truncated JSON': json.dumps(PI)[:-8],
                 'missing field': json.dumps({k: v for k, v in PI.items() if k != 'raspios'}),
                 'wrong type': json.dumps(dict(PI, authorized='yes')), 'null model': json.dumps(dict(PI, model=None))}
        for case, output in cases.items():
            with self.subTest(case=case):
                _, error, _ = self.answer(0, output)
                self.assertIsInstance(error, HardwareError)
                self.assertTrue(str(error).startswith('Invalid SSH response: '), error)

    def test_unsupported_platforms(self):
        for change in ({'model': 'Raspberry Pi 3 Model B Rev 1.2'}, {'arch': 'armv7l'}, {'raspios': False}):
            with self.subTest(change=change):
                _, error, _ = self.answer(0, json.dumps(dict(PI, **change)))
                self.assertRegex(str(error), '^The platform supports Raspberry Pi 4B')

    def test_ssh_and_remote_failures_keep_their_original_message(self):
        for code, output in ((255, 'ssh: Could not resolve hostname raspberrypi4.local: Name or service not known'),
                             (255, 'pi@raspberrypi4.local: Permission denied (publickey).'),
                             (1, "Command '['ssh']' timed out after 20 seconds")):
            with self.subTest(output=output):
                _, error, _ = self.answer(code, output)
                self.assertTrue(str(error).startswith('SSH failed. '), error)
                self.assertTrue(str(error).endswith(output))

    @unittest.skipUnless(shutil.which('ssh'), 'OpenSSH client not installed')
    def test_real_ssh_without_a_board(self):
        # Nothing listens on local port 1, so the connection is refused at once.
        manager = temporary_manager(self)
        with self.assertRaisesRegex(HardwareError, '^SSH failed. ') as raised:
            manager.probe({'host': '127.0.0.1', 'user': '', 'port': 1})
        self.assertIn('127.0.0.1', str(raised.exception))
        self.assertFalse((manager.runtime / 'probe.json').exists())


if __name__ == '__main__':
    unittest.main()
