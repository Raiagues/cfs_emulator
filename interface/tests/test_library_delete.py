"""Deleting local library sources is atomic and preserves archived consumers."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from project.appgen.native_startup import parse_startup
from project.mission_config import MissionConfig


class LibraryDeleteTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for group in ("apps", "libs"):
            (self.root / "cFS" / group).mkdir(parents=True)
        (self.root / "mission/sample_defs").mkdir(parents=True)
        for group in ("apps", "libs"):
            (self.root / "mission" / group).symlink_to("../cFS/" + group, target_is_directory=True)
        self.write("project/config.json", json.dumps({"schema_version": 1, "board": None, "os": None,
                                                       "apps": [], "devices": [], "buses": []}))
        self.source = self.root / "cFS/libs/math"
        self.write("cFS/libs/math/CMakeLists.txt", "add_cfe_app(math fsw/src/math.c)\n")
        self.write("cFS/libs/math/fsw/public_inc/math.h", "int MATH_Read(void);\n")
        self.write("cFS/libs/math/fsw/src/math.c", "int MATH_Read(void) { return 1; }\n")
        self.write("cFS/libs/math/private.bin", b"\x00\x01\xff")
        (self.source / "notes/empty").mkdir(parents=True)
        (self.source / "private.bin").chmod(0o640)
        self.write("cFS/libs/upstream/CMakeLists.txt", "# protected sentinel\n")
        self.write("mission/libraries.cmake", "set(MISSION_LIBRARIES math)\n")
        self.write("mission/sample_defs/targets.cmake", "# mission\n")
        self.write("mission/cpu1_cfe_es_startup.scr", "CFE_LIB, math, MATH_Init, MATH, 0, 0, 0, 0;\n!\n"
                   "CFE_APP, archived, ARCHIVED_Main, ARCHIVED, 50, 32768, 0, 0;\n")
        self.mission = MissionConfig(self.root)
        self.mission._revision = lambda: "revision"
        self.mission._evaluate = lambda revision: {"compiled": ["math"] if self.source.exists() else [],
                                                  "library_roots": ["math"], "default": "", "core": []}
        self.mission.snapshot = lambda: {"compiled": self.mission._evaluate("revision")["compiled"]}
        self.plan = {"mission/libraries.cmake": "set(MISSION_LIBRARIES)\n",
                     self.mission.STARTUP: "!\nCFE_APP, archived, ARCHIVED_Main, ARCHIVED, 50, 32768, 0, 0;\n"}
        limits = patch("project.cfs_config.module_limits_plan", return_value={})
        limits.start(); self.addCleanup(limits.stop)

    def write(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
        return path

    def snapshot(self):
        return {path.relative_to(self.root).as_posix():
                ("link", str(path.readlink())) if path.is_symlink() else
                ("file", path.read_bytes(), path.stat().st_mode & 0o777) if path.is_file() else ("directory",)
                for path in self.root.rglob("*") if ".runtime" not in path.parts}

    def test_delete_removes_empty_directories_binary_files_and_frees_name(self):
        result = self.mission._delete_library("math", self.plan, "revision")
        self.assertFalse(self.source.exists())
        self.assertIn("mission/libs/math/private.bin", result["deleted"])
        self.assertEqual(result["mission"]["compiled"], [])
        self.assertFalse(list((self.root / "cFS/libs").glob(".delete-*")))
        self.assertEqual((self.root / "cFS/libs/upstream/CMakeLists.txt").read_text(), "# protected sentinel\n")
        evaluated = {"compiled": [], "core": []}
        self.mission.available_module_name("math", evaluated)
        self.source.mkdir()
        self.assertTrue(self.source.is_dir())

    def test_failed_validation_restores_sources_empty_directories_and_mission_files(self):
        before = self.snapshot()
        with patch.object(self.mission, "snapshot", side_effect=ValueError("validation failed")):
            with self.assertRaisesRegex(ValueError, "validation failed"):
                self.mission._delete_library("math", self.plan, "revision")
        self.assertEqual(self.snapshot(), before)

    def test_archived_source_dependencies_includes_and_calls_block_delete(self):
        self.write("cFS/apps/archived/CMakeLists.txt", "add_cfe_app(archived fsw/src/archived.c)\n")
        cmake = self.root / "cFS/apps/archived/CMakeLists.txt"
        source = self.write("cFS/apps/archived/fsw/src/archived.c", "int read_value(void) { return 0; }\n")
        original = cmake.read_text()
        for dependency, code in (("add_cfe_app_dependency(archived math)\n", source.read_text()),
                                 ("", '#include "math.h"\nint read_value(void) { return 0; }\n'),
                                 ("", "int read_value(void) { return MATH_Read(); }\n")):
            with self.subTest(dependency=dependency, code=code):
                cmake.write_text(original + dependency); source.write_text(code)
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "depends on math|references math"):
                    self.mission._assert_library_unreferenced("math")
                self.assertEqual(self.snapshot(), before)

    def test_remove_still_archives_library_and_preserves_sources_with_archived_consumer(self):
        self.write("cFS/apps/archived/CMakeLists.txt", "add_cfe_app(archived main.c)\nadd_cfe_app_dependency(archived math)\n")
        active, archived = parse_startup(self.mission.startup_text())
        evaluated = self.mission._evaluate("revision")
        self.mission._read = lambda: ("revision", evaluated, active, archived, [])
        with patch("project.model.planned_project_files", return_value={"mission/sample_defs/generated/appgen_startup.scr": ""}), \
                patch("project.model.read_manifests", return_value=[]):
            self.mission.change_library("remove", "math", "revision")
        self.assertTrue(self.source.is_dir())
        enabled, disabled = parse_startup(self.mission.startup_text())
        self.assertNotIn("math", [entry.name for entry in enabled])
        self.assertIn("math", [entry.name for entry in disabled])


if __name__ == "__main__":
    unittest.main()
