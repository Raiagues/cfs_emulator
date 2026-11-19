"""Public HTTP lifecycle against an isolated copy of the NASA checkout installed in Setup."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from interface.server import Handler, Studio
from project.flight_sources import prepare_mission


ROOT = Path(__file__).resolve().parents[2]
NASA = ROOT / "cFS"
HAS_SAMPLE = (NASA / "apps/sample_app/fsw/src/sample_app.c").is_file()


class WorkspaceRoutingTest(unittest.TestCase):
    def test_deep_link_reaches_setup_before_checkout_and_workspace_afterwards(self):
        with tempfile.TemporaryDirectory() as root, ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            server.studio = Mock()
            server.studio.workspace.root = Path(root)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                workspace = base + "/studio?target=qemu"
                with urlopen(workspace) as setup:
                    self.assertEqual(setup.geturl(), base + "/?target=qemu#target")
                    self.assertIn(b'id="infrastructure-form"', setup.read())
                with patch("hardware.infrastructure.sources_ready", return_value=True), urlopen(workspace) as studio:
                    self.assertEqual(studio.geturl(), workspace)
                    self.assertIn(b'id="studio"', studio.read())
            finally:
                server.shutdown()
                worker.join()


@unittest.skipUnless(HAS_SAMPLE, "Install NASA cFS from workspace setup to exercise the mission HTTP lifecycle")
class WorkspaceHTTPTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="studio-http-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        ignore = shutil.ignore_patterns(".git", "__pycache__", ".runtime", ".state", "build-native", "build-flight")
        for directory in ("cFS", "project", "scripts", "sensors", "interface", "hardware", "ground_station"):
            shutil.copytree(ROOT / directory, self.root / directory, symlinks=True, ignore=ignore)
        shutil.copy2(ROOT / "Dockerfile", self.root / "Dockerfile")
        # Start from a new mission even if the developer has an active mission here.
        for relative in ("project/apps", "project/generated"):
            directory = self.root / relative
            if directory.exists():
                shutil.rmtree(directory)
        config = {"schema_version": 1, "board": "raspi4b", "os": "raspios", "devices": [], "apps": []}
        (self.root / "project/config.json").write_text(json.dumps(config))
        prepare_mission(self.root)
        old_path, bytecode = list(sys.path), sys.dont_write_bytecode
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        self.addCleanup(setattr, sys, "dont_write_bytecode", bytecode)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        server.studio = Studio(self.root)
        self.addCleanup(server.studio.close)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}/api/"
        self.token = ""
        self.token = self.api("session")["token"]

    def api(self, endpoint, body=None, status=200):
        request = Request(self.base + endpoint, json.dumps(body).encode() if body is not None else None,
                          {"Content-Type": "application/json", "X-Studio-Token": self.token})
        try:
            response = urlopen(request, timeout=120)
        except HTTPError as error:
            response = error
        with response:
            payload = json.load(response)
            self.assertEqual(response.status, status, f"{endpoint}: {payload.get('error', '')}")
        return payload

    def file(self, path):
        return self.api("file?" + urlencode({"path": path}))

    def mutate(self, action, **values):
        return self.api("mutate", {"action": action, "payload": values})

    def create(self, kind, name, revision):
        body = {"kind": kind, "name": name, "settings": {}, "expected_hash": revision}
        preview = self.api("mission/draft", body)
        self.assertIn(name, preview["preview"]["entry_point"].lower())
        return self.api("mission/save", {**body, "plan_hash": preview["plan_hash"]})["mission"]

    def test_bus_and_optional_hal_lifecycle(self):
        workspace = self.api("workspace")
        bus = "i2c-bus.1"
        self.assertIn(bus, workspace["catalog"]["available_buses"])
        self.assertEqual(workspace["catalog"]["buses"], {})
        sensor = {"id": "probe", "model": "tmp105", "bus": bus, "address": "0x48"}
        rejected = self.api("mutate", {"action": "add-device", "payload": sensor}, 400)
        self.assertIn("Add a bus", rejected["error"])
        self.mutate("add-bus", bus=bus)
        self.mutate("add-device", **sensor)
        self.assertFalse((self.root / "mission/libs/hal_sensor").exists())
        self.api("mutate", {"action": "remove-bus", "payload": {"bus": bus}}, 400)
        endpoint = "hardware/device?id=probe"
        current = self.api(endpoint)
        pins = {"VCC": 17, "GND": 14, "SDA": 3, "SCL": 5}
        settings = {"id": "probe", "bus": bus, "address": 72, "expected_hash": current["source"]["hash"]}
        self.api("hardware/device", {**settings, "pins": dict(pins, SDA=4)}, 400)
        self.api("hardware/device", {**settings, "pins": pins})
        self.assertEqual(self.api(endpoint)["device"]["pins"], pins)
        args = {"app": "science", "device": "probe", "name": "temp", "new_app": True}
        self.api("mutate", {"action": "link-hal", "payload": dict(args, device="absent")}, 400)
        self.assertFalse((self.root / "mission/apps/science").exists())
        self.mutate("link-hal", **args)
        self.assertTrue((self.root / "mission/libs/hal_sensor").exists())
        workspace = self.api("workspace")
        self.assertIn("science", workspace["mission"]["enabled"])
        self.assertEqual(workspace["project"]["apps"][0]["sensors"], {"temp": "probe"})
        self.assertTrue((self.root / "mission/apps/science/fsw/src/sensors/science_temp_sensor.c").is_file())
        self.mutate("remove-sensor", app="science", name="temp")
        self.mutate("link-hal", **dict(args, name="another", new_app=False))
        self.mutate("remove-sensor", app="science", name="another")
        self.mutate("remove-device", id="probe")
        self.mutate("remove-bus", bus=bus)
        self.assertEqual(self.api("workspace")["project"]["buses"], [])

    def test_app_library_device_sensor_and_source_lifecycle(self):
        snapshot = self.api("workspace")
        self.assertFalse(snapshot["builds"]["native"]["stale"])
        initial = snapshot["mission"]["source"]["hash"]
        self.assertIn("sample_app", snapshot["mission"]["included"])
        with patch("hardware.manager.HardwareManager._qemu_running", return_value=True):
            error = self.api("mission/profile", {"board": None, "os": None, "expected_hash": initial}, 400)
        self.assertIn("Stop QEMU", error["error"])
        upstream_path = "cFS/apps/sample_app/fsw/src/sample_app.c"
        nasa = self.file(upstream_path)
        self.assertFalse(nasa["editable"])
        self.api("file", {"path": upstream_path, "expected_hash": nasa["hash"], "content": "changed"}, 400)

        mission = self.create("app", "weather", initial)
        # Old mission revisions must not create, rename or remove a newer mission.
        lib = {"kind": "library", "name": "cal_lib", "settings": {}}
        self.api("mission/draft", {**lib, "expected_hash": initial}, 400)
        mission = self.create("library", "cal_lib", mission["source"]["hash"])
        lib_name = {"kind": "library", "name": "cal_lib", "new_name": "bench_lib"}
        self.api("mission/rename", {**lib_name, "expected_hash": initial}, 400)
        mission = self.api("mission/rename", {**lib_name, "expected_hash": mission["source"]["hash"]})["mission"]
        self.assertIn("bench_lib", [item["name"] for item in mission["libraries"]])
        self.assertNotIn("cal_lib", [item["name"] for item in mission["libraries"]])

        self.mutate("add-bus", bus="i2c-bus.1")
        device_revision = self.api("workspace")["mission"]["source"]["hash"]
        self.api("mutate", {"action": "add-device", "payload": {"id": "test_probe", "model": "tmp105", "address": 72},
                            "expected_hash": device_revision})
        stale = self.api("mutate", {"action": "remove-device", "payload": {"id": "test_probe"},
                                    "expected_hash": mission["source"]["hash"]}, 400)
        self.assertIn("changed", stale["error"])
        self.mutate("add-sensor", app="weather", name="temperature", device="test_probe")
        self.mutate("add-command", app="weather", name="calibrate")
        self.mutate("add-telemetry", app="weather", name="latest")
        cfg = self.file("mission/apps/weather/fsw/src/sensors/weather_temperature_sensor.h")
        tags = {item["tag"]: item["value"] for item in cfg["annotations"]}
        self.assertEqual(tags["unit"], "millidegrees Celsius")
        self.assertEqual(tags["range"], "-128000..127937")
        handler = self.file("mission/apps/weather/fsw/src/commands/weather_calibrate_cmd.c")
        self.assertIn("brief", [item["tag"] for item in handler["annotations"]])
        reader = self.file("mission/apps/weather/fsw/src/sensors/weather_temperature_sensor.c")
        self.assertIn("check", [item["tag"] for item in reader["annotations"]])
        # Only the managed section of this source changes when another command is added.
        dispatch = self.file("mission/apps/weather/fsw/src/weather_dispatch.c")
        revision = self.api("workspace")["mission"]["source"]["hash"]
        edit = {"kind": "app", "mode": "edit", "name": "weather", "settings": {}, "expected_hash": revision}
        draft = self.api("mission/draft", edit)
        custom = "/** @brief Dispatch local commands. */\n" + dispatch["content"]
        body = {"path": dispatch["path"], "content": custom, "expected_hash": dispatch["hash"]}
        self.api("file", body)
        self.api("file", {**body, "content": "stale"}, 400)
        stale_plan = self.api("mission/save", {**edit, "plan_hash": draft["plan_hash"]}, 400)
        self.assertIn("changed", stale_plan["error"])
        self.mutate("add-command", app="weather", name="set_rate")
        current = self.file(dispatch["path"])
        self.assertTrue(current["content"].startswith("/** @brief Dispatch local commands. */"))
        self.assertIn("case WEATHER_SET_RATE_CC:", current["content"])

        snapshot = self.api("workspace")
        revision = snapshot["mission"]["source"]["hash"]
        weather = next(app for app in snapshot["apps"] if app["name"] == "weather")
        location = next(item for item in weather["locations"] if item["id"] == "sensor.temperature.read")
        self.assertIn("_Acquire", self.file(location["path"])["content"].splitlines()[location["line"] - 1])
        name = {"kind": "app", "name": "weather", "new_name": "station", "expected_hash": revision}
        self.api("mission/rename", name)
        renamed = self.file(dispatch["path"].replace("weather", "station"))
        self.assertTrue(renamed["content"].startswith("/** @brief Dispatch local commands. */"))
        self.assertIn("case STATION_SET_RATE_CC:", renamed["content"])
        for kind, component in (("telemetry", "latest"), ("command", "calibrate"),
                                ("command", "set_rate"), ("sensor", "temperature")):
            self.mutate("remove-" + kind, app="station", name=component)
        self.mutate("remove-device", id="test_probe")
        snapshot = self.api("workspace")
        self.assertEqual(snapshot["project"]["devices"], [])
        revision = snapshot["mission"]["source"]["hash"]
        mission = self.api("mission/app", {"action": "remove", "name": "station", "expected_hash": revision})["mission"]
        self.assertNotIn("station", mission["included"])
        source = self.file("mission/apps/station/fsw/src/station.c")
        delete = {"action": "delete", "name": "station", "expected_hash": mission["source"]["hash"]}
        self.api("mission/app", {**delete, "expected_hash": initial}, 400)
        self.assertIn("project-created", self.api("mission/app", {**delete, "name": "sample_app"}, 400)["error"])
        consumer = self.file("mission/libs/bench_lib/fsw/src/bench_lib.c")
        self.api("file", {"path": consumer["path"], "expected_hash": consumer["hash"],
                          "content": '#include "station.h"\n' + consumer["content"]})
        self.assertIn("references station", self.api("mission/app", delete, 400)["error"])
        self.api("file", {"path": consumer["path"], "expected_hash": self.file(consumer["path"])["hash"],
                          "content": consumer["content"]})
        with patch("project.manage.commit", side_effect=ValueError("fixture write error")):
            self.assertIn("fixture write error", self.api("mission/app", delete, 400)["error"])
        self.assertEqual(self.file(source["path"])["hash"], source["hash"])
        mission = self.api("mission/app", delete)["mission"]
        for relative in ("project/apps/station.json", "mission/apps/station"):
            self.assertFalse((self.root / relative).exists())
        self.assertNotIn("station", self.file("mission/cpu1_cfe_es_startup.scr")["content"])
        mission = self.create("app", "station", mission["source"]["hash"])
        self.mutate("add-device", id="second_probe", model="tmp105", address=73)
        self.mutate("add-sensor", app="station", name="temp", device="second_probe")
        revision = self.api("workspace")["mission"]["source"]["hash"]
        mission = self.api("mission/app", {"action": "delete", "name": "station", "expected_hash": revision})["mission"]
        self.assertNotIn("station", mission["included"])
        config = json.loads(self.file("project/config.json")["content"])
        self.assertEqual(config["apps"], [])
        self.assertEqual([device["id"] for device in config["devices"]], ["second_probe"])
        mission = self.api("mission/library", {"action": "delete", "name": "bench_lib",
                                                "expected_hash": mission["source"]["hash"]})["mission"]
        self.assertNotIn("bench_lib", [item["name"] for item in mission["libraries"]])
        self.assertFalse((self.root / "mission/libs/bench_lib").exists())
        self.assertIn("sample_app", mission["included"])
        self.assertEqual(self.file(upstream_path)["hash"], nasa["hash"])
