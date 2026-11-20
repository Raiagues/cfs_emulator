"""Installing or editing a Studio mission must leave its NASA checkout intact."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from project.workspace import Workspace
from project.flight_sources import nasa_module_names, prepare_mission
from project.nasa_source import OFFICIAL_URL, install, source_status


class NasaSourceTest(unittest.TestCase):
    def test_readiness_uses_pinned_gitlinks_and_reserves_aliases(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "cFS"
            (source / ".git").mkdir(parents=True)
            (source / "apps/example").mkdir(parents=True)
            (source / "apps/plugin").symlink_to("example")
            (source / "sample_defs").mkdir()
            (source / "sample_defs/targets.cmake").touch()
            (source / ".gitmodules").write_text('[submodule "optional"]\npath = apps/optional\n')
            self.assertEqual(nasa_module_names(root, "apps"), {"example", "plugin", "optional"})
            for marker, expected in ((" ", "ready"), ("-", "incomplete"), ("+", "incomplete")):
                with patch("project.nasa_source._git", side_effect=[OFFICIAL_URL, "abc123", marker + "abc123 apps/example"]):
                    self.assertEqual(source_status(root)["state"], expected)

    def test_mission_definitions_are_independent_and_editor_protects_upstream(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            official = root / "cFS/sample_defs/targets.cmake"
            official.parent.mkdir(parents=True)
            official.write_text("set(MISSION_NAME SampleMission)\n")
            prepare_mission(root)
            local = root / "mission/sample_defs/targets.cmake"
            self.assertIn("generated/appgen.cmake", local.read_text())
            workspace = Workspace(root)
            nasa = workspace.read_file("cFS/sample_defs/targets.cmake")
            self.assertFalse(nasa["editable"])
            with self.assertRaisesRegex(ValueError, "not editable"):
                workspace.write_file(nasa["path"], "changed", nasa["hash"])
            internal = root / "hardware/manager.py"
            internal.parent.mkdir(exist_ok=True)
            internal.write_text("print('studio')\n")
            info = workspace.read_file("hardware/manager.py")
            self.assertFalse(info["editable"])
            with self.assertRaisesRegex(ValueError, "not editable"):
                workspace.write_file(info["path"], "changed", info["hash"])
            local.write_text("set(MISSION_NAME MyMission)\n")
            prepare_mission(root)
            self.assertIn("MyMission", local.read_text())
            self.assertEqual(official.read_text(), "set(MISSION_NAME SampleMission)\n")

    def test_interrupted_download_is_retryable(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            def interrupt_clone(command, **kwargs):
                staged = Path(command[-1])
                staged.mkdir()
                (staged / "partial").touch()
                raise subprocess.CalledProcessError(1, command)
            with patch("project.nasa_source.subprocess.run", side_effect=interrupt_clone):
                with self.assertRaises(subprocess.CalledProcessError):
                    install(root)
            self.assertEqual(source_status(root)["state"], "missing")
            self.assertFalse(list(root.glob(".nasa-cfs-*")))

    def test_installer_leaves_an_unrelated_checkout_in_place(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "cFS"
            subprocess.run(["git", "init", "--quiet", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "remote", "add", "origin", "https://example.org/fork"], check=True)
            owned = source / "notes"
            owned.write_text("in use")
            self.assertEqual(source_status(root)["state"], "occupied")
            with self.assertRaisesRegex(ValueError, "different checkout"):
                install(root)
            self.assertEqual(owned.read_text(), "in use")
