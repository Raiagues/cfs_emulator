import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hardware import emulator_ssh
from hardware.manager import HardwareManager
from interface.backend import first_boot


def result(stdout="", error="", code=0):
    return subprocess.CompletedProcess([], code, stdout, error)


class EmulatorIdentityTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "board").mkdir()
        self.pin = self.root / "board/known_hosts"
        self.pin.write_text("old disk key\n")
        blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))
        self.key = base64.b64encode(blob).decode()
        self.banner = "# 127.0.0.1:2222 SSH-2.0-OpenSSH_10.0p2 Debian\n"
        self.scan = self.banner + "[127.0.0.1]:2222 ssh-ed25519 " + self.key + "\n"
        self.container = {
            "Id": "container-A", "State": {"Running": True}, "HostConfig": {"NetworkMode": "bridge"},
            "NetworkSettings": {"Ports": {"2222/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3222"}]}},
            "Mounts": [{"Type": "bind", "Destination": "/work/board", "Source": str(self.root / "board")}],
        }

    def inspect(self):
        return result(json.dumps([self.container]))

    def test_recreated_disk_pinned_from_its_private_container_before_login(self):
        responses = [self.inspect(), result(self.banner, code=1), result(self.scan), result()]
        with patch.object(subprocess, "run", side_effect=responses) as run, patch.object(emulator_ssh.time, "sleep"):
            emulator_ssh.wait_for_guest(self.root, 3222, 20)
        calls = [c.args[0] for c in run.call_args_list]
        self.assertEqual(calls[1], calls[2])
        self.assertEqual(calls[1][:4], ["docker", "exec", "container-A", "ssh-keyscan"])
        self.assertEqual(calls[1][-1], "127.0.0.1")
        self.assertIn("StrictHostKeyChecking=yes", calls[3])
        self.assertIn("GlobalKnownHostsFile=none", calls[3])
        self.assertIn(f'UserKnownHostsFile="{self.pin}"', calls[3])
        self.assertEqual(calls[3][-4:], ["-p", "3222", "pi4-cfs", "true"])
        self.assertEqual(self.pin.read_text(), f"{emulator_ssh.ALIAS} ssh-ed25519 {self.key}\n")

    def test_wrong_container_disk_network_or_host_binding_cannot_replace_a_pin(self):
        for key, replacement in [
            ("Mounts", []), ("State", {"Running": False}), ("HostConfig", {"NetworkMode": "host"}),
            ("NetworkSettings", {"Ports": {"2222/tcp": [{"HostIp": "0.0.0.0", "HostPort": "3222"}]}}),
        ]:
            with self.subTest(key=key), patch.dict(self.container, {key: replacement}), \
                    patch.object(subprocess, "run", return_value=self.inspect()) as run:
                with self.assertRaisesRegex(ValueError, "emulator does not match"):
                    emulator_ssh.wait_for_guest(self.root, 3222, 1)
                run.assert_called_once()
                self.assertEqual(self.pin.read_text(), "old disk key\n")

    def test_reject_malformed_or_ambiguous_guest_reply(self):
        for bad in (self.scan * 2, self.scan.replace(":2222", ":22"),
                    self.scan.replace(self.key, "bWlzc2luZy1rZXk="), self.banner):
            with self.subTest(bad=bad), patch.object(subprocess, "run", return_value=result(bad)):
                with self.assertRaises(ValueError):
                    emulator_ssh.pin_guest(self.root, "container-A")
                self.assertEqual(self.pin.read_text(), "old disk key\n")

    def test_forwarded_endpoint_must_prove_guest_key(self):
        failed = result(error="Host key verification failed.", code=255)
        with patch.object(subprocess, "run", side_effect=[self.inspect(), result(self.scan), failed]) as run:
            with self.assertRaisesRegex(ValueError, "Host key verification failed"):
                emulator_ssh.wait_for_guest(self.root, 3222, 1)
            self.assertEqual(run.call_count, 3)

    def test_existing_qemu_is_enrolled_before_flight_state_check_on_retry(self):
        studio = Mock(hardware=Mock(spec=HardwareManager))
        studio.hardware._qemu_running.return_value = True
        studio.hardware.assert_can_start.side_effect = RuntimeError("stop at guard")
        cancel, emit = Mock(), Mock()
        with patch.object(first_boot.infrastructure, "target_verified", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "stop at guard"):
                first_boot.execute(studio, {"target": "qemu", "cancel": cancel}, {}, emit)
        studio.hardware.verify_running_emulator.assert_called_once_with(emit, cancel)
        studio.hardware.execute.assert_not_called()

    def test_board_uses_its_own_host_policy(self):
        argv = HardwareManager(self.root).ssh_argv("physical", {"host": "pi.local", "user": "pi"})
        self.assertIn("StrictHostKeyChecking=accept-new", argv)
        self.assertNotIn("-F", argv)
        self.assertFalse(any("HostKeyAlias" in arg or "board/known_hosts" in arg for arg in argv))
