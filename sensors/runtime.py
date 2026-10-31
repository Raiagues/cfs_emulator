#!/usr/bin/env python3
"""Translate project hardware into QEMU arguments and check the live board."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project.model import board_catalog, load_config, topology, validate_hardware

try:
    from .qmp import connect, set_property
except ImportError:
    from qmp import connect, set_property

REBOOT = "Run ./stop.sh, then ./boot.sh to apply the project hardware."


def qemu_models(config):
    result = subprocess.run(
        ["qemu-system-aarch64", "-M", config["board"], "-device", "help"],
        capture_output=True, text=True, check=True,
    )
    return dict(re.findall(r'name "([^"]+)", bus ([^,\s]+)', result.stdout + result.stderr))


def qemu_arguments(config):
    validate_hardware(config)
    available = qemu_models(config)
    arguments = []
    for device in config["devices"]:
        if available.get(device["model"]) != "i2c-bus":
            raise ValueError(
                f"Installed QEMU does not provide I2C model {device['model']!r}; "
                "run ./scripts/project.sh devices"
            )
        arguments.extend([
            "-device",
            f"{device['model']},id={device['id']},bus={device['bus']},address={device['address']:#x}",
        ])
    return arguments


def record(root, config):
    directory = root / "board"
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".hardware-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, directory / "hardware.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def check_record(root, config):
    try:
        recorded = json.loads((root / "board" / "hardware.json").read_text())
        matches = (recorded.get("board") == config["board"]
                   and recorded.get("os") == config["os"]
                   and topology(recorded) == topology(config))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError(f"The booted board has no valid hardware record. {REBOOT}") from None
    if not matches:
        raise ValueError(f"Project hardware differs from the booted board. {REBOOT}")


def check_live(config, qmp):
    children = qmp.execute("qom-list", {"path": "/machine/peripheral"})
    types = {entry["name"]: entry["type"] for entry in children}
    for device in config["devices"]:
        sensor_id = device["id"]
        path = f"/machine/peripheral/{sensor_id}"
        if types.get(sensor_id) != f"child<{device['model']}>":
            raise ValueError(f"QEMU sensor {sensor_id!r} is missing or has the wrong model. {REBOOT}")
        address = qmp.execute("qom-get", {"path": path, "property": "address"})
        bus = qmp.execute("qom-get", {"path": path, "property": "parent_bus"})
        if address != device["address"] or str(bus).rsplit("/", 1)[-1] != device["bus"]:
            raise ValueError(f"QEMU sensor {sensor_id!r} has the wrong bus or address. {REBOOT}")


def connect_board(root):
    try:
        return connect(root / "board" / "qmp.sock")
    except OSError as error:
        raise ValueError(f"Cannot connect to the board QMP socket: {error}. {REBOOT}") from error


def apply_values(config, qmp):
    for device in config["devices"]:
        for name, value in device.get("values", {}).items():
            set_property(qmp, f"/machine/peripheral/{device['id']}", name, value)


def prepare_guest(config):
    if not config["devices"]:
        return
    buses = board_catalog()["buses"]
    paths = sorted({buses[device["bus"]]["device"] for device in config["devices"]})
    commands = ["modprobe i2c-dev"]
    commands.extend(f"test -c {shlex.quote(path)}" for path in paths)
    subprocess.run([
        "ssh", "-F", str(Path.home() / ".ssh/cfs-emulator/config"),
        "pi4-cfs", " && ".join(commands),
    ], check=True)


def list_devices():
    catalog = board_catalog()
    config = {"board": catalog["board"], "os": catalog["os"][0]}
    print(f"Board: {config['board']} | OS: {config['os']}")
    for name, bus in catalog["buses"].items():
        print(f"Bus: {name} -> {bus['device']}")
    print("\nQEMU I2C model             cFS driver        Project support")
    for name, bus in sorted(qemu_models(config).items()):
        if bus != "i2c-bus":
            continue
        model = catalog["models"].get(name, {})
        print(f"{name:25} {model.get('cfs_driver') or '-':17} {'yes' if model else 'not configured'}")
    print("\nQEMU models require a project adapter and cFS driver before use by an app.")
    for name, model in catalog["models"].items():
        for prop, limits in model["properties"].items():
            print(f"{name}.{prop}: integer {limits['min']}..{limits['max']} {limits['unit']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("command", choices=("args", "record", "check", "values", "prepare", "devices"))
    args = parser.parse_args()
    try:
        if args.command == "devices":
            list_devices()
            return
        config = load_config(args.root)
        if args.command == "args":
            arguments = qemu_arguments(config)
            if arguments:
                sys.stdout.buffer.write(("\0".join(arguments) + "\0").encode())
        elif args.command == "record":
            record(args.root, config)
        else:
            check_record(args.root, config)
            if args.command == "prepare":
                with connect_board(args.root) as qmp:
                    check_live(config, qmp)
                # Do not occupy the shared QMP monitor while waiting for SSH.
                prepare_guest(config)
            with connect_board(args.root) as qmp:
                check_live(config, qmp)
                if args.command in ("values", "prepare"):
                    apply_values(config, qmp)
            print("Board hardware verified." if args.command == "check" else "Sensor values applied.")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
