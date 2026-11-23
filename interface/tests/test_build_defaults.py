"""Safe build defaults apply in the UI/runtime and the shell on each target."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from hardware.state import BuildSettings, RuntimeState

ROOT = Path(__file__).resolve().parents[2]


class BuildDefaultsTest(unittest.TestCase):
    def test_runtime_defaults_to_one_and_preserves_an_explicit_choice(self):
        self.assertEqual(BuildSettings().jobs, 1)
        with tempfile.TemporaryDirectory() as temporary:
            state = RuntimeState(temporary)
            self.assertEqual(state.build_settings().jobs, 1)
            state.write('native-build-settings.json', {'jobs': 3})
            self.assertEqual(RuntimeState(temporary).build_settings().jobs, 3)

    def test_scripts_use_one_worker_on_each_target_and_accept_explicit_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            (root / 'bin').mkdir()
            shutil.copyfile(ROOT / 'scripts/build-cfs.sh', root / 'scripts/build-cfs.sh')
            python = root / 'bin/python3'
            python.write_text('''#!/bin/sh
case "$*" in
  *build_settings*) echo "${TEST_SAVED_JOBS:-1}" ;;
  *build_profile*) echo aarch64 ;;
  *"defaults builder"*) echo fake-builder ;;
  *"defaults platform"*) echo linux/amd64 ;;
esac
''')
            python.chmod(0o755)
            for tool in ('cmake', 'docker'):
                fake = root / 'bin' / tool
                fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_COMMANDS"\n')
                fake.chmod(0o755)
            log = root / 'calls'
            env = {k: v for k, v in os.environ.items() if k not in ('BUILD_JOBS', 'SUDO_USER', 'SUDO_UID', 'SUDO_GID')}
            env.update(PATH=str(root / 'bin') + ':' + env['PATH'], TEST_COMMANDS=str(log))
            cases = [('native', {}, '1'), ('qemu', {}, '1'), ('physical', {}, '1'),
                     ('native', {'TEST_SAVED_JOBS': '2'}, '2'),
                     ('native', {'TEST_SAVED_JOBS': '2', 'BUILD_JOBS': '3'}, '3'),
                     ('qemu', {'BUILD_JOBS': '3'}, '3')]
            for target, extra, jobs in cases:
                with self.subTest(target=target, override=extra):
                    log.write_text('')
                    subprocess.run(['bash', str(root / 'scripts/build-cfs.sh'), '--target', target],
                                   env={**env, **extra}, check=True, capture_output=True, timeout=10)
                    self.assertIn('--parallel ' + jobs + ' --target mission-install', log.read_text())
