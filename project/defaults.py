"""Checkout-independent defaults shared by the command line and server."""
from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import math
import re
import sys
import os
import platform
from pathlib import Path


BOARD_PORT = 22
BOARD_DIRECTORY = "cfs-arm64"


def boot_timeout():
    seconds = float(os.environ.get("FLIGHT_STUDIO_BOOT_TIMEOUT", "120"))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("FLIGHT_STUDIO_BOOT_TIMEOUT must be a positive number of seconds")
    return seconds


def native_devices(root):
    return Path(os.environ.get("FLIGHT_STUDIO_NATIVE_DEVICES", runtime_dir(root) / "devices")).resolve()


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

def runtime_dir(root):
    return Path(os.environ.get('FLIGHT_STUDIO_RUNTIME', Path(root) / 'hardware/.runtime')).resolve()

def port(key, default):
    value = int(os.environ.get('FLIGHT_STUDIO_' + key, default))
    if not 1 <= value <= 65535:
        raise ValueError(f'FLIGHT_STUDIO_{key} must be a UDP or TCP port')
    return value


def loopback():
    value = os.environ.get('FLIGHT_STUDIO_LOOPBACK', '127.0.0.1')
    if not ipaddress.IPv4Address(value).is_loopback:
        raise ValueError('FLIGHT_STUDIO_LOOPBACK must be an IPv4 loopback address')
    return value


def builder():
    return os.environ.get('FLIGHT_STUDIO_BUILDER', 'flight-studio-builder:bookworm')


@dataclass(frozen=True)
class EmulatorNetwork:
    container: str
    ssh: int
    qmp: int
    command: int
    internal_ssh: int
    internal_qmp: int
    flight_command: int
    guest_host: str
    ssh_alias: str
    keys: str


def network(root):
    digest = hashlib.sha256(os.fsencode(Path(root).resolve())).hexdigest()
    base = 20000 + int(digest[:8], 16) % 8000 * 3
    name = os.environ.get('FLIGHT_STUDIO_CONTAINER', 'flight-studio-' + digest[:12])
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', name):
        raise ValueError('Invalid FLIGHT_STUDIO_CONTAINER')
    return EmulatorNetwork(name, port('SSH_PORT', base), port('QMP_PORT', base + 1), port('COMMAND_PORT', base + 2),
                           port('GUEST_SSH_PORT', 2222), port('GUEST_QMP_PORT', 4444), port('GUEST_COMMAND_PORT', 1234),
                           os.environ.get('FLIGHT_STUDIO_GUEST_HOST', '10.0.2.2'), 'pi4-cfs',
                           str(Path(os.environ.get('FLIGHT_STUDIO_EMULATOR_KEYS', runtime_dir(root) / 'ssh')).resolve()))


if __name__ == '__main__':
    values = dict(asdict(network(Path.cwd())), builder=builder(), platform=docker_platform(), loopback=loopback())
    if len(sys.argv) != 2 or sys.argv[1] not in values:
        sys.exit('Choose ' + ', '.join(values))
    print(values[sys.argv[1]])
