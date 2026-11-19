"""Earth orbit used by the signal preview and by the QMP waveform generator.

Distances in km, angles in degrees, and elapsed times in seconds from UTC epoch.
The J2 option applies first-order secular rates to the mean orbital elements.
"""
from datetime import datetime, timedelta, timezone
from math import asin, atan2, cos, degrees, exp, floor, isfinite, pi, radians, sin, sqrt, tau

EARTH = 6378.137
MU = 398600.4418
J2 = 1.08262668e-3
DAY = 86400
SAMPLES = 360


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
    shadow = sum(not point[3] for point in points[:-1]) / SAMPLES
    return dict(elements=orbit.elements, cycle=cycle, period=orbit.period, eccentricity=orbit.e,
                drift=degrees(orbit.dnode) * DAY, eclipse=shadow, responses=curves,
                points=[[round(lon, 5), round(lat, 5), round(height, 4), lit, round(sunlon, 5), round(sunlat, 5),
                         round(beta, 4)] for lon, lat, height, lit, sunlon, sunlat, beta in points])
