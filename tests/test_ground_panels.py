"""Ground Station packet view: a sample flagged Valid = 0 is never shown as current.

Renders interface/static/panels.js with Node when it is installed.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RENDER = r'''
const {renderTelemetry} = await import(process.argv[2]);
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
const hex = value => '0x' + Number(value).toString(16).padStart(4, '0');
const [fields, values] = JSON.parse(process.argv[3]);
const definition = {id: 'DEMO_Probe_Tlm_t', app: 'demo', mid: 0x0A01, size: 32, fields};
const packet = {mid: 0x0A01, app: 'demo', count: 1, received_at: 1, bytes: 32, values};
const state = {target: 'qemu', groundTab: 'telemetry', catalog: {packets: [definition], commands: []},
               ground: {target: 'qemu', connected: true, packets: [packet], history: [packet]}};
const html = renderTelemetry(state, {esc, hex});
const rows = [...html.matchAll(/<div( class="gs-invalid-field"[^>]*)?><code>([^<]+)<\/code><span>[^<]*<\/span><\/div>/g)];
const reading = html.match(/<div class="gs-reading ?([a-z]*)"><strong>([^<]*)<\/strong>/);
const view = {invalid: rows.filter(row => row[1]).map(row => row[2]), rows: rows.map(row => row[2]),
              reading: reading && {invalid: reading[1] === 'invalid', text: reading[2]}};
console.log(JSON.stringify(view));
'''


def field(name, kind):
    return {'name': name, 'type': kind, 'format': {'int32': 'i', 'uint8': 'B', 'uint32': 'I', 'float': 'f'}[kind], 'count': 1}


SENSOR = [field('Value', 'int32'), field('Status', 'int32'), field('ReadCounter', 'uint32'),
          field('ErrorCounter', 'uint32'), field('Valid', 'uint8')]


@unittest.skipUnless(shutil.which('node'), 'Node.js not installed')
class PacketViewTest(unittest.TestCase):
    def render(self, fields, values):
        with tempfile.TemporaryDirectory(prefix='panels-') as directory:
            script = Path(directory) / 'render.mjs'
            script.write_text(RENDER)
            # panels.js is a browser module without a package.json declaring it.
            command = ['node', '--experimental-default-type=module', str(script), str(ROOT / 'interface/static/panels.js'), json.dumps([fields, values])]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout.splitlines()[-1])

    def test_valid_sample_is_not_marked(self):
        view = self.render(SENSOR, {'Value': 23500, 'Status': 0, 'ReadCounter': 4, 'ErrorCounter': 0, 'Valid': 1})
        self.assertEqual(view['rows'], ['Value', 'Status', 'ReadCounter', 'ErrorCounter', 'Valid'])
        self.assertEqual(view['invalid'], [])

    def test_stale_or_zeroed_sample_is_marked_invalid(self):
        for value in (0, 18500):
            with self.subTest(value=value):
                view = self.render(SENSOR, {'Value': value, 'Status': -2, 'ReadCounter': 9, 'ErrorCounter': 9, 'Valid': 0})
                # Status and counters describe the failed read; they stay readable as they are.
                self.assertEqual(view['invalid'], ['Value'])

    def test_featured_reading_keeps_hiding_invalid_samples(self):
        fields = [field('Temperature', 'float'), field('Valid', 'uint8')]
        self.assertEqual(self.render(fields, {'Temperature': 21.5, 'Valid': 0})['reading'], {'invalid': True, 'text': '—'})
        self.assertEqual(self.render(fields, {'Temperature': 21.5, 'Valid': 1})['reading'], {'invalid': False, 'text': '21.5'})

    def test_packets_without_validity_are_unchanged(self):
        view = self.render([field('CommandCounter', 'uint8'), field('Value', 'int32')], {'CommandCounter': 1, 'Value': 0})
        self.assertEqual(view['invalid'], [])


if __name__ == '__main__':
    unittest.main()
