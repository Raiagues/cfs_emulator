"""Temperature in °C. Configuration and waveform for the shared runner."""

import math
from sensors.schema import Sensor, Signal

AMPLITUDE_C = 5.0
PERIOD_SECONDS = 30.0


SIGNALS = {"temperature": {"function": "script"}}


def configure(device):
    return Sensor.from_device(device, (Signal("temperature", "°C", 1000),))


def sample(seconds, initial_c):
    """Return one temperature in °C; seconds is time since this run started."""
    angle = 2 * math.pi * seconds / PERIOD_SECONDS
    return initial_c + AMPLITUDE_C * math.sin(angle)


def hold(seconds, initial):
    """Edit this function for a custom temperature signal."""
    return initial


if __name__ == "__main__":
    from sensors.session import sensor_main
    sensor_main(__file__)
