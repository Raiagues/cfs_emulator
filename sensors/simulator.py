#!/usr/bin/env python3
"""Run editable Python waveforms for devices registered in the project."""

import argparse
import math
from pathlib import Path
import time

try:
    from . import lsm303dlhc_mag, tmp105
    from .qmp import set_property
    from .runtime import ROOT, check_live, check_record, connect_board, load_config
except ImportError:
    import lsm303dlhc_mag
    import tmp105
    from qmp import set_property
    from runtime import ROOT, check_live, check_record, connect_board, load_config

from project.model import board_catalog, validate_values

SENSORS = {sensor.DEVICE: sensor for sensor in (tmp105, lsm303dlhc_mag)}


def sample_values(devices, elapsed_s):
    """Calculate and validate the entire tick before writing to QEMU."""
    samples = []
    for device in devices:
        adapter = SENSORS.get(device["model"])
        if adapter is None:
            raise ValueError(f"No waveform adapter for sensor {device['id']!r}")
        try:
            values = adapter.sample(elapsed_s, dict(device["values"]))
            validate_values(device, values)
            if not values:
                raise ValueError("sample() must return at least one property")
        except (ArithmeticError, TypeError, ValueError) as error:
            raise ValueError(f"Cannot sample {device['id']}: {error}") from error
        samples.append((device, values))
    return samples


def simulate(root, sensor_ids=(), interval=1.0, steps=None):
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("--interval must be finite and positive")
    if steps is not None and (type(steps) is not int or steps < 1):
        raise ValueError("--steps must be a positive integer")

    config = load_config(root)
    devices = {device["id"]: device for device in config["devices"]}
    selected = list(sensor_ids) or list(devices)
    if not selected:
        raise ValueError("The project has no configured sensors")
    if len(selected) != len(set(selected)):
        raise ValueError("Sensor IDs must not be repeated")
    for sensor_id in selected:
        if sensor_id not in devices:
            raise ValueError(f"Unknown configured sensor ID {sensor_id!r}")
    devices = [devices[sensor_id] for sensor_id in selected]
    check_record(root, config)
    models = board_catalog()["models"]

    started = time.monotonic()
    count = 0
    while steps is None or count < steps:
        tick = time.monotonic()
        samples = sample_values(devices, tick - started)
        # Release QMP each tick so values/prepare can also use the monitor.
        with connect_board(root) as qmp:
            check_live(config, qmp)
            for device, values in samples:
                for name, value in values.items():
                    set_property(qmp, f"/machine/peripheral/{device['id']}", name, value)
        for device, values in samples:
            properties = models[device["model"]]["properties"]
            output = ", ".join(f"{name}={value} {properties[name]['unit']}" for name, value in values.items())
            print(f"{device['id']}: {output}", flush=True)
        count += 1
        if steps is None or count < steps:
            time.sleep(max(0.0, interval - (time.monotonic() - tick)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="sensor IDs; defaults to every configured sensor")
    parser.add_argument("--root", type=Path, default=ROOT, help="project root (also selects board/qmp.sock)")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between updates")
    parser.add_argument("--steps", type=int, help="stop after this many updates; otherwise run until Ctrl+C")
    args = parser.parse_args()
    try:
        simulate(args.root, args.ids, args.interval, args.steps)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
