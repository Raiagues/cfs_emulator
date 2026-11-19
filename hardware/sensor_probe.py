"""Read a known sensor's registers using the same transaction on Linux targets."""
import json
import shlex
from project.model import board_catalog, load_config, validate_hardware
from hardware.manager import HardwareError
from project.sensor_models import display_units, burst, identity_bytes, load, model_paths
from project.qemu.generate import register_models


# Linux I2C_RDWR is present on both the minimal guest and Raspberry Pi OS.
# Use a repeated START between selecting the register and reading the burst.
READ_REGISTERS = """
import ctypes as c, fcntl, json, sys
bus, address = map(int, sys.argv[1:3])
class Message(c.Structure):
    _fields_ = [('addr', c.c_uint16), ('flags', c.c_uint16), ('len', c.c_uint16), ('buf', c.c_void_p)]
class Transfer(c.Structure):
    _fields_ = [('msgs', c.POINTER(Message)), ('nmsgs', c.c_uint32)]
blocks = []
with open('/dev/i2c-%d' % bus,'r+b', buffering=0) as device:
    for register, size in json.loads(sys.argv[3]):
        pointer, data = c.c_ubyte(register), (c.c_ubyte * size)()
        messages = (Message * 2)(Message(address, 0, 1, c.addressof(pointer)),
                                 Message(address, 1, size, c.addressof(data)))
        if fcntl.ioctl(device, 0x0707, Transfer(messages, 2)) != 2:
            raise OSError('Incomplete I2C read')
        blocks.append(bytes(data).hex())
print(json.dumps(blocks))
"""


def probe(manager, target, device_id, connection, emit):
    config = load_config(manager.root)
    validate_hardware(config, manager.root)
    catalog = board_catalog(config["board"], manager.root)
    device = next((item for item in config["devices"] if item["id"] == device_id), None)
    if target not in ("physical", "qemu") or device is None:
        raise HardwareError("Select a configured sensor on a board or emulator.")
    bus = catalog["buses"][device["bus"]]["device"].split("-")[-1]
    addr = hex(device["address"])
    values = {}
    result = {"model": device["model"], "address": device["address"], "bus": device["bus"], "values": values}

    def read(blocks):
        cmd = shlex.join(["python3", "-c", READ_REGISTERS, bus, str(device["address"]), json.dumps(blocks)])
        code, line = manager._capture(manager.ssh_argv(target, connection) + [cmd], 30)
        if code:
            raise HardwareError(line or "The sensor did not respond.")
        try:
            # _capture appends SSH diagnostics after stdout (e.g., on a first connection).
            data = [bytes.fromhex(raw) for raw in json.loads(line.splitlines()[0])]
        except (IndexError, TypeError, ValueError) as error:
            raise HardwareError("Unexpected I²C response: " + line) from error
        if [len(raw) for raw in data] != [size for _, size in blocks]:
            raise HardwareError("Incomplete I²C response")
        return data

    def sample(name, value, unit):
        values[name] = {"value": value, "unit": unit}
        emit(f"{name}: {value:.3f} {unit}")

    name = device["model"]
    definitions = model_paths(manager.root)
    if name in definitions:
        spec = load(definitions[name])
    else:
        legacy = register_models(manager.root).get(name)
        if legacy is None:
            raise HardwareError(f"{name} has no register map for the hardware probe")
        spec = json.loads(legacy.read_text())
    if spec.get("protocol") == "custom":
        raise HardwareError("This sensor uses its flight driver to read the device")
    first, size = burst(spec)
    identity = bytes(identity_bytes(spec))
    registers = [c["register"] for c in spec["controls"]]
    ready = spec.get("ready")
    if ready:
        registers.append(ready["register"])
    blocks = ([(spec["id_register"], len(identity))] if identity else [])
    blocks += [(reg, 1) for reg in registers] + [(first, size)]
    captured = read(blocks)
    if identity:
        found = captured.pop(0)
        if found != identity:
            raise HardwareError(f"Unexpected device identity {found.hex()}")
        result["identity"] = int.from_bytes(found, "big")
        emit(f"I²C {addr} · identity 0x{found.hex()}")
    data = captured.pop()
    control_values = {reg: raw[0] for reg, raw in zip(registers, captured)}
    if any(control_values[c["register"]] & c.get("sleep_mask", 0) for c in spec["controls"]):
        result["asleep"] = True
        emit("Identity verified. Start the flight reader to wake the sensor and read its outputs.")
        return result
    if ready and control_values[ready["register"]] & ready["mask"] != ready["mask"]:
        raise HardwareError("The sensor has no new sample ready")
    for output in spec["outputs"]:
        offset = output["register"] - first
        raw = int.from_bytes(data[offset:offset + 2], "big", signed=True)
        if raw == output.get("invalid_raw") or raw & output.get("reserved_mask", 0):
            raise HardwareError(f"Invalid raw sample for {output['name']}")
        counts = output.get("counts")
        numerator = raw * output["divisor"]
        if "range_register" in output:
            gains = output.get("gain_counts")
            mask = len(gains) - 1 if gains else 3
            index = (control_values[output["range_register"]] >> output["range_shift"]) & mask
            if gains:
                counts = gains[index]
            else:
                numerator *= 1 << index
        if not counts:
            raise HardwareError(f"Invalid sensitivity for {output['name']}")
        scale, unit = display_units(output["unit"])
        sample(output["name"], (numerator / counts + output["offset"]) / scale, unit)
    return result


def validate_model(manager, device_id, emit, cancel):
    from hardware.infrastructure import emulator_config
    config = load_config(manager.root)
    validate_hardware(config, manager.root)
    device = next((item for item in config["devices"] if item["id"] == device_id), None)
    definition = register_models(manager.root).get(device["model"]) if device else None
    if definition is None:
        raise HardwareError("Choose a registered I²C model on the workbench.")
    emit("Checking the register map on a separate emulated Pi 4.")
    project = manager.root / "project"
    manager._stream(["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "python3",
                     "-v", f"{project}:/work/project:ro", "-w", "/work", emulator_config(manager.root)["image"],
                     "-m", "project.qemu.check_device", str(definition.relative_to(manager.root))], emit, cancel, timeout=60)
    emit("Identity, reset values and the sample burst passed.")
