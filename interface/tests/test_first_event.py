import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ground_station.first_event import FirstEvent
from ground_station.round_trip import PassedTests
from ground_station.station import GroundStation


CATALOG = {
    'build_target': 'native',
    'transport': {'command_header_size': 8, 'telemetry_port': 2234, 'command_port': 1234, 'evs_information': 2},
    'packets': [{'id': 'SAMPLE_APP_HK_TLM_MID', 'app': 'sample_app', 'mid': 2179,
                 'fields': [{'name': 'CommandCounter'}]}],
    'commands': [{'id': 'TO_LAB_OUTPUT_ENABLE_CC', 'app': 'to_lab'},
                 {'id': 'SAMPLE_APP_NOOP_CC', 'app': 'sample_app'},
                 {'id': 'SCIENCE_NOOP_CC', 'app': 'science', 'source': 'mission/apps/science/config/commands.h'},
                 {'id': 'OTHER_NOOP_CC', 'app': 'other', 'source': 'cFS/apps/other/config/commands.h'}]
}


def packet(index, app, values, mid=2056):
    return {'event_id': index, 'received_at': index + .5, 'mid': mid, 'app': app, 'values': values, 'errors': []}


class FirstEventTest(unittest.TestCase):
    def test_only_passed_runs_survive_a_new_station(self):
        with tempfile.TemporaryDirectory() as root:
            receipts = PassedTests(root)
            run = {'status': 'waiting', 'sent': {'app': 'demo', 'sent_at': 1},
                   'command': 'DEMO_ACTION_CC', 'finished_at': 3, 'test_id': 'receipt',
                   'steps': [{'observation': {'mid': 2056, 'sequence': 21}}]}
            catalog = dict(CATALOG, build_fingerprint='flight-build')
            receipts.record(run, catalog)
            self.assertEqual(receipts.read(), [])
            receipts.record(dict(run, status='passed'), catalog)
            restored = GroundStation(root)
            self.assertEqual(restored.passed_tests('physical'), [])
            saved, = restored.passed_tests('native')
            self.assertEqual((saved['app'], saved['command'], saved['build']),
                             ('demo', 'DEMO_ACTION_CC', 'flight-build'))
            self.assertEqual(saved['observations'][0]['sequence'], 21)
            self.assertFalse(restored.snapshot()['first_flight']['event'])

    def test_connect_respects_the_requesting_browsers_last_reset(self):
        with tempfile.TemporaryDirectory() as root:
            ground = GroundStation(root)
            fake = MagicMock()
            with patch('ground_station.official', fake, create=True), patch.object(ground, '_enable_downlink') as enable:
                snapshot = ground.start('127.0.0.1', listen_host='127.0.0.1', catalog=CATALOG)
                self.assertEqual(snapshot['commands'], [])
                self.assertFalse(snapshot['first_flight']['automatic'])
                self.assertEqual(snapshot['first_flight']['return_host'], '127.0.0.1')
                enable.assert_not_called()
                # Receive a compiled INFO event after a manual NOOP. Record the flight
                # timestamp, so unrelated packets cannot satisfy a browser's replay.
                reply = {'PacketID.AppName': 'SAMPLE_APP', 'PacketID.EventType': 2,
                         'PacketID.EventID': 3, 'Message': 'SAMPLE: NOOP command'}
                fake.RoutingService.get_pkt_id.return_value = '0808'
                page = MagicMock()
                fake.Definitions.return_value.pages = {0x0808: page}
                def receive(at, sequence):
                    data = bytes.fromhex('0808c0') + bytes([sequence]) + bytes.fromhex('00010000')
                    ground._definitions[0x0808] = {'name': 'EVS', 'app': 'cfe_evs'}
                    with patch('ground_station.station.time.time', return_value=at):
                        ground._accept(data)
                ground.first_contact.sent({'id':'SAMPLE_APP_NOOP_CC', 'event_id':0})
                page.read.return_value = reply, []
                receive(10, 1)
                page.read.return_value = {**reply, 'Message':'Unrelated'}, []
                receive(20, 2)
                # Same browser after reset, before another qualifying reply.
                parameters = dict(listen_host='127.0.0.1', catalog=CATALOG, journey_reset_at=15)
                self.assertFalse(ground.start('127.0.0.1', **parameters)['first_flight']['automatic'])
                enable.assert_not_called()
                # A browser with no reset still has the original learning.
                snapshot = ground.start('127.0.0.1', listen_host='127.0.0.1', catalog=CATALOG)
                self.assertTrue(snapshot['first_flight']['automatic'])
                self.assertFalse(snapshot['first_flight']['event'])
                enable.assert_called_once_with('TO_LAB_OUTPUT_ENABLE_CC', '127.0.0.1')
                ground.first_contact.sent({'id':'SAMPLE_APP_NOOP_CC', 'event_id':0})
                page.read.return_value = reply, []
                receive(30, 1)
                self.assertTrue(ground.start('127.0.0.1', **parameters)['first_flight']['automatic'])
                with self.assertRaises(ValueError):
                    ground.start('127.0.0.1', **{**parameters, 'journey_reset_at':-1})
                self.assertTrue(ground.snapshot()['connected'])
                ground.stop()

    def test_only_the_first_app_command_reply_and_its_hk_advance(self):
        flight = FirstEvent(CATALOG)
        self.assertNotIn('OTHER_NOOP_CC', flight.noops)
        self.assertIn('SCIENCE_NOOP_CC', flight.noops)
        reply = {'PacketID.AppName': 'SAMPLE_APP', 'PacketID.EventType': 2, 'PacketID.EventID': 3,
                 'Message': 'SAMPLE: NOOP command'}
        flight.received(packet(1, 'sample_app', {'CommandCounter': 8}, 2179))
        flight.received(packet(2, 'cfe_evs', reply))
        flight.sent({'id': 'SAMPLE_APP_NOOP_CC', 'event_id': 3})
        flight.received(packet(2, 'cfe_evs', reply))
        flight.received(packet(4, 'other', reply))
        flight.received(packet(5, 'cfe_evs', {**reply, 'PacketID.AppName': 'OTHER'}))
        flight.received(packet(6, 'cfe_evs', {**reply, 'PacketID.EventType': 3}))
        flight.received(packet(7, 'cfe_evs', {**reply, 'Message': 'Initialized'}))
        self.assertFalse(flight.snapshot()['event'])
        flight.received(packet(8, 'cfe_evs', reply))
        self.assertTrue(flight.snapshot()['event'])
        self.assertFalse(flight.snapshot()['answer'])
        flight.received(packet(9, 'sample_app', {'CommandCounter': 8}, 2179))
        self.assertFalse(flight.snapshot()['answer'])
        flight.received(packet(10, 'sample_app', {'CommandCounter': 9}, 2179))
        self.assertTrue(flight.snapshot()['answer'])
        self.assertEqual(flight.snapshot()['receipt']['increase'], 10)
