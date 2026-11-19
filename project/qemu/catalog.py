"""Generate host waveforms, Linux readers and the board catalog from a register map."""
import json
import math
from pathlib import Path
from project.model import identifier, safe_path
from project.qemu.generate import integer, render
from sensors.simulator import UNITS


def register(root, spec):
    from project.manage import commit
    root = Path(root)
    render(spec)  # Validate the same register map used by the QEMU build.
    name = identifier(spec["name"])
    library = identifier(name + "_lib")
    prefix = name.upper()
    catalog_path = "project/boards/raspi4b.json"
    drivers_path = "project/drivers/catalog.json"
    catalog = json.loads(safe_path(root, catalog_path).read_text())
    drivers = json.loads(safe_path(root, drivers_path).read_text())
    if name in catalog["models"] or library in drivers:
        raise ValueError("This model or library is already registered")
    fields, reads, signals, setup = [], [], [], []
    properties, defaults = {}, {}
    for index, out in enumerate(spec["outputs"]):
        key, unit = out["name"], out["unit"]
        if unit not in UNITS:
            raise ValueError("Choose a supported output unit")
        scale, display = UNITS[unit]
        low = math.ceil(-32768 * out["divisor"] / out["counts"]) + out["offset"]
        high = math.floor(32767 * out["divisor"] / out["counts"]) + out["offset"]
        low, high = max(-2147483648,low), min(2147483647,high)
        integer(out["initial"], low, high)
        properties[key] = dict(type="integer", min=low, max=high, unit=unit)
        defaults[key] = out["initial"]
        field = "Value_" + key.replace("-", "_")
        fields.append(f"    int32 {field}; /* {unit} */")
        reads += [f"    Sample->{field} = (int32)((int64)DecodeWord(&data[{out['register'] - min(o['register'] for o in spec['outputs'])}]) * {out['divisor']} / {out['counts']} + {out['offset']});"]
        signals.append(f"        Signal({key!r}, {display!r}, {scale}),")
    for register in spec["controls"]:
        value = integer(register["setup"], 0, 255)
        setup.extend([f"    status = LINUX_I2C_WriteRegister(Device, Address, {register['register']:#04x}, {value:#04x});",
                      "    if (status != CFE_SUCCESS) { return status; }"])
    base = min(out["register"] for out in spec["outputs"])
    size = max(out["register"] for out in spec["outputs"]) - base + 2
    if size > 32:
        raise ValueError("Place the outputs in a single burst of up to 32 bytes")
    catalog["models"][name] = dict(cfs_driver=name,library=library,default_address=spec["address"],
                                   default_values=defaults,kind="sensor",properties=properties)
    drivers[library] = dict(entry_point=prefix+"_LIB_Init",systems=["linux"])
    encode=lambda data: json.dumps(data,indent=2,ensure_ascii=False)+"\n"
    files={catalog_path:encode(catalog),drivers_path:encode(drivers)}
    code=f"""/* Verify the device identity before applying its startup register writes. */
int32 {prefix}_Configure(const char *Device, uint16 Address)
{{
    uint8 identity;
    int32 status = LINUX_I2C_ReadRegister(Device, Address, {spec['id_register']:#04x}, &identity, 1);
    if (status != CFE_SUCCESS) {{ return status; }}
    if (identity != {spec['id_value']:#04x}) {{ return -ENODEV; }}
{chr(10).join(setup)}
    return CFE_SUCCESS;
}}

/* Sign extend one big-endian register pair before converting to engineering units. */
static int32 DecodeWord(const uint8 *data)
{{
    int32 word = ((int32)data[0] << 8) | data[1];
    return word >= 32768 ? word - 65536 : word;
}}

int32 {prefix}_Read(const char *Device, uint16 Address, {prefix}_Sample_t *Sample)
{{
    uint8 data[{size}];
    if (Sample == NULL) {{ return -EINVAL; }}
    int32 status = LINUX_I2C_ReadRegister(Device, Address, {base:#04x}, data, sizeof(data));
    if (status != CFE_SUCCESS) {{ return status; }}
{chr(10).join(reads)}
    return CFE_SUCCESS;
}}
"""
    header=f"""/* Values use the engineering units in the device register description. */
typedef struct
{{
{chr(10).join(fields)}
}} {prefix}_Sample_t;

int32 {prefix}_Configure(const char *Device, uint16 Address);
int32 {prefix}_Read(const char *Device, uint16 Address, {prefix}_Sample_t *Sample);

"""
    from project.appgen.sample import copy_sample
    driver = f"project/drivers/{library}/"
    sample = copy_sample(root / "cFS", "sample_lib", library)
    source_path = f"fsw/src/{library}.c"
    public_path = f"fsw/public_inc/{library}.h"
    sample[source_path] += f'\n#include "linux_i2c_lib.h"\n#include <errno.h>\n\n' + code
    declarations, guard = sample[public_path].rsplit("#endif", 1)
    sample[public_path] = declarations + header + "\n#endif" + guard
    sample["CMakeLists.txt"] += f"\n# Sensor registers use the selected board's Linux I2C transport.\nadd_cfe_app_dependency({library} linux_i2c_lib)\n"
    files.update({driver + path: content for path, content in sample.items()})
    adapter = f"project/adapters/{name}/"
    tokens=dict(VALUE_TYPE=prefix+"_Sample_t",VALUE_NOTE="Latest coherent register burst.",VALUE_INCLUDE=f'#include "{library}.h"',
                DRIVER_INCLUDE=f'#include "{library}.h"', DRIVER_STATE="static bool @PREFIX@_@ENTITY@_Configured;",DRIVER_INIT="    @PREFIX@_@ENTITY@_Configured = false;")
    files[adapter+"adapter.json"]=encode(dict(library=library,device_pattern="/dev/i2c-[0-9]+",max_address=127,tokens=tokens))
    files[adapter+"read.c.in"]=f"""    if (!@PREFIX@_@ENTITY@_Configured)
    {{
        int32 status = {prefix}_Configure(@PREFIX@_@ENTITY_UPPER@_DEVICE, @PREFIX@_@ENTITY_UPPER@_ADDRESS);
        if (status != CFE_SUCCESS) {{ return status; }}
        @PREFIX@_@ENTITY@_Configured = true;
    }}
    return {prefix}_Read(@PREFIX@_@ENTITY_UPPER@_DEVICE, @PREFIX@_@ENTITY_UPPER@_ADDRESS, Value);
"""
    files[adapter+"event.c.in"]=""
    files[f"sensors/{name}.py"]=f'''"""Synthetic outputs for the {name} register map."""
from sensors.schema import Sensor, Signal

SIGNALS = { {out["name"]:{"function":"constant"} for out in spec["outputs"]}!r}


def configure(device):
    return Sensor.from_device(device, (
{chr(10).join(signals)}
    ))


def sample(seconds, initial):
    return initial
'''
    spec_path=f"project/qemu/models/{name}.json"
    files[spec_path]=encode(spec)
    for path in files.keys() - {catalog_path,drivers_path}:
        dest=safe_path(root,path)
        if dest.exists() and not (path==spec_path and json.loads(dest.read_text())==spec):
            raise ValueError("A source file already exists: "+path)
    return {"changed":commit(root,files),"model":name}
