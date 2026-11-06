"""Edit configured bus locations through the project generation plan."""
import copy
import hashlib
import json


CONFIG = "project/config.json"


def device_settings(workspace, device_id):
    with workspace.lock:
        config = workspace.model.load_config(workspace.root)
        device = next((item for item in config["devices"] if item["id"] == device_id), None)
        if device is None:
            raise ValueError("Device not found")
        catalog = workspace.model.board_catalog(config["board"], workspace.root)
        return {"device": device, "buses": catalog["buses"],
                "source": {"path": CONFIG, "hash": workspace.read_file(CONFIG)["hash"]}}


def update_device(workspace, payload):
    """Save address/bus and regenerate bound readers; user-owned C files are kept."""
    from project.manage import commit

    if not isinstance(payload, dict) or set(payload) != {"id", "bus", "address", "expected_hash"}:
        raise ValueError("Sensor settings require id, bus, address and expected_hash")
    device_id = workspace.model.identifier(payload["id"])
    address = payload["address"]
    if isinstance(address, str):
        try:
            address = int(address, 16 if address.lower().startswith("0x") else 10)
        except ValueError as error:
            raise ValueError("Enter an integer I2C address, such as 0x48") from error
    with workspace.lock, workspace.mission.transaction(workspace.mission._revision()) as revision:
        before_config = workspace.path(CONFIG).read_bytes()
        if hashlib.sha256(before_config).hexdigest() != payload["expected_hash"]:
            raise ValueError("Hardware configuration changed. Reopen the sensor settings before saving.")
        config = copy.deepcopy(workspace.model.load_config(workspace.root))
        device = next((item for item in config["devices"] if item["id"] == device_id), None)
        if device is None:
            raise ValueError("Device not found")
        device["bus"], device["address"] = payload["bus"], address
        model = workspace.model
        before_apps = {f"project/apps/{app['name']}.json":
                       workspace.path(f"project/apps/{app['name']}.json").read_bytes()
                       for app in config["apps"]}
        manifests = model.read_manifests(workspace.root, config)
        model.validate_config(workspace.root, config, manifests)
        model.mapped_manifests(config, manifests, workspace.root)
        plan = model.planned_project_files(workspace.root, config, manifests)
        plan[CONFIG] = json.dumps(config, indent=2) + "\n"
        fragment = "cFS/sample_defs/generated/appgen_startup.scr"
        plan[workspace.mission.STARTUP] = workspace.mission.reconcile_generated_modules(
            workspace.path(fragment).read_text() if workspace.path(fragment).exists() else "", plan[fragment])
        if workspace.path(CONFIG).read_bytes() != before_config or any(
                workspace.path(path).read_bytes() != content for path, content in before_apps.items()):
            raise ValueError("Hardware configuration changed. Reopen the sensor settings before saving.")
        workspace.mission.assert_revision(revision)
        changed = commit(workspace.root, plan)
        return {"changed": changed, "deleted": [path for path, content in plan.items() if content is None],
                **device_settings(workspace, device_id)}
