"""Documented app purposes quote the app's own README; nothing is looked up by name."""
from pathlib import Path
import tempfile
import unittest

from interface.backend.architecture import _documented_purpose, summarize_application
from interface.backend.source_index import SourceIndex


ROOT = Path(__file__).resolve().parents[1]


class DocumentedPurposeTest(unittest.TestCase):
    def purpose(self, readme, name='thermal'):
        with tempfile.TemporaryDirectory(prefix='purpose-') as directory:
            root = Path(directory).resolve()
            app = root / 'cFS/apps' / name
            app.mkdir(parents=True)
            if isinstance(readme, bytes):
                (app / 'README.md').write_bytes(readme)
            elif readme is not None:
                (app / 'README.md').write_text(readme)
            return _documented_purpose({'name': name, 'path': 'cFS/apps/' + name}, root)

    def test_skips_the_cfs_membership_sentence(self):
        readme = ('# Thermal Control (TC)\n\n## Introduction\n\n'
                  'The Thermal application is a cFS application that is a plug in to the cFE.\n\n'
                  'The Thermal application keeps the [heaters](docs/heaters.md) inside `limits`. It logs.\n')
        found = self.purpose(readme)
        self.assertEqual(found['text'], 'The Thermal application keeps the heaters inside limits.')
        self.assertEqual(found['source'], {'path': 'cFS/apps/thermal/README.md', 'line': 7, 'kind': 'documentation'})

    def test_text_under_the_title_without_an_introduction_heading(self):
        readme = ('![badge](x.svg)\n# Thermal\n\nThis repository contains thermal, which is a framework component.\n\n'
                  'This lab application drives a heater.\n\n## Building\n\nRun make to build.\n')
        found = self.purpose(readme)
        self.assertEqual(found['text'], 'This lab application drives a heater.')

    def test_other_sections_and_code_blocks_are_not_purpose(self):
        self.assertIsNone(self.purpose('# Thermal\n\n## Building\n\nRun make to build the app.\n'))
        self.assertIsNone(self.purpose('# Thermal\n\n```\nmake prep\n```\n\n- a list item\n'))

    def test_missing_readme_keeps_the_source_summary(self):
        self.assertIsNone(self.purpose(None))

    def test_unreadable_readme_is_reported_instead_of_ignored(self):
        found = self.purpose(b'# Thermal\n\nThe \xff application.\n')
        self.assertEqual(set(found), {'error'})
        self.assertTrue(found['error'].startswith('README.md could not be read: '), found)
        self.assertEqual(set(self.purpose('x' * 128_001)), {'error'})

    def test_bundled_app_name_without_readme_gets_no_description(self):
        # A local app named like a NASA app must not inherit its documentation.
        with tempfile.TemporaryDirectory(prefix='purpose-') as directory:
            root = Path(directory).resolve()
            source = root / 'cFS/apps/hs/fsw/src/hs_app.c'
            source.parent.mkdir(parents=True)
            source.write_text('void HS_AppMain(void) { CFE_ES_RunLoop(0); }\n')
            app = {'name': 'hs', 'path': 'cFS/apps/hs', **SourceIndex(root).application(root / 'cFS/apps/hs')}
            behavior = summarize_application(app, 'HS_AppMain', root=root)
        self.assertIsNone(behavior['purpose_source'])
        self.assertIsNone(behavior['purpose_error'])
        self.assertEqual(behavior['description'], behavior['source_summary'])


@unittest.skipUnless((ROOT / 'cFS/apps/hs/README.md').is_file(), 'NASA cFS checkout not available')
class NasaReadmeTest(unittest.TestCase):
    def test_quotes_the_first_purpose_sentence(self):
        expected = {
            'sample_app': 'This sample application is a non-flight example application implementation for the cFS Bundle.',
            'hs': 'The HS application provides functionality for Application Monitoring, Event Monitoring, '
                  'Hardware Watchdog Servicing, Execution Counter Reporting (optional), and CPU Aliveness Indication (via UART).',
            'sbn': 'The SBN application connects the cFE Software Bus (SB) to other buses, bridging the publish/subscribe '
                   'messaging service to separate cFS instances in separate partitions, processes, processors, and/or networks.',
        }
        for name, text in expected.items():
            with self.subTest(app=name):
                found = _documented_purpose({'name': name, 'path': 'cFS/apps/' + name}, ROOT)
                self.assertEqual(found['text'], text)


if __name__ == '__main__':
    unittest.main()
