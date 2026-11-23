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


    def test_first_boot_reconnect_reuses_one_operation(self):
        with TemporaryDirectory() as temp:
            app = Laboratory(Path(temp))
            self.addCleanup(app.close)
            entered, release = Event(), Event()

            def boot(record, options, emit):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test boot did not receive release')
                return {'booted': True}

            options = {'target': 'physical', 'board': 'raspi4b', 'os': 'raspios'}
            connection = {'host': 'pi.local', 'port': 22, 'user': 'pi'}
            with patch.object(app.hardware, 'connection', return_value=connection), \
                    patch.object(app, '_execute_job', side_effect=boot) as execute:
                ident = app.job('first-boot', options)['id']
                try:
                    self.assertTrue(entered.wait(3))
                    again = app.job('first-boot', dict(options, sensorless=False))
                    self.assertEqual(again, {'id': ident, 'existing': True})
                    for change in ({'sensorless': True}, {'board': 'another-board'}, {'os': 'another-os'}):
                        with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'first boot'):
                            app.job('first-boot', dict(options, **change))
                    with self.assertRaisesRegex(ValueError, 'first boot'):
                        app.job('first-boot', {'target': 'qemu'})
                    self.assertEqual(execute.call_count, 1)
                finally:
                    release.set()
                frames = list(app.job_updates(ident))
                self.assertEqual(frames[-1]['status'], 'succeeded')

    def test_boot_failure_after_operational_does_not_complete_the_journey(self):
        with TemporaryDirectory() as temp:
            app = Laboratory(Path(temp))
            self.addCleanup(app.close)
            app.hardware.journey.observe('native', 'target', {'checked': True})
            def failing(record, options, emit):
                record['phase'] = 'run'
                emit('CFE_ES_Main entering OPERATIONAL state')
                raise ValueError('Process exited before startup was confirmed')
            with patch.object(app, '_execute_job', side_effect=failing):
                ident = app.job('first-boot', {'target': 'native'})['id']
                final = list(app.job_updates(ident))[-1]
            self.assertEqual(final['status'], 'failed')
            journey = app.hardware.journey.snapshot('native')
            self.assertEqual(journey['current'], 'boot')
            self.assertEqual(journey['boot_attempt'],
                             {'id': ident, 'started': app.jobs[ident]['started'], 'status': 'failed'})
            self.assertFalse(journey['steps']['boot']['done'])

    def test_monitor_recovers_after_a_transient_database_lock(self):
        import sqlite3
        from types import SimpleNamespace
        from unittest.mock import Mock
        from jobs.monitor import Changes, HardwareMonitor
        with TemporaryDirectory() as temp:
            root = Path(temp)
            expected = {'builds': {'native': {'fingerprint': 'ready'}}}
            status = Mock(side_effect=[sqlite3.OperationalError('database is locked'), expected])
            hardware = SimpleNamespace(status=status, journey=SimpleNamespace(path=root/'journey'),
                                       state=SimpleNamespace(database=root/'runtime'))
            monitor = HardwareMonitor(hardware, Changes(), ttl=300)
            try:
                with self.assertRaisesRegex(ValueError, 'database is locked'):
                    monitor.snapshot()
                self.assertTrue(monitor.thread.is_alive())
                monitor.invalidate()
                with monitor.condition:
                    self.assertTrue(monitor.condition.wait_for(lambda: monitor.value == expected, timeout=3))
                self.assertEqual(monitor.snapshot(), expected)
            finally:
                monitor.close()

    def test_status_probe_is_shared_until_invalidated(self):
        from types import SimpleNamespace
        from jobs.monitor import Changes, HardwareMonitor
        with TemporaryDirectory() as temp:
            root = Path(temp)
            probes = []
            def status():
                probes.append(len(probes) + 1)
                return {'builds':{'native':{'fingerprint':str(len(probes))}}}
            hardware = SimpleNamespace(status=status, journey=SimpleNamespace(path=root/'observations'),
                                       state=SimpleNamespace(database=root/'state'))
            events = Changes()
            monitor = HardwareMonitor(hardware, events, ttl=300)
            try:
                self.assertEqual(monitor.snapshot(), monitor.snapshot())
                self.assertEqual(probes, [1])
                with events.condition:
                    self.assertTrue(events.condition.wait_for(lambda: 'hardware' in events.topics, timeout=3))
                _, topics = next(events.stream(-1))
                self.assertIn('hardware', topics)
                monitor.invalidate()
                with monitor.condition:
                    self.assertTrue(monitor.condition.wait_for(lambda: len(probes) == 2, timeout=3))
                self.assertEqual(monitor.snapshot()['builds']['native']['fingerprint'], '2')
            finally:
                monitor.close()
