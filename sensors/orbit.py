"""Earth orbit used by the signal preview and by the QMP waveform generator.

Distances in km, angles in degrees, and elapsed times in seconds from UTC epoch.
The J2 option applies first-order secular rates to the mean orbital elements.
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from math import asin, ceil, atan2, cos, degrees, exp, floor, isfinite, pi, radians, sin, sqrt, tau

EARTH = 6378.137
MU = 398600.4418
J2 = 1.08262668e-3
DAY = 86400
SAMPLES = 360


THERMAL_SIZES = {
    # projected area, surface area (m²), mass bounds (kg), typical mass (kg)
    '1U': (.015, .060, .8, 2., 1.3),
    '3U': (.039, .156, 2., 6., 4.),
    '6U': (.071, .284, 6., 14., 10.),
}
SOLAR_FLUX, EARTH_IR, SIGMA, SPECIFIC_HEAT = 1361., 239., 5.67e-8, 900.


@dataclass(frozen=True)
class ThermalMaterial:
    size: str
    mass: float
    alpha: float
    emissivity: float
    power: float

    @classmethod
    def from_settings(cls, raw):
        if not isinstance(raw, dict) or set(raw) != {'size', 'mass', 'alpha', 'emissivity', 'power'}:
            raise ValueError('Set size, mass, absorptivity, emissivity and internal heat')
        size = raw['size']
        if not isinstance(size, str) or size not in THERMAL_SIZES:
            raise ValueError('Choose 1U, 3U or 6U')
        limits = {'mass': THERMAL_SIZES[size][2:4], 'alpha': (.10, .95),
                  'emissivity': (.05, .95), 'power': (0., 5.)}
        for field, (low, high) in limits.items():
            value = raw[field]
            if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
                raise ValueError(f'{field} must be between {low} and {high}')
        return cls(**raw)

    def equilibrium(self, factor, cosine, lit):
        projected, area = THERMAL_SIZES[self.size][:2]
        absorbed = self.alpha * projected * SOLAR_FLUX * (int(lit) + .3 * factor * max(0., cosine))
        heat = absorbed + self.emissivity * projected * EARTH_IR * factor + self.power
        return (heat / (self.emissivity * SIGMA * area)) ** .25

    def advance(self, temperature, equilibrium, seconds):
        # Factor T^4 - Teq^4, then use the midpoint conductance. The exponential
        # stays between T and Teq even with long steps on eccentric orbits.
        coefficient = self.emissivity * SIGMA * THERMAL_SIZES[self.size][1] / (self.mass * SPECIFIC_HEAT)
        def rate(t):
            return coefficient * (t + equilibrium) * (t*t + equilibrium*equilibrium)
        delta = temperature - equilibrium
        midpoint = equilibrium + delta * exp(-.5 * seconds * rate(temperature))
        return equilibrium + delta * exp(-seconds * rate(midpoint))


def sunlight(epoch_seconds):
    days = epoch_seconds / DAY - 10957.5  # Days from J2000.0
    anomaly = radians((357.528 + 0.9856003 * days) % 360)
    longitude = radians((280.460 + 0.9856474 * days + 1.915 * sin(anomaly) + .020 * sin(2 * anomaly)) % 360)
    tilt = radians(23.439 - .0000004 * days)
    return cos(longitude), cos(tilt) * sin(longitude), sin(tilt) * sin(longitude)


def default_elements():
    epoch = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sun = sunlight(epoch.timestamp())
    return dict(perigee=548, apogee=552, inclination=97.59,
                node=round((degrees(atan2(sun[1], sun[0])) - 22.5) % 360, 2),
                argument=90, anomaly=0, epoch=epoch.isoformat().replace('+00:00', 'Z'), model='J2')


def validate(raw):
    limits = {'perigee': (100, 100000), 'apogee': (100, 100000), 'inclination': (0, 180),
              'node': (0, 360), 'argument': (0, 360), 'anomaly': (0, 360)}
    if not isinstance(raw, dict) or set(raw) != set(limits) | {'model', 'epoch'}:
        raise ValueError('Set the orbital elements and UTC epoch.')
    for key, (low, high) in limits.items():
        number = raw[key]
        if type(number) not in (float, int) or not isfinite(number) or not low <= number <= high:
            raise ValueError(f'{key.capitalize()} must be between {low} and {high}.')
    if raw['apogee'] < raw['perigee'] or raw['model'] not in ('J2', 'Two-body'):
        raise ValueError('Select a propagator and set apogee at or above perigee.')
    try:
        epoch = datetime.fromisoformat(raw['epoch'].replace('Z', '+00:00'))
        if epoch.tzinfo is None or not 1900 <= epoch.year <= 2100:
            raise ValueError()
    except (TypeError, AttributeError, ValueError):
        raise ValueError('Use a UTC epoch between 1900 and 2100.') from None
    return {**raw, 'epoch': epoch.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}


def from_tle(text, model):
    if not isinstance(text, str) or len(text) > 1024:
        raise ValueError('Paste both TLE lines.')
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) == 3 and not lines[0].startswith(('1 ', '2 ')):
        lines = lines[1:]
    if len(lines) != 2 or not all(len(line) == 69 and line.startswith(f'{i} ') for i, line in enumerate(lines, 1)):
        raise ValueError('A TLE needs its two original 69-column lines.')
    one, two = lines
    if one[2:7] != two[2:7]:
        raise ValueError('The satellite identifiers in the two lines differ.')
    for line in lines:
        checksum = sum(int(c) if c.isascii() and c.isdigit() else int(c == '-') for c in line[:68]) % 10
        if str(checksum) != line[68]:
            raise ValueError(f'TLE checksum failed on line {line[0]}.')
    try:
        year = int(one[18:20])
        year += 1900 if year >= 57 else 2000
        day = float(one[20:32])
        year_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        if not 1 <= day < (year_start.replace(year=year + 1) - year_start).days + 1:
            raise ValueError()
        epoch = year_start + timedelta(days=day - 1)
        motion = float(two[52:63])
        if not 0 < motion < 25 or not two[26:33].isdigit():
            raise ValueError()
        a = (MU / (motion * tau / DAY) ** 2) ** (1 / 3)
        e = int(two[26:33]) / 1e7
        raw = dict(perigee=a * (1 - e) - EARTH, apogee=a * (1 + e) - EARTH,
                   inclination=float(two[8:16]), node=float(two[17:25]), argument=float(two[34:42]),
                   anomaly=float(two[43:51]), epoch=epoch.isoformat(), model=model)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Invalid TLE epoch or orbital elements.') from None
    return validate(raw)


class Orbit:
    def __init__(self, elements):
        elements = validate(elements)
        self.elements = elements
        self.epoch = datetime.fromisoformat(elements['epoch'].replace('Z', '+00:00')).timestamp()
        self.inc = radians(elements['inclination'])
        self.a = EARTH + (elements['apogee'] + elements['perigee']) / 2
        self.e = (elements['apogee'] - elements['perigee']) / (2 * self.a)
        n = sqrt(MU / self.a ** 3)
        k = 1.5 * J2 * n * (EARTH / (self.a * (1 - self.e ** 2))) ** 2 if elements['model'] == 'J2' else 0
        self.dnode = -k * cos(self.inc)
        self.darg = k * .5 * (5 * cos(self.inc) ** 2 - 1)
        self.motion = n + k * .5 * sqrt(1 - self.e ** 2) * (3 * cos(self.inc) ** 2 - 1)
        self.period = tau / self.motion
        self._responses = {}
        self._thermal = {}

    def sample(self, seconds):
        e = self.e
        mean = (radians(self.elements['anomaly']) + self.motion * seconds + pi) % tau - pi
        E = mean if e < .8 else (pi if mean >= 0 else -pi)
        for _ in range(16):
            delta = (E - e * sin(E) - mean) / (1 - e * cos(E))
            E -= delta
            if abs(delta) < 1.e-11:
                break
        radius = self.a * (1 - e * cos(E))
        argument = atan2(sqrt(1 - e * e) * sin(E), cos(E) - e) + radians(self.elements['argument']) + self.darg * seconds
        node = radians(self.elements['node']) + self.dnode * seconds
        x = cos(node) * cos(argument) - sin(node) * sin(argument) * cos(self.inc)
        y = sin(node) * cos(argument) + cos(node) * sin(argument) * cos(self.inc)
        z = sin(argument) * sin(self.inc)
        utc = self.epoch + seconds
        degrees_greenwich = 280.46061837 + 360.98564736629 * (utc / DAY - 10957.5)
        lon = (degrees(atan2(y, x)) - degrees_greenwich + 180) % 360 - 180
        sun = sunlight(utc)
        dot = x * sun[0] + y * sun[1] + z * sun[2]
        lit = dot >= 0 or radius * sqrt(max(0, 1 - dot * dot)) >= EARTH
        solar_lon = (degrees(atan2(sun[1], sun[0])) - degrees_greenwich + 180) % 360 - 180
        beta = asin(max(-1, min(1, (sun[0] * sin(node) - sun[1] * cos(node)) * sin(self.inc) + sun[2] * cos(self.inc))))
        return lon, degrees(asin(z)), radius - EARTH, lit, solar_lon, degrees(asin(sun[2])), degrees(beta)


    def thermal_curve(self, material, cycle):
        """One revolution in Celsius, sampled on the same grid as the ground track."""
        key = (material, cycle)
        if key in self._thermal:
            return self._thermal[key]
        dt = self.period / SAMPLES
        start = cycle * self.period
        # Use the same warm-up and grid for random access, dry runs and live QMP.
        # Perigee at noon and apogee in eclipse bound all possible steady states.
        hot = material.equilibrium((EARTH / (EARTH + self.elements['perigee']))**2, 1., True)
        cold = material.equilibrium((EARTH / (EARTH + self.elements['apogee']))**2, 0., False)
        temp_span = ((hot**4 + cold**4) / 2) ** .25
        prior = self._thermal.get((material, cycle-1))
        if prior:
            temperature, first = prior['values'][-1]+273.15, 0
        else:
            area = THERMAL_SIZES[material.size][1]
            relaxation = material.mass * SPECIFIC_HEAT / (4*material.emissivity*SIGMA*area*cold**3)
            # Forget the initial condition even for a random seek many orbits ahead.
            first = -min(64, max(3, ceil(20*relaxation/self.period))) * SAMPLES
            temperature = temp_span
        values = []
        for i in range(first, SAMPLES+1):
            if i >= 0:
                values.append(temperature - 273.15)
            if i == SAMPLES:
                break
            lon, lat, altitude, lit, sunlon, sunlat, _ = self.sample(start + (i + .5)*dt)
            cosine = (sin(radians(lat))*sin(radians(sunlat))
                      + cos(radians(lat))*cos(radians(sunlat))*cos(radians(lon-sunlon)))
            eq = material.equilibrium((EARTH/(EARTH+altitude))**2, cosine, lit)
            temperature = material.advance(temperature, eq, dt)
        result = dict(values=values, minimum=min(values), maximum=max(values),
                      steady_sun=hot-273.15, steady_shadow=cold-273.15)
        if len(self._thermal) >= 64:
            self._thermal.pop(next(iter(self._thermal)))
        self._thermal[key] = result
        return result

    def temperature(self, seconds, material):
        cycle = floor(seconds / self.period)
        curve = self.thermal_curve(material, cycle)['values']
        sample = max(0., min(SAMPLES, (seconds/self.period-cycle)*SAMPLES))
        i = min(floor(sample), SAMPLES-1)
        return curve[i] + (sample-i)*(curve[i+1]-curve[i])

    def illumination(self, seconds, response_time=0):
        """First-order response to sunlight, with baseline at the session epoch.

        Midpoint forcing on a fixed orbital grid and exact exponential decay
        give the same result at a requested instant regardless of sample rate.
        """
        if not response_time:
            return float(self.sample(seconds)[3])
        step = self.period / SAMPLES
        target = floor(seconds / step)
        earliest = max(0, floor((seconds - 16 * response_time) / step))
        index, value = self._responses.get(response_time, (earliest, 0.0))
        if not earliest <= index <= target:
            index, value = earliest, 0.0
        decay = exp(-step / response_time)
        for i in range(index, target):
            sunlit = int(self.sample((i + .5) * step)[3])
            value = sunlit + (value - sunlit) * decay
        self._responses[response_time] = (target, value)
        sunlit = int(self.sample((target + .5) * step)[3])
        return sunlit + (value - sunlit) * exp(-(seconds - target * step) / response_time)


def preview(body):
    elements = body['elements'] if 'elements' in body else default_elements()
    if 'tle' in body:
        elements = from_tle(body['tle'], elements.get('model', 'J2') if isinstance(elements, dict) else 'J2')
    orbit = Orbit(elements)
    cycle = body.get('cycle', 0)
    if type(cycle) is not int or not 0 <= cycle <= 1000000:
        raise ValueError('Invalid orbit number.')
    points = [orbit.sample((cycle + i / SAMPLES) * orbit.period) for i in range(SAMPLES + 1)]
    responses = body.get('responses', [])
    if not isinstance(responses, list) or len(responses) > 32 or any(type(tau) not in (float, int)
            or not 0 < tau <= 7200 for tau in responses):
        raise ValueError("Use up to 32 response times between zero and 7200 seconds.")
    curves = {str(float(tau)).removesuffix('.0'): [round(orbit.illumination((cycle + i / SAMPLES) * orbit.period, tau), 7)
                                                  for i in range(SAMPLES + 1)] for tau in set(responses)}
    materials = body.get('materials', [])
    if not isinstance(materials, list) or len(materials) > 32:
        raise ValueError('Use up to 32 thermal profiles per request')
    thermal = [orbit.thermal_curve(ThermalMaterial.from_settings(raw), cycle) for raw in materials]
    shadow = sum(not point[3] for point in points[:-1]) / SAMPLES
    return dict(elements=orbit.elements, cycle=cycle, period=orbit.period, eccentricity=orbit.e,
                drift=degrees(orbit.dnode) * DAY, eclipse=shadow, responses=curves, thermal=thermal,
                points=[[round(lon, 5), round(lat, 5), round(height, 4), lit, round(sunlon, 5), round(sunlat, 5),
                         round(beta, 4)] for lon, lat, height, lit, sunlon, sunlat, beta in points])
