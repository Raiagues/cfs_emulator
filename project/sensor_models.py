"""Sensor model contracts shared by cFS, board discovery, simulation and QEMU."""
import json
from pathlib import Path
import re

UNITS = {
    "counts": (1, "counts"),
    "millig": (1000, "g"),
    "millidegrees per second": (1000, "°/s"),
    "millidegrees Celsius": (1000, "°C"),
    "milli-microtesla": (1000, "µT"),
}
MODELS = Path("project/drivers/models")
MODEL_ID = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
C_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


def display_units(unit):
    """Unprefixed custom units are displayed in the same units as flight data."""
    return UNITS.get(unit, (1, unit))


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected an integer between {low} and {high}")
    return value


def identity_bytes(spec):
    if "identity_bytes" in spec:
        return spec["identity_bytes"]
    return [spec["id_value"]] if "id_value" in spec else []


def burst(spec):
    registers = [output["register"] for output in spec["outputs"]]
    first = min(registers)
    return first, max(registers) - first + 2


def output_limits(output):
    if "min" in output and "max" in output:
        return output["min"], output["max"]
    counts = output["counts"]
    scale = output["divisor"]
    return (max(-(2**31), -(32768 * scale // counts) + output["offset"]),
            min(2**31 - 1, 32767 * scale // counts + output["offset"]))


def _keys(value, required, optional, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - (required | optional)
    if missing:
        raise ValueError(f"{label} needs {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"Unknown field in {label}: {', '.join(sorted(unknown))}")


def _expand_scales(spec):
    """Several axes may use one named conversion, including the same gain table."""
    scales = spec["scales"]
    if not isinstance(scales, dict) or not isinstance(spec.get("outputs"), list):
        raise ValueError("Declare named scales and their output channels")
    for name, scale in scales.items():
        _keys(scale, {"unit", "offset", "divisor"},
              {"counts", "gain_counts", "range_register", "range_shift", "min", "max", "invalid_raw", "reserved_mask"},
              f"scale {name}")
    outputs = []
    for output in spec["outputs"]:
        if not isinstance(output, dict):
            raise ValueError("Each output must be an object")
        if "scale" in output:
            name = output["scale"]
            if not isinstance(name, str) or name not in scales:
                raise ValueError(f"Unknown output scale: {name}")
            if scales[name].keys() & output.keys():
                raise ValueError(f"Set shared conversion fields in scale {name}")
            output = {**scales[name], **output}
            del output["scale"]
        outputs.append(output)
    return {**{k: v for k, v in spec.items() if k != "scales"}, "outputs": outputs}


def _validate_conversion(output, controls, builtin):
    integer(output["divisor"], 1, 1000000)
    integer(output["offset"], -(2**30), 2**30)
    width = 2
    if ("range_register" in output) != ("range_shift" in output):
        raise ValueError("Specify both the range register and its bit shift")
    if ("counts" in output) == ("gain_counts" in output):
        raise ValueError(f"Choose fixed counts or a gain table for {output['name']}")
    if "gain_counts" in output:
        gains = output["gain_counts"]
        if not builtin or not isinstance(gains, list) or len(gains) not in (2, 4, 8) or "range_register" not in output:
            raise ValueError("A device gain table requires 2, 4 or 8 entries and a selector")
        for count in gains:
            integer(count, 0, 1000000)
        if not any(gains) or not {"min", "max"} <= output.keys():
            raise ValueError("Declare valid sensitivities and signal limits for a gain table")
        width = (len(gains) - 1).bit_length()
    else:
        integer(output["counts"], 1, 1000000)
    if "range_register" in output:
        reg = integer(output["range_register"], 0, 255)
        shift = integer(output["range_shift"], 0, 8 - width)
        if reg not in controls:
            raise ValueError("Declare the range register in controls")
        selection = (controls[reg] >> shift) & ((1 << width) - 1)
        if "gain_counts" in output and output["gain_counts"][selection] == 0:
            raise ValueError("The startup setting selects a reserved gain")
        if "gain_counts" not in output and selection != 0:
            raise ValueError("Choose a valid startup sensitivity")
    if not builtin and ("reserved_mask" in output or "invalid_raw" in output):
        raise ValueError("Reserved bits and overflow sentinels require a device-specific emulator")
    integer(output.get("reserved_mask", 0), 0, 65535)
    integer(output.get("invalid_raw", 0), -32768, 32767)


def validate(spec):
    if isinstance(spec, dict) and "scales" in spec:
        spec = _expand_scales(spec)
    custom = isinstance(spec, dict) and spec.get("protocol") == "custom"
    required = {"name", "address", "outputs"}
    optional = {"emulator", "abi", "addresses", "address_source", "protocol"}
    if not custom:
        required.add("controls")
        optional.update({"id_register", "id_value", "identity_bytes", "ready"})
    _keys(spec, required, optional, "model")
    if spec.get("protocol", "register") not in ("register", "custom"):
        raise ValueError("Choose a register or custom flight protocol")
    name = spec["name"]
    if not isinstance(name, str) or not MODEL_ID.fullmatch(name) or not 2 <= len(name) <= 15:
        raise ValueError("Use a snake_case model ID of 2–15 characters (the library adds _lib)")
    builtin = spec.get("emulator", "register") == "builtin"
    if custom and spec.get("emulator") != "external":
        raise ValueError("Use emulator=external for a protocol implemented in C")
    if not custom and spec.get("emulator", "register") not in ("register", "builtin"):
        raise ValueError("Choose a register model or an existing built-in QEMU device")
    address = integer(spec["address"], 8, 119)
    if "addresses" in spec and (not isinstance(spec["addresses"], list) or
                                address not in [integer(a, 8, 119) for a in spec["addresses"]]):
        raise ValueError("The default address must be one of the device addresses")
    occupied = set()

    def reserve(register, size):
        register = integer(register, 0, 256 - size)
        for byte in range(register, register + size):
            if byte in occupied:
                raise ValueError(f"Overlapping registers at {byte:#04x}")
            occupied.add(byte)

    identity = identity_bytes(spec)
    if not isinstance(identity, list) or ("id_register" in spec) != bool(identity) or ("identity_bytes" in spec and "id_value" in spec):
        raise ValueError("Declare an identity register and exactly one expected identity")
    if not custom and not builtin and ("id_value" not in spec or "identity_bytes" in spec):
        raise ValueError("Generated QEMU models require a one-byte identity")
    if identity:
        integer(len(identity), 1, 32)
        reserve(spec["id_register"], len(identity))
        for value in identity:
            integer(value, 0, 255)
    if "ready" in spec:
        _keys(spec["ready"], {"register", "mask"}, set(), "ready")
        if not builtin:
            raise ValueError("A data-ready register requires a device-specific emulator")
        reserve(spec["ready"]["register"], 1)
        integer(spec["ready"]["mask"], 1, 255)

    if not isinstance(spec.get("controls", []), list) or not isinstance(spec["outputs"], list):
        raise ValueError("Controls and outputs must be lists")
    controls = {}
    for control in spec.get("controls", []):
        _keys(control, {"register", "setup"} | (set() if builtin else {"reset"}), {"reset", "reset_mask", "sleep_mask"}, "control")
        reg = control["register"]
        reserve(reg, 1)
        controls[reg] = integer(control["setup"], 0, 255)
        if not builtin or "reset" in control:
            integer(control["reset"], 0, 255)
        reset = integer(control.get("reset_mask", 0), 0, 255)
        sleep = integer(control.get("sleep_mask", 0), 0, 255)
        if reset & sleep or controls[reg] & (reset | sleep):
            raise ValueError("Startup writes must wake the device and leave reset clear")

    integer(len(spec["outputs"]), 1, 16)
    names = {"type", "realized", "hotpluggable", "hotplugged", "address", "id", "bus"}
    for output in spec["outputs"]:
        if custom:
            _keys(output, {"name", "unit", "initial", "min", "max"}, set(), "custom output")
        else:
            _keys(output, {"name", "register", "unit", "initial", "divisor", "offset"},
                  {"counts", "range_register", "range_shift", "gain_counts", "reserved_mask", "invalid_raw", "min", "max"}, "output")
            reserve(output["register"], 2)
            _validate_conversion(output, controls, builtin)
        key = output["name"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", key) or key in names:
            raise ValueError("Output names must be unique lowercase signal identifiers")
        names.add(key)
        unit = output["unit"]
        if not isinstance(unit, str) or unit.strip() != unit or not re.fullmatch(r"[\w°µ%][\w°µ% .·/^+−-]{0,47}", unit):
            raise ValueError("Give each output a short engineering unit, such as counts, Pa or m/s²")
        if ("min" in output) != ("max" in output):
            raise ValueError("Specify both signal limits")
        low, high = output_limits(output)
        integer(low, -(2**31), 2**31 - 1)
        integer(high, low, 2**31 - 1)
        integer(output["initial"], low, high)
    if not custom:
        integer(burst(spec)[1], 2, 32)
    abi = spec.get("abi", {})
    _keys(abi, set(), {"fields", "sample", "read"}, "flight ABI")
    fields = abi.get("fields", [])
    if not isinstance(fields, list):
        raise ValueError("Flight ABI fields must be an array of C names")
    if abi.get("sample") == "int32" and len(spec["outputs"]) != 1:
        raise ValueError("A scalar sensor has exactly one output")
    if not all(isinstance(value, str) and C_NAME.fullmatch(value)
               for value in [*fields, *[abi[k] for k in ("sample", "read") if k in abi]]):
        raise ValueError("Invalid C identifier in sensor ABI")
    if "fields" in abi and (len(fields) != len(spec["outputs"]) or len(fields) != len(set(fields))):
        raise ValueError("Declare one unique C field for each output")
    return spec


def model_paths(root):
    from project.model import safe_path
    directory = safe_path(root, MODELS)
    return {p.parent.name: safe_path(root, MODELS / p.parent.name / "model.json")
            for p in sorted(directory.glob("*/model.json"))}


def load(path):
    try:
        spec = validate(json.loads(path.read_text()))
    except ValueError as exc:
        raise ValueError(f"{path.parent.name}/model.json: {exc}") from exc
    if spec["name"] != path.parent.name:
        raise ValueError(f"Sensor ID must match its directory: {path}")
    return spec


def board_model(spec):
    properties = {}
    for output in spec["outputs"]:
        low, high = output_limits(output)
        properties[output["name"]] = {"type": "integer", "min": low, "max": high, "unit": output["unit"]}
    return {"kind": "sensor", "transport": "linux_i2c", "register_probe": spec.get("protocol") != "custom", "cfs_driver": spec["name"],
            "library": spec["name"] + "_lib", "default_address": spec["address"],
            "default_values": {o["name"]: o["initial"] for o in spec["outputs"]}, "properties": properties,
            **{key: spec[key] for key in ("addresses", "address_source") if key in spec}}


def register(root, spec, driver=None, state_header=None):
    """Install an authored model and its editable waveform in one transaction."""
    import fcntl
    import os
    from project.model import safe_path
    # The CLI and Studio can register the same name concurrently. Lock a
    # stable directory inode across the collision check and the complete commit.
    lock = os.open(safe_path(root, "project/drivers"), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _register(Path(root), spec, driver, state_header)
    finally:
        os.close(lock)


def _register(root, spec, driver, state_header):
    from project.driver_catalog import load_catalog
    from project.model import board_catalogs, safe_path
    from project.manage import commit
    from project.flight_sources import nasa_module_names
    validate(spec)
    custom = spec.get("protocol") == "custom"
    if custom and not driver:
        raise ValueError("A custom protocol requires a driver.c implementing the model's Read operation")
    if state_header is not None and not driver:
        raise ValueError("Provide the driver that uses the per-device state header")
    if spec.get("emulator") == "builtin" or "abi" in spec:
        raise ValueError("The register designer creates standard register sensors")
    name = spec["name"]
    library = name + "_lib"
    path = (MODELS / name / "model.json").as_posix()
    waveform = f"sensors/{name}.py"
    if not custom and not name.startswith("lab_"):
        raise ValueError("Start a new QEMU device name with lab_")
    if (any(name in board["models"] for board in board_catalogs(root)) or library in load_catalog(root)
            or library in nasa_module_names(root, "libs") or library in nasa_module_names(root, "apps")
            or any(safe_path(root, p).exists() for p in
                   (f"mission/libs/{library}", f"mission/apps/{library}", MODELS / name, waveform))):
        raise ValueError(f"A model, module or waveform named {name} already exists")
    # The Python file is an editable formula. Signal order and units come from
    # model.json at runtime, also when the schema is edited after registration.
    template = safe_path(root, "project/drivers/templates/waveform.py.in").read_text()
    files = {path: json.dumps(spec, indent=2, ensure_ascii=False) + "\n", waveform: template}
    if driver is not None:
        files[str(MODELS / name / "driver.c")] = driver
    if state_header is not None:
        files[str(MODELS / name / "state.h")] = state_header
    return {"changed": commit(root, files), "model": name, "definition": path}
