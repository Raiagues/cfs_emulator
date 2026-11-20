"""Checkout-independent defaults shared by the command line and server."""
import math
import os
import platform


def boot_timeout():
    seconds = float(os.environ.get("FLIGHT_STUDIO_BOOT_TIMEOUT", "120"))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("FLIGHT_STUDIO_BOOT_TIMEOUT must be a positive number of seconds")
    return seconds


def native_devices(root):
    from pathlib import Path
    return Path(os.environ.get("FLIGHT_STUDIO_NATIVE_DEVICES", Path(root) / "hardware/.runtime/devices")).resolve()


def sensor_timeout():
    timeout = float(os.environ.get("FLIGHT_STUDIO_SENSOR_TIMEOUT", "30"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("FLIGHT_STUDIO_SENSOR_TIMEOUT must be a positive number of seconds")
    return timeout

def docker_platform():
    system = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine(), platform.machine())
    selected = os.environ.get('FLIGHT_STUDIO_PLATFORM', 'linux/' + system)
    if selected not in {'linux/amd64', 'linux/arm64'}:
        raise ValueError('Choose linux/amd64 or linux/arm64 for FLIGHT_STUDIO_PLATFORM')
    return selected
