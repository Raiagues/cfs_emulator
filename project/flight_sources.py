"""Locate NASA sources and the Studio-owned mission built against them."""
import configparser
import fcntl
from pathlib import Path
import shutil
import tempfile


def nasa_module_names(root, group):
    """Reserve the checkout's modules, including symlinks and unpopulated gitlinks."""
    source = Path(root) / "cFS"
    names = {p.name for p in (source / group).glob("*") if p.is_dir() or p.is_symlink()}
    modules = configparser.ConfigParser(interpolation=None)
    modules.read(source / ".gitmodules")
    for section in modules.sections():
        path = Path(modules[section].get("path", ""))
        if path.parent == Path(group):
            names.add(path.name)
    return names


def module_directory(root, group, name):
    """NASA module names take precedence, including aliases shipped by NASA."""
    root = Path(root)
    nasa = root / "cFS" / group / name
    return nasa if nasa.exists() else root / "mission" / group / name


def module_directories(root, group):
    root = Path(root)
    names = {p.name for base in ("mission", "cFS") for p in (root / base / group).glob("*") if p.is_dir()}
    return [module_directory(root, group, name) for name in sorted(names)]


def prepare_mission(root):
    """Seed writable mission definitions once, without overwriting a user's edits."""
    from project.model import ProjectError, safe_path
    from project.cfs_config import mission_targets
    root = Path(root)
    source = safe_path(root, "cFS/sample_defs")
    if not (source / "targets.cmake").is_file():
        raise ProjectError("Clone NASA cFS in workspace setup before configuring a mission.")
    mission = safe_path(root, "mission")
    mission.mkdir(exist_ok=True)
    definitions = safe_path(mission, "sample_defs")
    if (definitions / "targets.cmake").is_file():
        return
    with safe_path(mission, ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (definitions / "targets.cmake").is_file():
            return
        if definitions.exists():
            raise ProjectError("Incomplete mission/sample_defs. Restore its targets.cmake before continuing.")
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=mission) as temporary:
            stage = Path(temporary) / "sample_defs"
            shutil.copytree(source, stage, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            targets = stage / "targets.cmake"
            targets.write_text(mission_targets(targets.read_text()))
            stage.rename(definitions)
