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

    def test_connect_waits_for_user_before_first_answer(self):
        with tempfile.TemporaryDirectory() as root:
            ground = GroundStation(root)
            fake = MagicMock()
            with patch('ground_station.official', fake, create=True), patch.object(ground, '_enable_downlink') as enable:
                snapshot = ground.start('127.0.0.1', listen_host='127.0.0.1', catalog=CATALOG)
                self.assertEqual(snapshot['commands'], [])
                self.assertFalse(snapshot['first_flight']['automatic'])
                self.assertEqual(snapshot['first_flight']['return_host'], '127.0.0.1')
                enable.assert_not_called()
                # The station learns about a target only after a confirmed NOOP.
                ground._learned_targets.add(ground._target)
                snapshot = ground.start('127.0.0.1', listen_host='127.0.0.1', catalog=CATALOG)
                self.assertTrue(snapshot['first_flight']['automatic'])
                self.assertFalse(snapshot['first_flight']['event'])
                enable.assert_called_once_with('TO_LAB_OUTPUT_ENABLE_CC', '127.0.0.1')
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
