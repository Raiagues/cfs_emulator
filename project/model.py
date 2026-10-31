"""Project hardware and custom-app registry; cFS manifests own message IDs."""

import configparser
import importlib.util
import json
from pathlib import Path
import re
import sys


class ProjectError(ValueError):
    pass


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectError(f"Unsafe path: {relative}")
    path = Path(root)
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ProjectError(f"Refusing symlink: {path}")
    return path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", value) or len(value) > 19:
        raise ProjectError("Identifiers must use snake_case with at most 19 characters")
    return value


def fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ProjectError(f"{label} fields must be: {', '.join(sorted(expected))}")


def board_catalog():
    return json.loads(safe_path(Path(__file__).parent, "boards/raspi4b.json").read_text())


def validate_values(device, values):
    """Check static and simulated values against the same QEMU property limits."""
    properties = board_catalog()["models"][device["model"]]["properties"]
    if not isinstance(values, dict):
        raise ProjectError(f"Values for {device['id']} must be an object")
    for key, value in values.items():
        limits = properties.get(key)
        if limits is None or type(value) is not int or not limits["min"] <= value <= limits["max"]:
            raise ProjectError(f"Unsupported value for {device['id']}.{key}; run ./scripts/project.sh devices")


def validate_hardware(config):
    """Validate configuration without needing a cFS checkout (guest runtime)."""
    fields(config, {"schema_version", "board", "os", "devices", "apps"}, "project config")
    catalog = board_catalog()
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ProjectError("Unsupported project schema_version; expected 1")
    if config["board"] != catalog["board"] or config["os"] not in catalog["os"]:
        raise ProjectError("Supported board/OS: raspi4b/raspios; run ./scripts/project.sh devices")
    if not isinstance(config["devices"], list) or not isinstance(config["apps"], list):
        raise ProjectError("devices and apps must be lists")
    ids, addresses = set(), set()
    for device in config["devices"]:
        fields(device, {"name", "id", "model", "bus", "address", "values"}, "device")
        identifier(device["id"])
        if not isinstance(device["name"], str) or not device["name"].strip():
            raise ProjectError("Device name must be a nonempty display name")
        if not isinstance(device["model"], str) or device["model"] not in catalog["models"]:
            raise ProjectError("Unsupported device model; run ./scripts/project.sh devices")
        if not isinstance(device["bus"], str) or device["bus"] not in catalog["buses"]:
            raise ProjectError("Unsupported bus; run ./scripts/project.sh devices")
        if type(device["address"]) is not int or not 0x08 <= device["address"] <= 0x77:
            raise ProjectError("I2C address must be an integer in 0x08..0x77")
        address = (device["bus"], device["address"])
        if device["id"] in ids or address in addresses:
            raise ProjectError(f"Duplicate device ID or I2C bus/address: {device['id']}")
        ids.add(device["id"])
        addresses.add(address)
        validate_values(device, device["values"])


def load_config(root):
    config = json.loads(safe_path(root, "project/config.json").read_text())
    validate_hardware(config)
    return config


def topology(config):
    return sorted(({key: device[key] for key in ("id", "model", "bus", "address")}
                   for device in config["devices"]), key=lambda device: device["id"])


def appgen(root):
    source = safe_path(root, "cFS/tools/appgen/appgen.py")
    spec = importlib.util.spec_from_file_location("project_appgen", source)
    module = importlib.util.module_from_spec(spec)
    # Read-only commands must not create __pycache__ in the source checkout.
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def protected_apps(root):
    protected = set(board_catalog()["protected_apps"])
    modules = safe_path(root, "cFS/.gitmodules")
    if modules.exists():
        parser = configparser.ConfigParser()
        parser.read(modules)
        for section in parser.sections():
            path = parser.get(section, "path", fallback="")
            if path.startswith("apps/"):
                protected.add(path.split("/")[1])
    return protected


