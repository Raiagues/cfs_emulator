#!/usr/bin/env python3
"""Manage the project registry using the existing cFS app generator."""

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
from string import Template

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project.model import (ProjectError, appgen, board_catalog, identifier, load_config,
                           mapped_manifests, protected_apps, read_manifests, safe_path,
                           validate_config)


def commit(root, files, check=False):
    """Validate and stage the complete plan before replacing any source file."""
    protected = board_catalog()["protected_paths"] + [f"cFS/apps/{name}" for name in protected_apps(root)]
    for relative in files:
        if any(relative == path or relative.startswith(path + "/") for path in protected):
            raise ProjectError(f"Protected project path: {relative}")
    paths = {relative: safe_path(root, relative) for relative in files}
    for path in paths.values():
        if path.exists() and not path.is_file():
            raise ProjectError(f"Expected a regular file: {path}")
    changed = [relative for relative, path in sorted(paths.items())
               if not path.exists() or path.read_text() != files[relative]]
    if check or not changed:
        return changed
    previous, staged, replaced, directories = {}, {}, [], []
    try:
        for relative in changed:
            path = paths[relative]
            previous[relative] = path.read_bytes() if path.exists() else None
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
            staged[relative].replace(paths[relative])
            replaced.append(relative)
    except BaseException:
        for relative in reversed(replaced):
            if previous[relative] is None:
                paths[relative].unlink()
            else:
                paths[relative].write_bytes(previous[relative])
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for directory in reversed(directories):
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
    return changed


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
    stem = f"cFS/apps/{app}/fsw/src/telemetry/{app}_{packet}_tlm"
    templates = Path(__file__).parent / "templates"
    return {stem + suffix: Template(safe_path(templates, f"sensor_telemetry{suffix}.in").read_text()).substitute(values)
            for suffix in (".h", ".c")}


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    commands = cli.add_subparsers(dest="action", required=True)
    for action in ("sync", "check", "devices", "list", "stamp", "check-build"):
        commands.add_parser(action)
    for action in ("add-app", "locate"):
        command = commands.add_parser(action)
        command.add_argument("app")
    command = commands.add_parser("add-device")
    command.add_argument("name")
    command.add_argument("--id", required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--bus", default="i2c-bus.1")
    command.add_argument("--address", type=lambda value: int(value, 0), required=True)
    command.add_argument("--value", action="append", default=[], metavar="PROPERTY=INTEGER")
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
    if args.action == "devices":
        return board_catalog(), 0
    config = copy.deepcopy(load_config(root))
    validate_config(root, config)
    generator = appgen(root)
    manifests = read_manifests(root, config)
    if args.action in ("stamp", "check-build"):
        signature = {"schema_version": 1, "board": config["board"], "os": config["os"],
                     "apps": config["apps"], "manifests": mapped_manifests(config, manifests)}
        relative = "cFS/build-rpi_linux/exe/cpu1/project.json"
        path = safe_path(root, relative)
        if args.action == "check-build":
            if not path.is_file() or json.loads(path.read_text()) != signature:
                raise ProjectError("cFS build configuration is missing or stale; run ./scripts/build-cfs.sh")
            return {"build": "current"}, 0
        payload = safe_path(root, "cFS/build-rpi_linux/exe/cpu1")
        if not safe_path(root, "cFS/build-rpi_linux/exe/cpu1/core-cpu1").is_file() or not (payload / "cf").is_dir():
            raise ProjectError("Build payload is missing; run ./scripts/build-cfs.sh before stamping")
        plan = {"cFS/" + path: content for path, content in generator.planned_files(root / "cFS", manifests).items()}
        if commit(root, plan, check=True):
            raise ProjectError("Generated cFS configuration is stale; run ./scripts/build-cfs.sh")
        return {"changed": commit(root, {relative: json.dumps(signature, indent=2) + "\n"})}, 0
    if args.action == "list":
        return {"project": config, "manifests": manifests}, 0
    if args.action == "locate":
        registry_app(config, args.app)
        return generator.locations(root / "cFS", generator.app_by_name(manifests, args.app)), 0
    new_apps, extra = [], {}
    if args.action == "add-app":
        identifier(args.app)
        if args.app in protected_apps(root):
            raise ProjectError(f"Protected app: {args.app}")
        if safe_path(root, f"cFS/apps/{args.app}").exists():
            raise ProjectError(f"App directory already exists: {args.app}")
        manifests.append(generator.new_app(args.app, manifests))
        config["apps"].append({"name": args.app, "sensors": {}, "telemetry_bindings": {}, "command_bindings": {}})
        new_apps.append(args.app)
    elif args.action == "add-device":
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
                                  "bus": args.bus, "address": args.address, "values": values})
    elif args.action.startswith("add-"):
        registry = registry_app(config, args.app)
        manifest = generator.app_by_name(manifests, args.app)
        kind = args.action.removeprefix("add-")
        collection = generator.KINDS[kind]
        identifier(args.name)
        if any(entity["name"] == args.name for entity in manifest[collection]):
            raise ProjectError(f"{kind} already exists: {args.name}")
        for relative in generator.entity_files(args.app, kind, args.name):
            if safe_path(root, "cFS/" + relative).exists():
                raise ProjectError(f"Conflicting entity file: {relative}")
        used = {mid for app in manifests for mid in generator.mids(app)}
        if kind == "sensor":
            device = next((device for device in config["devices"] if device["id"] == args.device), None)
            if device is None:
                raise ProjectError(f"Unknown device: {args.device}")
            catalog = board_catalog()
            driver = catalog["models"][device["model"]]["cfs_driver"]
            if driver is None:
                raise ProjectError(f"No cFS driver is implemented for {device['model']}; QEMU simulation is available")
            manifest[collection].append({"name": args.name, "driver": driver,
                "device": catalog["buses"][device["bus"]]["device"], "address": device["address"],
                "tlm_mid": generator.allocate(generator.TELEMETRY_IDS, used, "telemetry MID")})
            registry["sensors"][args.name] = args.device
        elif kind == "command":
            code = args.code if args.code is not None else generator.allocate(
                range(2, 128), {command["code"] for command in manifest[collection]}, "command code")
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
    mapped_manifests(config, manifests)
    plan = {"cFS/" + path: content for path, content in generator.planned_files(root / "cFS", manifests).items()}
    plan.update(extra)
    if args.action not in ("sync", "check"):
        plan["project/config.json"] = json.dumps(config, indent=2) + "\n"
    changed = commit(root, plan, check=args.action == "check")
    result = {"changed": changed, "check": args.action == "check"}
    if args.action == "add-command":
        result["implementation"] = "Command handler is a user-code stub; use locate to implement it"
    return result, 1 if args.action == "check" and changed else 0


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
