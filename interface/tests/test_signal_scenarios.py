import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sensors.scenarios import run_scenario
from sensors.session import load_session
from project.sensor_models import board_model, load, model_paths


class SignalScenarioTest(unittest.TestCase):
    def test_board_defined_sensor_without_register_profile(self):
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ('sensors', 'project/boards'):
                shutil.copytree(source/path, root/path)
            board = root/'project/boards/raspi4b.json'
            catalog = json.loads(board.read_text())
            catalog['models'] = {'thermal_probe': board_model(load(model_paths(source)['tmp105']))}
            board.write_text(json.dumps(catalog))
            shutil.copy(root/'sensors/tmp105.py',root/'sensors/thermal_probe.py')
            device = dict(name='Cabin', id='cabin', model='thermal_probe', bus='i2c-bus.1', address=72, values={})
            config = dict(schema_version=1, board='raspi4b', os='raspios', buses=['i2c-bus.1'], devices=[device], apps=[])
            (root/'project/config.json').write_text(json.dumps(config))
            simulated = load_session(root)['available'][0]
            self.assertEqual(simulated['device_argument'], 'thermal_probe,id=cabin,bus=i2c-bus.1,address=0x48')
            channel = simulated['properties']['temperature']
            self.assertEqual(channel['scale'],1000)
            self.assertNotIn('register',channel)
            with self.assertRaisesRegex(ValueError, 'Register profile required'):
                run_scenario(root,device['id'],'orbit')

    @unittest.skipUnless(shutil.which('cc'), 'Native compiler required for flight HAL')
    def test_local_register_reads_and_fault_recovery(self):
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ('sensors', 'project/drivers', 'project/boards'):
                shutil.copytree(source/path, root/path)
            device = dict(name='Cabin', id='cabin', model='tmp105', bus='i2c-bus.1', address=72, values={})
            config = dict(schema_version=1, board='raspi4b', os='raspios', buses=['i2c-bus.1'], devices=[device], apps=[])
            (root/'project/config.json').write_text(json.dumps(config))
            for scenario in ('orbit', 'eclipse', 'dropout'):
                with self.subTest(scenario=scenario):
                    result = run_scenario(root, device['id'], scenario)
                    self.assertTrue(all(result['checks'].values()))
                    self.assertEqual(result['units'], {'temperature':'°C'})
                    low, high = result['ranges']['temperature']
                    self.assertIn(f'temperature in @range {low:g}..{high:g} °C', result['checks'])
                    samples = result['samples']
                    self.assertTrue(any(row['read'].get('temperature') != row['sent']['temperature']
                                        for row in samples if row['status'] == 0))
                    if scenario == 'dropout':
                        self.assertTrue(all(row['status'] and not row['read'] for row in samples[10:16]))
                        self.assertEqual(samples[16]['status'], 0)
                        self.assertTrue(result['checks']['Read recovered'])
                    else:
                        self.assertTrue(all(row['status'] == 0 for row in samples))
