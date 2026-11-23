from pathlib import Path
import tempfile
import unittest

from ground_station.contact_routes import first_contact_routes


class ContactRoutesTest(unittest.TestCase):
    def test_all_active_apps_core_modules_and_cross_app_mid_subscribers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps = [('alpha', 'apps/alpha', 'ALPHA', 'ALPHA_CMD_MID', 'ALPHA_HK_TLM_MID'),
                    ('observer', 'apps/observer', 'OBSERVER', 'OBSERVER_CMD_MID', 'OBSERVER_HK_TLM_MID'),
                    ('cfe_time', 'cfe/modules/time', 'CFE_TIME', 'CFE_TIME_CMD_MID', 'CFE_TIME_HK_TLM_MID'),
                    ('inactive', 'apps/inactive', 'INACTIVE', 'ALPHA_CMD_MID', 'ALPHA_HK_TLM_MID')]
            for name, relative, symbol, command_mid, telemetry_mid in apps:
                source = root / 'cFS' / relative / 'fsw/src' / (name + '.c')
                source.parent.mkdir(parents=True)
                source.write_text(f"""
#define {command_mid} 0x1810
#define {telemetry_mid} 0x0810
void {symbol}_Init(void)
{{
    CFE_SB_Subscribe(CFE_SB_ValueToMsgId({command_mid}), {symbol}.CommandPipe);
    CFE_MSG_Init(CFE_MSG_PTR({symbol}.Hk.TelemetryHeader), CFE_SB_ValueToMsgId({telemetry_mid}), sizeof({symbol}_Hk_t));
}}
void {symbol}_Send(void)
{{
    CFE_SB_TransmitMsg(CFE_MSG_PTR({symbol}.Hk.TelemetryHeader), true);
}}
""")
            catalog = {
                'apps': [dict(name=name, kind='core' if name.startswith('cfe_') else 'app')
                         for name, *_ in apps if name != 'inactive'],
                'commands': [dict(id=name + '_NOOP', app=name, mid=0x1880 if name == 'cfe_time' else 0x1877,
                                  mid_symbol=cmd) for name, _, _, cmd, _ in apps if name != 'inactive'],
                'packets': [dict(id=tlm, app=name, mid=0x0880 if name == 'cfe_time' else 0x0877, mid_symbol=tlm)
                            for name, _, _, _, tlm in apps if name != 'inactive'],
                'transport': {'subscriptions': [{'mid': 0x0877}, {'mid': 0x0880}]}}
            routes = first_contact_routes(root, catalog)
            self.assertEqual(set(routes['commands']), {'alpha_NOOP', 'observer_NOOP', 'cfe_time_NOOP'})
            self.assertEqual({r['app'] for r in routes['commands']['alpha_NOOP']}, {'alpha', 'observer'})
            self.assertEqual({r['pipe'] for r in routes['commands']['observer_NOOP']},
                             {'ALPHA.CommandPipe', 'OBSERVER.CommandPipe'})
            core, = routes['commands']['cfe_time_NOOP']
            self.assertEqual(core['pipe'], 'CFE_TIME.CommandPipe')
            self.assertEqual(core['source']['path'], 'cFS/cfe/modules/time/fsw/src/cfe_time.c')
            self.assertEqual({p['app'] for p in routes['returns'][str(0x0877)]['publishers']}, {'alpha', 'observer'})
            self.assertEqual(routes['returns'][str(0x0880)]['publishers'][0]['app'], 'cfe_time')
            self.assertNotIn('inactive', str(routes))
            self.assertEqual(set(routes['applications']), {'alpha', 'observer', 'cfe_time'})
            self.assertEqual(routes['applications']['cfe_time']['subscriptions'][0]['mid'], 0x1880)
            self.assertEqual(routes['applications']['cfe_time']['publications'][0]['mid'], 0x0880)
            catalog['transport']['subscriptions'] = []
            self.assertEqual(first_contact_routes(root, catalog)['returns'], {})

    def test_const_mid_array_and_pointer_aliases_have_real_source_evidence(self):
        from ground_station.contact_routes import _indirect_routes
        from project.source_index import SourceIndex
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'cFS/apps/demo'
            source = app / 'fsw/src/demo.c'
            source.parent.mkdir(parents=True)
            source.write_text("""
void Init(void) {
    const CFE_SB_MsgId_Atom_t MIDS[] = { DEMO_CMD_MID, DEMO_SEND_HK_MID };
    for (i = 0; i < (sizeof(MIDS) / sizeof(MIDS[0])); ++i) {
        CFE_SB_Subscribe(CFE_SB_ValueToMsgId(MIDS[i]), Demo.Pipe);
    }
    CFE_MSG_Init(CFE_MSG_PTR(Demo.Hk.TelemetryHeader), CFE_SB_ValueToMsgId(DEMO_HK_TLM_MID), sizeof(Demo.Hk));
}
void SendHk(void) {
    Hk_t *packet;
    packet = &Demo.Hk;
    CFE_SB_TransmitMsg(CFE_MSG_PTR(packet->TelemetryHeader), true);
}
void SendAllocated(void) {
    Packet_t *view;
    Buffer_t *buffer;
    buffer = Allocate();
    view = (void *)buffer;
    CFE_MSG_Init(CFE_MSG_PTR(view->TelemetryHeader), CFE_SB_ValueToMsgId(DEMO_DATA_TLM_MID), sizeof(*view));
    CFE_SB_TransmitBuffer(buffer, true);
}
void PartialLoop(void) {
    const CFE_SB_MsgId_Atom_t MIDS[] = { WRONG_CMD_MID, WRONG_SEND_HK_MID };
    for (i = 1; i < (sizeof(MIDS) / sizeof(MIDS[0])); ++i) {
        CFE_SB_Subscribe(CFE_SB_ValueToMsgId(MIDS[i]), Wrong.Pipe);
    }
}
void AmbiguousPointer(void) {
    Hk_t *packet;
    packet = &Demo.Hk;
    packet = &Other.Hk;
    CFE_SB_TransmitMsg(CFE_MSG_PTR(packet->TelemetryHeader), true);
}
void LateAssignment(void) {
    Hk_t *packet;
    CFE_SB_TransmitMsg(CFE_MSG_PTR(packet->TelemetryHeader), true);
    packet = &Demo.Hk;
}
""")
            subscriptions, publications = _indirect_routes(root, SourceIndex(root).application(app))
            self.assertEqual({s['mid']['symbol'] for s in subscriptions}, {'DEMO_CMD_MID', 'DEMO_SEND_HK_MID'})
            self.assertTrue(all(s['pipe'] == 'Demo.Pipe' and len(s['via']) == 2 for s in subscriptions))
            self.assertEqual({p['mid']['symbol'] for p in publications}, {'DEMO_HK_TLM_MID', 'DEMO_DATA_TLM_MID'})
            self.assertTrue(all(len(p['publishers']) == 1 for p in publications))
            for publication in publications:
                publisher = publication['publishers'][0]
                lines = source.read_text().splitlines()
                self.assertIn('CFE_SB_Transmit', lines[publisher['call_source']['line'] - 1])
                self.assertEqual(len(publisher['via']), 1)

    def test_unresolved_routes_are_empty_not_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = {'apps': [{'name': 'unavailable'}],
                       'commands': [{'id': 'MISSING_NOOP_CC', 'app': 'unavailable', 'mid': 0x1881}],
                       'packets': [{'id': 'MISSING_HK_TLM_MID', 'app': 'unavailable', 'mid': 0x0881}],
                       'transport': {'subscriptions': [{'mid': 0x0881}]}}
            routes = first_contact_routes(Path(directory), catalog)
            self.assertEqual(routes['commands']['MISSING_NOOP_CC'], [])
            self.assertEqual(routes['returns'][str(0x0881)]['publishers'], [])
            self.assertEqual(routes['applications']['unavailable'], {'subscriptions': [], 'publications': []})
            self.assertNotIn('ingress', routes)
            self.assertNotIn('egress', routes)


if __name__ == '__main__':
    unittest.main()
