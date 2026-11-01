#!/usr/bin/env python3
"""Run editable, physical-unit Python waveforms against configured QEMU devices."""

import argparse
import copy
import fcntl
import importlib.util
import math
from contextlib import ExitStack
from pathlib import Path
import json
import time
import traceback

try:
    from .qmp import set_property
    from .runtime import ROOT, check_live, check_record, connect_board, load_config
except ImportError:
    from qmp import set_property
    from runtime import ROOT, check_live, check_record, connect_board, load_config

from project.model import board_catalog, board_catalogs, validate_values
from sensors.schema import Sensor, Signal

# These are the units of the official QEMU QOM properties, not I2C wire fields.
# TMP105: 1000 = 1 °C; LSM303DLHC: 1000 = 1 µT. QEMU builds the register bytes.
UNITS = {"millidegrees Celsius": (1000, "°C"), "milli-microtesla": (1000, "µT")}


def simulation_scripts(root=ROOT):
    """Expose only waveform files for models supported by this board catalog."""
    selected = load_config(root)["board"]
    catalogs = [board_catalog(selected, root)] if selected else board_catalogs(root)
    return {model: f"sensors/{model}.py" for catalog in catalogs for model in catalog["models"]
            if (Path(root) / "sensors" / (model + ".py")).is_file()}


def load_waveform(root, model):
    path = simulation_scripts(root).get(model)
    if path is None:
        raise ValueError(f"No waveform script for model {model!r}")
    spec = importlib.util.spec_from_file_location("sensor_waveform_" + model, Path(root) / path)
    module = importlib.util.module_from_spec(spec)
    # Read fresh source even when same-size edits happen within one second.
    exec(compile((Path(root) / path).read_text(), str(Path(root) / path), "exec"), vars(module))
    return module


def binding(device, root=ROOT, catalog=None):
    """Expected target, shared by inspection and validation; does not load user code."""
    return {"qmp_socket": "board/qmp.sock", "qom_path": f"/machine/peripheral/{device['id']}",
            "bus": device["bus"], "address": device["address"],
            "linux_device": (catalog or board_catalog(load_config(root)["board"], root))["buses"][device["bus"]]["device"]}


def configuration(waveform, device, root=ROOT, catalog=None):
    config = waveform.configure(copy.deepcopy(device))
    expected = binding(device, root, catalog)
    if not isinstance(config, Sensor):
        raise ValueError("configure(device) must return a Sensor")
    if config.model != device["model"] or any(getattr(config, key) != expected[key] for key in ("bus", "address", "qom_path")):
        raise ValueError("Script binding differs from the selected project device. Update project/config.json and reboot before changing hardware.")
    properties = (catalog or board_catalog(load_config(root)["board"], root))["models"][device["model"]]["properties"]
    if not config.signals or not all(isinstance(signal, Signal) for signal in config.signals):
        raise ValueError("Declare the QEMU signals in configure(device)")
    names = [signal.property for signal in config.signals]
    if len(names) != len(set(names)) or set(names) != set(properties):
        raise ValueError("Declare each supported QEMU signal exactly once in configure(device)")
    for signal in config.signals:
        if (signal.scale, signal.unit) != UNITS[properties[signal.property]["unit"]]:
            raise ValueError(f"Incorrect QEMU units for {signal.property}")
    return config


def sample_values(devices, elapsed_s, waveforms=None, configurations=None, root=ROOT, catalog=None):
    """Convert and validate the entire tick before writing anything to QEMU."""
    catalog = catalog or board_catalog(load_config(root)["board"], root)
    models = catalog["models"]
    samples = []
    for device in devices:
        try:
            waveform = (waveforms.get(device["id"]) or waveforms[device["model"]]) if waveforms is not None else load_waveform(root, device["model"])
            # Keep technical checks here, out of the user's editable formula.
            period = getattr(waveform, "PERIOD_SECONDS", 1)
            if type(period) not in (int, float) or not math.isfinite(period) or period <= 0:
                raise ValueError("PERIOD_SECONDS must be finite and positive")
            properties = models[device["model"]]["properties"]
            config = configurations[device["id"]] if configurations else configuration(waveform, device, root, catalog)
            initial = tuple(device["values"][signal.property] / signal.scale for signal in config.signals)
            result = waveform.sample(elapsed_s, initial[0] if len(initial) == 1 else initial)
            values = (result,) if len(config.signals) == 1 else result
            if not isinstance(values, (tuple, list)) or len(values) != len(config.signals):
                raise ValueError(f"sample() must return {len(config.signals)} numbers in the declared signal order")
            converted = {}
            for signal, value in zip(config.signals, values):
                name, prop = signal.property, properties[signal.property]
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"{name}: sample() must return a finite number")
                scale, unit = signal.scale, signal.unit
                if not prop["min"] / scale <= value <= prop["max"] / scale:
                    raise ValueError(f"{name}: {value:g} {unit} is outside {prop['min'] / scale:g}..{prop['max'] / scale:g} {unit}")
                converted[name] = round(value * scale)
            validate_values(device, converted, catalog)
        except (ArithmeticError, KeyError, TypeError, AttributeError, ValueError) as error:
            frames = [frame for frame in traceback.extract_tb(error.__traceback__)
                      if Path(frame.filename).name == device["model"] + ".py"]
            location = f" ({Path(frames[-1].filename).name}:{frames[-1].lineno})" if frames else ""
            raise ValueError(f"Cannot sample {device['id']}{location}: {error}") from error
        samples.append((device, converted))
    return samples


