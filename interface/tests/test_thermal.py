import unittest

from sensors.orbit import Orbit, THERMAL_SIZES, ThermalMaterial, default_elements, preview


class ThermalTest(unittest.TestCase):
    def setUp(self):
        self.raw = dict(size="1U", mass=1.3, alpha=.7, emissivity=.7, power=1.)
        self.elements = dict(default_elements(), epoch="2026-11-19T12:00:00Z")

    def test_material_and_size_bounds(self):
        for size, (_, _, low, high, _) in THERMAL_SIZES.items():
            for mass in (low, high):
                self.assertEqual(ThermalMaterial.from_settings(dict(self.raw, size=size, mass=mass)).mass, mass)
        for key, value in [('size', '2U'), ('mass', .79), ('mass', 2.01), ('alpha', .09), ('alpha', .951),
                           ('emissivity', .049), ('emissivity', .96), ('power', -.1), ('power', 5.1),
                           ('mass', float('nan')), ('power', True)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                ThermalMaterial.from_settings(dict(self.raw, **{key:value}))

    def test_orbit_curve_and_qmp_generator_share_material_temperature(self):
        orbit = Orbit(self.elements)
        result = preview(dict(elements=self.elements, materials=[self.raw]))
        curve = result["thermal"][0]
        material = ThermalMaterial.from_settings(self.raw)
        self.assertGreater(curve["maximum"], curve["minimum"])
        self.assertGreater(curve["minimum"], curve["steady_shadow"])
        for i, point in enumerate(result["points"]):
            if not point[3]:
                self.assertLessEqual(curve["values"][i], curve["steady_sun"])
        for i in (305, 5, 245, 0, 359):
            self.assertAlmostEqual(orbit.temperature(i * orbit.period/360, material), curve["values"][i])
        next_orbit = Orbit(self.elements).thermal_curve(material, 1)
        self.assertAlmostEqual(curve["values"][-1], next_orbit["values"][0], places=5)

    def test_balance_matches_specified_energy_flux(self):
        material = ThermalMaterial.from_settings(self.raw)
        factor, cosine = .84, .6
        expected = (.7*.015*1361*(1+.3*factor*cosine) + .7*.015*239*factor + 1.)
        self.assertAlmostEqual(material.equilibrium(factor, cosine, True)**4 *.7*5.67e-8*.06, expected)
        temperature = 265.
        rate = (expected - .7*5.67e-8*.06*temperature**4)/(1.3*900)
        self.assertAlmostEqual((material.advance(temperature, material.equilibrium(factor, cosine, True), .001)
                                - temperature)/.001, rate, places=6)
