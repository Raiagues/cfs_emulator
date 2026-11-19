"""Generate QEMU register models from bounded, declarative I²C descriptions."""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Expected an integer between {low} and {high}")
    return value


def render(model):
    name = model["name"]
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,15}", name):
        raise ValueError("Use a lowercase model identifier of 2–16 characters")
    identity = integer(model["id_register"], 0, 255)
    identity_value = integer(model["id_value"], 0, 255)
    integer(model["address"], 8, 119)
    used, names, outputs = {identity}, set(), []
    reset, writes, sleep_checks = [], [], []
    setup = {}
    for register in model["controls"]:
        reg = integer(register["register"], 0, 255)
        if reg in used:
            raise ValueError("Overlapping control register")
        used.add(reg)
        reset.append(f'    s->registers[{reg}] = {integer(register["reset"], 0, 255)};')
        body = f's->registers[{reg}] = byte;'
        setup[reg] = integer(register["setup"], 0, 255)
        reset_mask = integer(register.get("reset_mask", 0), 0, 255)
        sleep_mask = integer(register.get("sleep_mask", 0), 0, 255)
        if reset_mask & sleep_mask or setup[reg] & (reset_mask | sleep_mask):
            raise ValueError("Startup writes must wake the device and leave reset clear")
        if sleep_mask:
            sleep_checks.append(f"    if (s->registers[{reg}] & {sleep_mask}) {{ return; }}")
        if reset_mask:
            body = f'if (byte & {reset_mask}) {{ reset_registers(s); }} else {{ {body} }}'
        writes.append(f'        case {reg}: {body} break;')
    for output in model["outputs"]:
        prop = output["name"]
        reg = integer(output["register"], 0, 254)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", prop) or prop in names or prop in {"type", "realized", "hotpluggable", "hotplugged", "address", "id", "bus"}:
            raise ValueError("Output names must be unique lowercase identifiers")
        if reg in used or reg + 1 in used:
            raise ValueError("Output registers overlap")
        used.update((reg, reg + 1))
        names.add(prop)
        values = [integer(output[key], -2**30, 2**30) for key in ("initial", "offset")]
        values += [integer(output[key], 1, 1000000) for key in ("counts", "divisor")]
        range_reg = -1
        shift = 0
        if "range_register" in output:
            range_reg = integer(output["range_register"], 0, 255)
            shift = integer(output["range_shift"], 0, 6)
            if range_reg not in setup or setup[range_reg] & (3 << shift):
                raise ValueError("Declare the range control and select its base sensitivity at startup")
        values.extend((range_reg, shift))
        outputs.append('    {"%s", %d, %s},' % (prop, reg, ', '.join(map(str, values))))
    integer(len(outputs), 1, 16)
    template = (HERE / "device.c.in").read_text()
    for key, value in dict(MODEL=name, COUNT=len(outputs), OUTPUTS="\n".join(outputs),
                           ID_REG=identity, ID_VALUE=identity_value, RESET="\n".join(reset),
                           WRITES="\n".join(writes), SLEEP="\n".join(sleep_checks)).items():
        template = template.replace("@"+key+"@", str(value))
    return template


def fingerprint():
    sources = [HERE / "device.c.in", HERE / "generate.py", *sorted((HERE / "models").glob("*.json"))]
    return hashlib.sha256(b"".join(path.read_bytes() for path in sources)).hexdigest()


if __name__ == "__main__" and sys.argv[1:] == ["--fingerprint"]:
    print(fingerprint())
elif __name__ == "__main__":
    target = Path(sys.argv[1])
    for path in sorted((HERE / "models").glob("*.json")):
        file = "studio_" + path.stem + ".c"
        (target / file).write_text(render(json.loads(path.read_text())))
        with (target / "meson.build").open("a") as build:
            build.write(f"\nsystem_ss.add(when: 'CONFIG_I2C', if_true: files('{file}'))\n")
