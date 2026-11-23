"""Native PSP tests use a simulated kernel table, never allocate or delete SHM."""
import copy
import errno
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from hardware.manager import HardwareManager
from hardware.native_ipc import NativeIPC, NAMES, file_key


class NativeIPCTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = self.root / 'mission/build-native/exe/cpu1'
        self.payload.mkdir(parents=True)
        environment = patch.dict(os.environ, {'FLIGHT_STUDIO_RUNTIME': str(self.root / 'hardware/.runtime')})
        environment.start()
        self.addCleanup(environment.stop)
        self.ipc = NativeIPC(self.root)
        self.table = {}
        self.kernel = patch('hardware.native_ipc.shared_segments', side_effect=lambda: copy.deepcopy(self.table)).start()
        self.addCleanup(patch.stopall)
        patch('hardware.native_ipc.boot_identity', return_value='same-boot').start()
        self.fingerprint = 'a' * 64

    def prepare(self, fingerprint=None):
        return self.ipc.prepare(self.payload, fingerprint or self.fingerprint)

    def segments(self, prepared, pid=123, attached=0):
        return {info['key']: dict(key=info['key'], shmid=100 + index, ctime=100,
                                  size=4096 * (index + 1), uid=os.geteuid(), cpid=pid,
                                  nattch=attached)
                for index, info in enumerate(prepared['keys'].values())}

    def own(self, prepared, pid=123):
        self.table.update(self.segments(prepared, pid))
        self.ipc.capture(prepared, pid, 99, complete=True)
        return self.ipc.store.read(self.ipc.RECORD)

    def test_normal_group_writable_workspace_directories_are_supported(self):
        self.payload.chmod(0o775)
        self.ipc.store.directory.mkdir(parents=True)
        self.ipc.store.directory.chmod(0o775)
        prepared = self.prepare()
        self.assertEqual(self.payload.stat().st_mode & 0o777, 0o775)
        self.assertEqual(self.ipc.store.directory.stat().st_mode & 0o777, 0o775)
        generation = self.ipc.directory / prepared['generation']
        self.assertEqual(generation.stat().st_mode & 0o777, 0o700)
        for name in NAMES:
            self.assertEqual((generation / name).stat().st_mode & 0o777, 0o600)

    def test_rebuild_keeps_hardlinks_keys_and_proven_warm_memory(self):
        first = self.own(self.prepare())
        before = copy.deepcopy(self.table)
        shutil.rmtree(self.payload)
        self.payload.mkdir()
        again = self.prepare()
        self.assertEqual(again, first)
        self.assertEqual(self.table, before)
        for name, info in first['keys'].items():
            anchor = self.ipc.directory / first['generation'] / name
            installed = self.payload / name
            self.assertFalse(installed.is_symlink())
            self.assertTrue(os.path.samefile(anchor, installed))
            self.assertEqual(installed.stat().st_ino, info['inode'])
            self.assertEqual(file_key(installed), info['key'])

    def test_unknown_same_uid_unattached_segments_are_never_adopted_or_deleted(self):
        first = self.prepare()
        self.table.update(self.segments(first, pid=999))
        before = copy.deepcopy(self.table)
        again = self.prepare()
        self.assertNotEqual(first['generation'], again['generation'])
        self.assertFalse({entry['key'] for entry in again['keys'].values()} & set(before))
        self.assertEqual(again['segments'], {})
        self.assertEqual(self.table, before)

    def test_changed_segment_identity_forces_rotation(self):
        for field in ('shmid', 'ctime', 'size', 'uid', 'cpid'):
            with self.subTest(field=field):
                first = self.own(self.prepare())
                key = next(iter(first['keys'].values()))['key']
                self.table[key][field] += 1
                before = copy.deepcopy(self.table)
                again = self.prepare()
                self.assertNotEqual(first['generation'], again['generation'])
                self.assertEqual(self.table, before)

    def test_new_source_generation_retains_owned_history_without_reusing_old_abi(self):
        first = self.own(self.prepare())
        before = copy.deepcopy(self.table)
        second = self.prepare('b' * 64)
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(second['segments'], {})
        self.assertEqual(self.table, before)
        self.assertEqual(self.ipc.store.read('native-ipc-' + first['generation'] + '.json'), first)
        self.assertEqual(self.ipc.store.read('native-ipc-' + second['generation'] + '.json'), second)

    def test_attached_owned_segment_blocks_launch(self):
        first = self.own(self.prepare())
        next(iter(self.table.values()))['nattch'] = 1
        with self.assertRaisesRegex(RuntimeError, 'still attached'):
            self.prepare()
        self.assertEqual(self.ipc.store.read(self.ipc.RECORD), first)

    def test_host_reboot_invalidates_segment_ownership(self):
        first = self.own(self.prepare())
        with patch('hardware.native_ipc.boot_identity', return_value='new-boot'):
            second = self.prepare()
        self.assertNotEqual(first['generation'], second['generation'])

    def test_complete_capture_refuses_foreign_memory_and_keeps_only_owned_partial_identity(self):
        first = self.prepare()
        rows = self.segments(first)
        names = list(first['keys'])
        self.table = rows
        self.table[first['keys'][names[1]]['key']]['cpid'] = 999
        self.table.pop(first['keys'][names[2]]['key'])
        with self.assertRaisesRegex(RuntimeError, 'not owned.*did not create'):
            self.ipc.capture(first, 123, 99, complete=True)
        saved = self.ipc.store.read(self.ipc.RECORD)
        self.assertEqual(list(saved['segments']), [names[0]])
        self.assertEqual(saved['segments'][names[0]]['cpid'], 123)
        self.assertEqual(self.ipc.store.read('native-ipc-' + first['generation'] + '.json'), saved)

    def test_pid_reuse_does_not_prove_old_segment_ownership(self):
        first = self.prepare()
        self.table = self.segments(first)
        with self.assertRaisesRegex(RuntimeError, 'not owned'):
            self.ipc.capture(first, 123, 101, complete=True)
        self.assertEqual(self.ipc.store.read(self.ipc.RECORD)['segments'], {})

    def test_unknown_collision_after_linking_fails_without_committing_identity(self):
        def table():
            if all((self.payload / name).exists() for name in NAMES):
                key = file_key(self.payload / NAMES[0])
                return {key: dict(key=key, shmid=1, ctime=100, size=8192,
                                  uid=os.geteuid(), cpid=999, nattch=0)}
            return {}
        self.kernel.side_effect = table
        with self.assertRaisesRegex(RuntimeError, 'became occupied'):
            self.prepare()
        self.assertIsNone(self.ipc.store.read(self.ipc.RECORD))

    def test_payload_outside_workspace_and_symbolic_links_are_rejected(self):
        outside = self.root / 'elsewhere'
        outside.mkdir()
        with self.assertRaisesRegex(ValueError, 'workspace native'):
            self.ipc.prepare(outside, self.fingerprint)
        marker = self.payload / NAMES[0]
        external = outside / 'untouched'
        external.write_text('outside')
        marker.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.prepare()
        self.assertEqual(external.read_text(), 'outside')

    def test_writable_or_nonempty_keyfiles_are_rejected(self):
        marker = self.payload / NAMES[0]
        marker.touch(mode=0o600)
        marker.chmod(0o666)
        with self.assertRaisesRegex(ValueError, 'permissions'):
            self.prepare()
        marker.chmod(0o600)
        marker.write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'must be empty'):
            self.prepare()

    def test_replaced_anchor_is_rejected(self):
        first = self.prepare()
        anchor = self.ipc.directory / first['generation'] / NAMES[0]
        anchor.unlink()
        anchor.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            self.prepare()

    def test_cross_filesystem_hardlink_error_has_no_symlink_fallback(self):
        with patch('hardware.native_ipc.os.link', side_effect=OSError(errno.EXDEV, 'Invalid cross-device link')):
            with self.assertRaises(OSError) as error:
                self.prepare()
        self.assertEqual(error.exception.errno, errno.EXDEV)
        self.assertFalse(any(self.payload.iterdir()))
        self.assertIsNone(self.ipc.store.read(self.ipc.RECORD))

    def test_preflight_failure_never_starts_flight_process(self):
        hardware = HardwareManager(self.root)
        hardware._require_build = Mock(return_value=(None, self.payload, {'fingerprint': self.fingerprint}))
        hardware.assert_can_start = Mock()
        hardware._native_command_port = Mock(return_value=0)
        with patch('sensors.registers.prepare', return_value=self.root / 'devices'), \
                patch('hardware.manager.socket.socket') as socket, \
                patch('hardware.native_ipc.NativeIPC.prepare', side_effect=RuntimeError('Unknown memory')), \
                patch('hardware.manager.subprocess.Popen') as process:
            socket.return_value.__enter__.return_value.bind.return_value = None
            with self.assertRaisesRegex(RuntimeError, 'Unknown memory'):
                hardware._run_native(lambda line: None, lambda: False)
        process.assert_not_called()

    def test_capture_failure_stops_child_and_never_records_success(self):
        hardware = HardwareManager(self.root)
        hardware._require_build = Mock(return_value=(None, self.payload, {'fingerprint': self.fingerprint}))
        hardware.assert_can_start = Mock()
        hardware._native_command_port = Mock(return_value=0)
        hardware._deploy_record = Mock()
        hardware.runtime.mkdir(parents=True, exist_ok=True)
        with patch('sensors.registers.prepare', return_value=self.root / 'devices'), \
                patch('hardware.manager.socket.socket'), \
                patch('hardware.manager.wait_native'), \
                patch('hardware.native_ipc.NativeIPC.capture', side_effect=RuntimeError('Unknown memory')), \
                patch('hardware.manager.subprocess.Popen') as process:
            process.return_value.pid = 123
            process.return_value.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, 'Unknown memory'):
                hardware._run_native(lambda line: None, lambda: False)
        process.return_value.terminate.assert_called_once()
        hardware._deploy_record.assert_not_called()

    def test_native_install_digest_includes_stable_keyfiles_before_resume(self):
        for directory in ('cFS', 'project/generated', 'scripts'):
            (self.root / directory).mkdir(parents=True)
        (self.root / 'project/config.json').write_text('{"apps":[],"devices":[],"board":null,"os":null}')
        (self.root / 'Dockerfile').write_text('FROM builder')
        (self.root / 'scripts/build-cfs.sh').write_text('build')
        hardware = HardwareManager(self.root)
        hardware._local_flight_state = Mock(return_value={'running': False})
        calls = []
        def install(argv, emit, cancel, cwd=None):
            if argv[0] != 'bash':
                return
            calls.append(argv)
            shutil.rmtree(self.payload)
            (self.payload / 'cf').mkdir(parents=True)
            (self.payload / 'core-cpu1').write_text('fixture')
            (self.payload / 'core-cpu1').chmod(0o755)
            (self.payload / 'cf/cfe_es_startup.scr').write_text('fixture')
            (self.root / 'project/generated/build-native.json').write_text('{}')
        hardware._stream = install
        first = hardware._build('native', False, lambda line: None, lambda: False)
        generation = self.ipc.store.read(self.ipc.RECORD)
        self.assertEqual(len(first['installed_sha256']), 64)
        self.assertTrue(all((self.payload / name).is_file() for name in NAMES))
        again = hardware._build('native', False, lambda line: None, lambda: False, reuse=True)
        self.assertEqual(again, first)
        self.assertEqual(len(calls), 1)
        rebuilt = hardware._build('native', False, lambda line: None, lambda: False)
        self.assertEqual(rebuilt['installed_sha256'], first['installed_sha256'])
        self.assertEqual(self.ipc.store.read(self.ipc.RECORD), generation)
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
