import json
from math import isclose
from pathlib import Path
import shutil
import tempfile
import unittest

from sensors.orbit import Orbit, default_elements, from_tle, preview
from sensors.session import load_session, planned_settings, waveform_for

ROOT=Path(__file__).resolve().parents[2]


class OrbitSignalTest(unittest.TestCase):
    def test_two_body_and_j2_element_propagation(self):
        elements = dict(default_elements(), perigee=500, apogee=550, inclination=90, node=20,
                        argument=0, anomaly=0, model='Two-body', epoch='2000-01-01T12:00:00Z')
        orbit=Orbit(elements)
        lon, lat, altitude = orbit.sample(0)[:3]
        self.assertAlmostEqual(lon, (20 - 280.46061837 + 180) % 360 - 180)
        self.assertAlmostEqual(lat, 0)
        self.assertAlmostEqual(altitude, 500)
        self.assertAlmostEqual(orbit.sample(orbit.period/2)[2], 550)
        self.assertTrue(5700 < Orbit(dict(elements,perigee=550)).period < 5800)
        result = preview({'elements':default_elements()})
        self.assertTrue(.94 < result['drift'] < 1.03)
        self.assertEqual(len(result['points']),361)
        self.assertTrue({row[3] for row in result['points']} == {False, True})

    def test_import_tle_validates_identifiers_epoch_and_checksum(self):
        lines = ('1 23455U 94089A   97320.90946019  .00000140  00000-0  10191-3 0  2621\n'
                 '2 23455  99.0090 272.6745 0008546 223.1686 136.8816 14.11711747148495')
        elements=from_tle(lines,'J2')
        self.assertTrue(elements['epoch'].startswith('1997-11-16'))
        self.assertAlmostEqual(elements['inclination'],99.009)
        self.assertTrue(800 < elements['perigee'] < elements['apogee'] < 900)
        with self.assertRaisesRegex(ValueError,'checksum'):
            from_tle(lines[:-1]+'0','J2')
        with self.assertRaisesRegex(ValueError,'identifiers'):
            from_tle(lines.replace('2 23455','2 23456'),'J2')

    def test_legacy_session_roundtrip_and_orbit_signal_matches_flight_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder in ('project/drivers','project/boards','sensors'):
                shutil.copytree(ROOT/folder,root/folder)
            device=dict(id='temp',name='Temperature',model='tmp105',address=72,values={'temperature':23000},bus='i2c-bus.1')
            (root/'project/config.json').write_text(json.dumps(dict(schema_version=1,board='raspi4b',os='raspios',devices=[device],apps=[],buses=['i2c-bus.1'])))
            (root/'sensors/signals.py').write_text("SESSION = {'interval':1, 'sensors':None}\n")
            session=load_session(root)['settings']
            elements=session['orbit']
            settings=session['sensors'][0]
            settings['signals']['temperature']=dict(initial=-5,amplitude=12,function='orbit.sunlight',enabled=True,noise='none')
            for name,content in planned_settings(root,session).items():
                (root/name).write_text(content)
            restored=load_session(root)['settings']
            self.assertEqual(restored['orbit'],elements)
            waveform=waveform_for(root,device,restored['sensors'][0])
            timeline=preview({'elements':elements})
            for lit in (False,True):
                step=next(i for i,row in enumerate(timeline['points']) if row[3] is lit)
                self.assertTrue(isclose(waveform.sample(step*timeline['period']/360,0),7 if lit else -5))


    def test_solar_response_matches_preview_after_seeking(self):
        elements = dict(default_elements(), epoch="2026-11-19T00:00:00Z")
        orbit = Orbit(elements)
        tau = 850
        result = preview({"elements": elements, "responses": [tau]})
        curve = result["responses"][str(tau)]
        self.assertEqual(curve[0], 0)
        self.assertTrue(.5 < max(curve) <= 1)
        for i in (250, 8, 119, 359):
            t = i * orbit.period / 360
            self.assertAlmostEqual(orbit.illumination(t, tau), curve[i], places=6)
        second = preview({"elements": elements, "responses": [tau], "cycle": 1})
        self.assertAlmostEqual(curve[-1], second["responses"][str(tau)][0], places=6)
