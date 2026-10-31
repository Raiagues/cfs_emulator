"""Project mutations are exercised exclusively in temporary source trees."""

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import manage
import model


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = PROJECT.parent
        for relative in ("cFS/tools/appgen", "cFS/apps/thermal_app", "cFS/sample_defs/generated"):
            shutil.copytree(source / relative, self.root / relative, ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "project").mkdir()
        shutil.copy2(PROJECT / "config.json", self.root / "project/config.json")
        shutil.copy2(source / "cFS/.gitmodules", self.root / "cFS/.gitmodules")

    def run_cli(self, *arguments):
        return manage.run(manage.parser().parse_args(["--root", str(self.root), *arguments]))

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()}

    def write_config(self, config):
        (self.root / "project/config.json").write_text(json.dumps(config, indent=2) + "\n")

    def test_current_check_is_read_only(self):
        before = self.snapshot()
        result, code = self.run_cli("check")
        self.assertEqual((result["changed"], code), ([], 0))
        self.assertEqual(before, self.snapshot())

    def test_app_command_sensor_and_functional_telemetry(self):
        self.run_cli("add-app", "science_app")
        self.run_cli("add-device", "Second temperature", "--id", "second_temp", "--model", "tmp105", "--address", "0x49")
        self.run_cli("add-sensor", "science_app", "board_temp", "--device", "second_temp")
        self.run_cli("add-command", "science_app", "set_mode")
        self.run_cli("add-telemetry", "science_app", "temperature", "--sensor", "board_temp")
        manifest = json.loads((self.root / "cFS/apps/science_app/app.json").read_text())
        self.assertEqual(manifest["commands"], [{"name": "set_mode", "code": 2}])
        self.assertEqual(manifest["sensors"][0]["address"], 0x49)
        packet = self.root / "cFS/apps/science_app/fsw/src/telemetry/science_app_temperature_tlm.c"
        self.assertIn("*Payload = *SCIENCE_APP_BoardTemp_GetData();", packet.read_text())
        packet.write_text(packet.read_text() + "\n/* user extension */\n")
        self.run_cli("sync")
        self.assertTrue(packet.read_text().endswith("/* user extension */\n"))
        self.assertEqual(self.run_cli("check")[1], 0)
        result, code = self.run_cli("locate", "science_app")
        self.assertTrue(any(item["id"] == "command.set_mode" for item in result["locations"]))

    def test_stock_app_protection_even_with_fake_manifest(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Protected app"):
            self.run_cli("add-app", "sample_app")
        self.assertEqual(before, self.snapshot())
        stock = self.root / "cFS/apps/sample_app"
        stock.mkdir()
        manifest = json.loads((self.root / "cFS/apps/thermal_app/app.json").read_text())
        manifest["name"] = "sample_app"
        (stock / "app.json").write_text(json.dumps(manifest))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Protected or unregistered app"):
            self.run_cli("sync")
        self.assertEqual(before, self.snapshot())
        config = model.load_config(self.root)
        config["apps"].append({"name": "sample_app", "sensors": {}, "telemetry_bindings": {}, "command_bindings": {}})
        self.write_config(config)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Protected or duplicate app"):
            self.run_cli("sync")
        self.assertEqual(before, self.snapshot())

    def test_invalid_devices_and_collisions_leave_no_changes(self):
        for arguments in (
            ("--id", "other", "--model", "unknown", "--address", "0x49"),
            ("--id", "other", "--model", "tmp105", "--bus", "wrong", "--address", "0x49"),
            ("--id", "other", "--model", "tmp105", "--address", "0x48"),
            ("--id", "tmp105", "--model", "tmp105", "--address", "0x49"),
            ("--id", "other", "--model", "tmp105", "--address", "0x80"),
        ):
            with self.subTest(arguments=arguments):
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.run_cli("add-device", "Another", *arguments)
                self.assertEqual(before, self.snapshot())

    def test_paths_and_unregistered_apps_are_protected(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.run_cli("add-app", "../../escape")
        (self.root / "cFS/apps/linked_app").symlink_to(self.root / "cFS/apps/thermal_app", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.run_cli("sync")
        (self.root / "cFS/apps/linked_app").unlink()
        config = model.load_config(self.root)
        config["apps"] = []
        self.write_config(config)
        with self.assertRaisesRegex(ValueError, "unregistered"):
            self.run_cli("sync")

    def test_invalid_bindings_and_unsupported_driver_do_not_mutate(self):
        self.run_cli("add-device", "Magnetometer", "--id", "mag", "--model", "lsm303dlhc_mag", "--address", "0x1e")
        for arguments in (
            ("add-sensor", "thermal_app", "magnetic", "--device", "mag"),
            ("add-telemetry", "thermal_app", "status", "--sensor", "missing"),
            ("add-command", "thermal_app", "heat", "--actuator", "tmp105"),
        ):
            before = self.snapshot()
            with self.assertRaises(ValueError):
                self.run_cli(*arguments)
            self.assertEqual(before, self.snapshot())

    def test_duplicate_command_code_preserves_every_file(self):
        self.run_cli("add-command", "thermal_app", "set_mode", "--code", "2")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "unique"):
            self.run_cli("add-command", "thermal_app", "set_state", "--code", "2")
        self.assertEqual(before, self.snapshot())

    def test_sync_maps_hardware_and_preserves_user_code(self):
        config = model.load_config(self.root)
        config["devices"][0]["address"] = 0x49
        self.write_config(config)
        user = self.root / "cFS/apps/thermal_app/fsw/src/thermal_app_user.c"
        user.write_text(user.read_text() + "\n/* custom logic */\n")
        before = self.snapshot()
        self.assertEqual(self.run_cli("check")[1], 1)
        self.assertEqual(before, self.snapshot())
        self.run_cli("sync")
        manifest = json.loads((self.root / "cFS/apps/thermal_app/app.json").read_text())
        self.assertEqual(manifest["sensors"][0]["address"], 0x49)
        self.assertTrue(user.read_text().endswith("/* custom logic */\n"))
        self.assertEqual(self.run_cli("check")[1], 0)

    def test_build_stamp_ignores_live_values_but_checks_binding_config(self):
        with self.assertRaisesRegex(ValueError, "build configuration"):
            self.run_cli("check-build")
        payload = self.root / "cFS/build-rpi_linux/exe/cpu1"
        (payload / "cf").mkdir(parents=True)
        (payload / "core-cpu1").write_text("test placeholder")
        self.run_cli("stamp")
        config = model.load_config(self.root)
        config["devices"][0]["values"]["temperature"] = 30000
        self.write_config(config)
        self.assertEqual(self.run_cli("check-build")[1], 0)
        config["devices"][0]["address"] = 0x49
        self.write_config(config)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.run_cli("check-build")

    def test_hardware_validation_needs_no_cfs(self):
        config = model.load_config(self.root)
        shutil.rmtree(self.root / "cFS")
        self.assertEqual(model.load_config(self.root), config)
        changed = copy.deepcopy(config)
        changed["devices"][0]["name"] = "Different label"
        changed["devices"][0]["values"]["temperature"] = 25000
        self.assertEqual(model.topology(config), model.topology(changed))

    def test_failed_replacement_rolls_back_existing_and_new_files(self):
        before = self.snapshot()
        original_replace = Path.replace
        count = 0

        def fail_second(path, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulated write failure")
            return original_replace(path, target)

        with mock.patch.object(Path, "replace", fail_second):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.run_cli("add-app", "science_app")
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / "cFS/apps/science_app").exists())


if __name__ == "__main__":
    unittest.main()
