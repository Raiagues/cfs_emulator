"""Render the sample_app-style C files; no filesystem writes occur here."""

from pathlib import Path
import json
import re


TEMPLATES = Path(__file__).with_name("templates")
ADAPTERS = Path(__file__).resolve().parents[1] / "adapters"


def entity_name(name):
    return "".join(part.capitalize() for part in name.split("_"))


def render_app(manifest):
    """Return {relative_path: (contents, managed)} for one app manifest.

    Managed files are derived from project app settings. User files are created once, then
    preserved so regeneration never replaces implementation code or payloads.
    """
    app = manifest["name"]
    prefix = app.upper()
    sensors = manifest.get("sensors", [])
    commands = manifest.get("commands", [])
    telemetry = manifest.get("telemetry", [])
    result = {}
    license_text = (TEMPLATES / "license.txt").read_text()
    values = {
        "APP": app,
        "PREFIX": prefix,
        "CMD_MID": f'0x{manifest["cmd_mid"]:04X}',
        "HK_REQUEST_MID": f'0x{manifest["hk_request_mid"]:04X}',
        "WAKEUP_MID": f'0x{manifest["wakeup_mid"]:04X}',
        "HK_TLM_MID": f'0x{manifest["hk_tlm_mid"]:04X}',
        "PERF_ID": str(manifest["perf_id"]),
    }

    def emit(template, path, managed=True, extra=None):
        text = (TEMPLATES / template).read_text()
        tokens = dict(values)
        tokens.update(extra or {})
        for key, value in tokens.items():
            text = text.replace(f"@{key}@", str(value))
        unresolved = re.findall(r"@[A-Z][A-Z0-9_]*@", text)
        if unresolved:
            raise ValueError(f"Unresolved template tokens in {template}: {', '.join(unresolved)}")
        if path.endswith((".c", ".h")):
            ownership = "Generated mission integration; edit native configuration or project app settings." if managed else "User file: preserved by appgen sync."
            text = license_text + f"\n/* {ownership} */\n\n" + text
        result[path] = (text, managed)

    command_includes = []
    command_cases = []
    component_includes = [f'#include "{app}_user.h"']
    component_init = []
    component_wakeup = []
    sources = [f"fsw/src/{app}{suffix}.c" for suffix in ("", "_cmds", "_dispatch", "_components", "_user")]
    dependencies = set()
    code_definitions = []
    telemetry_definitions = []

    for command in commands:
        name = command["name"]
        entity = entity_name(name)
        extra = {"NAME": name, "ENTITY": entity, "ENTITY_UPPER": name.upper()}
        stem = f"fsw/src/commands/{app}_{name}_cmd"
        emit("command.c.in", stem + ".c", False, extra)
        emit("command.h.in", stem + ".h", False, extra)
        sources.append(stem + ".c")
        command_includes.append(f'#include "commands/{app}_{name}_cmd.h"')
        code_definitions.append(f'#define {prefix}_{name.upper()}_CC {command["code"]}')
        command_cases.append(
            f"        case {prefix}_{name.upper()}_CC:\n"
            f"            if ({prefix}_VerifyCmdLength(&SBBufPtr->Msg, sizeof({prefix}_{entity}Cmd_t)))\n"
            "            {\n"
            f"                if ({prefix}_{entity}Cmd((const {prefix}_{entity}Cmd_t *)SBBufPtr) == CFE_SUCCESS)\n"
            "                {\n"
            f"                    {prefix}_Data.CommandCounter++;\n"
            "                }\n"
            "                else\n"
            "                {\n"
            f"                    {prefix}_Data.CommandErrorCounter++;\n"
            "                }\n"
            "            }\n"
            "            break;\n"
        )

    for sensor in sensors:
        name = sensor["name"]
        entity = entity_name(name)
        extra = {
            "NAME": name, "ENTITY": entity, "ENTITY_UPPER": name.upper(),
            "SENSOR_TLM_MID": f'0x{sensor["tlm_mid"]:04X}',
            "DEVICE": sensor["device"],
            "ADDRESS": f'0x{sensor["address"]:02X}',
            "DRIVER": sensor["driver"],
            "VALUE_TYPE": "int32", "VALUE_NOTE": "Latest successful sample.",
            "VALUE_INCLUDE": "", "DRIVER_STATE": "", "DRIVER_INIT": "",
            "DRIVER_INCLUDE": "", "READ_VALUE": "    (void)Value;\n    return CFE_STATUS_NOT_IMPLEMENTED;",
            "VALUE_EVENT": "",
        }
        stem = f"fsw/src/sensors/{app}_{name}_sensor"
        emit("sensor_cfg.h.in", stem + "_cfg.h", True, extra)
        if sensor["driver"] != "custom":
            adapter_path = ADAPTERS / sensor["driver"]
            adapter = json.loads((adapter_path / "adapter.json").read_text())
            dependencies.add(adapter["library"])
            tokens = {**adapter["tokens"], "READ_VALUE": (adapter_path / "read.c.in").read_text(),
                      "VALUE_EVENT": (adapter_path / "event.c.in").read_text()}
            for key, content in tokens.items():
                for token, value in {**values, **extra}.items():
                    content = content.replace(f"@{token}@", str(value))
                extra[key] = content
        emit("sensor.h.in", stem + ".h", False, extra)
        emit("sensor.c.in", stem + ".c", False, extra)
        sources.append(stem + ".c")
        component_includes.append(f'#include "sensors/{app}_{name}_sensor.h"')
        component_init.append(f"    {prefix}_{entity}_Init();")
        component_wakeup.append(f"    {prefix}_{entity}_Read();")

    component_wakeup.append(f"    {prefix}_UserWakeup();")
    for item in telemetry:
        name = item["name"]
        entity = entity_name(name)
        extra = {"NAME": name, "ENTITY": entity, "ENTITY_UPPER": name.upper()}
        stem = f"fsw/src/telemetry/{app}_{name}_tlm"
        emit("telemetry.c.in", stem + ".c", False, extra)
        emit("telemetry.h.in", stem + ".h", False, extra)
        sources.append(stem + ".c")
        component_includes.append(f'#include "telemetry/{app}_{name}_tlm.h"')
        component_init.append(f"    {prefix}_{entity}_Init();")
        component_wakeup.append(f"    {prefix}_{entity}_Send();")
        telemetry_definitions.append(f'#define {prefix}_{name.upper()}_TLM_MID 0x{item["mid"]:04X}')

    values.update({
        "COMMAND_INCLUDES": "\n".join(command_includes),
        "COMMAND_CASES": "\n".join(command_cases),
        "COMMAND_CODES": "\n".join(code_definitions),
        "TELEMETRY_IDS": "\n".join(telemetry_definitions),
        "COMPONENT_INCLUDES": "\n".join(component_includes),
        "COMPONENT_INIT": "\n".join(component_init),
        "COMPONENT_WAKEUP": "\n".join(component_wakeup),
        "SOURCES": "\n".join("    " + source for source in sources),
        "DEPENDENCIES": "\n".join(f"add_cfe_app_dependency({app} {dependency})" for dependency in sorted(dependencies)),
    })

    for suffix in ("", "_cmds", "_dispatch", "_components"):
        for extension in ("c", "h"):
            emit(f"app{suffix}.{extension}.in", f"fsw/src/{app}{suffix}.{extension}")
    for extension in ("c", "h"):
        emit(f"app_user.{extension}.in", f"fsw/src/{app}_user.{extension}", False)
    for suffix in ("msg", "msgdefs", "msgstruct", "mission_cfg", "platform_cfg", "msgids", "perfids", "fcncode_values"):
        emit(f"app_{suffix}.h.in", f"config/default_{app}_{suffix}.h")
    for suffix in ("eventids", "fcncodes", "version"):
        emit(f"app_{suffix}.h.in", f"fsw/inc/{app}_{suffix}.h")
    for filename in ("CMakeLists.txt", "mission_build.cmake", "arch_build.cmake"):
        emit(filename + ".in", filename)
    return result
