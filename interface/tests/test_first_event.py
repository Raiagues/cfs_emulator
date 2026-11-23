import copy
import socket
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

    def test_connections_and_downlink_packets_never_transmit_a_command(self):
        with tempfile.TemporaryDirectory() as root, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as flight:
            flight.bind(('127.0.0.1', 0))
            flight.settimeout(.1)
            ground = GroundStation(root)
            self.addCleanup(ground.stop)
            catalog = copy.deepcopy(CATALOG)
            catalog.update(byte_order='little', packets=[])
            catalog['transport'].update(command_port=flight.getsockname()[1], telemetry_port=0)
            catalog['commands'][1].update(mid=0x1882, code=0, fields=[], size=8)
            for _ in range(2):
                ground.start('127.0.0.1', '127.0.0.1', catalog=catalog)
                flight.sendto(bytes.fromhex('0808c000000000'), ground._receiver.socket.getsockname())
                with ground._updates:
                    self.assertTrue(ground._updates.wait_for(lambda: ground._received > 0, timeout=2))
                with self.assertRaises(TimeoutError):
                    flight.recvfrom(64)
                self.assertEqual(ground.snapshot()['commands'], [])
                ground.send('SAMPLE_APP_NOOP_CC')
                self.assertEqual(flight.recvfrom(64)[0].hex(), '1882c000000100a4')
                ground.stop()

    def test_each_enable_requires_downlink_after_its_own_send(self):
        flight = FirstEvent(CATALOG)
        enable = 'TO_LAB_OUTPUT_ENABLE_CC'
        flight.sent({'id': enable, 'event_id': 2})
        flight.received({**packet(3, 'to_lab', {}), 'errors': ['bad packet']})
        self.assertIsNone(flight.snapshot()['downlink_receipt'])
        flight.received({**packet(4, 'sample_app', {'CommandCounter': 7}, 2179), 'sequence': 5})
        self.assertEqual(flight.snapshot()['downlink_receipt'],
                         {'send_id': 2, 'mid': 2179, 'sequence': 5, 'received_at': 4.5})
        flight.sent({'id': enable, 'event_id': 7})
        self.assertIsNone(flight.snapshot()['downlink_receipt'])
        flight.received(packet(6, 'to_lab', {}))
        flight.received({**packet(8, 'to_lab', {}), 'errors': ['bad packet']})
        self.assertIsNone(flight.snapshot()['downlink_receipt'])
        flight.received(packet(9, 'to_lab', {}))
        self.assertEqual(flight.snapshot()['downlink_receipt'],
                         {'send_id': 7, 'mid': 2056, 'sequence': None, 'received_at': 9.5})

    def test_authored_command_requires_its_compiled_event_and_counter_increment(self):
        catalog = copy.deepcopy(CATALOG)
        catalog['packets'][0]['app'] = 'orbit_demo'
        command = 'ORBIT_DEMO_SET_RATE_CC'
        flight = FirstEvent(catalog, authored={command:'orbit_demo'}, information_ids={command:[15]})
        flight.received(packet(1, 'orbit_demo', {'CommandCounter': 9}, 2179))
        flight.sent({'id':command, 'event_id':2, 'values':{'Rate_Hz':17}})
        event = {'PacketID.AppName':'ORBIT_DEMO', 'PacketID.EventType':2, 'PacketID.EventID':1,
                 'Message':'Initialized'}
        flight.received(packet(3, 'cfe_evs', event))
        flight.received(packet(4, 'orbit_demo', {'CommandCounter':10}, 2179))
        self.assertFalse(flight.snapshot()['answer'])
        flight.received(packet(5, 'cfe_evs', {**event, 'PacketID.EventID':15, 'Message':'Rate set to 17 Hz'}))
        self.assertEqual(flight.snapshot()['receipt']['reply'], 5)
        self.assertTrue(flight.snapshot()['answer'])

    def test_only_the_matching_app_command_reply_and_its_hk_advance(self):
        flight = FirstEvent(CATALOG)
        self.assertIn('OTHER_NOOP_CC', flight.noops)
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


