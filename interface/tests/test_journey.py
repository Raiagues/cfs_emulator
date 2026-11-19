from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hardware import infrastructure
from hardware.manager import HardwareManager
from interface.backend.journey import derive, mission_evidence, record_signal, setup_observed_at
from interface.server import Studio
from project.appgen.source_tags import region
from sensors.runtime import apply_values


class Memory:
    def __init__(self):
        self.saved = {}

    def _save(self, key, value):
        self.saved[key] = value

    def _load(self, key, default):
        return self.saved.get(key, default)


class JourneyTest(unittest.TestCase):
    def test_compiled_defaults_are_not_a_new_command(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "mission/apps/example"
            (app / "fsw/inc").mkdir(parents=True)
            (app / "CMakeLists.txt").touch()
            header = app / "fsw/inc/example_fcncodes.h"
            header.write_text("#define EXAMPLE_NOOP_CC 0\n" + region("command.codes", "#define EXAMPLE_READ_CC 2\n"))
            apps, commands = mission_evidence(root, [{"name": "example"}])
            self.assertEqual(list(apps), ["example"])
            self.assertEqual(list(commands), [("example", "EXAMPLE_READ_CC")])

    def test_only_matching_flight_observations_complete_steps(self):
        command = ("example", "EXAMPLE_READ_CC")
        ground = {"connected": True, "target": "native", "first_flight": {"event": True, "event_at": 3},
                  "runs": [{"status": "passed", "sent": {"app": "example"}, "command": command[1], "finished_at": 6}]}
        history = {"devices": {"probe": 7}, "tested": 8}
        args = (1, {"native": 2}, {"example": 4}, {command: 5}, {"probe"}, ground, [])
        steps = derive("native", *args, signal_history=history)["steps"]
        self.assertEqual([key for key, v in steps.items() if not v["done"]], ["board"])
        self.assertEqual(steps["send"]["observed_at"], 6)
        disconnected = derive("native", None, {}, {}, {}, set(), {**ground, "connected": False}, [])
        self.assertFalse(disconnected["steps"]["event"]["done"])
        other = derive("qemu", *args)["steps"]
        self.assertFalse(any(other[k]["done"] for k in ["boot", "event", "send", "sensor", "test"]))
        empty = derive("native", None, {}, {}, {}, set(), ground, [], signal_history=history)["steps"]
        self.assertFalse(any(empty[k]["done"] for k in ["target", "command", "send", "sensor"]))
        passed = [{"app":command[0],"command":command[1],"target":"native","finished_at":9,"observations":[12]}]
        self.assertTrue(derive("native",None,{}, {},{command:5},set(),{},[],passed)["steps"]["send"]["done"])

    def test_setup_remembers_the_flown_target_without_permitting_a_new_boot(self):
        with TemporaryDirectory() as tmp, patch.object(infrastructure, "_source_inventory") as source, \
                patch.object(infrastructure, "_check_plan") as plan:
            hardware = HardwareManager(tmp)
            probe = infrastructure.Probe("Compiler", ("cc", "--version"))
            plan.return_value = [probe]
            source.return_value = {"state": "installed"}
            hardware.select_target("native")
            identity = infrastructure._identity(hardware, "native")
            infrastructure._receipt(hardware, "native", identity, {"label": "Compiler", "ready": True})
            hardware.select_target("physical")
            self.assertFalse(infrastructure.target_verified(hardware, "native"))
            self.assertIsNotNone(setup_observed_at(hardware, "native", None))

            # An old validated First boot is evidence of selection. A plain Run is not.
            path = "checks-native.json"
            receipt = hardware._load(path)
            receipt.pop("selected")
            hardware._save(path, receipt)
            self.assertIsNone(setup_observed_at(hardware, "native", 1))
            hardware._save("operational-native.json", {"boot_trace": [{"phase": "build"}]})
            self.assertIsNotNone(setup_observed_at(hardware, "native", 1))
            self.assertIsNone(setup_observed_at(hardware, "native", None))
            for invalid in ({"identity": "stale"}, {"checks": {}}, {"checks": {"Compiler": False}}):
                hardware._save(path, {**receipt, **invalid})
                self.assertIsNone(setup_observed_at(hardware, "native", 1))

    def test_dry_run_is_not_a_device_write(self):
        hw = Memory()
        sample = {"devices":[{"id":"sensor1"}], "received_at":3}
        record_signal(hw, {"action":"simulate-preview","samples":sample})
        self.assertFalse(hw.saved)
        record_signal(hw, {"action":"simulate","samples":sample})
        self.assertEqual(hw.saved["signal-observations.json"]["devices"], {"sensor1":3})

    def test_manual_qmp_receipts_survive_a_partially_failed_job(self):
        config = {"devices": [{"id": "imu", "values": {"x": 10, "y": 20}},
                              {"id": "thermal", "values": {"temp": 30000}}]}
        qmp = Mock()
        qmp.execute.side_effect = [{}, {}, ValueError("Device disconnected")]
        stream = StringIO()
        with redirect_stdout(stream), patch("sensors.runtime.time.time", side_effect=[11.5, 12.5]):
            with self.assertRaisesRegex(ValueError, "disconnected"):
                apply_values(config, qmp, report=True)
        studio = SimpleNamespace(lock=Lock(), hardware=Memory())
        job = {"action": "values", "lines": [], "line_count": 0, "status": "failed"}
        for line in stream.getvalue().splitlines():
            Studio._emit(studio, job, line)
        self.assertEqual(job["qmp_writes"], {"imu": 12.5})
        self.assertEqual(len(job["lines"]), 2)
        history = studio.hardware.saved["signal-observations.json"]
        for device, expected in (("imu", True), ("thermal", False)):
            state = derive("qemu", None, {}, {}, {}, {device}, {}, [], signal_history=history)
            self.assertEqual(state["steps"]["sensor"]["done"], expected)
