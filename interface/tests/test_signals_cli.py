"""CLI settings must be visible to the widgets and to the flight waveform sampler."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import sys
import unittest

from project.workspace import Workspace
from sensors.cli import execute, parser
from sensors.session import run_session


class SignalsCliTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        source = Path(__file__).resolve().parents[2]
        for path in ['sensors', 'project/boards', 'project/drivers']:
            shutil.copytree(source / path, self.root / path, ignore=shutil.ignore_patterns('__pycache__'))
        # Waveform source is user-editable in a live mission. Start the fixture
        # with known model defaults even after a user saves field measurements.
        (self.root / 'sensors/signals.py').write_text("SESSION = {'interval': 1, 'sensors': None}\n")
        (self.root / 'sensors/mpu6050.py').write_text(
            'from sensors.schema import Sensor\n'
            "SIGNALS = {'accel-x': {'function': 'constant'}}\n"
            'def configure(device):\n    return Sensor.from_model(device, __file__)\n'
            'def sample(seconds, initial):\n    return initial\n')
        config = dict(schema_version=1, board='raspi4b', os='raspios', buses=['i2c-bus.1'],
                      apps=[], devices=[dict(name='Probe', id='imu', model='mpu6050',
                                             bus='i2c-bus.1', address=104, values={})])
        (self.root / 'project/config.json').write_text(json.dumps(config))
        self.addCleanup(sys.path.__setitem__, slice(None), list(sys.path))
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.workspace = Workspace(self.root)

    def command(self, *args):
        return execute(self.workspace, parser().parse_args(args))

    def test_selected_noisy_output_and_units_in_widget_session_and_runner(self):
        self.command('configure', 'imu', '--outputs', 'accel-x', '--function', 'constant', '--initial', '1',
                     '--noise', 'uniform', '--noise-level', '0.02')
        widgets = self.workspace.simulation_snapshot()
        channels = widgets['settings']['sensors'][0]['signals']
        self.assertEqual([k for k, channel in channels.items() if channel['enabled']], ['accel-x'])
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            run_session(self.root, steps=3, events=True, dry_run=True)
        samples = [json.loads(line[8:])['devices'][0] for line in log.getvalue().splitlines() if line.startswith('@sensor ')]
        self.assertEqual(len(samples), 3)
        for sample in samples:
            self.assertEqual(sample['units'], {'accel-x': 'g'})
            self.assertTrue(.98 <= sample['values']['accel-x'] <= 1.02)

    def test_orbital_settings_persist_and_invalid_edits_are_atomic(self):
        self.command('orbit', '--model', 'Two-body', '--perigee', '495', '--apogee', '505')
        self.command('configure', 'imu', '--outputs', 'temperature', '--function', 'orbit.thermal',
                     '--material', '{"size":"3U","mass":4,"alpha":0.7,"emissivity":0.7,"power":1.0}')
        before = self.workspace.simulation_snapshot()
        self.assertEqual(before['settings']['orbit']['perigee'], 495)
        self.assertEqual(before['settings']['sensors'][0]['signals']['temperature']['material']['size'], '3U')
        with self.assertRaisesRegex(ValueError, 'Choose distinct outputs'):
            self.command('configure', 'imu', '--outputs', 'pressure')
        with self.assertRaisesRegex(ValueError, 'apogee'):
            self.command('orbit', '--apogee', '200')
        self.assertEqual(self.workspace.simulation_snapshot()['hash'], before['hash'])

    def test_select_preserves_channel_edits_and_resets_for_multiple_instances(self):
        path = self.root / 'project/config.json'
        config = json.loads(path.read_text())
        config['devices'].append(dict(config['devices'][0], id='imu2', address=105))
        path.write_text(json.dumps(config))
        model = self.root / 'sensors/mpu6050.py'
        model.write_text(model.read_text().replace("'accel-x': {'function': 'constant'}",
            "'accel-x': {'function': 'constant', 'enabled': False, 'noise': 'gaussian', 'noise_level': 0.1}"))
        self.command('configure','imu','--outputs','accel-x','--noise','none','--initial','0.123')
        self.command('select','imu2')
        self.assertFalse(self.command('show','imu')['enabled'])
        self.command('select','imu')
        first, second = self.command('show','imu'), self.command('show','imu2')
        self.assertTrue(first['enabled'])
        self.assertFalse(second['enabled'])
        first_x, second_x = first['signals']['accel-x'], second['signals']['accel-x']
        self.assertEqual((first_x['initial'], first_x['enabled'], first_x['noise']), (.123, True, 'none'))
        self.assertEqual((second_x['enabled'], second_x['noise']), (False, 'gaussian'))

    def test_two_clients_cannot_overwrite_edits_from_same_snapshot(self):
        from concurrent.futures import ThreadPoolExecutor
        clients = [Workspace(self.root), Workspace(self.root)]
        snapshots = [client.simulation_snapshot() for client in clients]
        def save(index):
            snapshot = snapshots[index]
            snapshot['settings']['interval'] = 0.25 + index
            try:
                clients[index].save_simulation(snapshot['settings'], snapshot['hash'])
                return 'saved'
            except ValueError as error:
                self.assertIn('changed', str(error))
                return 'stale'
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(executor.map(save, range(2)), ['saved', 'stale'])
