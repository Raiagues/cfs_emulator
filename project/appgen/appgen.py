#!/usr/bin/env python3
"""Create cFS apps and register their commands, telemetry and sensors."""

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path


class AppgenError(ValueError):
    """An invalid model or unsafe filesystem operation."""


NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
COMMAND_IDS = range(0x1A00, 0x1B00)
TELEMETRY_IDS = range(0x0A00, 0x0B00)
PERFORMANCE_IDS = range(100, 128)
APP_KEYS = {
    "schema_version", "name", "cmd_mid", "hk_request_mid", "wakeup_mid",
    "hk_tlm_mid", "period_ticks", "hk_period_ticks", "priority", "stack_size",
    "perf_id", "sensors", "commands", "telemetry",
}
ENTITY_KEYS = {
    "sensors": {"name", "driver", "device", "address", "tlm_mid"},
    "commands": {"name", "code"},
    "telemetry": {"name", "mid"},
}
KINDS = {"sensor": "sensors", "command": "commands", "telemetry": "telemetry"}
ROOT_DEFAULT = Path(__file__).resolve().parents[2] / "cFS"
TEMPLATE_DIR = Path(__file__).resolve().parent


def valid_name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value) or len(value) > 19:
        raise AppgenError("Names must be snake_case identifiers of at most 19 characters")
    return value


def pascal(value):
    return "".join(part.capitalize() for part in value.split("_"))


def sensor_adapter(driver):
    valid_name(driver)
    if driver == "custom":
        return {"device_pattern": r"/dev/[A-Za-z0-9/_-]+", "max_address": 65535}
    path = ROOT_DEFAULT.parent / "project/adapters" / driver / "adapter.json"
    if not path.is_file():
        raise AppgenError(f"No sensor adapter configured for driver: {driver}")
    return json.loads(path.read_text())


def integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise AppgenError(f"{label} must be an integer from {minimum} to {maximum}")


def keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise AppgenError(f"{label} fields must be: {', '.join(sorted(expected))}")


def validate_manifest(manifest):
    keys(manifest, APP_KEYS, "application configuration")
    valid_name(manifest["name"])
    integer(manifest["schema_version"], "schema_version", 1, 1)
    for field in ("cmd_mid", "hk_request_mid", "wakeup_mid"):
        integer(manifest[field], field, COMMAND_IDS.start, COMMAND_IDS.stop - 1)
    integer(manifest["hk_tlm_mid"], "hk_tlm_mid", TELEMETRY_IDS.start, TELEMETRY_IDS.stop - 1)
    integer(manifest["period_ticks"], "period_ticks", 1, 65535)
    integer(manifest["hk_period_ticks"], "hk_period_ticks", 1, 65535)
    integer(manifest["priority"], "priority", 1, 255)
    integer(manifest["stack_size"], "stack_size", 16384, 1048576)
    integer(manifest["perf_id"], "perf_id", PERFORMANCE_IDS.start, PERFORMANCE_IDS.stop - 1)
    symbols = set()
    for collection, expected in ENTITY_KEYS.items():
        if not isinstance(manifest[collection], list):
            raise AppgenError(f"{collection} must be a list")
        for entity in manifest[collection]:
            keys(entity, expected, collection)
            valid_name(entity["name"])
            symbol = pascal(entity["name"])
            if symbol in {"Hk", "HkTlm", "Noop", "ResetCounters", "SendHk", "Wakeup"}:
                raise AppgenError(f"Entity name is reserved by the standard app interface: {entity['name']}")
            if symbol in symbols:
                raise AppgenError(f"Duplicate entity name/symbol across commands, sensors or telemetry: {entity['name']}")
            symbols.add(symbol)
            if collection == "sensors":
                adapter = sensor_adapter(entity["driver"])
                if not isinstance(entity["device"], str) or not re.fullmatch(adapter["device_pattern"], entity["device"]):
                    raise AppgenError(f"Invalid device path for driver {entity['driver']}")
                integer(entity["address"], "sensor address", 0, adapter["max_address"])
                integer(entity["tlm_mid"], "sensor tlm_mid", TELEMETRY_IDS.start, TELEMETRY_IDS.stop - 1)
            elif collection == "commands":
                integer(entity["code"], "command code", 2, 127)
            else:
                integer(entity["mid"], "telemetry mid", TELEMETRY_IDS.start, TELEMETRY_IDS.stop - 1)
    codes = [command["code"] for command in manifest["commands"]]
    if len(codes) != len(set(codes)):
        raise AppgenError("Command codes must be unique within an app")


