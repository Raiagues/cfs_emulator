"""Magnetic field waveform. QEMU units are thousandths of a microtesla."""

import math


DEVICE = "lsm303dlhc_mag"
DEFAULT_UT = (30.0, 30.0, 40.0)
AMPLITUDE_UT = 20.0
PERIOD_SECONDS = 30.0


def sample(elapsed_s, initial_values):
    """Return the three QEMU properties; values sets each axis offset."""
    if not math.isfinite(PERIOD_SECONDS) or PERIOD_SECONDS <= 0:
        raise ValueError("PERIOD_SECONDS must be finite and positive")
    x, y, z = (initial_values.get(f"mag-{axis}", round(default * 1000)) / 1000
               for axis, default in zip("xyz", DEFAULT_UT))
    angle = 2 * math.pi * elapsed_s / PERIOD_SECONDS
    x += AMPLITUDE_UT * math.cos(angle)
    y += AMPLITUDE_UT * math.sin(angle)
    return {"mag-x": round(x * 1000), "mag-y": round(y * 1000), "mag-z": round(z * 1000)}
