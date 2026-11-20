from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hardware.readiness import StartupError, wait_native


class NativeReadinessTest(unittest.TestCase):
    def launch(self, script, *, timeout=3):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "native.log"
            with log.open("wb") as output:
                process = subprocess.Popen([sys.executable, "-u", "-c", script], stdout=output, stderr=subprocess.STDOUT,
                                           stdin=subprocess.PIPE)
            lines = []
            try:
                wait_native(process, log, lines.append, timeout)
                self.assertIsNone(process.poll())
                return lines
            finally:
                process.stdin.close()
                process.wait(timeout=3)

    def test_only_operational_releases_the_caller(self):
        lines = self.launch("import sys; print('CFE_ES_Main entering CORE_READY state'); "
                            "print('CFE_ES_Main: CFE_ES_Main entering OPERATIONAL state'); sys.stdin.read()")
        self.assertEqual(len(lines), 2)

    def test_an_early_exit_always_fails_with_the_exit_status(self):
        for code in (0, 23):
            with self.subTest(code=code), self.assertRaisesRegex(StartupError, f"exited with status {code}"):
                self.launch(f"import sys; print('Starting'); sys.exit({code})")

    def test_fatal_lines_fail_while_the_process_is_still_alive(self):
        examples = [("OS_QueueCreate_Impl(): OS_QueueCreate Error: 22", "msg_max"),
                    ("EVS Port1 CI_LAB 2: CI: bind socket failed = -1", "CI_LAB UDP"),
                    ("CFE_PSP: Exiting cFE", "Exiting cFE")]
        for line, cause in examples:
            with self.subTest(line=line), self.assertRaisesRegex(StartupError, cause):
                self.launch(f"import sys; print({line!r}); sys.stdin.read()")

    def test_other_apps_cannot_announce_es_operational(self):
        with self.assertRaisesRegex(StartupError, "Timed out"):
            self.launch("import sys; print('sample: waiting for CFE_ES_Main entering OPERATIONAL state'); sys.stdin.read()", timeout=.1)
