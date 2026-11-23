import tempfile
import unittest
from unittest.mock import patch

from ground_station.station import GroundStation


class GroundCounterTest(unittest.TestCase):
    def test_session_totals_survive_history_eviction_and_reset_on_reconnect(self):
        commands = [dict(id=name, app=app, mid=mid, code=code, size=8, fields=[])
                    for name, app, mid, code in [('TO_LAB_OUTPUT_ENABLE_CC', 'to_lab', 0x1880, 6),
                                                ('SAMPLE_APP_NOOP_CC', 'sample_app', 0x1882, 0)]]
        catalog = dict(build_target='native', byte_order='little', commands=commands,
                       transport={'command_header_size': 8, 'command_port': 1234, 'telemetry_port': 2234},
                       packets=[dict(id='SAMPLE_APP_HK_TLM_MID', name='Sample HK', app='sample_app',
                                     mid=0x0883, size=16, fields=[])])
        with tempfile.TemporaryDirectory() as directory, patch('ground_station.station.socket.socket') as socket, \
                patch('ground_station.station.official.Receiver') as receiver:
            socket.return_value.sendto.side_effect = lambda packet, address: len(packet)
            receiver.return_value.connected.return_value = True
            station = GroundStation(directory)
            station.start('127.0.0.1', '127.0.0.1', catalog=catalog)
            for _ in range(140):
                station.send('SAMPLE_APP_NOOP_CC')
            station.send('TO_LAB_OUTPUT_ENABLE_CC')
            data = bytes.fromhex('0883c0000009') + bytes(10)
            for _ in range(300):
                station._accept(data)
            station._accept(b'bad')
            result = station.snapshot()
            self.assertEqual(len(result['commands']), 100)
            self.assertEqual(len(result['history']), 256)
            self.assertEqual(result['communication']['totals'],
                             dict(commands_sent=141, telemetry_received=300, malformed=1))
            self.assertEqual(result['communication']['commands'],
                             {'SAMPLE_APP_NOOP_CC': 140, 'TO_LAB_OUTPUT_ENABLE_CC': 1})
            self.assertEqual(result['packets'][0]['count'], 300)
            self.assertEqual(sum(app['commands_sent'] for app in result['communication']['apps']), 141)
            socket.return_value.sendto.side_effect = OSError('test send failure')
            with self.assertRaises(ValueError):
                station.send('SAMPLE_APP_NOOP_CC')
            self.assertEqual(station.snapshot()['communication']['totals']['commands_sent'], 141)
            socket.return_value.sendto.side_effect = lambda packet, address: len(packet)
            station.start('127.0.0.1', '127.0.0.1', catalog=catalog)
            reset = station.snapshot()
            self.assertEqual(reset['communication']['totals'], dict(commands_sent=0, telemetry_received=0, malformed=0))
            self.assertEqual(reset['communication']['commands'], {})
            self.assertEqual(reset['packets'], [])
            station.stop()


if __name__ == '__main__':
    unittest.main()
