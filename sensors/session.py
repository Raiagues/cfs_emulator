"""Sensor-owned Python settings shared by Widgets, previews and QMP execution."""
import argparse
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import pprint
from types import SimpleNamespace

from project.model import board_catalog, board_catalogs, load_config
from sensors.runtime import ROOT
from sensors.simulator import UNITS, configuration, load_waveform, sample_values, simulate, print_samples

SOURCE = "sensors/signals.py"
FUNCTIONS = ("script", "constant", "sine", "ramp")


def _source(path):
    text = path.read_text()
    try:
        return text, ast.parse(text, filename=str(path))
    except SyntaxError as error:
        raise ValueError(f"{path.name}:{error.lineno}: {error.msg}") from error


def _assignment(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(matches) > 1 or matches and len(matches[0].targets) != 1:
        raise ValueError(f"Define {name} once, in its own assignment")
    return matches[0] if matches else None


def _literal(tree, name, default):
    node = _assignment(tree, name)
    if node is None:
        return copy.deepcopy(default)
    try:
        value = ast.literal_eval(node.value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name} must contain literal settings; put formulas in Python functions") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dictionary")
    return value


def _replace(text, tree, name, value):
    """Edit only the settings assignment; keep formulas and comments intact."""
    node = _assignment(tree, name)
    replacement = name + " = " + pprint.pformat(value, sort_dicts=False, width=100)
    if node is None:
        # Settings precede functions, following the existing imports/constants.
        first = next((item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.ClassDef))), None)
        line = min([first.lineno] + [item.lineno for item in first.decorator_list]) - 1 if first else len(text.splitlines())
        lines = text.splitlines(keepends=True)
        return "".join(lines[:line]) + replacement + "\n\n\n" + "".join(lines[line:])
    data = text.encode()
    lines = data.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
    return (data[:start] + replacement.encode() + data[end:]).decode()


def _model_source(root, model):
    path = Path(root) / "sensors" / (model + ".py")
    text, tree = _source(path)
    functions = {node.name: node.lineno for node in tree.body
                 if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
                 and node.name not in {"configure", "sample", *FUNCTIONS} and len(node.args.posonlyargs + node.args.args) == 2
                 and not node.args.vararg and not node.args.kwonlyargs}
    sample = next((node.lineno for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "sample"), None)
    return {"text": text, "tree": tree, "signals": _literal(tree, "SIGNALS", {}),
            "instances": _literal(tree, "INSTANCES", {}), "functions": functions, "sample_line": sample,
            "source_line": (_assignment(tree, "SIGNALS").lineno if _assignment(tree, "SIGNALS") else sample or 1)}


