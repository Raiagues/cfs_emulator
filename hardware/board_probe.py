#!/usr/bin/env python3
"""Read-only board report for HardwareManager.probe, sent over SSH to `python3 -`.

Prints one JSON object as its last line. sudo is queried only with -n, so a
missing authorization fails instead of waiting for a password. Uses only the
standard library of the board's Python 3.10 or newer.
"""
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import subprocess

SERVICE = Path("/etc/systemd/system/cfs-studio.service")


def succeeds(*command):
    return subprocess.run(command, capture_output=True, text=True).returncode == 0


def output(*command):
    return subprocess.run(command, capture_output=True, text=True).stdout.strip()


def board_model():
    model = Path("/proc/device-tree/model")
    return model.read_bytes().decode().strip("\0") if model.exists() else ""


def service_installed():
    # setup_board.py marks the unit with the account allowed to control it.
    marker = "# Flight Studio managed; account=" + pwd.getpwuid(os.getuid()).pw_name + "\n"
    return SERVICE.is_file() and SERVICE.read_text().startswith(marker)


def report():
    return {
        "arch": platform.machine(),
        "model": board_model(),
        "home": os.path.expanduser("~"),
        "hostname": platform.node(),
        # Device nodes only show that the I2C interface exists, not that a sensor answers.
        "i2c": sorted(str(path) for path in Path("/dev").glob("i2c-*")),
        "sudo": succeeds("sudo", "-n", "true"),
        "authorized": succeeds("sudo", "-n", "-l", "systemctl", "start", "cfs-studio.service"),
        "shutdown_authorized": succeeds("sudo", "-n", "-l", "systemctl", "poweroff", "--no-block"),
        "service_installed": service_installed(),
        "service": output("systemctl", "is-active", "cfs-studio.service"),
        "service_directory": output("systemctl", "show", "cfs-studio.service", "--property=WorkingDirectory", "--value"),
        "systemd": bool(shutil.which("systemd-run")),
        "os": platform.freedesktop_os_release().get("PRETTY_NAME", ""),
        "raspios": Path("/etc/rpi-issue").exists(),
    }


if __name__ == "__main__":
    print(json.dumps(report()))
