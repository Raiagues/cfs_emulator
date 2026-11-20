"""Regression tests for CLI launch, PTY reads and physical deployment ownership."""
import base64
from collections import deque
from pathlib import Path
import runpy
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from hardware import activate_release
from hardware.manager import HardwareError, HardwareManager
from interface.backend.terminal import Shell, Shells


ROOT = Path(__file__).resolve().parents[2]


class ExecutionTest(unittest.TestCase):
    def test_installer_streams_interactive_output_and_reports_its_own_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory, "scripts")
            scripts.mkdir()
            installer = scripts / "setup.sh"
            installer.write_text("#!/bin/sh\ntest -t 0 || exit 9\necho checking-$1\necho Receiving: 100%\nstty -echo\nprintf Password:\nread -r answer\nstty echo\necho done-$answer\nexit 7\n")
            installer.chmod(0o755)
            shells = Shells(directory)
            self.addCleanup(shells.close)
            job = shells.create(setup_action="dependencies", target="physical")
            session = shells.get(job["id"])
            self.assertEqual(job["setup_action"], "dependencies")
            self.assertEqual(job["status"], "running")
            cursor = 0
            output = bytearray()

            def read_until(condition):
                nonlocal cursor
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    update = session.read(cursor)
                    cursor = update["cursor"]
                    output.extend(base64.b64decode(update["data"]))
                    if condition(update):
                        return update
                    time.sleep(.01)
                self.fail("Installer did not produce the expected output")

            update = read_until(lambda _: b"Password:" in output)
            self.assertFalse(update["exited"])
            self.assertIsNone(update["exit_code"])
            self.assertTrue(session.snapshot()["input_required"])
            self.assertIsNone(session.snapshot()["progress"])
            retry = shells.create(setup_action="dependencies", target="physical")
            self.assertEqual(retry["id"], job["id"])
            with self.assertRaisesRegex(ValueError, "installation is running"):
                shells.create(setup_action="emulator-image", target="qemu")
            session.write("next\n")
            update = read_until(lambda response: response["exited"])
            self.assertIn(b"checking---build-only", output)
            self.assertIn(b"done-next", output)
            self.assertFalse(session.snapshot()["input_required"])
            self.assertEqual(update["exit_code"], 7)
            self.assertEqual(shells.snapshots()[0]["status"], "failed")
            session.close()
            self.assertEqual(session.snapshot()["status"], "failed")
            next_job = shells.create(setup_action="dependencies", target="physical")
            next_session = shells.get(next_job["id"])
            next_session.close()
            self.assertEqual(next_session.snapshot()["status"], "cancelled")

    def test_port_with_and_without_ui(self):
        main = runpy.run_path(str(ROOT / "start"))["main"]
        for options in (["--port", "8766"], ["--ui", "--port", "8766"], ["--port=8766"]):
            with self.subTest(options=options), patch.dict(main.__globals__, {"replace": Mock()}) as globals_:
                main(options)
                argv = globals_["replace"].call_args.args[0]
                self.assertEqual(Path(argv[1]), ROOT / "interface/server.py")
                self.assertEqual(argv[2:], options[1:] if options[0] == "--ui" else options)

    def test_terminal_byte_window_crosses_chunks_and_handles_eviction(self):
        terminal = Shell.__new__(Shell)
        terminal.lock = threading.Lock()
        terminal.chunks = deque([b"a" * 60000, b"b" * 40000, b"c" * 10000])
        terminal.start, terminal.end, terminal.exit_code = 20, 110020, None
        result = terminal.read(0)
        self.assertTrue(result["truncated"])
        self.assertEqual(base64.b64decode(result["data"]), b"a" * 60000 + b"b" * 5536)
        self.assertEqual(result["cursor"], 65556)
        tail = terminal.read(result["cursor"])
        self.assertEqual(base64.b64decode(tail["data"]), b"b" * 34464 + b"c" * 10000)
        self.assertEqual(terminal.read(tail["cursor"])["data"], "")

    def test_stopping_another_board_keeps_the_active_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = HardwareManager(temporary)
            board_a = {"host": "pi-a.local", "port": 22, "user": "pi"}
            manager._save_active("physical", board_a, "running")
            manager._save("deployed.json", {"physical": {"connection": board_a}})
            manager._mark_stopped("physical", {**board_a, "host": "pi-b.local"})
            self.assertEqual(manager._load("active.json")["phase"], "running")
            self.assertNotIn("stopped_at", manager._load("deployed.json")["physical"])
            manager._mark_stopped("physical", {**board_a, "host": "PI-A.LOCAL"})
            self.assertEqual(manager._load("active.json")["phase"], "stopped")
            self.assertIn("stopped_at", manager._load("deployed.json")["physical"])

    def test_recheck_authorization_before_upload_and_reuse_board_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = HardwareManager(temporary)
            board = {"ready": False, "sudo": True, "systemd": True}
            manager.assert_can_start = Mock()
            manager.probe = Mock(return_value=board)
            manager._require_build = Mock(return_value=(manager.root, None, {}))
            manager.prepare_board = Mock(return_value={"setup_required": True, "setup_command": "manual setup"})
            manager._stream = Mock()
            with self.assertRaisesRegex(HardwareError, "manual setup"):
                manager._run("physical", {"host": "pi.local"}, False, Mock(), None, None)
            manager.probe.assert_called_once()
            self.assertIs(manager.prepare_board.call_args.kwargs["board"], board)
            manager._stream.assert_not_called()


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "studio").mkdir()
        self.current = self.root / "studio/current"

    def release(self, sequence, mark=False):
        directory = self.root / "releases" / f"a1234567890bcdef-{sequence}"
        (directory / "cpu1").mkdir(parents=True)
        (directory / "cpu1/core-cpu1").touch()
        if mark:
            (directory / activate_release.MARKER).write_text(directory.name)
        return directory

    def test_success_retains_current_rollback_unmarked_and_symlinks(self):
        obsolete = self.release(1, mark=True)
        rollback = self.release(2, mark=True)
        old_installation = self.release(3)
        new = self.release(4)
        unrelated = self.root / "releases/user-data"
        unrelated.mkdir()
        alias = self.root / "releases/a1234567890bcdef-5"
        alias.symlink_to(rollback)
        self.current.symlink_to(Path("..") / "releases" / rollback.name)
        calls = [subprocess.CompletedProcess([], status) for status in (1, 0, 0)]
        with patch("hardware.activate_release.wait_service") as watch, patch("hardware.activate_release.subprocess.run", side_effect=calls) as run:
            activate_release.activate(self.root, new.name, 10)
        self.assertEqual(run.call_args_list[-1].args[0], ["sudo", "-n", "systemctl", "start", "cfs-studio.service"])
        self.assertEqual(watch.call_args.args[:2], ("cfs-studio.service", 10))
        self.assertFalse(obsolete.exists())
        self.assertTrue(all(path.exists() for path in (old_installation, rollback, alias, unrelated)))
        self.assertEqual(self.current.resolve(), new)
        self.assertEqual((new / activate_release.MARKER).read_text(), new.name)

    def test_failed_activation_restores_previous_and_preserves_every_release(self):
        before = self.release(1, mark=True)
        prior = self.release(2, mark=True)
        new = self.release(3)
        self.current.symlink_to(prior)
        calls = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0), subprocess.CalledProcessError(3, "is-active")]
        with patch("hardware.activate_release.wait_service", side_effect=subprocess.CalledProcessError(3, "journalctl")), \
                patch("hardware.activate_release.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(subprocess.CalledProcessError):
                activate_release.activate(self.root, new.name, 10)
        self.assertEqual(self.current.resolve(), prior)
        self.assertTrue(before.exists())
        self.assertTrue(new.exists())
        self.assertFalse((new / activate_release.MARKER).exists())
