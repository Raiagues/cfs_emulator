"""Wire layouts use the target compiler, including nested structure arrays."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ground_station.catalog import _build_catalog, fields_for, structures, unavailable_apps
from ground_station.official import decode, encode


class CatalogLayoutsTest(unittest.TestCase):
    def test_unavailable_inventory_excludes_libraries_plugins_and_active_apps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definitions = {'inactive': 'add_cfe_app(inactive source.c)',
                           'active': 'add_cfe_app(active source.c)',
                           'plugin': 'add_sbn_module(plugin Ops source.c)',
                           'library': 'add_cfe_library(library source.c)',
                           'dependency': 'add_cfe_app_dependency(dependency inactive)',
                           'comment': '# add_cfe_app(comment source.c)'}
            for app, text in definitions.items():
                directory = root / 'cFS/apps' / app
                directory.mkdir(parents=True)
                (directory / 'CMakeLists.txt').write_text(text)
            result = unavailable_apps(root, {'active'})
            self.assertEqual([item['app'] for item in result], ['inactive'])
            self.assertIn('startup', result[0]['reason'])

    def test_single_element_and_expression_arrays_keep_their_member_paths(self):
        arrays = {}
        types = structures('''
            typedef struct { uint16 Value; } Item;
            typedef struct { Item One[1]; Item Many[(2 + 1)]; } Packet;
        ''', arrays)
        fields = fields_for('Packet', types, array_members=arrays,
                            array_length=lambda typ, member: 1 if member == 'One' else 3)
        self.assertEqual([field['member'] for field in fields],
                         ['One[0].Value', 'Many[0].Value', 'Many[1].Value', 'Many[2].Value'])
        self.assertTrue(all(field['format'] == 'H' for field in fields))

    @unittest.skipUnless(shutil.which('cc') and shutil.which('objcopy'), 'C compiler and objcopy needed')
    def test_compiled_fields_round_trip_arrays_and_padding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / 'cFS/apps/demo'
            app.mkdir(parents=True)
            (app / 'demo_msg.h').write_text('''
                #include "cfe.h"
                typedef struct { uint8 Flag; uint32 Value; char Name[8]; } DEMO_Item_t;
                typedef struct { CFE_MSG_CommandHeader_t Header; DEMO_Item_t One[1];
                                 uint16 Samples[(2 + 1)]; } DEMO_Set_t;
                typedef struct { CFE_MSG_TelemetryHeader_t Header;
                                 DEMO_Item_t Items[(1 + 1)]; } DEMO_HkTlm_t;
            ''')
            (app / 'demo_msgids.h').write_text('#define DEMO_CMD_MID 0x1882\n#define DEMO_HK_TLM_MID 0x0882\n')
            (app / 'demo_fcncodes.h').write_text('#define DEMO_SET_CC 2\n#define DEMO_UNRESOLVED_CC 3\n')
            (root / 'cFS/cfe.h').write_text('''
                #ifndef CFE_H
                #define CFE_H
                #include <stdint.h>
                typedef uint8_t uint8;
                typedef uint16_t uint16;
                typedef uint32_t uint32;
                typedef struct { uint8 FunctionCode; uint8 Checksum; } Secondary;
                typedef struct { uint8 Primary[6]; Secondary Sec; } CFE_MSG_CommandHeader_t;
                typedef struct { uint8 Bytes[16]; } CFE_MSG_TelemetryHeader_t;
                #endif
            ''')
            source = app / 'demo.c'
            source.write_text('''
                #include "demo_msg.h"
                #include "demo_msgids.h"
                #include "demo_fcncodes.h"
                void Dispatch(void *Msg, int mid, int code) {
                    if (CFE_SB_MsgId_Equal(mid, CFE_SB_ValueToMsgId(DEMO_CMD_MID))) {
                            switch(code) {
                                case DEMO_SET_CC: Accept((DEMO_Set_t *)Msg); break;
                                case DEMO_UNRESOLVED_CC: Unknown(Msg); break;
                            }
                    }
                }
                void Init(void) {
                    DEMO_HkTlm_t Hk;
                    CFE_MSG_Init(&Hk.Header, DEMO_HK_TLM_MID, sizeof(DEMO_HkTlm_t));
                }
            ''')
            build = root / 'mission/build-native'
            flags = build / 'cache/native/default_cpu1/apps/demo/CMakeFiles/demo.dir'
            flags.mkdir(parents=True)
            (flags / 'flags.make').write_text(f'# compile C with {shutil.which("cc")}\nC_INCLUDES = -I{root}/cFS -I{app}\n')
            (flags / 'DependInfo.cmake').write_text(f'set(SOURCES "{source}")\n')
            startup = build / 'exe/cpu1/cf/cfe_es_startup.scr'
            startup.parent.mkdir(parents=True)
            startup.write_text('CFE_APP, demo, DEMO_Main, DEMO, 50, 8192, 0, 0;\n')
            with patch('ground_station.contact_routes.first_contact_routes', return_value={}):
                catalog = _build_catalog(root, build_dir=build)
            self.assertEqual([x['id'] for x in catalog['unresolved_commands']], ['DEMO_UNRESOLVED_CC'])
            self.assertTrue(all('unresolved' in error for error in catalog['errors']), catalog['errors'])
            command, = catalog['commands']
            self.assertEqual(command['id'], 'DEMO_SET_CC')
            fields = {f['name']: f for f in command['fields']}
            self.assertEqual((fields['One[0].Value']['offset'], fields['One[0].Value']['size']), (12, 4))
            self.assertEqual((fields['Samples']['count'], fields['Samples']['size']), (3, 6))
            values = {'One[0].Flag': 1, 'One[0].Value': 0x12345678,
                      'One[0].Name': 'sample', 'Samples': [3, 5, 7]}
            wire = encode(dict(command, header_size=8), values, catalog['byte_order'])
            self.assertEqual(wire[9:12], bytes(3))  # Real C padding stays clear.
            self.assertEqual(decode(command, wire, 'little'), (values, []))
            packet, = catalog['packets']
            fields = {f['name']: f for f in packet['fields']}
            self.assertEqual((fields['Items[1].Value']['offset'], fields['Items[1].Name']['offset']), (36, 40))
            self.assertEqual(packet['size'], 48)
