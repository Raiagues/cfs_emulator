"""Encode engineering values as the register bytes consumed by the flight HAL."""
import fcntl
import os
import re

from project.defaults import native_devices
from project.model import board_catalog, load_config
from project.sensor_models import identity_bytes, load, model_paths


def initial_registers(spec):
    data = bytearray(256)
    for index, value in enumerate(identity_bytes(spec)):
        data[spec["id_register"] + index] = value
    if ready := spec.get("ready"):
        data[ready["register"]] = ready["mask"]
    for control in spec["controls"]:
        data[control["register"]] = control["setup"]
    return data


def encode_values(registers, spec, values):
    tolerance = {}
    for output in spec["outputs"]:
        name = output["name"]
        if name not in values:
            continue
        gain = output.get("counts", 1)
        if "range_register" in output:
            selector = registers[output["range_register"]] >> output["range_shift"]
            gains = output.get("gain_counts")
            gain = gains[selector & (len(gains)-1)] if gains else gain / (1 << (selector & 3))
        if gain <= 0:
            raise ValueError(f"Invalid gain on register {output['register']} of {spec['name']}")
        quantum = 1 + output.get("reserved_mask", 0)
        raw = round((values[name]-output["offset"])*gain/output["divisor"]/quantum)*quantum
        raw = max(-32768, min(32767 & ~(quantum-1), raw))
        start = output["register"]
        registers[start:start+2] = raw.to_bytes(2, "big", signed=True)
        tolerance[name] = .5*quantum*output["divisor"]/gain + 1
    return tolerance


def register_file(root, device, catalog):
    path = catalog["buses"][device["bus"]]["device"]
    bus = re.fullmatch(r"/dev/i2c-(\d+)", path)
    if not bus:
        raise ValueError(f"Unsupported I2C bus path {path}")
    return native_devices(root) / f"i2c{int(bus[1])}-0x{device['address']:02x}.bin"


def prepare(root):
    directory = native_devices(root)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = load_config(root)
    catalog = board_catalog(config["board"], root)
    paths = model_paths(root)
    for device in config["devices"]:
        if catalog["buses"][device["bus"]].get("transport") != "linux_i2c" or device["model"] not in paths:
            continue
        spec = load(paths[device["model"]])
        if spec.get("protocol") == "custom":
            continue
        registers = initial_registers(spec)
        values = {output["name"]: output["initial"] for output in spec["outputs"]}
        encode_values(registers, spec, {**values, **device["values"]})
        path = register_file(root, device, catalog)
        with path.open("a+b", buffering=0) as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.truncate(0)
            stream.write(registers)
    return directory


def write(path, spec, values):
    with path.open("r+b", buffering=0) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        data = bytearray(stream.read())
        if len(data) != 256:
            raise ValueError(f"{path} is not a complete register image")
        tolerance = encode_values(data, spec, values)
        if os.pwrite(stream.fileno(), data, 0) != len(data):
            raise OSError(f"Incomplete register write to {path}")
    return tolerance
