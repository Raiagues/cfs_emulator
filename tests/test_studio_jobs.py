"""Studio job lifecycle: validation, mutual exclusion, cancellation and lock release.

The hardware manager and ground station are replaced by in-memory doubles; no
build, QEMU, SSH or board is involved.
"""
from pathlib import Path
import threading
import time
import unittest
from unittest import mock

from hardware.manager import HardwareError
from interface.server import Studio


ROOT = Path(__file__).resolve().parents[1]
BOARD = {'host': 'board.local', 'user': 'pi', 'port': 22}


class FakeGround:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


class FakeHardware:
    """Records calls; `gates` block an action and `failures` make it raise."""
    def __init__(self):
        self.calls, self.gates, self.failures, self.started = [], {}, {}, {}

    def default_target(self):
        return 'qemu'

    def connection(self, value=None):
        return dict(BOARD)

    def assert_can_boot(self, retry=False):
        if 'assert_can_boot' in self.failures:
            raise self.failures['assert_can_boot']

    def simulation_script(self, device=None):
        return 'sensors/tmp105.py'

    def execute(self, action, emit, cancel=None, on_start=None, **options):
        self.calls.append((action, options))
        self.started.setdefault(action, threading.Event()).set()
        if on_start:
            on_start()
        if action in self.failures:
            raise self.failures[action]
        while action in self.gates and not self.gates[action].wait(0.01) and not cancel.is_set():
            pass
        if action == 'logs' or action == 'simulate':
            emit(action + ' line')
            cancel.wait(5)
            return None
        emit(action + ' done')
        return {'fingerprint': 'a' * 64} if action == 'build' else {'ok': True}


