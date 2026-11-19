"""Namespace and cFE artifact regressions for native mission module renames."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interface.backend.module_rename import ModuleNames, _startup
from project.appgen.native_startup import parse_startup
from project.cfs_config import module_limits_plan


def library_template(root, sample, name):
    return {
        'CMakeLists.txt': f'add_cfe_app({name} fsw/src/{name}.c)\n',
        f'fsw/public_inc/{name}.h': f'int {name.upper()}_Init(void);\n',
        f'fsw/src/{name}.c': f'int {name.upper()}_Init(void) {{ return 0; }}\n',
        'README.md': f'Library {name} uses {name.upper()}_Init.\n',
    }


class ModuleRenameTest(unittest.TestCase):
    def setUp(self):
        # A one-character module exercises collisions with .c and with local
        # variables, while c_aux is a distinct module with a shared prefix.
        with patch('interface.backend.module_rename.copy_sample', library_template):
            self.names = ModuleNames(Path('.'), 'c', 'camera', None, {'c_aux'})
        self.names.prepare({
            Path('fsw/public_inc/c.h'): 'int C_Init(void);\n',
            Path('fsw/src/c.c'): 'int C_Calibrate(int c) { return C_External(c); }\n',
        })

    def test_updates_owned_symbols_and_dependencies(self):
        source = '#include "c.h"\nint read(int c) { return C_Calibrate(c) + C_External(c) + C_AUX_Count(); }\n'
        self.assertEqual(self.names.text(source, Path('caller.c')),
                         source.replace('"c.h"', '"camera.h"').replace('C_Calibrate', 'CAMERA_Calibrate'))
        self.assertEqual(self.names.text('add_cfe_app_dependency(c_aux c)', Path('CMakeLists.txt')),
                         'add_cfe_app_dependency(c_aux camera)')
        self.assertEqual(self.names.filename('cpu1_c_extra.h'), 'cpu1_camera_extra.h')
        self.assertEqual(self.names.filename('c_aux.h'), 'c_aux.h')
        self.assertEqual(self.names.filename('other_c_message.h'), 'other_c_message.h')
        self.assertEqual(self.names.text('log_value("c");', Path('caller.c')), 'log_value("c");')
        self.assertEqual(self.names.owned_text('Library c uses C_Init.\r\nHand edited\r\n', Path('README.md'), 'README.md'),
                         'Library camera uses CAMERA_Init.\r\nHand edited\r\n')

    def test_renames_an_archived_native_record_in_place(self):
        comment = '# Previously tested CFE_LIB, /cf/c.so, C_Init, C, 0, 0, 0, 0;\n'
        original = 'CFE_LIB, sample_lib, SAMPLE_LIB_Init, SAMPLE_LIB, 0, 0, 0, 0;\n!\n' + comment + 'CFE_LIB, /cf/c.so, C_Init, C, 0, 0, 0, 0;\n'
        result = _startup(original, self.names)
        self.assertIn(comment, result)
        self.assertEqual(_startup('', self.names), '')
        active, archived = parse_startup(result)
        self.assertEqual([item.name for item in active], ['sample_lib'])
        self.assertEqual(archived[0].fields[1:4], ('/cf/camera.so', 'CAMERA_Init', 'CAMERA'))

    def test_loader_allocates_space_for_planned_table_filename(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            defaults = root / 'cFS/osal/default_config.cmake'
            defaults.parent.mkdir(parents=True)
            defaults.write_text('set(OSAL_CONFIG_MAX_API_NAME 32)\nset(OSAL_CONFIG_MAX_FILE_NAME 20)\nset(OSAL_CONFIG_MAX_MODULES 32)\n')
            api = root / 'cFS/cfe/modules/core_api/fsw/inc/cfe_core_api_interface_cfg.h'
            api.parent.mkdir(parents=True)
            api.write_text('#define CFE_MISSION_MAX_FILE_LEN CFE_MISSION_CORE_API_CFGVAL(MAX_FILE_LEN)\n')
            header = 'mission/sample_defs/cfe_core_api_interface_cfg_values.h'
            files = {
                header: '#define CFE_MISSION_CORE_API_CFGVAL(x) DEFAULT_##x\n',
                'mission/cpu1_cfe_es_startup.scr': 'CFE_APP, camera, CAMERA_Main, CAMERA, 50, 32768, 0, 0;\n',
                'cFS/apps/camera/fsw/tables/camera_tbl.c': 'CFE_TBL_FILEDEF(Table, CAMERA.Calib, Calibration, camera_calibration_table.tbl)\n',
            }
            plan = module_limits_plan(root, files)
            self.assertIn('set(OSAL_CONFIG_MAX_FILE_NAME 32)', plan['mission/sample_defs/default_osconfig.cmake'])
            self.assertIn('MAX_FILE_LEN) : 32)', plan[header])


if __name__ == '__main__':
    unittest.main()
