"""Verify measurement boundaries with synthetic CLI processes, never study results."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation import compilation


PROGRAM = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path.cwd()
args = sys.argv[2:]
with (root/'invocations.jsonl').open('a') as log:
    log.write(json.dumps({'argv':args, 'jobs':os.environ.get('BUILD_JOBS'),
                          'cmake_jobs':os.environ.get('CMAKE_BUILD_PARALLEL_LEVEL')})+'\n')
if args[0] == 'build':
    if (root/'fail-build').exists(): raise SystemExit(3)
    file = root/'mission/build-flight/exe/cpu1/core-cpu1'
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('synthetic fixture executable')
elif args[:2] == ['app', 'new']:
    file = root/'cFS/apps'/args[2]
    file.mkdir(parents=True)
elif args[:2] == ['app', 'delete']:
    (root/'cFS/apps'/args[2]).rmdir()
print('{}')
"""


class CompilationSupplementTest(unittest.TestCase):
    def prepare(self, base):
        root = base/'flight'; root.mkdir()
        (root/'.evaluation.json').write_text(json.dumps({'platform_commit':'a'*40, 'nasa_commit':'b'*40}))
        (root/'start').write_text(PROGRAM); (root/'start').chmod(0o755)
        return root

    def test_real_cli_records_only_incremental_cycles_and_restores_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = self.prepare(base); output = base/'measurements'
            with patch.object(compilation, 'procedure_identity', return_value={'commit':'c'*40, 'files':{}}):
                result = compilation.run(root, output, repetitions=2)
            self.assertEqual(result['status'], 'final')
            self.assertEqual(result['build_destinations'], ['qemu', 'physical'])
            self.assertEqual(result['source_differences_after_restoration'], [])
            commands = json.loads((output/'commands.json').read_text())['commands']
            self.assertEqual(len(commands), 8)
            invocations = [json.loads(line) for line in (root/'invocations.jsonl').read_text().splitlines()]
            self.assertTrue(all(call['jobs'] == call['cmake_jobs'] == '1' for call in invocations))
            self.assertEqual(commands[0]['name'], 'prepare-baseline')
            self.assertEqual(commands[-1]['name'], 'restore-base-mission')
            builds = [c for c in commands if 'build' in c['argv']]
            self.assertTrue(all(c['argv'][-3:] == ['--target', 'qemu', '--json'] for c in builds))
            with (output/'q5_timings.csv').open() as stream: rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 6)
            self.assertEqual({r['repetition'] for r in rows}, {'1', '2'})
            self.assertEqual(result['tables']['q5_statistics.csv']['rows'], 3)
            self.assertEqual(result['tables']['q5_statistics.csv']['columns'], compilation.STAT_FIELDS)

    def test_failed_baseline_never_produces_final_summary_or_statistics(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = self.prepare(base); output = base/'measurements'
            (root/'fail-build').touch()
            with patch.object(compilation, 'procedure_identity', return_value={'commit':'c'*40, 'files':{}}):
                with self.assertRaisesRegex(RuntimeError, 'exited 3'):
                    compilation.run(root, output, repetitions=2)
            self.assertEqual(json.loads((output/'metrics.json').read_text())['status'], 'failed')
            self.assertFalse((output/'summary.json').exists())
            self.assertFalse((output/'q5_statistics.csv').exists())

    def test_old_builds_are_rejected_before_any_cli_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = self.prepare(base)
            (root/'mission/build-flight').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'without existing ARM'):
                compilation.run(root, base/'measurements')
            self.assertFalse((root/'invocations.jsonl').exists())

    def test_statistics_keep_slow_observations_and_reject_incomplete_series(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = [dict(repetition=n, create_s=1, build_s=value, delete_s=2)
                    for n, value in enumerate([1, 2, 3, 100], 1)]
            compilation.write_tables(output, rows, 4)
            with (output/'q5_statistics.csv').open() as stream: stats = list(csv.DictReader(stream))
            build = next(row for row in stats if row['stage'] == 'build_s')
            self.assertEqual((build['n'], build['median'], build['max']), ('4', '2.5', '100'))
            with self.assertRaisesRegex(ValueError, 'Incomplete or reordered'):
                compilation.write_tables(output, rows[:3], 4)


if __name__ == '__main__':
    unittest.main()
