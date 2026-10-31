"""TMP105 waveform. Edit the constants or sample() to change the simulation."""

import math


DEVICE = "tmp105"
DEFAULT_C = 25.0
AMPLITUDE_C = 5.0
PERIOD_SECONDS = 30.0


def sample(elapsed_s, initial_values):
    """Return QEMU properties in millidegrees Celsius; values sets the center."""
    if not math.isfinite(PERIOD_SECONDS) or PERIOD_SECONDS <= 0:
        raise ValueError("PERIOD_SECONDS must be finite and positive")
    center = initial_values.get("temperature", round(DEFAULT_C * 1000)) / 1000
    temperature = center + AMPLITUDE_C * math.sin(2 * math.pi * elapsed_s / PERIOD_SECONDS)
    return {"temperature": round(temperature * 1000)}
