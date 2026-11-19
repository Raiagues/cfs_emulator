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
        self.assertEqual(parse_boot_line("CFE_ES_Main entering OPERATIONAL state"), {"state": "OPERATIONAL"})
        self.assertIsNone(parse_boot_line("sample_app: waiting for CFE_ES_Main entering OPERATIONAL state"))
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

    def test_replay_records_only_new_build_and_flight_observations(self):
        self.job["started"] = 100
        lines = ["[ 12%] Building demo", "[ 10%] Building other", "CFE_PSP: startup",
                 "EVS Port1 2000-001 9/2/TEST 4: Initialized", "CFE_ES_Main entering OPERATIONAL state"]
        with patch("interface.backend.first_boot.time.time", return_value=102):
            for line in lines[:2]:
                observe(self.hardware, self.job, line)
            self.job["phase"] = "run"
            for line in lines[2:]:
                observe(self.hardware, self.job, line)
                observe(self.hardware, self.job, line)
        trace = self.hardware._load("operational-native.json")["boot_trace"]
        self.assertEqual([event["line"] for event in trace], [lines[0], *lines[2:]])
        self.assertTrue(all(event["ms"] == 2000 for event in trace))
        self.assertEqual(trace[-2]["fact"]["spacecraft"], 9)

    def test_event_uses_packet_identity_without_assuming_spacecraft_or_application(self):
        self.job["phase"] = "run"
        observe(self.hardware, self.job, "EVS Port2 1980-012-14:03:20.55 89/2/LIGHTING 7: Lighting initialized.")
        fact = self.job["flight"]["initialized"]["LIGHTING"]
        self.assertEqual((fact["spacecraft"], fact["processor"], fact["eid"]), (89, 2, 7))
        self.assertIsNone(parse_boot_line("SCH Lab Initialized"))
        self.assertIsNone(parse_boot_line("EVS Port1 1980-012 66/1/DEMO 4: Not initialized"))
        self.assertIsNone(parse_boot_line("EVS Port1 1980-012 66/1/DEMO 4: NOOP"))

    def test_boot_page_before_the_first_clone(self):
        studio = SimpleNamespace(hardware=self.hardware, jobs_snapshot=lambda **kwargs: [])
        with patch.object(self.hardware, "profiles", return_value=[]):
            state = snapshot(studio, "native")
        self.assertEqual(state["apps"], [])
        self.assertFalse(state["verified"])
        self.assertFalse(state["running"])

    def test_running_and_stopped_snapshot_preserve_startup_modules(self):
        h = self.hardware
        studio = SimpleNamespace(hardware=h, jobs_snapshot=lambda **kwargs: [self.job])
        # Capture the installed manifest independently of edits to the next mission.
        self.job.update(phase="run", started=1, boot_apps=[{"name": "sample_app", "task": "SAMPLE_APP"}])
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

    def test_remote_receipt_requires_live_service_with_same_invocation(self):
        h = self.hardware
        instances = ("a" * 32, "b" * 32)
        for target in ("qemu", "physical"):
            with self.subTest(target=target):
                connection = {"host": "flight-board", "port": 22} if target == "physical" else None
                if connection:
                    h._save("connection.json", connection)
                job = dict(self.job, phase="run", started=1, instance=instances[0], connection=connection,
                           boot_apps=[], target=target)
                observe(h, job, "CFE_ES_Main: CFE_ES_Main entering OPERATIONAL state")
                # Reopening the server leaves a flight receipt, but no in-memory job.
                studio = SimpleNamespace(hardware=h, jobs_snapshot=lambda **kwargs: [])
                with patch.object(h, "profiles", return_value=[]), patch.object(h, "_flight_state") as probe:
                    probe.return_value = {"running": True, "service": "active", "pids": [71], "instance": instances[0]}
                    self.assertTrue(snapshot(studio, target)["running"])
                    self.assertTrue(snapshot(studio, target)["running"])
                    probe.assert_called_once()
                    for observation, stopped, unknown in (
                        ({"running": False, "service":"inactive"}, True, False),
                        ({"running": True, "service":"active", "instance":instances[1]}, True, False),
                        ({"running": None, "service":"unknown"}, False, True),
                    ):
                        h._invalidate_observation(target)
                        probe.return_value = observation
                        state = snapshot(studio, target)
                        self.assertFalse(state["running"])
                        self.assertEqual((state["stopped"], state["unverified"]), (stopped, unknown))
                        self.assertTrue(boot_observed(h, target))
                        self.assertIn("OPERATIONAL", state["flight"]["states"])

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
