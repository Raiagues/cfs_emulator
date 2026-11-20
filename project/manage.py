#!/usr/bin/env python3
"""Manage the project registry with the app generator in project/appgen."""

import argparse
import copy
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from string import Template

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
from project.model import (ProjectError, appgen, board_catalog, identifier, load_config,
                           mapped_manifests, protected_apps, read_manifests, safe_path,
                           validate_config, required_libraries, planned_project_files)


def commit(root, files, check=False, library_names=(), mutable_libraries=(), validate=None):
    """Validate and stage the complete plan before replacing any source file."""
    # App generation owns its library dependencies, while the native script
    # owns application selection. Keep both in this same atomic transaction.
    fragment = "mission/sample_defs/generated/appgen_startup.scr"
    startup = "mission/cpu1_cfe_es_startup.scr"
    if fragment in files and (startup in files or safe_path(root, startup).is_file()):
        from project.appgen.native_startup import reconcile_generated_modules
        previous = safe_path(root, fragment)
        current = files[startup] if startup in files else safe_path(root, startup).read_text()
        updated = reconcile_generated_modules(current, previous.read_text() if previous.exists() else "", files[fragment])
        files = {**files, startup: updated}
    if startup in files:
        from project.cfs_config import module_limits_plan
        files = {**files, **module_limits_plan(root, files)}
    allowed_libraries = set()
    for name in library_names:
        identifier(name)
        relative = "mission/libs/" + name
        if safe_path(root, relative).exists():
            raise ProjectError(f"Library directory already exists: {name}")
        allowed_libraries.add(relative)
    for name in mutable_libraries:
        identifier(name)
        relative = "mission/libs/" + name
        directory = safe_path(root, relative)
        if (directory / ".git").exists():
            raise ProjectError(f"Cannot replace a library submodule: {name}")
        allowed_libraries.add(relative)
    from project.driver_catalog import load_catalog
    allowed_libraries.update("mission/libs/" + name for name in load_catalog(root))
    selected = load_config(root)
    from project.flight_sources import nasa_module_names
    reserved = protected_apps(root) | nasa_module_names(root, "libs")
    protected = board_catalog(selected["board"], root)["protected_paths"]
    for relative in files:
        parts = Path(relative).parts
        if parts[:1] == ("cFS",):
            raise ProjectError(f"NASA sources are read-only: {relative}")
        if len(parts) >= 3 and parts[:2] in (("mission", "apps"), ("mission", "libs")) and parts[2] in reserved:
            raise ProjectError(f"Reserved NASA module name: {parts[2]}")
        if any(relative.startswith(path + "/") for path in allowed_libraries):
            continue
        if any(relative == path or relative.startswith(path + "/") for path in protected):
            raise ProjectError(f"Protected project path: {relative}")
    paths = {relative: safe_path(root, relative) for relative in files}
    for path in paths.values():
        if path.exists() and not path.is_file():
            raise ProjectError(f"Expected a regular file: {path}")
    changed = [relative for relative, path in sorted(paths.items())
               if (path.exists() if files[relative] is None else
                   not path.exists() or path.read_text() != files[relative])]
    if check or not changed:
        if validate and not check:
            validate()
        return changed
    previous, modes, staged, replaced, directories = {}, {}, {}, [], []
    try:
        for relative in changed:
            path = paths[relative]
            previous[relative] = path.read_bytes() if path.exists() else None
            modes[relative] = path.stat().st_mode & 0o777 if path.exists() else 0o644
            if files[relative] is None:
                continue
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                directories.append(directory)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".project-", delete=False) as handle:
                temporary = Path(handle.name)
                staged[relative] = temporary
                handle.write(files[relative])
            temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o644)
        for relative in changed:
            if files[relative] is None:
                paths[relative].unlink()
            else:
                staged[relative].replace(paths[relative])
            replaced.append(relative)
        if validate:
            validate()
    except BaseException:
        for relative in reversed(replaced):
            if previous[relative] is None:
                paths[relative].unlink()
            else:
                paths[relative].write_bytes(previous[relative])
                paths[relative].chmod(modes[relative])
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for directory in reversed(directories):
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
    for relative in changed:
        if files[relative] is None:
            parent = paths[relative].parent
            while parent != Path(root) and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    return changed