def read_manifests(root, config):
    """Reject unregistered/stock app manifests before appgen can touch them."""
    registered = {app.get("name") for app in config["apps"] if isinstance(app, dict)}
    protected = protected_apps(root)
    for path in safe_path(root, "cFS/apps").glob("*/app.json"):
        safe_path(root, path.relative_to(root))
        if path.parent.name in protected or path.parent.name not in registered:
            raise ProjectError(f"Protected or unregistered app: {path.parent.name}")
    return appgen(root).read_manifests(safe_path(root, "cFS"))


def validate_config(root, config, manifests=None, new_apps=()):
    validate_hardware(config)
    catalog = board_catalog()
    protected = protected_apps(root)
    names = set()
    devices = {device["id"]: device for device in config["devices"]}
    for app in config["apps"]:
        fields(app, {"name", "sensors", "telemetry_bindings", "command_bindings"}, "app registry")
        identifier(app["name"])
        if app["name"] in protected or app["name"] in names:
            raise ProjectError(f"Protected or duplicate app: {app['name']}")
        names.add(app["name"])
        for key in ("sensors", "telemetry_bindings", "command_bindings"):
            if not isinstance(app[key], dict):
                raise ProjectError(f"{app['name']}.{key} must be an object")
        if app["name"] not in new_apps:
            path = safe_path(root, f"cFS/apps/{app['name']}/CMakeLists.txt")
            if not path.is_file() or "Generated from app.json." not in path.read_text():
                raise ProjectError(f"App was not created by appgen: {app['name']}")
    if manifests is None:
        manifests = read_manifests(root, config)
    generator = appgen(root)
    generator.validate_all(manifests)
    if {app["name"] for app in manifests} != names:
        raise ProjectError("Project app registry and cFS app manifests differ")
    for app in config["apps"]:
        manifest = generator.app_by_name(manifests, app["name"])
        sensors = {sensor["name"]: sensor for sensor in manifest["sensors"]}
        if set(app["sensors"]) != set(sensors):
            raise ProjectError(f"Every {app['name']} sensor must have one device binding")
        for name, device_id in app["sensors"].items():
            if not isinstance(device_id, str) or device_id not in devices:
                raise ProjectError(f"Unknown physical device for {app['name']}.{name}")
            driver = catalog["models"][devices[device_id]["model"]]["cfs_driver"]
            if driver is None:
                raise ProjectError(f"No cFS driver is implemented for {devices[device_id]['model']}; QEMU simulation is available")
            if sensors[name]["driver"] != driver:
                raise ProjectError(f"Sensor driver does not match device model: {app['name']}.{name}")
        telemetry = {packet["name"] for packet in manifest["telemetry"]}
        for packet, sensor in app["telemetry_bindings"].items():
            if packet not in telemetry or not isinstance(sensor, str) or sensor not in sensors:
                raise ProjectError(f"Telemetry binding must name an existing packet and sensor: {app['name']}.{packet}")
        commands = {command["name"] for command in manifest["commands"]}
        for command, device_id in app["command_bindings"].items():
            if command not in commands or not isinstance(device_id, str) or device_id not in devices:
                raise ProjectError(f"Command binding must name an existing command and device: {app['name']}.{command}")
            if catalog["models"][devices[device_id]["model"]]["kind"] != "actuator":
                raise ProjectError("No actuator model is currently supported; command handlers remain user code")


def mapped_manifests(config, manifests):
    """Apply hardware locations to manifests, keeping all message IDs intact."""
    catalog = board_catalog()
    devices = {device["id"]: device for device in config["devices"]}
    apps = {app["name"]: app for app in manifests}
    for registry in config["apps"]:
        for sensor in apps[registry["name"]]["sensors"]:
            device = devices[registry["sensors"][sensor["name"]]]
            sensor["device"] = catalog["buses"][device["bus"]]["device"]
            sensor["address"] = device["address"]
    return manifests
