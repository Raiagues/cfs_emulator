"""Viewing completed steps must never propose or apply new project changes."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from project.command_lesson import CommandLesson, STUB


class CommandLessonViewsTest(unittest.TestCase):
    def fixture(self, stage=4):
        lesson = CommandLesson.__new__(CommandLesson)
        lesson.workspace = SimpleNamespace(mission=SimpleNamespace(_revision=lambda: 'revision'),
                                           source_path=lambda path: path.replace('mission/', 'cFS/'))
        lesson.stage, lesson.app, lesson.prefix = stage, 'example', 'EXAMPLE'
        lesson.symbol, lesson.code = 'EXAMPLE_SET_RATE_CC', 4
        lesson.line, lesson.manifest = 'EXAMPLE_Data.Rate_Hz = Rate_Hz;', {'name': 'example'}
        lesson.paths = {key: 'mission/apps/example/' + key + '.h' for key in
                        ('code', 'struct', 'handler', 'dispatch', 'events', 'data')}
        lesson.source = {key: 'current ' + key + '\n' for key in lesson.paths}
        lesson.changes = Mock(side_effect=AssertionError('Review must not calculate proposed changes'))
        return lesson

    def test_review_returns_current_source_without_proposals_and_preserves_progress(self):
        lesson = self.fixture()
        snapshot = lesson.snapshot(view='0')
        self.assertEqual(snapshot['stage'], 4)
        self.assertEqual(snapshot['view'], 0)
        self.assertEqual(snapshot['completed'], [True, True, True, True, False, False, False])
        self.assertEqual(snapshot['content'], lesson.source['code'])
        self.assertEqual(snapshot['ranges'], [])
        self.assertEqual(snapshot['path'], 'cFS/apps/example/code.h')
        lesson.changes.assert_not_called()

    def test_current_handler_remains_editable_but_reviewed_handler_is_read_only(self):
        lesson = self.fixture(stage=5)
        lesson.source['handler'] = 'handler\n' + STUB + '\n'
        self.assertEqual(lesson.snapshot()['ranges'], [[2, 2]])
        lesson.stage = 6
        snapshot = lesson.snapshot(view=5)
        self.assertEqual(snapshot['ranges'], [])
        self.assertTrue(snapshot['reviewing'])
        lesson.changes.assert_not_called()

    def test_future_and_malformed_views_are_rejected(self):
        lesson = self.fixture()
        for value in [5, -1, '7', '1.5', 'bad', True, 1.2]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                lesson.snapshot(view=value)