def mids(manifest):
    result = [manifest[k] for k in ("cmd_mid", "hk_request_mid", "wakeup_mid", "hk_tlm_mid")]
    result.extend(sensor["tlm_mid"] for sensor in manifest["sensors"])
    result.extend(packet["mid"] for packet in manifest["telemetry"])
    return result


def validate_all(manifests):
    names, ids, perf_ids = set(), set(), set()
    for manifest in manifests:
        validate_manifest(manifest)
        if manifest["name"] in names:
            raise AppgenError(f"Duplicate app: {manifest['name']}")
        names.add(manifest["name"])
        for mid in mids(manifest):
            if mid in ids:
                raise AppgenError(f"Duplicate message ID: 0x{mid:04X}")
            ids.add(mid)
        if manifest["perf_id"] in perf_ids:
            raise AppgenError(f"Duplicate performance ID: {manifest['perf_id']}")
        perf_ids.add(manifest["perf_id"])


def safe_path(root, relative):
    """Reject symlinks as well as traversal before touching managed files."""
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise AppgenError(f"Unsafe path: {relative}")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise AppgenError(f"Refusing symlink: {path}")
    return path


def read_manifests(root):
    result = []
    apps = safe_path(root.parent, "project/apps")
    for path in sorted(apps.glob("*.json")):
        path = safe_path(root.parent, path.relative_to(root.parent))
        try:
            manifest = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise AppgenError(f"Cannot read {path}: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("name") != path.stem:
            raise AppgenError(f"Application name must match its configuration filename: {path}")
        result.append(manifest)
    validate_all(result)
    return result


def renderer():
    # Keep the templates independent from CLI and filesystem operations.
    spec = importlib.util.spec_from_file_location("appgen_render", TEMPLATE_DIR / "render.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render_app


def render_mission(manifests, libraries=None):
    """Small generated fragments included by the mission files."""
    apps = sorted(manifests, key=lambda app: app["name"])
    if libraries is None:
        libraries = []
    cmake = "# Generated application build selection.\n"
    cmake += f"set(APPGEN_APPS {' '.join(app['name'] for app in apps)})\n"
    cmake += f"set(APPGEN_LIBS {' '.join(item['name'] for item in libraries)})\n"
    startup = [f"CFE_LIB, {item['name']}, {item['entry_point']}, {item['name'].upper()}, 0, 0, 0x0, 0;\n"
               for item in libraries]
    includes = ["/* Generated by appgen; edit the app manifests. */\n"]
    schedule, telemetry = [], []
    for app in apps:
        name, prefix = app["name"], app["name"].upper()
        startup.append(f"CFE_APP, {name}, {prefix}_Main, {prefix}, {app['priority']}, {app['stack_size']}, 0x0, 0;\n")
        includes.append(f'#include "{name}_msgids.h"\n')
        schedule.append(f"{{CFE_SB_MSGID_WRAP_VALUE({prefix}_WAKEUP_MID), {app['period_ticks']}, 0}},\n")
        schedule.append(f"{{CFE_SB_MSGID_WRAP_VALUE({prefix}_SEND_HK_MID), {app['hk_period_ticks']}, 0}},\n")
        telemetry.append(f"{{CFE_SB_MSGID_WRAP_VALUE({prefix}_HK_TLM_MID), {{0, 0}}, 1}},\n")
        for sensor in app["sensors"]:
            telemetry.append(f"{{CFE_SB_MSGID_WRAP_VALUE(0x{sensor['tlm_mid']:04X}), {{0, 0}}, 1}},\n")
        for packet in app["telemetry"]:
            telemetry.append(f"{{CFE_SB_MSGID_WRAP_VALUE(0x{packet['mid']:04X}), {{0, 0}}, 1}},\n")
    return {
        "sample_defs/generated/appgen.cmake": cmake,
        "sample_defs/generated/appgen_startup.scr": "".join(startup),
        "sample_defs/generated/appgen_includes.h": "".join(includes),
        "sample_defs/generated/appgen_schedule.inc": "".join(schedule),
        "sample_defs/generated/appgen_telemetry.inc": "".join(telemetry),
    }


def merged_app_cmake(root, manifest, generated=None):
    """Replace generated source/dependency blocks while preserving native edits."""
    generated = generated if generated is not None else renderer()(manifest)["CMakeLists.txt"][0]
    path = safe_path(root, f"apps/{manifest['name']}/CMakeLists.txt")
    if not path.exists():
        return generated
    current = path.read_text()

    def block(text, section):
        pattern = r"(?m)^# APPGEN BEGIN " + section + r"\n[\s\S]*?^# APPGEN END " + section + r"\n"
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1 or text.count("# APPGEN BEGIN " + section) != 1 or text.count("# APPGEN END " + section) != 1:
            raise AppgenError(f"Expected one APPGEN {section} block in {path}")
        return matches[0]

    if "# APPGEN BEGIN" not in current and "# APPGEN END" not in current:
        previous_path = safe_path(root.parent, f"project/apps/{manifest['name']}.json")
        if not previous_path.is_file():
            previous_path = safe_path(root, f"apps/{manifest['name']}/app.json")
        if not previous_path.is_file():
            raise AppgenError(f"Cannot identify generated CMake entries without previous app settings: {path}")
        previous = renderer()(json.loads(previous_path.read_text()))["CMakeLists.txt"][0]
        source_sets = list(re.finditer(r"\bset\s*\(\s*APP_SRC_FILES\b([^)]*)\)", current))
        if len(source_sets) != 1:
            raise AppgenError(f"Expected one native APP_SRC_FILES list in {path}")
        old_sources = block(previous, "SOURCES").group().splitlines()[1:-1]
        original = source_sets[0].group(1)
        lines = original.splitlines(keepends=True)
        expected = {line.strip() for line in old_sources if line.strip()}
        if any(sum(line.strip() == source for line in lines) != 1 for source in expected):
            raise AppgenError(f"Generated source entries were edited ambiguously in {path}; restore them before sync")
        replacement, inserted = [], False
        for line in lines:
            if line.strip() in expected:
                if not inserted:
                    replacement.append(block(generated, "SOURCES").group())
                    inserted = True
            else:
                replacement.append(line)
        start, end = source_sets[0].span(1)
        current = current[:start] + "".join(replacement) + current[end:]
        old_dependencies = [line for line in block(previous, "DEPENDENCIES").group().splitlines()[1:-1] if line]
        lines = current.splitlines(keepends=True)
        if any(sum(line.rstrip("\r\n") == dependency for line in lines) != 1 for dependency in old_dependencies):
            raise AppgenError(f"Generated library dependencies were edited ambiguously in {path}; restore them before sync")
        replacement, inserted = [], False
        for line in lines:
            if line.rstrip("\r\n") in old_dependencies:
                if not inserted:
                    replacement.append(block(generated, "DEPENDENCIES").group())
                    inserted = True
            else:
                replacement.append(line)
        if not inserted:
            replacement.append(("" if current.endswith("\n") else "\n") + block(generated, "DEPENDENCIES").group())
        current = "".join(replacement)
    for section in ("SOURCES", "DEPENDENCIES"):
        match = block(current, section)
        current = current[:match.start()] + block(generated, section).group() + current[match.end():]
    return current


def planned_files(root, manifests, libraries=None, excluded=()):
    capacity_spec = importlib.util.spec_from_file_location("appgen_mission_capacity", TEMPLATE_DIR / "mission_capacity.py")
    capacity = importlib.util.module_from_spec(capacity_spec)
    capacity_spec.loader.exec_module(capacity)
    included = [app for app in manifests if app['name'] not in excluded]
    capacity.validate_mission_capacity(root, included)
    render_app = renderer()
    if libraries is None and safe_path(root.parent, "project/config.json").is_file():
        # Project mutations pass their in-memory selection explicitly. Ordinary
        # appgen sync can discover the same catalog without a second registry.
        project_model = root.parent / "project/model.py"
        if project_model.is_file():
            spec = importlib.util.spec_from_file_location("appgen_project_model", project_model)
            model = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(model)
            libraries = model.required_libraries(model.load_config(root.parent), root.parent, manifests, excluded)
    files = render_mission(included, libraries)
    for manifest in manifests:
        name = manifest["name"]
        for sensor in manifest["sensors"]:
            source = safe_path(root, entity_files(name, "sensor", sensor["name"])[0])
            if source.exists():
                marker = re.search(r"APPGEN: DRIVER ([a-z0-9_]+)", source.read_text())
                if marker and marker.group(1) != sensor["driver"]:
                    raise AppgenError(f"Sensor driver is immutable: {name}/{sensor['name']}; remove/add the sensor")
        for relative, (content, managed) in render_app(manifest).items():
            target = f"apps/{name}/{relative}"
            path = safe_path(root, target)
            if relative == "CMakeLists.txt":
                content = merged_app_cmake(root, manifest, content)
            if managed or not path.exists():
                files[target] = content
    for relative in files:
        path = safe_path(root, relative)
        if path.exists() and not path.is_file():
            raise AppgenError(f"Expected a file: {path}")
    return files


def plan_library(root, name):
    """Plan a sample_lib-style library in memory; the caller writes files and mission entries."""
    valid_name(name)
    directory = safe_path(root, "libs/" + name)
    if directory.exists():
        raise AppgenError(f"Library directory already exists: {name}")
    prefix = name.upper()
    replacements = {"NAME": name, "PREFIX": prefix}
    files = {}
    for template, destination in (
            ("library_cmake.in", "CMakeLists.txt"),
            ("library.h.in", f"fsw/public_inc/{name}.h"),
            ("library.c.in", f"fsw/src/{name}.c"),
            ("library_internal.h.in", f"fsw/src/{name}_internal.h"),
            ("library_version.h.in", f"fsw/src/{name}_version.h"),
            ("library_readme.md.in", "README.md")):
        content = safe_path(TEMPLATE_DIR / "templates", template).read_text()
        for key, value in replacements.items():
            content = content.replace("@" + key + "@", value)
        files["libs/" + name + "/" + destination] = content
    entry = prefix + "_Init"
    return {"files": files, "startup": {"module": name, "entry_point": entry,
            "fields": ["CFE_LIB", name, entry, prefix, "0", "0", "0x0", "0"]},
            "include": name + ".h"}


def write_files(root, files, check=False):
    changed = []
    for relative, content in sorted(files.items()):
        path = safe_path(root, relative)
        if not path.exists() or path.read_text() != content:
            changed.append(relative)
    if not check:
        staged = []
        try:
            # Stage all content before replacing any existing source.
            for relative in changed:
                path = safe_path(root, relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = safe_path(root, relative + ".appgen-tmp")
                temporary.write_text(files[relative])
                staged.append((temporary, path))
            for temporary, path in staged:
                temporary.replace(path)
        finally:
            for temporary, _ in staged:
                if temporary.exists():
                    temporary.unlink()
    return changed


def sync(root, manifests, check=False):
    validate_all(manifests)
    if (root.parent / 'project/config.json').is_file():
        sys.path.insert(0, str(root.parent))
        from project.model import load_config, planned_project_files
        from project.manage import commit
        return commit(root.parent, planned_project_files(root.parent, load_config(root.parent), manifests), check=check)
    files = {root.name + '/' + path: content for path, content in planned_files(root, manifests).items()}
    files.update({f"project/apps/{app['name']}.json": json.dumps(app, indent=2) + "\n" for app in manifests})
    return write_files(root.parent, files, check)


def app_by_name(manifests, name):
    valid_name(name)
    for app in manifests:
        if app["name"] == name:
            return app
    raise AppgenError(f"Managed app not found: {name}")


def allocate(pool, used, label):
    for value in pool:
        if value not in used:
            return value
    raise AppgenError(f"No free {label} in the appgen reserved range")


def new_app(name, manifests):
    valid_name(name)
    used = {mid for app in manifests for mid in mids(app)}
    command_ids = []
    for _ in range(3):
        mid = allocate(COMMAND_IDS, used, "command MID")
        command_ids.append(mid)
        used.add(mid)
    return {
        "schema_version": 1, "name": name,
        "cmd_mid": command_ids[0], "hk_request_mid": command_ids[1], "wakeup_mid": command_ids[2],
        "hk_tlm_mid": allocate(TELEMETRY_IDS, used, "telemetry MID"),
        "period_ticks": 20, "hk_period_ticks": 40, "priority": 55, "stack_size": 32768,
        "perf_id": allocate(PERFORMANCE_IDS, {app["perf_id"] for app in manifests}, "performance ID"),
        "sensors": [], "commands": [], "telemetry": [],
    }


def entity_files(app, kind, name):
    suffix = {"sensor": "sensor", "command": "cmd", "telemetry": "tlm"}[kind]
    directory = {"sensor": "sensors", "command": "commands", "telemetry": "telemetry"}[kind]
    stem = f"apps/{app}/fsw/src/{directory}/{app}_{name}_{suffix}"
    result = [stem + ".c", stem + ".h"]
    if kind == "sensor":
        result.append(stem + "_cfg.h")
    return result


def remove_files(root, relatives):
    paths = [safe_path(root, relative) for relative in relatives]
    for path in paths:
        if path.exists() and not path.is_file():
            raise AppgenError(f"Expected a file: {path}")
    for path in paths:
        if path.exists():
            path.unlink()


def locations(root, manifest):
    """Resolve semantic markers and standard handlers against the current text."""
    result, identifiers = [], set()
    prefix = manifest["name"].upper()
    standards = {
        "Main": "app.main", "Init": "app.standard_init", "TaskPipe": "app.dispatch",
        "NoopCmd": "command.noop", "ResetCountersCmd": "command.reset_counters",
        "SendHkCmd": "telemetry.hk",
    }
    app_dir = safe_path(root, f"apps/{manifest['name']}")
    for path in sorted(app_dir.rglob("*")):
        if path.suffix not in (".c", ".h") or not path.is_file():
            continue
        path = safe_path(root, path.relative_to(root))
        for number, line in enumerate(path.read_text().splitlines(), 1):
            marker = re.search(r"APPGEN: USER ([a-zA-Z0-9_.]+)", line)
            function = re.match(r"(?:void|CFE_Status_t|bool)\s+" + re.escape(prefix) + r"_(\w+)\(", line)
            if marker:
                identifier, location = marker.group(1), number + 1
                symbol = None
            elif path.suffix == ".c" and function and function.group(1) in standards:
                identifier, location = standards[function.group(1)], number
                symbol = prefix + "_" + function.group(1)
            else:
                continue
            if identifier in identifiers:
                raise AppgenError(f"Duplicate editable location marker: {identifier}")
            identifiers.add(identifier)
            entry = {"id": identifier, "path": str(path.relative_to(root)), "line": location,
                     "editable": marker is not None}
            if symbol:
                entry["symbol"] = symbol
            result.append(entry)
    return {"app": manifest["name"], "configuration": f"project/apps/{manifest['name']}.json", "locations": result}


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT_DEFAULT, help="cFS source root")
    commands = cli.add_subparsers(dest="action", required=True)
    for action in ("create-app", "delete-app", "locate"):
        command = commands.add_parser(action)
        command.add_argument("app")
    command = commands.add_parser("sync")
    command.add_argument("--check", action="store_true", help="report pending generated changes, without writing")
    commands.add_parser("list")
    for kind in KINDS:
        for operation in ("add", "remove"):
            command = commands.add_parser(f"{operation}-{kind}")
            command.add_argument("app")
            command.add_argument("name")
            if operation == "add" and kind == "sensor":
                command.add_argument("--driver", required=True, help="Configured sensor adapter or custom")
                command.add_argument("--device", required=True)
                command.add_argument("--address", type=lambda value: int(value, 0), required=True)
            if operation == "add" and kind == "command":
                command.add_argument("--code", type=lambda value: int(value, 0))
    return cli


def run(args):
    root = args.root.resolve()
    manifests = read_manifests(root)
    if args.action == "list":
        return {"apps": manifests}, 0
    if args.action == "locate":
        return locations(root, app_by_name(manifests, args.app)), 0
    if args.action == "sync":
        changed = sync(root, manifests, args.check)
        return {"changed": changed, "check": args.check}, 1 if args.check and changed else 0
    if args.action == "create-app":
        valid_name(args.app)
        target = safe_path(root, f"apps/{args.app}")
        if target.exists():
            raise AppgenError(f"App directory already exists: {target}")
        manifests.append(new_app(args.app, manifests))
        return {"changed": sync(root, manifests)}, 0
    app = app_by_name(manifests, args.app)
    if args.action == "delete-app":
        target = safe_path(root, f"apps/{args.app}")
        # Never delete a linked subtree, even when the manifest itself is regular.
        for path in target.rglob("*"):
            safe_path(root, path.relative_to(root))
        manifests.remove(app)
        changed = sync(root, manifests)
        shutil.rmtree(target)
        safe_path(root.parent, f"project/apps/{args.app}.json").unlink()
        return {"changed": changed, "deleted": [f"apps/{args.app}"]}, 0
    operation, kind = args.action.split("-", 1)
    valid_name(args.name)
    collection = KINDS[kind]
    existing = next((entity for entity in app[collection] if entity["name"] == args.name), None)
    if operation == "add":
        if existing:
            raise AppgenError(f"{kind} already exists: {args.name}")
        for relative in entity_files(args.app, kind, args.name):
            if safe_path(root, relative).exists():
                raise AppgenError(f"Conflicting entity file already exists: {relative}")
        used = {mid for item in manifests for mid in mids(item)}
        if kind == "sensor":
            entity = {"name": args.name, "driver": args.driver, "device": args.device, "address": args.address,
                      "tlm_mid": allocate(TELEMETRY_IDS, used, "telemetry MID")}
        elif kind == "command":
            code = args.code
            if code is None:
                code = allocate(range(2, 128), {item["code"] for item in app[collection]}, "command code")
            entity = {"name": args.name, "code": code}
        else:
            entity = {"name": args.name, "mid": allocate(TELEMETRY_IDS, used, "telemetry MID")}
        app[collection].append(entity)
        return {"changed": sync(root, manifests)}, 0
    if existing is None:
        raise AppgenError(f"{kind} not found: {args.name}")
    app[collection].remove(existing)
    removed = entity_files(args.app, kind, args.name)
    # Validate all paths before rewriting registry files.
    for relative in removed:
        path = safe_path(root, relative)
        if path.exists() and not path.is_file():
            raise AppgenError(f"Expected a file: {path}")
    changed = sync(root, manifests)
    remove_files(root, removed)
    return {"changed": changed, "deleted": removed}, 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result, status = run(args)
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
