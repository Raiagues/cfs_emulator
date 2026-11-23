import copy
from functools import reduce
from operator import xor
import unittest
from unittest.mock import patch

from ground_station.official import encode, preview


class PacketPreviewTest(unittest.TestCase):
    def command(self, **changes):
        return dict(id='DEMO_NOOP_CC', app='demo', mid=0x1882, code=0,
                    header_size=8, size=8, fields=[], **changes)

    def test_known_noop_is_exact_and_preview_does_not_open_a_socket(self):
        command = self.command()
        with patch('ground_station.official.socket.socket', side_effect=AssertionError('Preview sent data')):
            result = preview(command, {}, 'little')
        self.assertEqual(result['hex'], '1882c000000100a4')
        self.assertEqual(result['length_field'], 1)
        self.assertEqual(result['checksum'], 0xa4)
        self.assertTrue(result['checksum_valid'])
        self.assertEqual([s['name'] for s in result['segments']],
                         ['MID', 'Sequence', 'Length', 'Function code', 'Checksum'])

    def test_compiler_offsets_padding_arrays_and_abi_order_match_send(self):
        command = self.command()
        command.update(code=7, size=24, fields=[
            dict(name='Values', type='uint16[2]', format='H', count=2, offset=12, size=4),
            dict(name='Flag', type='uint8', format='B', count=1, offset=8, size=1),
            dict(name='Payload.Reserved', type='uint16', format='H', count=1, offset=18, size=2)])
        values = {'Values': [0x1234, 0xabcd], 'Flag': 9}
        before = copy.deepcopy((command, values))
        for order, expected in [('little', '3412cdab'), ('big', '1234abcd')]:
            result = preview(command, values, order)
            packet = bytes.fromhex(result['hex'])
            self.assertEqual(packet, encode(command, values, order))
            self.assertEqual(reduce(xor, packet), 0xff)
            self.assertEqual(result['length_field'], len(packet) - 7)
            self.assertEqual(''.join(s['hex'] for s in result['segments']), result['hex'])
            field = next(s for s in result['segments'] if s['name'] == 'Values')
            self.assertEqual((field['offset'], field['hex'], field['value']), (12, expected, values['Values']))
            self.assertEqual([(s['offset'], s['size']) for s in result['segments'] if s['kind'] == 'padding'],
                             [(9, 3), (16, 2), (18, 2), (20, 4)])
        self.assertEqual((command, values), before)

    def test_utf8_text_uses_byte_length_and_null_padding(self):
        command = self.command()
        command.update(size=12, fields=[dict(name='Name', type='char[4]', format='s', count=4, offset=8, size=4)])
        result = preview(command, {'Name': 'é'}, 'little')
        self.assertEqual(result['payload_hex'], 'c3a90000')
        self.assertEqual(result['segments'][-1]['value'], 'é')
        with self.assertRaisesRegex(ValueError, 'fewer than 4 bytes'):
            preview(command, {'Name': 'éé'}, 'little')

    def test_invalid_fields_fail_instead_of_displaying_invented_bytes(self):
        command = self.command()
        command.update(size=9, fields=[dict(name='Level', type='uint8', format='B', count=1, offset=8, size=1)])
        for values in ({}, {'Level': 256}, {'Level': 1, 'Missing': 2}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                preview(command, values, 'little')
        with self.assertRaisesRegex(ValueError, 'Unknown byte order'):
            preview(command, {'Level': 1}, 'invalid')

    def test_large_integer_is_exact_and_json_safe(self):
        command = self.command()
        command.update(size=16, fields=[dict(name='Counter', type='uint64', format='Q', count=1, offset=8, size=8)])
        result = preview(command, {'Counter': '18446744073709551615'}, 'little')
        self.assertEqual(result['payload_hex'], 'ffffffffffffffff')
        self.assertEqual(result['segments'][-1]['value'], '18446744073709551615')


if __name__ == '__main__':
    unittest.main()
