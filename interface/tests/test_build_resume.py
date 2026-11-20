import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from hardware.manager import HardwareManager


class FirstBootBuildResumeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for folder in ("cFS", "project/generated", "mission", "scripts"):
            (self.root / folder).mkdir(parents=True)
        (self.root / "project/config.json").write_text('{"apps":[],"devices":[],"board":"raspi4b","os":"raspios"}')
        (self.root / "Dockerfile").write_text("FROM builder")
        (self.root / "scripts/build-cfs.sh").write_text("build")
        self.source = self.root / "mission/app.c"
        self.source.write_text("version 1")
        self.hardware = HardwareManager(self.root)
        self.hardware._validate_profile = Mock()
        self.hardware._stream = self.stream
        self.payload = self.root / "mission/build-flight/exe/cpu1"
        self.stamp = self.root / "project/generated/build-flight.json"
        self.compilations = 0

    def stream(self, argv, emit, cancel, cwd=None):
        if argv[0] != "bash":
            return
        self.compilations += 1
        if self.payload.exists():
            shutil.rmtree(self.payload)
        (self.payload / "cf").mkdir(parents=True)
        binary = self.payload / "core-cpu1"
        binary.write_bytes(self.source.read_bytes())
        binary.chmod(0o755)
        (self.payload / "cf/cfe_es_startup.scr").write_text("startup")
        (self.payload / "cf/sample_app.so").write_bytes(b"module")
        self.stamp.write_text('{"target":"flight"}')

    def build(self, resume=False):
        return self.hardware.execute("build", emit=lambda line: None, target="qemu", reuse_build=resume)

    def test_resume_verifies_install_and_explicit_build_always_compiles(self):
        first = self.build()
        self.assertEqual(len(first["installed_sha256"]), 64)
        self.assertEqual(self.build(resume=True), first)
        self.assertEqual(self.compilations, 1)
        self.build()
        self.assertEqual(self.compilations, 2)

    def test_changes_to_payload_config_or_sources_force_a_new_build(self):
        self.build()
        bad_changes = [
            lambda: (self.payload / "cf/sample_app.so").write_bytes(b"broken"),
            lambda: (self.payload / "core-cpu1").chmod(0o644),
            lambda: (self.payload / "cf/cfe_es_startup.scr").unlink(),
            lambda: (self.payload / "extra").touch(),
            lambda: self.stamp.write_text("different profile"),
            lambda: self.source.write_text("version 2"),
        ]
        for index, change in enumerate(bad_changes, 2):
            with self.subTest(index=index):
                change()
                self.build(resume=True)
                self.assertEqual(self.compilations, index)

    def test_old_receipts_and_other_targets_cannot_be_reused(self):
        current = self.build()
        for count, state in enumerate(({k: v for k, v in current.items() if k != "installed_sha256"},
                                       dict(current, target="physical")), 2):
            with self.subTest(count=count):
                self.hardware.state.write("build-flight.json", state)
                self.build(resume=True)
                self.assertEqual(self.compilations, count)
