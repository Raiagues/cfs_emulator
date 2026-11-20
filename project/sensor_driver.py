"""Materialize the cFS ABI and constant HAL profile of one sensor model."""
import json
from pathlib import Path
import re

from project.model import safe_path
from project.sensor_models import MODELS, burst, identity_bytes, load, output_limits


def value_type(spec):
    return spec.get("abi", {}).get("sample", spec["name"].upper() + "_Sample_t")


def output_tags(output):
    minimum, maximum = output_limits(output)
    return f'@unit {output["unit"]} @range {minimum}..{maximum}'


def binding_fragments(template, model_prefix):
    """Map named fragments to the insertion points in the sample_app reader template."""
    parts = re.split(r"(?m)^/\* @studio\.fragment ([A-Z][A-Z0-9_]*) \*/\n", template.read_text())
    result = {}
    for name, body in zip(parts[1::2], parts[2::2]):
        if name in result:
            raise ValueError(f"{template}: duplicate fragment {name}")
        result[name] = body.rstrip("\n").replace("@MODEL_PREFIX@", model_prefix)
    if parts[0].strip() or result.keys() != {"DRIVER_INCLUDE", "DRIVER_STATE", "DRIVER_INIT", "READ_VALUE"}:
        raise ValueError(f"{template}: incomplete HAL binding fragments")
    return result


def register_profile(spec):
    if spec.get("protocol") == "custom":
        return "static const HAL_SENSOR_Profile_t Profile = {.OutputCount = %d};" % len(spec["outputs"])
    declarations = []
    setup, ranges, outputs = [], [], []
    selectors = []
    gain_tables = {}
    first, size = burst(spec)

    def array(ctype, name, rows):
        if not rows:
            return "NULL"
        declarations.append(f"static const {ctype} {name}[] = {{\n    " + ",\n    ".join(rows) + "\n};")
        return name

    identity = identity_bytes(spec)
    id_table = array("uint8_t", "Identity", [hex(n) for n in identity])
    for item in spec["controls"]:
        setup.append("{.Register = %#04x, .Value = %#04x}" % (item["register"], item["setup"]))
    writes = array("HAL_SENSOR_Write_t", "Setup", setup)
    for i, output in enumerate(spec["outputs"]):
        fields = [f'.ByteOffset = {output["register"] - first}', f'.Numerator = {output["divisor"]}',
                  f'.Counts = {output.get("counts", 0)}', f'.Zero = {output["offset"]}']
        index = -1
        if "range_register" in output:
            gains = output.get("gain_counts")
            selector = (output["range_register"], output["range_shift"], len(gains) - 1 if gains else 3)
            if selector not in selectors:
                selectors.append(selector)
                ranges.append("{.Register = %#04x, .Shift = %d, .Mask = %d}" % selector)
            index = selectors.index(selector)
            if gains:
                key = tuple(gains)
                if key not in gain_tables:
                    gain_tables[key] = array("int32_t", f"Gain{i}", list(map(str, gains)))
                fields.append(f".GainCounts = {gain_tables[key]}")
        fields.append(f".RangeIndex = {index}")
        if "invalid_raw" in output:
            fields.extend([".HasInvalidRaw = true", f'.InvalidRaw = {output["invalid_raw"]}'])
        if "reserved_mask" in output:
            fields.append(f'.ReservedMask = {output["reserved_mask"]:#06x}')
        outputs.append("{" + ", ".join(fields) + "}")
    range_table = array("HAL_SENSOR_Range_t", "Ranges", ranges)
    output_table = array("HAL_SENSOR_Output_t", "Outputs", outputs)
    ready = spec.get("ready", {})
    declarations.append(f"""static const HAL_SENSOR_Profile_t Profile = {{
    .Identity = {id_table}, .IdentityRegister = {spec.get("id_register", 0):#04x}, .IdentitySize = {len(identity)},
    .Setup = {writes}, .SetupCount = {len(setup)},
    .ReadyRegister = {ready.get("register", 0):#04x}, .ReadyMask = {ready.get("mask", 0):#04x},
    .Ranges = {range_table}, .RangeCount = {len(ranges)},
    .FirstRegister = {first:#04x}, .BurstSize = {size},
    .Outputs = {output_table}, .OutputCount = {len(outputs)}
}};""")
    return "\n\n".join(declarations)


def library_cmake(module, sources, dependencies=()):
    contents = (f"project(CFE_{module.upper()} C)\n\nadd_cfe_app({module} {' '.join(sources)})\n"
                f"target_include_directories({module} PUBLIC fsw/public_inc)\n")
    if dependencies:
        contents += f"add_cfe_app_dependency({module} {' '.join(dependencies)})\n"
    if module == "linux_i2c_lib":
        contents += ('if(TARGETSYSTEM MATCHES "^native_")\n'
                     '    target_compile_definitions(linux_i2c_lib PRIVATE FLIGHT_STUDIO_NATIVE_I2C)\nendif()\n')
    return contents


def cmake(root, name, spec=None):
    directory = MODELS / name
    module = name + "_lib"
    if spec is None:
        spec = load(safe_path(root, directory / "model.json"))
    dependencies = ["hal_sensor", "linux_i2c_lib"] if "abi" in spec else ["hal_sensor"]
    sources = [f"fsw/src/{module}.c"]
    for extra in ("driver.c", "compat.c"):
        if safe_path(root, directory / extra).is_file():
            sources.append("fsw/src/" + extra)
    return library_cmake(module, sources, dependencies)


