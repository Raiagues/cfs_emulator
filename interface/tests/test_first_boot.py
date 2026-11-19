import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from interface.backend.first_boot import boot_observed, observe, parse_boot_line, snapshot
from hardware.manager import HardwareManager
from hardware import infrastructure


class BootTest(unittest.TestCase):
    def setUp(self):
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        self.hardware = HardwareManager(Path(project.name))
        self.job = {"id": "run-1", "target": "native", "action": "first-boot", "phase": "build"}

    def test_make_progress_and_es_states(self):
        observe(self.hardware, self.job, "[ 17%] Building C object kernel.o")
        observe(self.hardware, self.job, "[  8%] Building C object other.o")
        self.assertEqual(self.job["build_percent"], 17)
        line = "1980-012-14:03:20.65405 CFE_ES_Main: CFE_ES_Main entering OPERATIONAL state"
        observe(self.hardware, self.job, line)
        self.assertFalse(boot_observed(self.hardware, "native"))
        self.job["phase"] = "run"
        observe(self.hardware, self.job, "CFE_ES_Main: CFE_ES_Main in EARLY_INIT state")
        self.assertFalse(boot_observed(self.hardware, "native"))
        observe(self.hardware, self.job, line)
        self.assertEqual(self.job["flight"]["states"], ["EARLY_INIT", "OPERATIONAL"])
        self.assertTrue(boot_observed(self.hardware, "native"))

    def test_event_uses_packet_identity_without_assuming_spacecraft_or_application(self):
        self.job["phase"] = "run"
        observe(self.hardware, self.job, "EVS Port2 1980-012-14:03:20.55 89/2/LIGHTING 7: Lighting initialized.")
        fact = self.job["flight"]["initialized"]["LIGHTING"]
        self.assertEqual((fact["spacecraft"], fact["processor"], fact["eid"]), (89, 2, 7))
        self.assertIsNone(parse_boot_line("SCH Lab Initialized"))
        self.assertIsNone(parse_boot_line("EVS Port1 1980-012 66/1/DEMO 4: Not initialized"))
        self.assertIsNone(parse_boot_line("EVS Port1 1980-012 66/1/DEMO 4: NOOP"))

    def test_running_and_stopped_snapshot_preserve_startup_modules(self):
        h = self.hardware
        startup = "CFE_APP, /cf/sample_app.so, SAMPLE_APP_Main, SAMPLE_APP, 50, 8192, 0, 0;"
        mission = SimpleNamespace(startup_text=lambda: startup)
        studio = SimpleNamespace(hardware=h, workspace=SimpleNamespace(mission=mission), jobs_snapshot=lambda: [self.job])
        self.job.update(phase="run", started=1)
        observe(h, self.job, "CFE_ES_Main: CFE_ES_Main entering OPERATIONAL state")
        h._save("deployed.json", {"native": {"pid": 42, "deployed_at": 1}})
        with patch.object(h, "profiles", return_value=[]), patch.object(h, "_local_flight_state", return_value={"pids": [42]}) as processes:
            running = snapshot(studio, "native")
            self.assertEqual(running["apps"], [{"name": "sample_app", "task": "SAMPLE_APP"}])
            self.assertTrue(running["running"])
            processes.return_value = {"pids": []}
            self.assertTrue(snapshot(studio, "native")["stopped"])
            h._mark_stopped("native")
            processes.return_value = {"pids": [42]}
            stopped = snapshot(studio, "native")
            self.assertFalse(stopped["running"])
            self.assertTrue(stopped["stopped"])
            self.assertTrue(boot_observed(h, "native"))

    def test_saved_target_requires_verified_plan_and_an_installed_checkout(self):
        h = self.hardware
        for folder in ("config", "project", "cFS/.git", "cFS/cfe", "cFS/sample_defs"):
            (h.root / folder).mkdir(parents=True)
        (h.root/"config/image").write_text("pi:test")
        (h.root/"project/config.json").write_text('{"board":null,"os":null}')
        for marker in ("cFS/cfe/CMakeLists.txt", "cFS/sample_defs/targets.cmake"):
            (h.root/marker).touch()
        plan = list(infrastructure._check_plan(h, "native"))
        with patch.object(infrastructure, "_run", side_effect=lambda p: {"label":p.label,"ready":True}):
            for p in plan:
                infrastructure.check_one(h, "native", p.label)
        self.assertFalse(infrastructure.target_verified(h, "native"))
        h.select_target("native")
        self.assertTrue(infrastructure.target_verified(h, "native"))
        (h.root/"cFS/cfe/CMakeLists.txt").unlink()
        self.assertFalse(infrastructure.target_verified(h, "native"))
