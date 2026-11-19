"""Build QEMU I²C devices from the same register descriptions used in flight."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from project.sensor_models import model_paths, load, validate


def render(model):
    model = validate(model)
    if model.get("emulator", "register") != "register":
        raise ValueError("This device uses a separately implemented QEMU model")
    reset, writes, sleep_checks = [], [], []
    for control in model["controls"]:
        reg, mask = control["register"], control.get("reset_mask", 0)
        reset.append(f'    s->registers[{reg}] = {control["reset"]};')
        body = f's->registers[{reg}] = byte;'
        if control.get("sleep_mask"):
            sleep_checks.append(f'    if (s->registers[{reg}] & {control["sleep_mask"]}) {{ return; }}')
        if mask:
            body = f'if (byte & {mask}) {{ reset_registers(s); }} else {{ {body} }}'
        writes.append(f'        case {reg}: {body} break;')
    outputs = []
    for output in model["outputs"]:
        values = [output[k] for k in ("initial", "offset", "counts", "divisor")]
        values.extend([output.get("range_register", -1), output.get("range_shift", 0)])
        outputs.append('    {"%s", %d, %s},' % (output["name"], output["register"], ', '.join(map(str, values))))
    template = (HERE / "device.c.in").read_text()
    for key, value in dict(MODEL=model["name"], COUNT=len(outputs), OUTPUTS="\n".join(outputs),
                           ID_REG=model["id_register"], ID_VALUE=model["id_value"], RESET="\n".join(reset),
                           WRITES="\n".join(writes), SLEEP="\n".join(sleep_checks)).items():
        template = template.replace("@"+key+"@", str(value))
    return template


def register_models(root=ROOT):
    # Older Studio projects keep already registered custom emulators here.
    models = {path.stem: path for path in sorted((root / "project/qemu/models").glob("*.json"))}
    for name, path in model_paths(root).items():
        if load(path).get("emulator", "register") == "register":
            models[name] = path
        else:
            models.pop(name, None)
    return models


def fingerprint():
    digest = hashlib.sha256((HERE / "device.c.in").read_bytes())
    for name, path in sorted(register_models().items()):
        digest.update(name.encode())
        digest.update(render(json.loads(path.read_text())).encode())
    return digest.hexdigest()


if __name__ == "__main__":
    if sys.argv[1:] == ["--fingerprint"]:
        print(fingerprint())
    else:
        target = Path(sys.argv[1])
        for name, path in register_models().items():
            file = "studio_" + name + ".c"
            (target / file).write_text(render(json.loads(path.read_text())))
            with (target / "meson.build").open("a") as build:
                build.write(f"\nsystem_ss.add(when: 'CONFIG_I2C', if_true: files('{file}'))\n")
