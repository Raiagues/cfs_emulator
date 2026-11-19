"""Regression for navigation in a mission app copied from NASA's sample_app."""
import tempfile
import unittest
from pathlib import Path

from project.appgen.appgen import AppgenError, locations


class AppLocationsTest(unittest.TestCase):
    def test_only_the_compiled_dispatch_contributes_a_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "apps/weather"
            handler = "void WEATHER_TaskPipe(void)\n{\n}\n"
            for source in ("fsw/src/weather_dispatch.c", "fsw/src/weather_eds_dispatch.c",
                           "unit-test/stubs/weather_dispatch_stubs.c"):
                path = app / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(handler)

            result = locations(root, {"name": "weather"})["locations"]
            self.assertEqual([(item["id"], item["path"]) for item in result],
                             [("app.dispatch", "apps/weather/fsw/src/weather_dispatch.c")])

            (app / "fsw/src/other.c").write_text(handler)
            with self.assertRaisesRegex(AppgenError, r"Duplicate editable location marker: app\.dispatch"):
                locations(root, {"name": "weather"})
