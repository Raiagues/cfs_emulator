"""Build reservations, mission editing and reconnectable output use separate resources."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from jobs.service import Laboratory


class JobStreamTest(unittest.TestCase):
    def test_edit_and_resume_log_during_build(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            mission = root / 'mission'
            mission.mkdir()
            (mission / 'operator.c').write_text('int before;')
            app = Laboratory(root)
            self.addCleanup(app.close)
            entered, release = Event(), Event()

            def build(action, emit, **options):
                emit('compiling')
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test build did not receive release')
                emit('linked')
                return {'compiled': True}

            with patch.object(app.hardware, 'execute', side_effect=build):
                ident = app.job('build', {'target':'native'})['id']
                try:
                    self.assertTrue(entered.wait(3))
                    cursor = next(app.job_updates(ident))['cursor']
                    source = app.workspace.read_file('mission/operator.c')
                    app.workspace.write_file(source['path'], 'int after;', source['hash'])
                    self.assertNotIn('lines', app.jobs_snapshot(include_lines=False)[0])
                    with self.assertRaisesRegex(ValueError, 'operation'):
                        app.job('build', {'target':'native'})
                finally:
                    release.set()
                frames = list(app.job_updates(ident, cursor))
                self.assertEqual([line for frame in frames for line in frame['lines']], ['linked'])
                self.assertEqual(frames[-1]['result'], {'compiled': True})
                self.assertEqual(frames[-1]['status'], 'succeeded')
                self.assertEqual(next(app.job_updates(ident, 2))['lines'], [])