def _number(value, label, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or positive and value <= 0:
        raise ValueError(label + " must be a finite" + (" positive" if positive else "") + " number")
    return value


def _signal_settings(device, prop, limits, model, overrides=None):
    scale, _ = UNITS[limits["unit"]]
    defaults = model["signals"].get(prop, {})
    instance = model["instances"].get(device["id"], {})
    if not isinstance(defaults, dict) or not isinstance(instance, dict) or not isinstance(instance.get(prop, {}), dict):
        raise ValueError(device["id"] + "." + prop + ": settings must be a dictionary")
    raw = {**defaults, **instance.get(prop, {})}
    if overrides is not None:
        raw = overrides
    if not isinstance(raw, dict):
        raise ValueError(device["id"] + "." + prop + ": settings must be a dictionary")
    if set(raw) - {"initial", "function", "amplitude", "period", "slope", "custom"}:
        raise ValueError(device["id"] + "." + prop + ": unknown waveform setting")
    kind = raw.get("function", "script")
    custom = raw.get("custom", "") if kind == "custom" else kind if kind not in FUNCTIONS else ""
    kind = "custom" if custom else kind
    if kind not in (*FUNCTIONS, "custom") or kind == "custom" and custom not in model["functions"]:
        raise ValueError(f"Define {custom or kind}(seconds, initial) in sensors/{device['model']}.py")
    if kind == "script" and model["sample_line"] is None:
        raise ValueError(f"Define sample(seconds, initial) in sensors/{device['model']}.py")
    initial = raw.get("initial", device["values"].get(prop, 0) / scale)
    settings = {"initial": _number(initial, prop + " initial"), "function": kind}
    if kind == "sine":
        settings.update(amplitude=_number(raw.get("amplitude", 1.0), prop + " amplitude"),
                        period=_number(raw.get("period", 30.0), prop + " period", True))
    elif kind == "ramp":
        settings["slope"] = _number(raw.get("slope", 1.0), prop + " rate")
    elif kind == "custom":
        settings["custom"] = custom
    low, high = limits["min"] / scale, limits["max"] / scale
    if not low <= initial <= high:
        raise ValueError(device["id"] + "." + prop + ": initial value is outside the sensor range")
    if kind == "sine" and not low <= initial - abs(settings["amplitude"]) <= initial + abs(settings["amplitude"]) <= high:
        raise ValueError(device["id"] + "." + prop + ": sine amplitude exceeds the sensor range")
    return settings


def _device_settings(device, catalog, model, overrides=None):
    props = catalog["models"][device["model"]]["properties"]
    instance = model["instances"].get(device["id"], {})
    if set(model["signals"]) - set(props) or isinstance(instance, dict) and set(instance) - set(props):
        raise ValueError(device["id"] + ": unsupported signal in Python settings")
    if overrides is not None and (not isinstance(overrides, dict) or set(overrides) != set(props)):
        raise ValueError(device["id"] + ": configure each sensor signal")
    return {name: _signal_settings(device, name, limits, model, overrides[name] if overrides else None)
            for name, limits in props.items()}


def load_session(root=ROOT):
    root = Path(root)
    config = load_config(root)
    catalog = board_catalog(config["board"], root) if config["board"] else {"models": {}}
    text, tree = _source(root / SOURCE)
    saved = _literal(tree, "SESSION", {"interval": 1.0, "sensors": None})
    if set(saved) != {"interval", "sensors"}:
        raise ValueError("SESSION needs only interval and sensors")
    _number(saved["interval"], "Interval", True)
    if saved["sensors"] is not None and (not isinstance(saved["sensors"], dict)
            or not all(isinstance(name, str) and type(enabled) is bool for name, enabled in saved["sensors"].items())):
        raise ValueError("SESSION sensors must be None or a dictionary of device IDs and True/False")
    models, sources = {}, {SOURCE: text}
    available, selected = [], []
    for original in config["devices"]:
        device = copy.deepcopy(original)
        definition = catalog["models"][device["model"]]
        device["values"] = {**definition.get("default_values", {}), **device["values"]}
        script = "sensors/" + device["model"] + ".py"
        if device["model"] not in models:
            models[device["model"]] = _model_source(root, device["model"])
            sources[script] = models[device["model"]]["text"]
        model = models[device["model"]]
        signals = _device_settings(device, catalog, model)
        entry = {"device": device["id"], "enabled": True, "signals": signals}
        available.append({"id": device["id"], "model": device["model"], "bus": device["bus"],
                          "address": device["address"], "qom_path": "/machine/peripheral/" + device["id"],
                          "script": script, "source_line": model["source_line"], "sample_line": model["sample_line"],
                          "functions": [{"name": name, "line": line} for name, line in model["functions"].items()],
                          "defaults": copy.deepcopy(entry),
                          "properties": {name: {"unit": UNITS[prop["unit"]][1],
                                                "min": prop["min"] / UNITS[prop["unit"]][0],
                                                "max": prop["max"] / UNITS[prop["unit"]][0]}
                                         for name, prop in definition["properties"].items()}})
        if saved["sensors"] is None or device["id"] in saved["sensors"]:
            entry["enabled"] = True if saved["sensors"] is None else saved["sensors"][device["id"]]
            selected.append(entry)
    digest = hashlib.sha256()
    digest.update(json.dumps({key: config[key] for key in ("board", "devices")}, sort_keys=True).encode())
    for name, source in sorted(sources.items()):
        digest.update(name.encode()); digest.update(source.encode())
    return {"settings": {"interval": saved["interval"], "sensors": selected}, "available": available,
            "source": SOURCE, "sources": list(sources), "hash": digest.hexdigest()}


def _compact(settings):
    result = {"initial": settings["initial"], "function": settings["function"]}
    if settings["function"] == "custom":
        result["function"] = settings["custom"]
    elif settings["function"] == "sine":
        result.update(amplitude=settings["amplitude"], period=settings["period"])
    elif settings["function"] == "ramp":
        result["slope"] = settings["slope"]
    return result


def planned_settings(root, settings):
    """Return edited session/model files for one atomic Widgets save."""
    root = Path(root)
    if not isinstance(settings, dict) or set(settings) != {"interval", "sensors"}:
        raise ValueError("Expected interval and sensors")
    _number(settings["interval"], "Interval", True)
    if not isinstance(settings["sensors"], list):
        raise ValueError("Select sensors before saving")
    config = load_config(root)
    catalog = board_catalog(config["board"], root) if config["board"] else {"models": {}}
    devices = {item["id"]: copy.deepcopy(item) for item in config["devices"]}
    selected, groups = {}, {}
    for item in settings["sensors"]:
        if not isinstance(item, dict) or set(item) != {"device", "enabled", "signals"}:
            raise ValueError("Expected a device, enabled flag and signal settings")
        name = item["device"]
        if not isinstance(name, str) or name not in devices or name in selected or type(item["enabled"]) is not bool:
            raise ValueError("Select each configured device once")
        selected[name] = item["enabled"]
        device = devices[name]
        device["values"] = {**catalog["models"][device["model"]].get("default_values", {}), **device["values"]}
        groups.setdefault(device["model"], {})[name] = item["signals"]
    files = {}
    text, tree = _source(root / SOURCE)
    selection = None if set(selected) == set(devices) and all(selected.values()) else selected
    files[SOURCE] = _replace(text, tree, "SESSION", {"interval": settings["interval"], "sensors": selection})
    for model_name, entries in groups.items():
        model = _model_source(root, model_name)
        validated = {name: {prop: _compact(signal) for prop, signal in _device_settings(devices[name], catalog, model, values).items()}
                     for name, values in entries.items()}
        # A model has one default waveform. Only differing device instances
        # need overrides; functions always remain in the same sensor file.
        all_instances = [device for device in devices.values() if device["model"] == model_name]
        if len(all_instances) == 1:
            signals = next(iter(validated.values()))
            instances = {}
        else:
            signals = copy.deepcopy(model["signals"])
            instances = {name: value for name, value in model["instances"].items() if name in devices}
            for name, values in validated.items():
                inherited = {prop: _compact(_signal_settings(devices[name], prop, limits,
                             {**model, "instances": {}}))
                             for prop, limits in catalog["models"][model_name]["properties"].items()}
                difference = {prop: value for prop, value in values.items() if value != inherited[prop]}
                if difference: instances[name] = difference
                else: instances.pop(name, None)
        updated = _replace(model["text"], model["tree"], "SIGNALS", signals)
        if instances or _assignment(ast.parse(updated), "INSTANCES"):
            updated = _replace(updated, ast.parse(updated), "INSTANCES", instances)
        files["sensors/" + model_name + ".py"] = updated
    return files


def waveform_for(root, device, settings, catalog=None):
    original = load_waveform(root, device["model"])
    sensor = configuration(original, device, root=root, catalog=catalog)
    signals = [settings["signals"][signal.property] for signal in sensor.signals]
    def sample(seconds, initial):
        base = None
        if any(signal["function"] == "script" for signal in signals):
            initial = tuple(signal["initial"] for signal in signals)
            initial = initial[0] if len(initial) == 1 else initial
            base = original.sample(seconds, initial)
            base = (base,) if len(signals) == 1 else base
        values = []
        for index, signal in enumerate(signals):
            value, kind = signal["initial"], signal["function"]
            if kind == "script": value = base[index]
            elif kind == "sine": value += signal["amplitude"] * math.sin(2 * math.pi * seconds / signal["period"])
            elif kind == "ramp": value += signal["slope"] * seconds
            elif kind == "custom": value = getattr(original, signal["custom"])(seconds, value)
            values.append(value)
        return values[0] if len(values) == 1 else tuple(values)
    return SimpleNamespace(configure=original.configure, sample=sample)


def run_session(root=ROOT, steps=None, events=False, dry_run=False, device_id=None,
                sensor_ids=(), interval=None, trace_qmp=False):
    root = Path(root)
    session = load_session(root)
    selected = [sensor for sensor in session["settings"]["sensors"] if sensor["enabled"]]
    requested = [device_id] if device_id is not None else list(sensor_ids)
    if requested:
        available = {device["id"]: device["defaults"] for device in session["available"]}
        if len(requested) != len(set(requested)) or any(name not in available for name in requested):
            raise ValueError("Select each configured sensor ID once")
        selected = [available[name] for name in requested]
    if not selected:
        raise ValueError("Select a configured sensor in Synthetic data")
    config = load_config(root)
    catalog = board_catalog(config["board"], root)
    devices = {device["id"]: device for device in config["devices"]}
    waveforms = {}
    for sensor in selected:
        device = devices[sensor["device"]]
        waveforms[device["id"]] = waveform_for(root, device, sensor)
    def report(elapsed, samples):
        payload = []
        for device, values in samples:
            props = catalog["models"][device["model"]]["properties"]
            payload.append({"id": device["id"],
                            "values": {name: value / UNITS[props[name]["unit"]][0] for name, value in values.items()},
                            "units": {name: UNITS[props[name]["unit"]][1] for name in values}})
        print("@sensor " + json.dumps({"elapsed": elapsed, "devices": payload}), flush=True)
    simulate(root, list(waveforms), interval if interval is not None else session["settings"]["interval"],
             steps, waveforms, trace_qmp=trace_qmp, on_sample=report if events else None, dry_run=dry_run)


def sensor_main(filename):
    """Execute a sensor module in the terminal without requiring a running board."""
    parser = argparse.ArgumentParser(description="Preview this sensor's configured Python functions.")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    model_name = Path(filename).stem
    root = Path(filename).resolve().parents[1]
    try:
        _number(args.interval, "Interval", True)
        if args.steps < 1: raise ValueError("Steps must be positive")
        catalog = next((item for item in board_catalogs(root) if model_name in item["models"]), None)
        if catalog is None: raise ValueError("No sensor capability definition for " + model_name)
        definition = catalog["models"][model_name]
        device = {"id": model_name, "model": model_name, "bus": next(iter(catalog["buses"])),
                  "address": definition["default_address"], "values": definition.get("default_values", {})}
        model = _model_source(root, model_name)
        settings = {"signals": _device_settings(device, catalog, model)}
        waveform = waveform_for(root, device, settings, catalog)
        configuration_ = configuration(waveform, device, root=root, catalog=catalog)
        print("Preview · " + Path(filename).name + " · no data sent", flush=True)
        for step in range(args.steps):
            samples = sample_values([device], step * args.interval, {model_name: waveform},
                                    {model_name: configuration_}, root=root, catalog=catalog)
            print_samples(samples, step * args.interval, catalog)
    except (OSError, ValueError, RuntimeError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--events", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="preview samples without connecting or sending to QEMU")
    parser.add_argument("--device", help="preview or send only this configured device ID")
    args = parser.parse_args()
    try:
        run_session(steps=args.steps, events=args.events, dry_run=args.dry_run, device_id=args.device)
    except KeyboardInterrupt:
        print("Synthetic data stopped.", flush=True)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")