class RepeatedCommandReceiptTest(unittest.TestCase):
    def tracker(self, information_ids=None):
        catalog = copy.deepcopy(CATALOG)
        catalog['packets'][0].update(app='orbit_demo')
        catalog['packets'][0]['fields'][0].update(format='B', size=1)
        command = 'ORBIT_DEMO_SET_RATE_CC'
        return FirstEvent(catalog, authored={command: 'orbit_demo'},
                          information_ids=information_ids if information_ids is not None else {command: [15]})

    def event(self, index, event_id=15, app='ORBIT_DEMO', event_type=2):
        return packet(index, 'cfe_evs', {'PacketID.AppName': app, 'PacketID.EventType': event_type,
                                       'PacketID.EventID': event_id, 'Message': 'Rate set to 17 Hz'})

    def test_each_send_requires_a_new_event_and_new_counter(self):
        flight = self.tracker()
        command = 'ORBIT_DEMO_SET_RATE_CC'
        flight.received(packet(1, 'orbit_demo', {'CommandCounter': 9}, 2179))
        flight.sent({'id': command, 'event_id': 2})
        flight.received(self.event(3))
        flight.received(packet(4, 'orbit_demo', {'CommandCounter': 10}, 2179))
        self.assertTrue(flight.snapshot()['answer'])
        flight.sent({'id': command, 'event_id': 5})
        current = flight.snapshot()
        self.assertFalse(current['answer'])
        self.assertFalse(current['event'])
        self.assertEqual(current['receipt']['send_id'], 5)
        self.assertEqual(current['receipt']['baseline'], 10)
        # Replaying an old event, or a different app's event, cannot confirm this send.
        flight.received(self.event(3))
        flight.received(self.event(6, app='SAMPLE_APP'))
        flight.received(packet(7, 'orbit_demo', {'CommandCounter': 11}, 2179))
        self.assertFalse(flight.snapshot()['answer'])
        flight.received(self.event(8))
        self.assertTrue(flight.snapshot()['answer'])
        self.assertEqual(flight.snapshot()['receipt']['reply'], 8)
        self.assertEqual(flight.snapshot()['receipt']['increase'], 7)

    def test_unidentified_info_or_error_cannot_confirm_an_authored_command(self):
        command = 'ORBIT_DEMO_SET_RATE_CC'
        for ids in ({}, {command: []}, {command: [15]}):
            with self.subTest(ids=ids):
                flight = self.tracker(ids)
                flight.received(packet(1, 'orbit_demo', {'CommandCounter': 9}, 2179))
                flight.sent({'id': command, 'event_id': 2})
                flight.received(self.event(3, event_id=1))
                flight.received(self.event(4, event_id=15, event_type=3))
                flight.received(packet(5, 'orbit_demo', {'CommandCounter': 10}, 2179))
                self.assertFalse(flight.snapshot()['answer'])

    def test_unsigned_counter_wrap_uses_the_compiled_field_width(self):
        flight = self.tracker()
        flight.received(packet(1, 'orbit_demo', {'CommandCounter': 255}, 2179))
        flight.sent({'id': 'ORBIT_DEMO_SET_RATE_CC', 'event_id': 2})
        flight.received(self.event(3))
        flight.received(packet(4, 'orbit_demo', {'CommandCounter': 0}, 2179))
        self.assertTrue(flight.snapshot()['answer'])
        self.assertEqual(flight.snapshot()['receipt']['count'], 0)

    def test_send_without_preexisting_hk_does_not_infer_a_baseline(self):
        flight = self.tracker()
        flight.sent({'id': 'ORBIT_DEMO_SET_RATE_CC', 'event_id': 2})
        flight.received(self.event(3))
        flight.received(packet(4, 'orbit_demo', {'CommandCounter': 1}, 2179))
        self.assertFalse(flight.snapshot()['answer'])


class CommandReceiptHistoryTest(unittest.TestCase):
    def test_snapshot_keeps_each_confirmed_send_until_the_session_is_replaced(self):
        command_id = 'ORBIT_DEMO_SET_RATE_CC'
        catalog = copy.deepcopy(CATALOG)
        catalog.update(build_fingerprint='compiled', byte_order='little')
        catalog['commands'] = [
            dict(id='TO_LAB_OUTPUT_ENABLE_CC', app='to_lab', mid=0x1880, code=6, size=8, fields=[]),
            dict(id=command_id, app='orbit_demo', mid=0x1A00, code=4, size=8, fields=[]),
        ]
        catalog['packets'][0].update(app='orbit_demo')
        with tempfile.TemporaryDirectory() as root, patch('ground_station.station.socket.socket') as socket, \
                patch('ground_station.station.official.Receiver') as receiver:
            socket.return_value.sendto.side_effect = lambda data, address: len(data)
            receiver.return_value.connected.return_value = True
            station = GroundStation(root)
            self.addCleanup(station.stop)
            station.journey.observe('native', 'command', {'app': 'orbit_demo', 'command': command_id,
                                                         'build': 'compiled', 'information_ids': [15]})
            station.start('127.0.0.1', '127.0.0.1', catalog=catalog)
            def receive(app, values, mid=2056):
                index = station._record_communication(app, 'telemetry', 18, 1)
                current = packet(index, app, values, mid)
                station._observe_reply(current, station.first_contact, 'event')
                station._observe_reply(current, station.command_reply, 'send')
            enabled = station.send('TO_LAB_OUTPUT_ENABLE_CC')
            receive('orbit_demo', {'CommandCounter': 0}, 2179)
            sent = []
            for rate, count in ((17, 1), (23, 2)):
                sent.append(station.send(command_id))
                receive('cfe_evs', {'PacketID.AppName': 'ORBIT_DEMO', 'PacketID.EventType': 2,
                                   'PacketID.EventID': 15, 'Message': f'Rate set to {rate} Hz'})
                # INFO alone never creates a confirmed history row.
                self.assertNotIn('receipt', station.snapshot()['commands'][-1])
                receive('orbit_demo', {'CommandCounter': count}, 2179)
            snapshot = station.snapshot()
            first, second = snapshot['commands'][1:]
            self.assertEqual(snapshot['commands'][0]['receipt']['send_id'], enabled['event_id'])
            self.assertEqual([row['receipt']['send_id'] for row in (first, second)],
                             [row['event_id'] for row in sent])
            self.assertEqual([row['receipt']['count'] for row in (first, second)], [1, 2])
            self.assertEqual([row['receipt']['message'] for row in (first, second)],
                             ['Rate set to 17 Hz', 'Rate set to 23 Hz'])
            self.assertEqual(snapshot['authored_reply']['receipt']['send_id'], second['event_id'])
            # A reload receives independent copies of both completed receipts.
            first['receipt']['message'] = 'client edit'
            self.assertEqual(station.snapshot()['commands'][1]['receipt']['message'], 'Rate set to 17 Hz')
            station.start('127.0.0.1', '127.0.0.1', catalog=catalog)
            self.assertEqual(station.snapshot()['commands'], [])
            self.assertIsNone(station.snapshot()['authored_reply']['receipt'])
