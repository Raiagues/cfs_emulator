"""Read a known sensor's registers using the same transaction on Linux targets."""
import json
import shlex
from project.model import board_catalog, load_config, validate_hardware
from hardware.manager import HardwareError
from sensors.simulator import UNITS


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

    if device["model"] == "tmp105":
        data, = read([(0, 2)])
        sample("temperature", int.from_bytes(data, "big", signed=True) / 256, "°C")
    elif device["model"] == "lsm303dlhc_mag":
        identity, data = read([(10, 3), (3, 6)])
        if identity != b"H43":
            raise HardwareError("Magnetometer identity mismatch")
        for index, axis in enumerate(("x", "z", "y")):
            sample("mag-" + axis, int.from_bytes(data[2*index:2*index+2], "big", signed=True), "counts")
    else:
        spec = json.loads((manager.root / "project/qemu/models" / (device["model"] + ".json")).read_text())
        first = min(out["register"] for out in spec["outputs"])
        size = max(out["register"] for out in spec["outputs"]) - first + 2
        blocks = [(spec["id_register"], 1)] + [(c["register"], 1) for c in spec["controls"]] + [(first, size)]
        id_bytes, *controls, data = read(blocks)
        identity = id_bytes[0]
        if identity != spec["id_value"]:
            raise HardwareError(f"Unexpected device identity {identity:#04x}")
        emit(f"I²C {addr} · WHO_AM_I = {identity:#04x}")
        result["identity"] = identity
        control_values = {}
        for control, raw_value in zip(spec["controls"], controls):
            register = control["register"]
            control_values[register] = raw_value[0]
            if control_values[register] & control.get("sleep_mask", 0):
                result["asleep"] = True
                emit("Identity verified. Start the flight reader to wake the sensor and read its outputs.")
                return result
        for out in spec["outputs"]:
            index = out["register"] - first
            raw = int.from_bytes(data[index:index+2], "big", signed=True)
            counts = out["counts"]
            if "range_register" in out:
                step = (control_values[out["range_register"]] >> out["range_shift"]) & 3
                counts /= 1 << step
            value = raw * out["divisor"] / counts + out["offset"]
            scale, unit = UNITS[out["unit"]]
            sample(out["name"], value / scale, unit)
    return result


def validate_model(manager, device_id, emit, cancel):
    from hardware.infrastructure import emulator_config
    config = load_config(manager.root)
    validate_hardware(config, manager.root)
    device = next((item for item in config["devices"] if item["id"] == device_id), None)
    directory = manager.root / "project/qemu"
    if not device or not (directory / "models" / (device["model"] + ".json")).is_file():
        raise HardwareError("Choose a registered I²C model on the workbench.")
    emit("Checking the register map on a separate emulated Pi 4.")
    manager._stream(["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "python3",
                     "-v", f"{directory}:/models:ro", emulator_config(manager.root)["image"],
                     "/models/check_device.py", "/models/models/" + device["model"] + ".json"], emit, cancel, timeout=60)
    emit("Identity, reset values and the sample burst passed.")
