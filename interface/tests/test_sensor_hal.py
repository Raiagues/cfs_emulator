"""The register designer, native app scaffold and flight drivers share one model."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from project.driver_catalog import plan_drivers, requirements
from project.manage import commit
from project.model import board_catalog, load_config, validate_hardware
from project.sensor_models import register
from project.qemu.generate import register_models, render
from project.sensor_driver import app_adapter
from project.sensor_models import MODELS, model_paths

ROOT = Path(__file__).resolve().parents[2]


class SensorHalTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in ("drivers", "boards"):
            shutil.copytree(ROOT / "project" / directory, self.root / "project" / directory)
        self.spec = json.loads((self.root / "project/drivers/templates/model.json").read_text())

    def test_legacy_mission_adopts_only_buses_with_devices(self):
        path = self.root / "project/config.json"
        legacy = dict(schema_version=1, board="raspi4b", os="raspios", devices=[], apps=[])
        path.write_text(json.dumps(legacy))
        self.assertEqual(load_config(self.root)["buses"], [])
        probe = dict(id="probe", name="TMP105", model="tmp105", bus="i2c-bus.1", address=72, values={})
        legacy["devices"].append(probe)
        path.write_text(json.dumps(legacy))
        self.assertEqual(load_config(self.root)["buses"], ["i2c-bus.1"])
        self.assertEqual(json.loads(path.read_text()), legacy)
        with self.assertRaisesRegex(ValueError, "Add the bus"):
            validate_hardware(dict(legacy, buses=[]), self.root)

    @unittest.skipUnless(all(shutil.which(name) for name in ("dtc", "fdtput", "fdtget")), "device tree tools")
    def test_guest_bus_configuration_follows_the_selected_project(self):
        from sensors.runtime import boot_hardware, check_record
        board = self.root / "board"
        board.mkdir()
        bus_node = "/soc/i2c@7e804000"
        base = board / "bcm2711-rpi-4-b.dtb"
        subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(base), "-"],
                       input='/dts-v1/; / {soc { i2c@7e804000 {status = "okay";};};};', text=True, check=True)
        config = dict(schema_version=1, board="raspi4b", os="raspios", devices=[], apps=[], buses=[])
        with patch("sensors.runtime.qemu_models", return_value={}):
            for enabled in (False, True, False):
                config["buses"] = ["i2c-bus.1"] if enabled else []
                if (board / "hardware.json").exists():
                    with self.assertRaisesRegex(ValueError, "Project hardware differs"):
                        check_record(self.root, config)
                self.assertEqual(boot_hardware(self.root, config), [])
                check_record(self.root, config)
                status = subprocess.check_output(["fdtget", str(board / "mission.dtb"), bus_node, "status"], text=True).strip()
                self.assertEqual(status, "okay" if enabled else "disabled")
        self.assertEqual(subprocess.check_output(["fdtget", str(base), bus_node, "status"], text=True).strip(), "okay")

    def test_register_once_and_reuse_in_all_consumers(self):
        result = register(self.root, self.spec)
        self.assertEqual(set(result["changed"]), {str(MODELS / "lab_sensor/model.json"), "sensors/lab_sensor.py"})
        with self.assertRaises(ValueError):
            register(self.root, self.spec)
        self.assertIn("lab_sensor", register_models(self.root))
        self.assertNotIn("tmp105", register_models(self.root))
        self.assertIn('"temperature", 16,', render(self.spec))
        model = board_catalog("raspi4b", self.root)["models"]["lab_sensor"]
        device = dict(id="temp", name="payload", model="lab_sensor", bus="i2c-bus.1", address=72, values=model["default_values"])
        config = dict(schema_version=1, board="raspi4b", os="raspios", devices=[device], apps=[])
        (self.root / "project/config.json").write_text(json.dumps(config))
        validate_hardware(config, self.root)
        self.assertEqual(requirements(self.root, config)[0], [])
        flight_config = dict(config, apps=[{"name": "science", "sensors": {"reading": "temp"}}])
        libraries, _ = requirements(self.root, flight_config)
        self.assertEqual([lib["name"] for lib in libraries], ["linux_i2c_lib", "hal_sensor", "lab_sensor_lib"])
        self.assertIn("LAB_SENSOR_Acquire", app_adapter(self.root, "lab_sensor")["tokens"]["READ_VALUE"])
        from sensors.simulator import load_waveform, configuration
        waveform = load_waveform(self.root, "lab_sensor")
        signals = configuration(waveform, device, self.root).signals
        self.assertEqual([(s.property, s.unit, s.scale) for s in signals], [("temperature", "°C", 1000)])
        commit(self.root, plan_drivers(self.root, libraries))
        self.assertNotIn("linux_i2c_lib", (self.root / "mission/libs/lab_sensor_lib/CMakeLists.txt").read_text())
        self.assertFalse(commit(self.root, plan_drivers(self.root, libraries), check=True))
        self.assertFalse((self.root / "cFS").exists())
        with self.assertRaises(ValueError):
            register(self.root, {**self.spec, "name": "lab_bad", "id_register": 16})
        self.assertNotIn("lab_bad", model_paths(self.root))

    def test_register_transactions_and_legacy_flight_abi(self):
        register(self.root, self.spec)
        templates = self.root / "project/drivers/templates"
        byte_model = json.loads((templates / "custom-model.json").read_text())
        with self.assertRaisesRegex(ValueError, "driver.c"):
            register(self.root, byte_model)
        register(self.root, byte_model, driver=(templates / "driver.c.example").read_text())
        self.assertNotIn("lab_byte", register_models(self.root))
        register(self.root, {**self.spec, "name": "lab_cal"})
        model_dir = self.root / MODELS / "lab_cal"
        adapter_before = app_adapter(self.root, "lab_cal")["tokens"]
        (model_dir / "state.h").write_text("typedef struct { int32_t Count; } LAB_CAL_State_t;\n")
        (model_dir / "driver.c").write_text('''#include "lab_cal_lib.h"
static int32_t Count(const HAL_SENSOR_Device_t *device, int32_t *values)
{
    LAB_CAL_State_t *state = device->DriverContext;
    values[0] = ++state->Count;
    return 0;
}
const HAL_SENSOR_Ops_t LAB_CAL_Ops = {.Read = Count};
''')
        self.assertEqual(app_adapter(self.root, "lab_cal")["tokens"], adapter_before)
        names = ["hal_sensor", "linux_i2c_lib"] + [name + "_lib" for name in model_paths(self.root)]
        commit(self.root, plan_drivers(self.root, [{"name": name} for name in names]))
        # The HAL and generated flight sources compile against the cFE integer
        # ABI. Only Linux I/O is replaced with the deterministic test endpoint.
        (self.root / "cfe.h").write_text(
            '#pragma once\n#include <stdint.h>\n#include <stdbool.h>\n'
            'typedef int32_t int32; typedef uint8_t uint8; typedef uint16_t uint16;\n'
            '#define CFE_SUCCESS 0\n#define OS_printf(...) ((void)0)\n')
        libs = self.root / "mission/libs"
        includes = ["-I" + str(libs / name / "fsw/public_inc") for name in names]
        sources = [str(p) for name in names if name != "linux_i2c_lib" for p in (libs / name / "fsw/src").glob("*.c")]
        binary = self.root / "check"
        subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-I" + str(self.root),
                        *includes, *sources, str(Path(__file__).with_name("hal_sensor_check.c")), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

    def test_migration_distinguishes_pristine_and_edited_driver_sources(self):
        name = "tmp105_lib"
        original = {"CMakeLists.txt": "add_cfe_app_dependency(tmp105_lib linux_i2c_lib)\n",
                    "fsw/src/tmp105_lib.c": "/* previous generator */\n",
                    "fsw/src/obsolete.h": "/* old private header */\n"}
        state = {key: hashlib.sha256(contents.encode()).hexdigest() for key, contents in original.items()}
        files = {f"mission/libs/{name}/{key}": contents for key, contents in original.items()}
        files["project/generated/drivers.json"] = json.dumps({"modules": {name: state}, "retained": {}})
        commit(self.root, files)
        source = self.root / "mission/libs/tmp105_lib/fsw/src/tmp105_lib.c"
        source.write_text("/* locally maintained implementation */\n")
        modules = [{"name": name}]
        commit(self.root, plan_drivers(self.root, modules))
        tokens = app_adapter(self.root, "tmp105")["tokens"]
        self.assertIn("TMP105_LIB_ReadTemperature", tokens["READ_VALUE"])
        self.assertTrue(source.with_name("obsolete.h").exists())
        self.assertIn("locally maintained", source.read_text())
        source.write_text(original["fsw/src/tmp105_lib.c"])
        commit(self.root, plan_drivers(self.root, modules))
        self.assertFalse(source.with_name("obsolete.h").exists())
        self.assertIn("TMP105_Acquire", source.read_text())


if __name__ == "__main__":
    unittest.main()