def command_source_changes(root, plan, app):
    """Capture only lines introduced by this command in its owning app."""
    result = {}
    prefix = f"mission/apps/{app}/"
    for relative, content in plan.items():
        if not relative.startswith(prefix) or Path(relative).suffix not in {".c", ".h"} or content is None:
            continue
        path = safe_path(root, relative)
        previous = path.read_text() if path.exists() else ""
        if previous == content:
            continue
        delta = SequenceMatcher(None, previous.splitlines(), content.splitlines(), autojunk=False)
        ranges = [[start + 1, end] for kind, _, _, start, end in delta.get_opcodes() if start < end and kind != "equal"]
        if ranges:
            result[relative] = {"hash": hashlib.sha256(content.encode()).hexdigest(), "ranges": ranges}
    return result


def registry_app(config, name):
    identifier(name)
    for app in config["apps"]:
        if app["name"] == name:
            return app
    raise ProjectError(f"App is not registered for project editing: {name}")


def sensor_packet(app, packet, sensor, generator):
    """One-time scaffold; future sync preserves these appgen user files."""
    values = {"app": app, "packet": packet, "sensor": sensor, "prefix": app.upper(),
              "entity": generator.pascal(packet), "source": generator.pascal(sensor),
              "packet_upper": packet.upper(), "guard": f"{app.upper()}_{packet.upper()}_TLM_H"}
    stem = f"mission/apps/{app}/fsw/src/telemetry/{app}_{packet}_tlm"
    templates = Path(__file__).parent / "templates"
    return {stem + suffix: Template(safe_path(templates, f"sensor_telemetry{suffix}.in").read_text()).substitute(values)
            for suffix in (".h", ".c")}


