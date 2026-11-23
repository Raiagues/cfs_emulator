"""Preview reads one target's compiler catalog and never opens a downlink."""
import copy
import unittest
from unittest.mock import Mock, patch

from jobs.service import Laboratory


class GroundPreviewServiceTest(unittest.TestCase):
    def setUp(self):
        self.command = dict(id='DEMO_SET_CC', app='demo', mid=0x1882, code=1, size=12,
                            header_size=999, fields=[dict(name='Data', type='Opaque', format='raw',
                                                        count=1, offset=8, size=4)])
        self.catalog = dict(commands=[self.command], transport={'command_header_size': 8}, byte_order='little')
        self.studio = Mock()
        self.studio.ground_catalog.return_value = self.catalog

    def test_preview_uses_target_catalog_header_without_sending_or_mutating(self):
        before = copy.deepcopy(self.catalog)
        body = {'target': 'physical', 'command_id': 'DEMO_SET_CC', 'values': {'Data': '00000100'}}
        with patch('ground_station.official.socket.socket', side_effect=AssertionError('Preview opened a socket')):
            result = Laboratory.ground_preview(self.studio, body)
        self.studio.ground_catalog.assert_called_once_with('physical')
        self.studio.ground.send.assert_not_called()
        self.studio.ground.start.assert_not_called()
        self.assertEqual(result['size'], 12)
        self.assertEqual(result['payload_hex'], '00000100')
        self.assertEqual(result['segments'][-1]['offset'], 8)
        self.assertEqual(self.catalog, before)

    def test_unknown_commands_overrides_and_incomplete_values_cannot_be_previewed(self):
        base = {'target': 'native', 'command_id': 'DEMO_SET_CC', 'values': {'Data': '00000100'}}
        rejected = [dict(base, command_id='UNKNOWN_CC'), dict(base, header_size=8),
                    dict(base, values=[]), dict(base, values={'Data': ''}),
                    dict(base, values={'Data': '00000100', 'Unknown': 0})]
        for body in rejected:
            with self.subTest(body=body), self.assertRaises(ValueError):
                Laboratory.ground_preview(self.studio, body)
        self.studio.ground.send.assert_not_called()
