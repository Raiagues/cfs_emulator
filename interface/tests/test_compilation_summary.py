"""Synthetic postprocessing cases; no measured values are created by these tests."""
from copy import deepcopy
from pathlib import Path
import re
import unittest

from validation.compilation_summary import validate_commands, WRAPPER


def fixture():
    root = Path('/isolated/flight')
    def command(name, args, seconds=1):
        return {'name': name, 'argv': [str(root/'start'), '--no-ui', *args], 'exit_code': 0, 'elapsed_s': seconds}
    commands = [command('prepare-baseline', ['build', '--target', 'qemu', '--json'], 999)]
    cycles = []
    for index in range(1, 11):
        name = f'eval_cycle_{index:02d}'
        commands.extend([command('create-'+name, ['app', 'new', name, '--json'], 1),
                         command('build-'+name, ['build', '--target', 'qemu', '--json'], index*10),
                         command('delete-'+name, ['app', 'delete', name, '--json'], 2)])
        cycles.append({'repetition': index, 'app': name, 'create_s': 1, 'build_s': index*10, 'delete_s': 2})
    commands.append(command('restore-base-mission', ['build', '--target', 'qemu', '--json'], 999))
    report = {'kind': 'q5_compilation_supplement', 'planned_n': 10, 'target': 'qemu',
              'build_destinations': ['qemu', 'physical'], 'host': {'build_jobs': 1}, 'cycles': cycles,
              'baseline_build': commands[0], 'restoration_build': commands[-1]}
    return root, report, commands


class CompilationSummaryTest(unittest.TestCase):
    def test_requires_all_thirty_two_successful_commands_without_modifying_records(self):
        root, report, commands = fixture(); original = deepcopy((report, commands))
        validate_commands(report, commands, root)
        self.assertEqual((report, commands), original)
        commands[5]['exit_code'] = 1
        with self.assertRaisesRegex(ValueError, 'Unsuccessful command'):
            validate_commands(report, commands, root)

    def test_rejects_missing_operations_wrong_target_and_changed_duration(self):
        for mutation in ('missing', 'target', 'duration'):
            root, report, commands = fixture()
            if mutation == 'missing': commands.pop(8)
            if mutation == 'target': commands[2]['argv'][-2] = 'native'
            if mutation == 'duration': report['cycles'][0]['build_s'] = 2
            with self.assertRaises(ValueError, msg=mutation):
                validate_commands(report, commands, root)

    def test_removes_only_exact_generated_wrappers(self):
        before = '#include "sample_app_msgids.h"\n{ SAMPLE_APP_HK_TLM_MID, 1 },\n'
        after = ('#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SAMPLE_APP))\n'
                 '#include "sample_app_msgids.h"\n#endif\n'
                 '#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SAMPLE_APP))\n'
                 '{ SAMPLE_APP_HK_TLM_MID, 1 },\n#endif\n')
        self.assertEqual(re.sub(WRAPPER, r'\1', after, flags=re.M), before)
        self.assertNotEqual(re.sub(WRAPPER, r'\1', after.replace(', 1 }', ', 2 }'), flags=re.M), before)


if __name__ == '__main__':
    unittest.main()
