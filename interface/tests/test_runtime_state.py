import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hardware.state import RuntimeState, Selection


class RuntimeStateTest(unittest.TestCase):
    def test_existing_checkout_and_cleared_legacy_value(self):
        with TemporaryDirectory() as temp:
            state = RuntimeState(Path(temp))
            state.directory.mkdir(parents=True)
            old = state.directory / 'target.json'
            old.write_text('{"target":"qemu"}')
            self.assertEqual(state.selection(), Selection('qemu'))
            self.assertFalse(state.database.exists())
            state.choose(Selection('physical', 'qemu'))
            reopened = RuntimeState(temp)
            self.assertEqual(reopened.selection(), Selection('physical', 'qemu'))
            state.write('target.json', None)
            self.assertIsNone(reopened.selection())
            self.assertEqual(json.loads(old.read_text())['target'], 'qemu')

    def test_reader_keeps_committed_state_during_an_inflight_write(self):
        with TemporaryDirectory() as temp:
            state = RuntimeState(Path(temp))
            state.choose(Selection('native'))
            with ThreadPoolExecutor(max_workers=1) as pool:
                with state.writer() as writer:
                    state.store(writer, 'target.json', {'target': 'physical'})
                    observed = pool.submit(RuntimeState(temp).selection).result(timeout=2)
                    self.assertEqual(observed, Selection('native'))
            self.assertEqual(state.selection(), Selection('physical'))

    def test_concurrent_record_updates_keep_each_observation(self):
        with TemporaryDirectory() as temp:
            def record(index):
                with RuntimeState(temp).edit('checks-native.json') as checks:
                    checks[str(index)] = True
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(record, range(30)))
            self.assertEqual(len(RuntimeState(temp).read('checks-native.json')), 30)
