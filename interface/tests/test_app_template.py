"""Source ownership and migration of sample_app-derived flight applications."""
from pathlib import Path
import tempfile
import unittest

from project.appgen import appgen
from project.appgen.source_tags import annotations, region, update, without_markers


class SourceTagTest(unittest.TestCase):
    def test_editor_tags_ignore_literals_and_report_real_lines(self):
        source = r'''const char *text = "/** @brief not a comment */";
/**
 * \brief Read the latest sample
 * @check only accept a complete packet
 */
int value; /**< @unit m/s² @range -12..12 */
'''
        self.assertEqual(annotations(source), [
            {"tag": "brief", "value": "Read the latest sample", "line": 3},
            {"tag": "check", "value": "only accept a complete packet", "line": 4},
            {"tag": "unit", "value": "m/s²", "line": 6},
            {"tag": "range", "value": "-12..12", "line": 6},
        ])

    def test_changed_duplicate_and_missing_sections_are_never_overwritten(self):
        old = region("sensor.endpoint", "old\n")
        new = region("sensor.endpoint", "new\n")
        for working in (old + old, old.replace("old", "manual"), old.replace("@studio.end", "@studio.was")):
            with self.subTest(working=working), self.assertRaisesRegex(ValueError, "reader.c"):
                update(working, new, "reader.c", lambda: old)

    def test_migrating_legacy_sources_preserves_independent_user_changes(self):
        before = "void original(void);\n\nint x;\nint y;\nint z;\n"
        old = before + region("app.subscribe", "subscribe(1);\n") + "return;\n"
        new = old.replace(region("app.subscribe", "subscribe(1);\n"), region("app.subscribe", "subscribe(2);\n"))
        current = without_markers(old).replace("original", "custom")
        self.assertEqual(update(current, new, "main.c", lambda: old), new.replace("original", "custom"))
        with self.assertRaisesRegex(ValueError, "main.c"):
            update(current.replace("subscribe(1)", "custom_hook()"), new, "main.c", lambda: old)


class AppTemplateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "mission"
        self.root.mkdir()
        checkout = self.root.parent / "cFS/apps/sample_app"
        fixtures = {
            "CMakeLists.txt": "set(APP_SRC_FILES fsw/src/sample_app.c)\n# Create the app module\nadd_cfe_app(sample_app ${APP_SRC_FILES})\n# Add table\n",
            "fsw/src/sample_app.c": '#include "sample_app.h"\nint unrelated(void) { return status; }\nint SAMPLE_APP_Init(void)\n{\n  return   status;\n}\n',
            "fsw/src/sample_app_dispatch.c": '#include "sample_app.h"\nvoid SAMPLE_APP_ProcessGroundCommand(void)\n{\n    switch (cc) {\n       default : break;\n    }\n}\nvoid SAMPLE_APP_TaskPipe(void)\n{\n    if (hk) {}\n    else if ( CFE_SB_MsgId_Equal( MsgId, CMD_MID ) ) {}\n}\n',
            "fsw/inc/sample_app_fcncodes.h": "#define SAMPLE_APP_NOOP_CC 0\n#endif\n",
            "fsw/inc/sample_app_eventids.h": "#define SAMPLE_APP_INIT_EID 0\n#endif\n",
        }
        for relative, source in fixtures.items():
            path = checkout / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        self.upstream = {path: path.read_text() for path in checkout.rglob("*") if path.is_file()}
        self.manifest = appgen.new_app("weather", [])
        self.sync()

    def sync(self):
        files = appgen.planned_files(self.root, [self.manifest], libraries=[])
        appgen.write_files(self.root, files)

    def test_custom_command_updates_only_its_scoped_hooks(self):
        driver = self.root / "apps/weather/fsw/src/weather_dispatch.c"
        source = driver.read_text()
        driver.write_text("/* custom logging */\n" + source.replace("if (hk)", "if (check_hk())"))
        self.manifest["commands"].append({"name": "calibrate", "code": 4})
        self.sync()
        active = driver.read_text()
        self.assertTrue(active.startswith("/* custom logging */"))
        self.assertIn("if (check_hk())", active)
        self.assertEqual(active.count("case WEATHER_CALIBRATE_CC:"), 1)
        handler = self.root / "apps/weather/fsw/src/commands/weather_calibrate_cmd.c"
        handler.write_text(handler.read_text().replace("return CFE_STATUS_NOT_IMPLEMENTED", "return CFE_SUCCESS"))
        self.sync()
        self.assertEqual(active, driver.read_text())
        self.assertIn("return CFE_SUCCESS", handler.read_text())
        locations = appgen.locations(self.root, self.manifest)["locations"]
        item = next(loc for loc in locations if loc["id"] == "command.calibrate")
        self.assertEqual((self.root / item["path"]).read_text().splitlines()[item["line"] - 1].strip(), "(void)Msg;")
        self.assertEqual(self.upstream, {path: path.read_text() for path in self.upstream})

    def test_ambiguous_region_cancels_plan_before_new_files_are_written(self):
        path = self.root / "apps/weather/fsw/src/weather_dispatch.c"
        original = path.read_text()
        path.write_text(original.replace("/* @studio.end dispatch.commands */", "/* @studio.end other */"))
        self.manifest["commands"].append({"name": "calibrate", "code": 4})
        with self.assertRaisesRegex(appgen.AppgenError, "dispatch.c"):
            self.sync()
        self.assertFalse((path.parent / "commands/weather_calibrate_cmd.c").exists())


if __name__ == "__main__":
    unittest.main()
