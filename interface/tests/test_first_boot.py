import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from journey.first_boot import CATALOG_ACTIVITY, boot_observed, console_text, observe, parse_boot_line, snapshot
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
        with patch("journey.first_boot.time.time", return_value=102):
            for line in lines[:2]:
                observe(self.hardware, self.job, line)
            self.job["phase"] = "run"
            for line in lines[2:]:
                observe(self.hardware, self.job, line)
                observe(self.hardware, self.job, line)
        trace = self.hardware.state.read("operational-native.json")["boot_trace"]
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

    def test_make_percentage_does_not_carry_into_install_or_catalog(self):
        for line in ("[ 86%] Building example.o", "[100%] Built target example",
                     "-- Installing: /mission/core-cpu1", CATALOG_ACTIVITY):
            observe(self.hardware, self.job, line)
        phases = [(e.get("activity"), e.get("percent")) for e in self.job["boot_trace"]]
        self.assertEqual(phases, [("Compiling", 86), (None, None), ("Installing", None), ("Indexing catalog", None)])
        self.assertIsNone(self.job["build_percent"])
        observe(self.hardware, self.job, "[100%] unrelated subprocess")
        self.assertEqual(self.job["build_activity"], "Indexing catalog")
        self.assertEqual(len(self.job["boot_trace"]), 4)

    def test_serial_observations_and_console_strip_terminal_commands(self):
        self.job.update(target="qemu", phase="boot")
        dirty = "[\x1b[0;32m OK \x1b[0m] Started ssh.service - OpenBSD Secure Shell server."
        lines = ["[emulator] Disk ready. Starting the guest kernel.", "Booting Linux on physical CPU",
                 "[Boot: 222s] SSH check: Connection closed by 127.0.0.1 port 2222", dirty, dirty,
                 "\x1b[!p\x1b]104\x07\x1b[?7h\x1b[6n\x1b[32766;32766H", " "]
        for line in lines:
            observe(self.hardware, self.job, line)
        self.assertEqual([e["guest_stage"] for e in self.job["boot_trace"]], [3, 4, 5])
        self.assertNotIn("flight", self.job)
        self.assertEqual(console_text(lines[-2]), "")
        self.assertEqual(console_text("␛]104␇␛[!pLinux"), "Linux")
        self.job.update(lines=lines, boot_apps=[])
        studio = SimpleNamespace(hardware=self.hardware, jobs_snapshot=lambda **kwargs: [self.job])
        with patch.object(self.hardware, "profiles", return_value=[]):
            boot = snapshot(studio, "qemu")
        self.assertEqual(boot["lines"][-1], "[ OK ] Started ssh.service - OpenBSD Secure Shell server.")
        self.assertEqual(self.job["lines"][-3], dirty)
        observe(self.hardware, self.job, "[emulator] Linux SSH ready.")
        self.assertEqual(self.job["guest_stage"], 6)

    def test_platform_layers_and_app_receipts_use_the_reporting_component(self):
        self.job["phase"] = "run"
        for line in ("CFE_PSP: Default CPU ID = 1", "CFE_PSP: Default Reset SubType = 1",
                     "OS_Posix_TaskAPI_Impl_Init():401:Selected policy 2"):
            observe(self.hardware, self.job, line)
        self.assertEqual(self.job["flight"]["platform_layers"], ["psp", "osal"])
        self.assertEqual([e["fact"]["layer"] for e in self.job["boot_trace"]], ["psp", "osal"])
        unrelated = "EVS Port1 1980-012-14:03:20.65432 66/1/MD 7: Dwell Tables Recovered: 0, Dwell Tables Initialized: 4"
        confirmation = "EVS Port1 1980-012-14:03:20.65464 66/1/MD 1: MD Initialized."
        for line in (unrelated, confirmation):
            observe(self.hardware, self.job, line)
        self.assertEqual(self.job["flight"]["initialized"]["MD"]["eid"], 1)

        legacy = {**self.job, "boot_apps": [], "lines": [unrelated, confirmation],
                  "boot_trace": [{"ms": 5, "line": unrelated, "fact": {"app": "MD", "eid": 7}}]}
        studio = SimpleNamespace(hardware=self.hardware, jobs_snapshot=lambda **kwargs: [legacy])
        with patch.object(self.hardware, "profiles", return_value=[]):
            corrected = snapshot(studio, "native")
            self.assertNotIn("fact", corrected["trace"][0])
            self.assertEqual(corrected["flight"]["initialized"]["MD"]["eid"], 1)
            legacy["lines"] = []
            self.assertNotIn("MD", snapshot(studio, "native")["flight"]["initialized"])
        self.assertEqual(legacy["boot_trace"][0]["fact"]["eid"], 7)

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
        h.state.write("deployed.json", {"native": {"pid": 42, "deployed_at": 1}})
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
                    h.state.write("connection.json", connection)
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

    def test_reopened_studio_follows_only_the_confirmed_invocation(self):
        from interface.server import Studio

        studio = Studio(self.hardware.root)
        self.addCleanup(studio.close)
        h = studio.hardware
        instance = "a" * 32
        h.state.write("target.json", {"target": "qemu"})
        h.state.write("operational-qemu.json", {"time": 5, "target": "qemu", "instance": instance, "apps": [],
                  "boot_trace": [], "flight": {"states": ["OPERATIONAL"], "initialized": {}}})
        h.state.write("deployed.json", {"qemu": {"deployed_at": 3}})
        confirmed = {"running": True, "service": "active", "pids": [71], "instance": instance}
        received = threading.Event()
        stopped = threading.Event()

        def journal_only(action, emit, *, cancel, target, kind, on_start, on_invocation):
            self.assertEqual((action, target, kind), ("logs", "qemu", "current-flight"))
            on_invocation(instance)
            emit("EVS Port1 1980-012 66/1/MD 1: MD Initialized.")
            for i in range(400):
                emit(f"journal row {i}")
            received.set()
            cancel.wait(5)
            stopped.set()

        def read():
            return snapshot(studio, "qemu", journal=studio.boot_journal_snapshot)

        with patch.object(h, "profiles", return_value=[]), patch.object(h, "observed_flight", return_value=confirmed) as probe, \
             patch.object(h, "execute", side_effect=journal_only) as execute:
            self.assertTrue(read()["running"])
            self.assertEqual(studio.jobs_snapshot(), [])
            execute.assert_not_called()
            studio.job("logs", {"target": "qemu", "kind": "current-flight"})
            self.assertTrue(received.wait(2))
            for _ in range(3):
                boot = read()
                self.assertEqual(boot["flight"]["initialized"]["MD"]["eid"], 1)
                self.assertEqual((len(boot["lines"]), boot["lines"][-1]), (300, "journal row 399"))
                self.assertEqual(boot["trace"], [])
            execute.assert_called_once()
            probe.return_value = dict(confirmed, instance="b" * 32)
            superseded = read()
            self.assertFalse(superseded["running"])
            self.assertEqual(superseded["lines"], [])
            self.assertNotIn("MD", superseded["flight"]["initialized"])
            self.assertFalse(stopped.is_set())
            studio.close()
            self.assertTrue(stopped.is_set())
            execute.assert_called_once()

    def test_journal_rechecks_invocation_after_the_live_probe(self):
        from interface.server import Studio

        studio = Studio(self.hardware.root)
        self.addCleanup(studio.close)
        h = studio.hardware
        h.state.write("target.json", {"target": "qemu"})
        h.state.write("operational-qemu.json", {"instance": "a" * 32})
        current = {"instance": "a" * 32, "service": "active"}
        with patch.object(h, "observed_flight", return_value=current), patch.object(h, "ssh_argv", return_value=["ssh", "guest"]), \
             patch.object(h, "_capture", return_value=(0, "b" * 32)), patch.object(h, "_stream") as open_journal:
            studio.job("logs", {"target": "qemu", "kind": "current-flight"})
            reader, = list(studio.jobs.values())
            reader["thread"].join(2)
            self.assertEqual(reader["status"], "failed")
            self.assertIn("invocation changed", reader["error"])
            studio.job("logs", {"target": "qemu", "kind": "current-flight"})
            self.assertEqual(len(studio.jobs), 1)
            open_journal.assert_not_called()

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