def simulate(root, sensor_ids=(), interval=1.0, steps=None, waveforms=None, trace_qmp=False,
             initial_values=None, on_sample=None, dry_run=False):
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("--interval must be finite and positive")
    if steps is not None and (type(steps) is not int or steps < 1):
        raise ValueError("--steps must be a positive integer")

    root = Path(root)
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
    devices = copy.deepcopy([devices[sensor_id] for sensor_id in selected])
    for device in devices:
        if initial_values and device["id"] in initial_values:
            device["values"].update(initial_values[device["id"]])
    catalog = board_catalog(config["board"], root)
    models = catalog["models"]
    for device in devices:
        device["values"] = {**models[device["model"]].get("default_values", {}), **device["values"]}
    if waveforms is None:
        waveforms = {device["model"]: load_waveform(root, device["model"]) for device in devices}

    configurations = {device["id"]: configuration(waveforms.get(device["id"]) or waveforms[device["model"]], device, root, catalog) for device in devices}

    if dry_run:
        print("Preview · no data sent to QEMU", flush=True)
        for count in range(steps if steps is not None else 8):
            elapsed = count * interval
            samples = sample_values(devices, elapsed, waveforms, configurations, root, catalog)
            print_samples(samples, elapsed, catalog)
            if on_sample:
                on_sample(elapsed, samples)
        return

    check_record(root, config)
    with ExitStack() as lifetime:
        # A device has one writer, even if a second CLI or Studio is opened.
        for device in sorted(devices, key=lambda item: item["id"]):
            lock = lifetime.enter_context((root / "board" / (".simulate-" + device["id"] + ".lock")).open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError(f"Synthetic data is already running for {device['id']}") from None
        with connect_board(root) as qmp:
            check_live(config, qmp)
            for device in devices:
                for name in models[device["model"]]["properties"]:
                    if name not in device["values"]:
                        device["values"][name] = qmp.execute("qom-get", {
                            "path": f"/machine/peripheral/{device['id']}", "property": name})

        for device in devices:
            sensor_config = configurations[device["id"]]
            print(f"{device['id']}  |  {sensor_config.bus}  |  I2C {sensor_config.address:#04x}", flush=True)
            print(f"QMP: {root / binding(device, root, catalog)['qmp_socket']}", flush=True)
            print(f"Object: {sensor_config.qom_path}", flush=True)
            for signal in sensor_config.signals:
                print(f"{signal.property}: sample in {signal.unit}; QEMU value = sample × {signal.scale}", flush=True)
        print("\nElapsed  Sensor  Value  |  QMP command  |  Result", flush=True)
        started = time.monotonic()
        count = 0
        while steps is None or count < steps:
            tick = time.monotonic()
            samples = sample_values(devices, tick - started, waveforms, configurations, root, catalog)
            # Release QMP each tick so other tools can inspect the monitor.
            with connect_board(root) as qmp:
                check_live(config, qmp)
                for device, values in samples:
                    for name, value in values.items():
                        path = configurations[device["id"]].qom_path
                        request = {"execute": "qom-set", "arguments": {"path": path, "property": name, "value": value}}
                        if trace_qmp:
                            print("QMP > " + json.dumps(request), flush=True)
                        result = set_property(qmp, path, name, value)
                        if trace_qmp:
                            print("QMP < " + json.dumps({"return": result}), flush=True)
                        scale, unit = UNITS[models[device["model"]]["properties"][name]["unit"]]
                        reply = "OK" if result == {} else json.dumps(result)
                        print(f"{tick - started:7.2f}s  {device['id']}  {name}={value / scale:.3f} {unit}"
                              f"  |  qom-set {name}={value}  |  {reply}", flush=True)
            if on_sample:
                on_sample(tick - started, samples)
            count += 1
            if steps is None or count < steps:
                time.sleep(max(0.0, interval - (time.monotonic() - tick)))


def print_samples(samples, elapsed, catalog):
    for device, values in samples:
        props = catalog["models"][device["model"]]["properties"]
        line = ", ".join(f"{name}={value / UNITS[props[name]['unit']][0]:.3f} {UNITS[props[name]['unit']][1]}"
                         for name, value in values.items())
        print(f"{elapsed:7.2f}s  {device['id']}  {line}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="configured sensor IDs; defaults to the selected session")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--interval", type=float, help="seconds between updates; defaults to SESSION")
    parser.add_argument("--steps", type=int, help="stop after this many updates")
    parser.add_argument("--dry-run", action="store_true", help="preview samples without connecting to QEMU")
    parser.add_argument("--trace-qmp", action="store_true", help="also print complete QMP requests and responses")
    args = parser.parse_args()
    try:
        from sensors.session import run_session
        run_session(args.root, sensor_ids=args.ids, interval=args.interval, steps=args.steps,
                    trace_qmp=args.trace_qmp, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("Synthetic data stopped.", flush=True)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
