"""The evaluation must distinguish input, real C reads, dropout and missing data."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest

from validation.common import checked_workspace, describe
from validation.protocol import trace
from validation.registers import run


class EvaluationProtocolTest(unittest.TestCase):
    def test_trace_has_fixed_levels_and_explicit_outage(self):
        points = trace('tmp105', 'step')
        self.assertEqual([points[index]['input']['temperature'] for index in (0, 5, 10)], [21537, -3241, 31719])
        self.assertEqual([p['index'] for p in trace('mpu6050', 'dropout') if p['disconnected']], list(range(5, 10)))
        self.assertFalse(trace('mpu6050', 'dropout')[10]['disconnected'])
        with self.assertRaises(ValueError):
            trace('tmp105', 'orbit')

    def test_statistics_report_sample_size_and_require_dedicated_workspace(self):
        self.assertEqual(describe([1, 2, 3, 4]), {'n': 4, 'min': 1, 'median': 2.5, 'max': 4,
                                              'q1': 1.75, 'q3': 3.25, 'iqr': 1.5, 'quartile_method': 'inclusive'})
        self.assertNotIn('iqr', describe([12]))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                checked_workspace(directory)

    @unittest.skipUnless(shutil.which('cc'), 'Native C compiler is needed')
    def test_actual_c_hal_and_register_bytes_include_failure_and_recovery(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'registers'
            result = run(root, output, repetitions=1)
            self.assertEqual((result['status'], len(result['runs']), result['samples']), ('passed', 9, 135))
            for row in result['runs']:
                if row['scenario'] == 'dropout':
                    self.assertTrue(all(p['status'] != 0 and not p['read'] and not p['read_scaled']
                                        for p in row['samples'][5:10]))
                    self.assertEqual(row['samples'][10]['status'], 0)
                self.assertTrue(all(len(bytes.fromhex(p['register_hex'])) == 256 for p in row['samples']))
            temperature = next(row for row in result['runs'] if row['model'] == 'tmp105' and row['scenario'] == 'step')
            negative = temperature['samples'][5]
            raw = int.from_bytes(bytes.fromhex(negative['register_hex'])[:2], 'big', signed=True)
            self.assertLess(raw, 0)
            self.assertLessEqual(abs(raw / 256 - negative['input']['temperature']), .03125)
            self.assertTrue((output / 'tmp105-compile.log').is_file())
            self.assertEqual(json.loads((output / 'registers.json').read_text())['status'], 'passed')


if __name__ == '__main__':
    unittest.main()
