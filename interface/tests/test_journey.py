from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from io import StringIO
from itertools import product
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Condition
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hardware import infrastructure
from hardware.manager import HardwareManager
from interface.server import Studio
from journey import STEPS, SHIPPED_APPS, Observation, Store, derive, route
from journey.mission import built, created, record_signal
from project.appgen.source_tags import region
from sensors.runtime import apply_values


class JourneyTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = Store(self.root)

    def test_every_combination_credits_only_the_contiguous_prefix(self):
        for present in product((False, True), repeat=len(STEPS)):
            with self.subTest(present=present):
                events = [Observation(step, "native", i + 1, {"test": i}) for i, step in enumerate(STEPS) if present[i]]
                state = derive("native", reversed(events))
                first = next((i for i, evidence in enumerate(present) if not evidence), len(STEPS))
                current = STEPS[first] if first < len(STEPS) else None
                self.assertEqual(state["current"], current)
                self.assertEqual(state["next_route"], route(current, "native") if current else None)
                for i, step in enumerate(STEPS):
                    self.assertEqual(state["steps"][step]["done"], i < first)
                    self.assertEqual(state["steps"][step]["reachable"], i <= first)

    def test_reads_do_not_create_state_and_observations_survive_reset_and_restart(self):
        self.assertEqual(self.store.snapshot(None)["current"], "target")
        self.assertFalse(self.store.path.exists())
        self.store.observe("native", "boot", {"instance": "first"}, 2)
        self.store.observe("qemu", "target", {"checks": 1}, 1)
        self.store.observe("native", "target", {"checks": 1}, 1)
        self.assertEqual(Store(self.root).snapshot("native")["current"], "event")
        reset = self.store.reset("native")
        self.store.observe("native", "event", {"send": 1}, 3)
        self.assertIsNone(self.store.snapshot("native")["steps"]["event"]["observed_at"])
        self.assertEqual(reset["current"], "target")
        self.assertEqual(Store(self.root).snapshot("qemu")["current"], "boot")

    def test_independent_observers_can_write_concurrently(self):
        def write(value):
            Store(self.root).observe("native", "boot", {"pid": value}, 2)
        with ThreadPoolExecutor(8) as workers:
            list(workers.map(write, list(range(20)) * 2))
        self.assertEqual(len(self.store.events("native")), 20)

    def test_app_and_command_require_creation_and_the_installed_implementation(self):
        name = "example"
        for app in [name, *SHIPPED_APPS]:
            path = self.root / "mission/apps" / app
            path.mkdir(parents=True)
            (path / "CMakeLists.txt").touch()
            created(self.root, "native", app)
        self.assertEqual(self.store.references("native", "app"), [{"app": name}])
        app = self.root / "mission/apps/example/fsw"
        (app / "inc").mkdir(parents=True)
        (app / "inc/example_fcncodes.h").write_text("#define EXAMPLE_NOOP_CC 0\n" + region("command.codes", "#define EXAMPLE_READ_CC 2\n"))
        (app / "src/commands").mkdir(parents=True)
        handler = app / "src/commands/example_read_cmd.c"
        handler.write_text("return CFE_STATUS_NOT_IMPLEMENTED;")
        state = dict(target="native", build_dir="build", fingerprint="a", built_at=2)
        install = self.root / "build/exe/cpu1/cf"
        install.mkdir(parents=True)
        (install / "example.so").touch()
        built(self.root, state)
        self.assertFalse(self.store.references("native", "command"))
        handler.write_text("return CFE_SUCCESS;")
        built(self.root, state)
        self.assertEqual(self.store.references("native", "command"), [{"app": name, "build": "a", "command": "EXAMPLE_READ_CC"}])
        self.assertFalse(self.store.references("qemu", "command"))

    def test_selected_completed_checks_persist_after_switching_targets(self):
        with patch.object(infrastructure, "_source_inventory", return_value={"state": "installed"}), \
                patch.object(infrastructure, "_check_plan") as plan:
            hardware = HardwareManager(self.root)
            plan.return_value = [infrastructure.Probe("Compiler", ("cc", "--version"))]
            identity = infrastructure._identity(hardware, "native")
            hardware.select_target("native")
            infrastructure._receipt(hardware, "native", identity, {"label": "Compiler", "ready": True})
            hardware.select_target("physical")
            self.assertFalse(infrastructure.target_verified(hardware, "native"))
            self.assertTrue(self.store.snapshot("native")["steps"]["target"]["done"])
            self.assertFalse(self.store.snapshot("physical")["steps"]["target"]["done"])

    def link(self):
        self.store.observe("qemu", "app", {"app": "demo"}, 1)
        (self.root / "project").mkdir()
        source = Path(__file__).resolve().parents[2] / "project"
        for name in ("boards", "drivers"):
            shutil.copytree(source / name, self.root / "project" / name)
        config = json.loads((Path(__file__).parent / "fixtures/bancada/config.json").read_text())
        config["apps"] = [dict(config["apps"][-1], name="demo")]
        (self.root / "project/config.json").write_text(json.dumps(config))

    def test_dry_run_is_not_a_device_write(self):
        self.link()
        record_signal(self.root, {"target": "qemu", "action": "simulate-preview", "samples": {"devices": [{"id": "imu"}]}})
        self.assertFalse(self.store.references("qemu", "sensor"))

    def test_manual_qmp_receipts_survive_a_partially_failed_job(self):
        self.link()
        config = {"devices": [{"id": "imu", "values": {"x": 10, "y": 20}}, {"id": "thermal", "values": {"temp": 30000}}]}
        qmp = Mock()
        qmp.execute.side_effect = [{}, {}, ValueError("Device disconnected")]
        stream = StringIO()
        with redirect_stdout(stream), patch("sensors.runtime.time.time", side_effect=[11.5, 12.5]):
            with self.assertRaisesRegex(ValueError, "disconnected"):
                apply_values(config, qmp, report=True)
        studio = SimpleNamespace(lock=Condition(), changes=Mock(), hardware=HardwareManager(self.root))
        job = {"target": "qemu", "action": "values", "lines": [], "line_count": 0, "status": "failed"}
        for line in stream.getvalue().splitlines():
            Studio._emit(studio, job, line)
        self.assertEqual(job["qmp_writes"], {"imu": 12.5})
        self.assertEqual(len(job["lines"]), 2)
        self.assertEqual(self.store.snapshot("qemu")["steps"]["sensor"]["observed_at"], 11.5)
        self.assertEqual(self.store.references("qemu", "sensor"), [{"device": "imu"}])
        self.assertEqual(self.store.references("native", "sensor"), [])
