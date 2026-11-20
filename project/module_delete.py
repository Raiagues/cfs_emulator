"""Permanently delete a Studio app and its registry, startup and build entries together."""
import hashlib
import json
from pathlib import Path
import tempfile

from project.mission_tables import table_membership_plan
from project.module_rename import assert_no_module_references
from project import model


def source_hashes(directory, relative):
    files = {}
    for path in directory.rglob("*"):
        if path.is_symlink() or path.name == ".git" or not (path.is_dir() or path.is_file()):
            raise ValueError(f"Cannot delete an application with linked or external sources: {relative}")
        if path.is_file():
            files[(relative / path.relative_to(directory)).as_posix()] = hashlib.sha256(path.read_bytes()).digest()
    return files


def delete_app(workspace, name, revision):
    """Caller holds the same mission transaction lock used for rename and membership."""
    from project.manage import commit
    root, mission = workspace.root, workspace.mission
    name = model.identifier(name)
    config = model.load_config(root)
    manifests = model.read_manifests(root, config)
    model.validate_config(root, config, manifests)
    if name in model.protected_apps(root) or not any(app["name"] == name for app in manifests):
        raise ValueError("Only project-created application sources can be deleted")
    relative = Path("mission/apps") / name
    directory = workspace.path(str(relative))
    mission.assert_can_remove(name)
    sources = source_hashes(directory, relative)
    headers = {Path(path).name for path in sources if path.endswith((".h", ".hpp")) and "/fsw/" in path}
    symbols = {fn["symbol"] for fn in workspace.source_index.application(directory)["functions"]
               if not fn["static"] and fn["symbol"].startswith(name.upper() + "_")}
    peers = [module for group in ("apps", "libs") for module in (root / "mission" / group).glob("*")
             if module != directory and (module / "CMakeLists.txt").is_file()]
    assert_no_module_references(root, peers, name, headers, symbols)

    config["apps"] = [app for app in config["apps"] if app["name"] != name]
    remaining = [app for app in manifests if app["name"] != name]
    selection = mission.selection()
    plan = model.planned_project_files(root, config, remaining, excluded=selection["removed"] - {name},
                                       selected=selection["added"] - {name})
    plan.update(table_membership_plan(root, sources=plan))
    plan.update(mission.selection_plan(forget=[name], sources=plan))
    plan[mission.STARTUP] = mission.reconcile_removed_modules([name])
    plan[f"project/apps/{name}.json"] = None
    plan["project/config.json"] = json.dumps(config, indent=2) + "\n"
    mission.assert_revision(revision)
    result = {}

    def validate():
        model.validate_config(root, model.load_config(root))
        if name in mission._evaluate(mission._revision())["compiled"]:
            raise ValueError(f"A native CPU1 build entry still references {name}")
        result["mission"] = mission.snapshot()

    # Rename the entire source tree, including user files and empty directories.
    # Keep it available for rollback until the rest of the mission is validated.
    with tempfile.TemporaryDirectory(dir=root / "mission") as staging:
        staged = Path(staging) / name
        directory.rename(staged)
        try:
            if source_hashes(staged, relative) != sources:
                raise ValueError("Application sources changed during deletion. Reload before retrying.")
            changed = commit(root, plan, validate=validate)
        except BaseException:
            staged.rename(directory)
            raise
    result["changed"] = sorted(set(changed) | set(sources))
    result["deleted"] = sorted(set(sources) | {path for path in changed if path in plan and plan[path] is None})
    return result