def source_files(root, model_path):
    spec = load(model_path)
    name = spec["name"]
    directory = MODELS / name
    module, prefix = name + "_lib", name.upper()
    abi = spec.get("abi", {})
    sample = value_type(spec)
    fields = abi.get("fields", ["Value_" + o["name"].replace("-", "_") for o in spec["outputs"]])
    outputs = spec["outputs"]
    declaration = ""
    if sample == "int32":
        copy = "        *sample = values[0];"
    else:
        members = [f'    int32 {field}; /**< {output_tags(o)} */' for field, o in zip(fields, outputs)]
        declaration = "typedef struct\n{\n" + "\n".join(members) + "\n} " + sample + ";\n"
        copy = "\n".join(f"        sample->{field} = values[{i}];" for i, field in enumerate(fields))
    files = {"CMakeLists.txt": cmake(root, name, spec)}
    for extra in ("driver.c", "compat.c"):
        path = safe_path(root, directory / extra)
        if path.is_file():
            files["fsw/src/" + extra] = path.read_text()
    state = safe_path(root, directory / "state.h")
    if state.is_file():
        files[f"fsw/public_inc/{name}_state.h"] = state.read_text()
    custom = "fsw/src/driver.c" in files
    if spec.get("protocol") == "custom" and not custom:
        raise ValueError(f"{name} needs driver.c to implement its custom protocol")
    compat = safe_path(root, directory / "compat.h")
    read = abi.get("read", prefix + "_Read")
    legacy = "abi" in spec
    legacy_source = safe_path(root, "project/drivers/templates/linux_api.c.in").read_text() if legacy else ""
    tokens = {"LEGACY_SOURCE": legacy_source,
              "LEGACY_DECLARATIONS": (f"int32 {prefix}_Configure(const char *path, uint16 address);\n"
                                      f"int32 {read}(const char *path, uint16 address, {sample} *sample);\n") if legacy else "",
              "TRANSPORT_INCLUDE": '#include "linux_i2c_sensor.h"\n' if legacy else "",
              "PREFIX": prefix, "MODEL": name, "LIBRARY": module, "VALUE_TYPE": sample,
              "READ_NAME": read, "COUNT": len(outputs), "COPY_VALUES": copy,
              "STATE_DECLARATION": (f'#include "{name}_state.h"\n' if state.is_file()
                                    else f"typedef struct {{ uint8_t Reserved; }} {prefix}_State_t;\n"),
              "CHECK_STATE": "    if (!state)\n        return (HAL_SENSOR_Device_t){0};\n" if state.is_file() else "",
              "SAMPLE_DECLARATION": declaration, "REGISTER_PROFILE": register_profile(spec),
              "OPS": "&" + prefix + "_Ops" if custom else "NULL",
              "OPS_DECLARATION": f"extern const HAL_SENSOR_Ops_t {prefix}_Ops;\n" if custom else "",
              "EXTRA_API": compat.read_text() if compat.is_file() else ""}
    for template, dest in [("sensor.h.in", f"fsw/public_inc/{module}.h"), ("sensor.c.in", f"fsw/src/{module}.c")]:
        content = safe_path(root, Path("project/drivers/templates") / template).read_text()
        for key, value in tokens.items():
            content = content.replace("@" + key + "@", str(value))
        files[dest] = content
    return {path: content.encode() for path, content in files.items()}


def app_adapter(root, name):
    """Resolve model-backed adapters and existing hand-written project adapters."""
    directory = MODELS / name
    path = safe_path(root, directory / "model.json")
    if path.is_file():
        spec = load(path)
        prefix, library = name.upper(), name + "_lib"
        endpoint = "@PREFIX@_@ENTITY_UPPER@"
        event = safe_path(root, directory / "event.c.in")
        header = f'#include "{library}.h"'
        note = output_tags(spec["outputs"][0]) if value_type(spec) == "int32" else "Latest complete sample in model output units."
        binding = Path(__file__).with_name("appgen") / "templates/hal_sensor/i2c_binding.c.in"
        tokens = {"VALUE_TYPE": value_type(spec), "VALUE_NOTE": note,
                  "VALUE_INCLUDE": header, "VALUE_EVENT": event.read_text() if event.is_file() else "",
                  **binding_fragments(binding, prefix)}
        from project.driver_catalog import retains_legacy_sources
        dependencies = [library, "linux_i2c_lib"]
        if retains_legacy_sources(root, library):
            # Existing hand-edited libraries keep their old API and sources.
            dependencies = [library]
            read = spec.get("abi", {}).get("read", prefix + "_Read")
            args = f"{endpoint}_DEVICE, {endpoint}_ADDRESS"
            tokens.update(DRIVER_INCLUDE=header, DRIVER_STATE="", DRIVER_INIT="",
                          READ_VALUE=f"    return {read}({args}, Value);")
            if spec.get("controls") or identity_bytes(spec):
                flag = "@PREFIX@_@ENTITY@_Configured"
                tokens.update(DRIVER_STATE=f"static bool {flag};", DRIVER_INIT=f"    {flag} = false;",
                              READ_VALUE=f"""    if (!{flag})
    {{
        int32 status = {prefix}_Configure({args});
        if (status != CFE_SUCCESS)
            return status;
        {flag} = true;
    }}
""" + tokens["READ_VALUE"])
        return {"device_pattern": r"/dev/i2c-[0-9]+", "max_address": 127, "library": library,
                "dependencies": dependencies, "tokens": tokens}
    directory = Path("project/adapters") / name
    path = safe_path(root, directory / "adapter.json")
    if not path.is_file():
        raise ValueError(f"No sensor model or adapter configured for driver: {name}")
    adapter = json.loads(path.read_text())
    adapter["tokens"].update(READ_VALUE=safe_path(root, directory / "read.c.in").read_text(),
                             VALUE_EVENT=safe_path(root, directory / "event.c.in").read_text())
    return adapter