def parser(public=False):
    cli = argparse.ArgumentParser(prog="./start --no-ui project" if public else None, description=__doc__)
    if public:
        cli.set_defaults(root=ROOT)
    else:
        cli.add_argument("--root", type=Path, default=ROOT)
    commands = cli.add_subparsers(dest="action", required=True)
    device = commands.add_parser("device", help="Read or update an existing device's bus, address and pins")
    device.add_argument("id")
    device.add_argument("--bus")
    device.add_argument("--address", type=lambda value: int(value, 0))
    device.add_argument("--pins", type=json.loads)
    for action in ("sync", "check", "devices", "list"):
        commands.add_parser(action)
    command = commands.add_parser("register-model", help="Register a sensor from its model.json")
    command.add_argument("definition", type=Path)
    command.add_argument("--driver", type=Path, help="C implementation of the model operations")
    command.add_argument("--state-header", type=Path, help="Header defining per-device state")
    for action in ("stamp", "check-build"):
        command = commands.add_parser(action)
        command.add_argument("--target", choices=("native", "qemu", "physical"))
    for action in ("add-app", "locate"):
        command = commands.add_parser(action)
        command.add_argument("app")
    for action in ("add-bus", "remove-bus"):
        commands.add_parser(action).add_argument("bus")
    command = commands.add_parser("link-hal", help="Generate a HAL reader in an existing or new mission app")
    command.add_argument("app")
    command.add_argument("name", help="Reader identifier")
    command.add_argument("--device", required=True)
    command.add_argument("--new-app", action="store_true", help="Create the app and its reader together")
    command.add_argument("--read-command", metavar="NAME", help="Also create a command to read and publish this sensor on demand")
    command = commands.add_parser("add-device")
    command.add_argument("name")
    command.add_argument("--id", required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--bus", help="Configured bus (optional when exactly one is selected)")
    command.add_argument("--address", type=lambda value: int(value, 0), required=True)
    command.add_argument("--value", action="append", default=[], metavar="PROPERTY=INTEGER")
    commands.add_parser("remove-device").add_argument("id")
    for kind in ("sensor", "command", "telemetry"):
        command = commands.add_parser(f"add-{kind}")
        command.add_argument("app")
        command.add_argument("name")
        if kind == "sensor":
            command.add_argument("--device", required=True)
        if kind == "command":
            command.add_argument("--code", type=lambda value: int(value, 0))
            command.add_argument("--actuator")
        if kind == "telemetry":
            command.add_argument("--sensor")
    for kind in ("sensor", "command", "telemetry"):
        command = commands.add_parser(f"remove-{kind}")
        command.add_argument("app")
        command.add_argument("name")
    command = commands.add_parser("bind-telemetry")
    command.add_argument("app")
    command.add_argument("name")
    command.add_argument("--sensor", required=True)
    command = commands.add_parser("bind-command")
    command.add_argument("app")
    command.add_argument("name")
    command.add_argument("--actuator", required=True)
    return cli


def run(args):
    root = args.root.resolve()
    if args.action == "device":
        from hardware.device_settings import device_settings, update_device
        from project.workspace import Workspace
        workspace = Workspace(root)
        current = device_settings(workspace, args.id)
        updates = {key: getattr(args, key) for key in ("address", "bus", "pins") if getattr(args, key) is not None}
        if not updates:
            return current, 0
        payload = {key: current["device"][key] for key in ("id", "address", "bus")}
        return update_device(workspace, {**payload, **updates, "expected_hash": current["source"]["hash"]}), 0
    if args.action in {"remove-sensor", "remove-command", "remove-telemetry"}:
        from project.workspace import Workspace
        return Workspace(root).mutate(args.action, {"app": args.app, "name": args.name}), 0
    if args.action == "register-model":
        from project.sensor_models import register
        return register(root, json.loads(args.definition.read_text()),
                        driver=args.driver.read_text() if args.driver else None,
                        state_header=args.state_header.read_text() if args.state_header else None), 0
    if args.action == "devices":
        return board_catalog(load_config(root)["board"], root), 0
    from project.flight_sources import prepare_mission
    prepare_mission(root)
    config = copy.deepcopy(load_config(root))
    validate_config(root, config)
    generator = appgen(root)
    manifests = read_manifests(root, config)
    from project.cfs_config import configured
    if args.action in ("sync", "check") and not configured(root, config):
        return {"changed": [], "deleted": [], "check": args.action == "check"}, 0
    if args.action in ("stamp", "check-build"):
        from hardware.targets import selected_target
        target = getattr(args, 'target', None) or selected_target(root, required=True)
        if target != 'native' and config['board'] is None:
            raise ProjectError('Build target must match the selected native or board profile')
        kind = 'native' if target == 'native' else 'flight'
        signature = {"schema_version": 1, "target": kind, "board": config["board"], "os": config["os"],
                     "apps": config["apps"], "libraries": required_libraries(config, root),
                     "manifests": mapped_manifests(config, manifests, root)}
        relative = f"project/generated/build-{kind}.json"
        path = safe_path(root, relative)
        if args.action == "check-build":
            if not path.is_file() or json.loads(path.read_text()) != signature:
                raise ProjectError("cFS build configuration is missing or stale; run ./scripts/build-cfs.sh")
            return {"build": "current"}, 0
        payload = safe_path(root, f"mission/build-{kind}/exe/cpu1")
        if not (payload / "core-cpu1").is_file() or not (payload / "cf").is_dir():
            raise ProjectError("Build payload is missing; run ./scripts/build-cfs.sh before stamping")
        plan = planned_project_files(root, config, manifests) if configured(root, config) else {}
        if commit(root, plan, check=True):
            raise ProjectError("Generated cFS configuration is stale; run ./scripts/build-cfs.sh")
        return {"changed": commit(root, {relative: json.dumps(signature, indent=2) + "\n"})}, 0
    if args.action == "list":
        return {"project": config, "manifests": manifests}, 0
    if args.action == "locate":
        registry_app(config, args.app)
        return generator.locations(root / "mission", generator.app_by_name(manifests, args.app)), 0
    new_apps, extra = [], {}
    if args.action in ("add-bus", "remove-bus"):
        if args.bus not in board_catalog(config["board"], root)["buses"]:
            raise ProjectError("Select a supported bus on this board")
        if args.action == "add-bus":
            if args.bus in config["buses"]:
                raise ProjectError("This bus is already configured")
            config["buses"].append(args.bus)
        else:
            if args.bus not in config["buses"]:
                raise ProjectError("This bus is not configured")
            if any(device["bus"] == args.bus for device in config["devices"]):
                raise ProjectError("Disconnect the devices on this bus before removing it")
            config["buses"].remove(args.bus)
        changed = commit(root, {"project/config.json": json.dumps(config, indent=2) + "\n"})
        return {"changed": changed, "deleted": []}, 0
    if args.action == "add-app" or (args.action == "link-hal" and args.new_app):
        identifier(args.app)
        if args.app in protected_apps(root):
            raise ProjectError(f"Protected app: {args.app}")
        if safe_path(root, f"mission/apps/{args.app}").exists():
            raise ProjectError(f"App directory already exists: {args.app}")
        manifests.append(generator.new_app(args.app, manifests))
        config["apps"].append({"name": args.app, "sensors": {}, "telemetry_bindings": {}, "command_bindings": {}})
        new_apps.append(args.app)
    if args.action == "remove-device":
        if not any(device["id"] == args.id for device in config["devices"]):
            raise ProjectError("Device not found")
        if any(args.id in app["sensors"].values() for app in config["apps"]):
            raise ProjectError("Remove the sensor readers from the apps first")
        config["devices"] = [device for device in config["devices"] if device["id"] != args.id]
    elif args.action == "add-device":
        bus = args.bus
        if bus is None:
            if len(config["buses"]) != 1:
                raise ProjectError("Select a configured bus using --bus")
            bus = config["buses"][0]
        values = {}
        for specification in args.value:
            key, separator, value = specification.partition("=")
            if not separator or key in values:
                raise ProjectError("--value requires unique PROPERTY=INTEGER entries")
            try:
                values[key] = int(value, 0)
            except ValueError as exc:
                raise ProjectError("--value requires PROPERTY=INTEGER") from exc
        config["devices"].append({"name": args.name, "id": args.id, "model": args.model,
                                  "bus": bus, "address": args.address, "values": values})
    elif args.action in ("add-command", "add-sensor", "add-telemetry", "link-hal"):
        registry = registry_app(config, args.app)
        manifest = generator.app_by_name(manifests, args.app)
        kind = "sensor" if args.action == "link-hal" else args.action.removeprefix("add-")
        collection = generator.KINDS[kind]
        identifier(args.name)
        if any(entity["name"] == args.name for entity in manifest[collection]):
            raise ProjectError(f"{kind} already exists: {args.name}")
        for relative in generator.entity_files(args.app, kind, args.name):
            if safe_path(root, "mission/" + relative).exists():
                raise ProjectError(f"Conflicting entity file: {relative}")
        used = {mid for app in manifests for mid in generator.mids(app)}
        if kind == "sensor":
            device = next((device for device in config["devices"] if device["id"] == args.device), None)
            if device is None:
                raise ProjectError(f"Unknown device: {args.device}")
            if args.action == "link-hal" and args.device in registry["sensors"].values():
                raise ProjectError("This app already has a HAL reader for this sensor")
            catalog = board_catalog(config["board"], root)
            driver = catalog["models"][device["model"]]["cfs_driver"]
            if driver is None:
                raise ProjectError(f"No cFS driver is implemented for {device['model']}; QEMU simulation is available")
            manifest[collection].append({"name": args.name, "driver": driver,
                "device": catalog["buses"][device["bus"]]["device"], "address": device["address"],
                "tlm_mid": generator.allocate(generator.TELEMETRY_IDS, used, "telemetry MID")})
            registry["sensors"][args.name] = args.device
            if args.action == "link-hal" and args.read_command:
                command_name = identifier(args.read_command)
                for relative in generator.entity_files(args.app, "command", command_name):
                    if safe_path(root, "mission/" + relative).exists():
                        raise ProjectError(f"Conflicting command file: {relative}")
                used_codes = {command["code"] for command in manifest["commands"]}
                first_code = 4 if manifest["schema_version"] == 2 else 2
                manifest["commands"].append({"name": command_name, "reader": args.name,
                    "code": generator.allocate(range(first_code, 128), used_codes, "command code")})
        elif kind == "command":
            code = args.code if args.code is not None else generator.allocate(
                range(4 if manifest["schema_version"] == 2 else 2, 128), {command["code"] for command in manifest[collection]}, "command code")
            manifest[collection].append({"name": args.name, "code": code})
            if args.actuator:
                registry["command_bindings"][args.name] = args.actuator
        else:
            manifest[collection].append({"name": args.name,
                "mid": generator.allocate(generator.TELEMETRY_IDS, used, "telemetry MID")})
            if args.sensor:
                registry["telemetry_bindings"][args.name] = args.sensor
                extra = sensor_packet(args.app, args.name, args.sensor, generator)
    elif args.action == "bind-telemetry":
        registry_app(config, args.app)
        raise ProjectError(f"Existing telemetry files are user-owned. Run ./scripts/project.sh locate {args.app}; "
                           "implement the payload/fill there, or create a new packet using add-telemetry --sensor")
    elif args.action == "bind-command":
        registry = registry_app(config, args.app)
        registry["command_bindings"][args.name] = args.actuator
    validate_config(root, config, manifests, new_apps)
    if args.action in ("add-device", "remove-device"):
        changed = commit(root, {"project/config.json": json.dumps(config, indent=2) + "\n"})
        return {"changed": changed, "deleted": []}, 0
    mapped_manifests(config, manifests, root)
    plan = planned_project_files(root, config, manifests)
    plan.update(extra)
    if new_apps:
        from project.appgen.native_startup import parse_startup, render_startup
        from project.cfs_config import STARTUP, native_startup
        current = plan[STARTUP] if STARTUP in plan else native_startup(root, config)
        active, archived = parse_startup(current)
        recipes, _ = parse_startup(plan['mission/sample_defs/generated/appgen_startup.scr'])
        active.append(next(entry for entry in recipes if entry.name == args.app))
        plan[STARTUP] = render_startup(active, [entry for entry in archived if entry.name != args.app])
    if args.action not in ("sync", "check"):
        plan["project/config.json"] = json.dumps(config, indent=2) + "\n"
    changes = command_source_changes(root, plan, args.app) if args.action == "add-command" else None
    if new_apps:
        from hardware.targets import selected_target
        from journey.mission import created
        target = selected_target(root)
    changed = commit(root, plan, check=args.action == "check")
    for name in new_apps:
        created(root, target, name)
    result = {"changed": changed, "deleted": [path for path, content in plan.items() if content is None],
              "check": args.action == "check"}
    if args.action == "add-command":
        result["source_changes"] = changes
        result["implementation"] = "Command handler is a user-code stub; use locate to implement it"
    return result, 1 if args.action == "check" and changed else 0


def main(argv=None, *, public=False):
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = not public or "--json" in argv
    if public and "--json" in argv:
        argv.remove("--json")
    args = parser(public).parse_args(argv)
    try:
        result, status = run(args)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if machine:
        print(json.dumps(result))
    elif args.action == "list":
        print("\n".join(app["name"] for app in result["project"]["apps"]) or "No project apps")
    elif args.action == "devices":
        print("\n".join(sorted(result["models"])))
    elif args.action == "device":
        device = result["device"]
        print(f'{device["id"]} · {device["bus"]} · {device["address"]:#04x}')
    elif "changed" in result:
        print("\n".join(result["changed"]) or "Up to date")
    else:
        for key, value in result.items():
            print(f"{key} · {value}")
    return status


if __name__ == "__main__":
    sys.exit(main())
