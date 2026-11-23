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

    def test_new_attempt_requires_fresh_runtime_evidence_and_success(self):
        events = [Observation(step, "native", i, {"source": step})
                  for i, step in enumerate(("target", "boot", "event", "app", "command", "send"), 1)]
        events += [Observation("boot-start", "native", 10, {"job": "new"}),
                   Observation("event", "native", 11, {"sent_at": 3}),
                   Observation("boot", "native", 12, {"started": 2}),
                   Observation("boot-finish", "native", 13, {"job": "old", "status": "succeeded"})]
        pending = derive("native", events)
        self.assertEqual(pending["current"], "boot")
        self.assertIsNone(pending["steps"]["boot"]["ref"])
        self.assertIsNone(pending["steps"]["event"]["ref"])
        events.append(Observation("boot", "native", 14, {"started": 10, "run": "new"}))
        self.assertFalse(derive("native", events)["steps"]["boot"]["done"])
        events.append(Observation("boot-finish", "native", 15, {"job": "new", "status": "failed"}))
        self.assertEqual(derive("native", events)["current"], "boot")
        events[-1] = Observation("boot-finish", "native", 15, {"job": "new", "status": "succeeded"})
        recovered = derive("native", events)
        self.assertEqual(recovered["current"], "send")
        self.assertEqual(recovered["steps"]["event"]["observed_at"], 3)
        events.append(Observation("event", "native", 17, {"sent_at": 16}))
        completed = derive("native", events)
        self.assertEqual(completed["current"], "send")
        self.assertTrue(completed["steps"]["app"]["done"])
        self.assertTrue(completed["steps"]["command"]["done"])
        self.assertFalse(completed["steps"]["send"]["done"])

    def test_reload_after_rebuild_keeps_learned_event_but_requires_a_new_send(self):
        for at, step in enumerate(("target", "boot", "event", "app", "command", "send"), 1):
            self.store.observe("native", step, {"evidence": step}, at)
        self.store.begin_boot("native", "new-app-run", 10)
        pending = Store(self.root).snapshot("native")
        self.assertEqual(pending["current"], "boot")
        self.assertFalse(pending["steps"]["event"]["done"])
        self.store.observe("native", "boot", {"started": 10, "instance": "new"}, 11)
        self.assertEqual(Store(self.root).snapshot("native")["current"], "boot")
        self.store.finish_boot("native", "new-app-run", "succeeded")
        resumed = Store(self.root).snapshot("native")
        self.assertEqual(resumed["current"], "send")
        for step in ("event", "app", "command"):
            self.assertTrue(resumed["steps"][step]["done"], step)
        self.assertTrue(resumed["steps"]["send"]["reachable"])
        self.assertFalse(resumed["steps"]["send"]["done"])
        self.assertEqual(resumed["steps"]["event"]["observed_at"], 3)
        self.assertEqual(resumed["steps"]["event"]["ref"], {"evidence": "event"})
        # Historical course progress does not become current receiver evidence.
        self.assertEqual(self.store.references("native", "event"), [])
        self.assertEqual(self.store.references("native", "send"), [])
        self.store.observe("native", "send", {"sent_at": 12, "reply": "new"}, 13)
        self.assertTrue(Store(self.root).snapshot("native")["steps"]["send"]["done"])
        reset = self.store.reset("native")
        self.assertEqual(reset["current"], "target")
        self.assertFalse(reset["contact_completed"])
        self.assertTrue(all(not step["done"] for step in reset["steps"].values()))

    def test_failed_first_boot_cannot_supply_a_learned_event_to_a_retry(self):
        for status in ("failed", "cancelled"):
            with self.subTest(status=status):
                events = [Observation("target", "native", 1, {"checked": True}),
                          Observation("boot-start", "native", 2, {"job": "first"}),
                          Observation("boot", "native", 3, {"started": 2}),
                          Observation("event", "native", 4, {"sent_at": 4}),
                          Observation("boot-finish", "native", 5, {"job": "first", "status": status}),
                          Observation("boot-start", "native", 6, {"job": "retry"}),
                          Observation("boot", "native", 7, {"started": 6}),
                          Observation("boot-finish", "native", 8, {"job": "retry", "status": "succeeded"})]
                state = derive("native", events)
                self.assertEqual(state["current"], "event")
                self.assertFalse(state["contact_completed"])
                self.assertIsNone(state["steps"]["event"]["ref"])

    def test_reset_prevents_old_completed_contact_from_returning_after_boot(self):
        events = [Observation(step, "native", at, {"evidence": step})
                  for at, step in enumerate(("target", "boot", "event", "app", "command"), 1)]
        events.extend([Observation("reset", "native", 10, {"explicit": True}),
                       Observation("target", "native", 11, {"checked": True}),
                       Observation("boot-start", "native", 12, {"job": "restart"}),
                       Observation("event", "native", 13, {"sent_at": 3}),
                       Observation("boot", "native", 14, {"started": 12}),
                       Observation("boot-finish", "native", 15, {"job": "restart", "status": "succeeded"})])
        state = derive("native", events)
        self.assertEqual(state["current"], "event")
        self.assertFalse(state["contact_completed"])
        self.assertIsNone(state["steps"]["event"]["ref"])

    def test_attempt_persists_without_deleting_previous_history(self):
        self.store.observe("native", "target", {"checked": True}, 1)
        self.store.observe("native", "boot", {"run": "old"}, 2)
        self.store.begin_boot("native", "new", 3)
        self.store.finish_boot("native", "new", "cancelled")
        reopened = Store(self.root).snapshot("native")
        self.assertEqual(reopened["current"], "boot")
        self.assertEqual(reopened["boot_attempt"]["status"], "cancelled")
        self.assertEqual(len(self.store.events("native")), 4)
        self.assertEqual(self.store.references("native", "boot"), [])

    def test_remote_tutorial_unlock_survives_run_until_explicit_reset(self):
        for at, step in enumerate(("target", "boot", "event", "app", "command"), 1):
            self.store.observe("native", step, {"evidence": step}, at)
        self.assertTrue(self.store.snapshot("qemu")["remote_unlocked"])
        self.store.begin_boot("native", "new-run", 10)
        pending = self.store.snapshot("native")
        self.assertTrue(pending["remote_unlocked"])
        self.assertFalse(pending["steps"]["event"]["done"])
        self.assertEqual(pending["current"], "boot")
        self.assertEqual(self.store.references("native", "command"), [{"evidence": "command"}])
        self.store.finish_boot("native", "new-run", "failed")
        self.assertTrue(Store(self.root).snapshot("physical")["remote_unlocked"])
        self.store.reset("native")
        self.assertFalse(self.store.snapshot("physical")["remote_unlocked"])

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
