"""Checkout-independent defaults shared by the command line and server."""
import math
import os


def boot_timeout():
    seconds = float(os.environ.get("FLIGHT_STUDIO_BOOT_TIMEOUT", "120"))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("FLIGHT_STUDIO_BOOT_TIMEOUT must be a positive number of seconds")
    return seconds
