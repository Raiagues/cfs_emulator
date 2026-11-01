"""Magnetic field in µT. Configuration and waveform for the shared runner."""

import math
from sensors.schema import Sensor, Signal

AMPLITUDE_UT = 20.0
PERIOD_SECONDS = 30.0


SIGNALS = {
    "mag-x": {"function": "hold"},
    "mag-y": {"function": "script"},
    "mag-z": {"function": "script"},
}


def configure(device):
    return Sensor.from_device(device, (
        Signal("mag-x", "µT", 1000),
        Signal("mag-y", "µT", 1000),
        Signal("mag-z", "µT", 1000),
    ))


def sample(seconds, initial_xyz):
    """Return X, Y, Z in µT, starting at the configured field."""
    x, y, z = initial_xyz
    angle = 2 * math.pi * seconds / PERIOD_SECONDS
    x += AMPLITUDE_UT * math.cos(angle)
    y += AMPLITUDE_UT * math.sin(angle)
    return x, y, z


def hold(seconds, initial):
    """Custom functions receive elapsed seconds and this signal's initial value."""
    return initial


if __name__ == "__main__":
    from sensors.session import sensor_main
    sensor_main(__file__)
