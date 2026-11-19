import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sensors.scenarios import run_scenario


class SignalScenarioTest(unittest.TestCase):
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
                    samples = result['samples']
                    self.assertTrue(any(row['read'].get('temperature') != row['sent']['temperature']
                                        for row in samples if row['status'] == 0))
                    if scenario == 'dropout':
                        self.assertTrue(all(row['status'] and not row['read'] for row in samples[10:16]))
                        self.assertEqual(samples[16]['status'], 0)
                        self.assertTrue(result['checks']['Read recovered'])
                    else:
                        self.assertTrue(all(row['status'] == 0 for row in samples))