def wait(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class StudioJobsTest(unittest.TestCase):
    def setUp(self):
        self.studio = Studio(ROOT)
        self.studio.hardware = FakeHardware()
        self.studio.ground = FakeGround()
        self.frozen = []
        self.studio.freeze_catalog = lambda state, sensorless: self.frozen.append(state['fingerprint'])
        # A second release of the operation lock would only surface in its thread.
        self.thread_errors = []
        self.addCleanup(setattr, threading, 'excepthook', threading.excepthook)
        threading.excepthook = lambda args: self.thread_errors.append(args.exc_value)

    def tearDown(self):
        for gate in self.studio.hardware.gates.values():
            gate.set()
        self.studio.close()
        self.assertEqual(self.thread_errors, [])

    def record(self, ident):
        return self.studio.jobs[ident]

    def finished(self, ident):
        self.assertTrue(wait(lambda: self.record(ident)['status'] != 'running'), 'job did not finish')
        self.record(ident)['thread'].join(5)
        return self.record(ident)

    def operation_free(self):
        if not self.studio.operation.acquire(blocking=False):
            return False
        self.studio.operation.release()
        return True

    def test_invalid_requests_never_take_the_operation_lock(self):
        for action, options in [('erase', {}), ('build', {'unknown': 1}), ('build', {'target': 'mars'}),
                                ('run', {'retry': True}), ('logs', {'kind': 'kernel'}),
                                ('simulate', {'target': 'physical'}), ('build', {'device': 'tmp105'})]:
            with self.subTest(action=action, options=options):
                with self.assertRaises(ValueError):
                    self.studio.job(action, options)
                self.assertTrue(self.operation_free())
        self.assertEqual(self.studio.jobs, {})

    def test_exclusive_operations_are_mutually_exclusive(self):
        self.studio.hardware.gates['build'] = threading.Event()
        build = self.studio.job('build', {})['id']
        self.assertTrue(self.studio.hardware.started['build'].wait(5))
        with self.assertRaisesRegex(ValueError, 'already running'):
            self.studio.job('stop', {})
        # Background readers do not need the operation lock.
        logs = self.studio.job('logs', {'kind': 'boot'})['id']
        self.studio.hardware.gates['build'].set()
        self.assertEqual(self.finished(build)['status'], 'succeeded')
        self.assertEqual(self.frozen, ['a' * 64])
        self.assertTrue(self.operation_free())
        self.assertEqual(self.record(logs)['status'], 'running')

    def test_failure_releases_the_operation_lock(self):
        self.studio.hardware.failures['stop'] = HardwareError('SSH failed')
        record = self.finished(self.studio.job('stop', {})['id'])
        self.assertEqual((record['status'], record['error']), ('failed', 'SSH failed'))
        self.assertIn('SSH failed', record['lines'])
        self.assertTrue(self.operation_free())
        self.assertEqual(self.finished(self.studio.job('stop', {})['id'])['status'], 'failed')

    def test_refused_boot_keeps_the_ground_station_and_readers(self):
        reader = self.studio.job('logs', {})['id']
        self.studio.hardware.failures['assert_can_boot'] = HardwareError('QEMU is already running')
        record = self.finished(self.studio.job('boot', {})['id'])
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(self.studio.ground.stops, 0)
        self.assertFalse(self.record(reader)['cancel'].is_set())
        self.assertTrue(self.operation_free())

    def test_run_releases_the_lock_while_its_log_reader_continues(self):
        run = self.studio.job('run', {})['id']
        self.assertTrue(wait(lambda: self.record(run)['operation_complete']))
        self.assertTrue(self.operation_free())
        self.assertEqual(self.studio.hardware.calls[-1], ('logs', {'target': 'qemu', 'kind': 'flight'}))
        # Opening the flight output again reuses the run job's reader.
        self.assertEqual(self.studio.job('logs', {}), {'id': run, 'existing': True})
        self.assertEqual(self.studio.cancel(run)['cancel_requested'], True)
        record = self.finished(run)
        self.assertEqual(record['status'], 'cancelled')
        self.assertTrue(self.operation_free())

    def test_log_reader_failure_is_reported_without_a_second_release(self):
        self.studio.hardware.failures['logs'] = HardwareError('journal unavailable')
        record = self.finished(self.studio.job('run', {})['id'])
        self.assertEqual((record['status'], record['error']), ('failed', 'Log reader stopped: journal unavailable'))
        self.assertTrue(record['operation_complete'])
        self.assertTrue(self.operation_free())

    def test_run_start_replaces_readers_of_other_destinations_and_of_its_log_kind(self):
        flight = self.studio.job('logs', {})['id']
        boot_log = self.studio.job('logs', {'kind': 'boot'})['id']
        physical = self.studio.job('logs', {'target': 'physical'})['id']
        simulation = self.studio.job('simulate', {'device': 'tmp105'})['id']
        run = self.studio.job('run', {})['id']
        self.assertTrue(wait(lambda: self.record(run)['operation_complete']))
        self.assertTrue(self.record(flight)['cancel'].is_set())
        self.assertTrue(self.record(physical)['cancel'].is_set())
        self.assertFalse(self.record(boot_log)['cancel'].is_set())
        self.assertFalse(self.record(simulation)['cancel'].is_set())
        self.assertEqual(self.studio.ground.stops, 1)

    def test_stop_cancels_flight_readers_and_shutdown_cancels_every_reader_of_the_target(self):
        flight = self.studio.job('logs', {})['id']
        boot_log = self.studio.job('logs', {'kind': 'boot'})['id']
        physical = self.studio.job('logs', {'target': 'physical'})['id']
        self.assertEqual(self.finished(self.studio.job('stop', {})['id'])['status'], 'succeeded')
        self.assertTrue(self.record(flight)['cancel'].is_set())
        self.assertFalse(self.record(boot_log)['cancel'].is_set())
        self.assertEqual(self.finished(self.studio.job('shutdown', {})['id'])['status'], 'succeeded')
        self.assertTrue(self.record(boot_log)['cancel'].is_set())
        self.assertFalse(self.record(physical)['cancel'].is_set())
        self.assertEqual(self.record(physical)['connection'], BOARD)

    def test_thread_start_failure_unregisters_the_job_and_releases_the_lock(self):
        with mock.patch('threading.Thread.start', side_effect=RuntimeError('no threads')):
            with self.assertRaisesRegex(RuntimeError, 'no threads'):
                self.studio.job('build', {})
        self.assertEqual(self.studio.jobs, {})
        self.assertTrue(self.operation_free())

    def test_sensor_samples_are_kept_apart_from_output(self):
        ident = self.studio.job('simulate', {'device': 'tmp105'})['id']
        record = self.record(ident)
        self.studio._emit(record, '@sensor {"tmp105": {"temperature": 23500}}')
        self.studio._emit(record, '@sensor [1, 2]')
        self.assertEqual(record['samples']['tmp105'], {'temperature': 23500})
        self.assertIn('@sensor [1, 2]', record['lines'])

    def test_close_cancels_jobs_and_refuses_new_ones(self):
        self.studio.hardware.gates['build'] = threading.Event()
        build = self.studio.job('build', {})['id']
        reader = self.studio.job('logs', {'kind': 'boot'})['id']
        self.assertTrue(self.studio.hardware.started['build'].wait(5))
        self.studio.close()
        self.assertEqual(self.finished(reader)['status'], 'cancelled')
        self.assertEqual(self.finished(build)['status'], 'cancelled')
        self.assertEqual(self.frozen, [])
        with self.assertRaisesRegex(ValueError, 'shutting down'):
            self.studio.job('logs', {})
        self.assertTrue(self.operation_free())


if __name__ == '__main__':
    unittest.main()
