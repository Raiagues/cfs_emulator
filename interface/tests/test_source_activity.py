import hashlib
import tempfile
import unittest
from pathlib import Path

from project.source_activity import SourceActivity


class IndexedWorkspace:
    def __init__(self, root):
        self.root = Path(root)
        self.files = {'cFS/apps/example/ids.h': '#define EXAMPLE_NOOP_CC 0\n',
                      'cFS/apps/example/cmd.c': 'void Noop(void) {}\n'}
        for path, content in self.files.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        ref = lambda name: {'path': name, 'line': 1}
        self.handler = {'cc': {'symbol': 'EXAMPLE_NOOP_CC', 'source': ref('cFS/apps/example/ids.h')},
                        'source': ref('cFS/apps/example/cmd.c'), 'handler': ref('cFS/apps/example/cmd.c')}

    def snapshot(self):
        return {'apps': [{'name': 'example', 'behavior': {'details': {'commands': [
            {'mid': {'symbol': 'EXAMPLE_CMD_MID'}, 'handlers': [self.handler]}]}}}]}

    def path(self, relative):
        path = self.root / relative
        if path.is_relative_to(self.root) and '..' not in path.parts:
            return path
        raise ValueError('Outside workspace')

    def source_path(self, relative):
        return self.path(relative).relative_to(self.root).as_posix()


class SourceActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = IndexedWorkspace(self.temp.name)

    def activity(self, target='native'):
        return SourceActivity(self.workspace, target, 'example', 'EXAMPLE_NOOP_CC')

    def test_navigation_does_not_complete_steps_and_review_survives_reload_without_source_changes(self):
        a = self.activity()
        before = {p: self.workspace.path(p).read_bytes() for p in self.workspace.files}
        snap = a.snapshot()
        self.assertFalse(any(s['done'] for s in snap['steps']))
        a.review(0, snap['steps'][0]['fingerprint'])
        reloaded = self.activity().snapshot()
        self.assertTrue(reloaded['steps'][0]['done'])
        self.assertFalse(reloaded['steps'][3]['done'])
        self.assertTrue(reloaded['files']['cFS/apps/example/ids.h'])
        self.assertFalse(self.activity('qemu').snapshot()['steps'][0]['done'])
        self.assertEqual(before, {p: self.workspace.path(p).read_bytes() for p in self.workspace.files})
        self.assertTrue(a.store.database.exists())

    def test_stale_sources_invalidate_completion_and_reject_a_stale_review(self):
        a = self.activity()
        fingerprint = a.snapshot()['steps'][0]['fingerprint']
        a.review(0, fingerprint)
        self.workspace.path('cFS/apps/example/ids.h').write_text('#define EXAMPLE_NOOP_CC 1\n')
        self.assertFalse(a.snapshot()['steps'][0]['done'])
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            a.review(0, fingerprint)

    def test_unavailable_and_placeholder_sources_cannot_be_completed_or_mark_flight_tests(self):
        a = self.activity()
        with self.assertRaisesRegex(ValueError, 'not ready'):
            a.review(1, a.snapshot()['steps'][1]['fingerprint'])
        with self.assertRaisesRegex(ValueError, 'flight test'):
            a.review(6, 'anything')
        self.workspace.handler['placeholder'] = True
        a = self.activity()
        self.assertFalse(a.snapshot()['steps'][5]['available'])
        with self.assertRaises(ValueError):
            SourceActivity(self.workspace, 'native', 'example', 'MADE_UP_CC')
        with self.assertRaises(ValueError):
            self.activity('unknown')


if __name__ == '__main__':
    unittest.main()
