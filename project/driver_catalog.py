"""Select native cFS libraries from platform capabilities and CMake dependencies."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import tempfile
import platform


STATE = "project/generated/drivers.json"


def _safe(root, relative):
    from project.model import safe_path
    return safe_path(root, relative)


def load_catalog(root):
    path = _safe(root, "project/drivers/catalog.json")
    return json.loads(path.read_text()) if path.is_file() else {}


def _native_set(path, variable):
    if not path.is_file():
        return set()
    text = re.sub(r"#[^\n]*", "", path.read_text())
    values = set()
    for match in re.finditer(r"\b(set|list)\s*\(\s*(?:(APPEND|REMOVE_ITEM)\s+)?" + variable + r"\b([^)]*)\)", text, re.I):
        words = match[3].split()
        if match[1].lower() == "set":
            values = set(words)
        elif (match[2] or "").upper() == "APPEND":
            values.update(words)
        elif (match[2] or "").upper() == "REMOVE_ITEM":
            values.difference_update(words)
    return values


def selection(root):
    path = _safe(root, "cFS/sample_defs/modules.cmake")
    return {"added": _native_set(path, "MISSION_CPU1_ADDED_MODULES"),
            "removed": _native_set(path, "MISSION_CPU1_REMOVED_MODULES")}


def _commands(text, allowed):
    """Extract balanced CMake commands, including nested if() expressions."""
    commands, offset = [], 0
    for match in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', text):
        if match.start() < offset:
            continue
        start, depth, quoted, cursor = match.end(), 1, False, match.end()
        while cursor < len(text) and depth:
            char = text[cursor]
            if char == '\\':
                cursor += 2
                continue
            if char == '"':
                quoted = not quoted
            elif not quoted:
                bracket = re.match(r'\[(=*)\[', text[cursor:]) if char == '[' else None
                if bracket:
                    end = text.find(']' + bracket[1] + ']', cursor + len(bracket[0]))
                    if end < 0:
                        raise ValueError('Unterminated CMake bracket argument')
                    cursor = end + len(bracket[1]) + 2
                    continue
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
            cursor += 1
        if depth:
            raise ValueError('Unterminated CMake command: ' + match[1])
        offset = cursor
        if match[1].lower() in allowed:
            commands.append((match[1], text[start:cursor - 1]))
    return commands


@lru_cache(maxsize=256)
def _dependency_values(text, cache):
    """Evaluate only native CMake declarations, with no build/filesystem commands."""
    functions = re.findall(r"\b(?:function|macro)\s*\(\s*(\w+)", text, re.I)
    allowed = set("set option list if elseif else endif function endfunction macro endmacro foreach endforeach add_cfe_app_dependency".split())
    allowed.update(name.lower() for name in functions)
    commands = _commands(text, allowed)
    declarations = []
    for variable, value in re.findall(r"^([A-Za-z_]\w*):[^=\n]+=([^\n]*)$", cache, re.M):
        if re.search(r"\b" + variable + r"\b", text):
            declarations.append(f"set({variable} [==[{value}]==] CACHE STRING \"\")")
    script = "\n".join([
        "cmake_minimum_required(VERSION 3.16)",
        "function(add_cfe_app_dependency module)",
        '  message("__CFS_DEP__:${module}:${ARGN}")',
        "endfunction()",
        *declarations,
        *(f"{command}({arguments})" for command, arguments in commands),
    ])
    with tempfile.TemporaryDirectory(prefix="cfs-dependencies-") as temporary:
        path = Path(temporary) / "dependencies.cmake"
        path.write_text(script)
        result = subprocess.run(["cmake", "-P", str(path)], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise ValueError("Cannot evaluate native library dependencies: " + result.stderr.strip())
    return [(name, [item for item in values.split(";") if item])
            for name, values in re.findall(r"^__CFS_DEP__:([^:]+):(.*)$", result.stderr, re.M)]


def dependencies(root, name, sources=None):
    """Read the native dependency declarations of an app or library."""
    from project.model import identifier
    identifier(name)
    candidates = [f"cFS/apps/{name}/CMakeLists.txt", f"cFS/libs/{name}/CMakeLists.txt",
                  f"project/drivers/{name}/CMakeLists.txt"]
    text = None
    for relative in candidates:
        if sources and relative in sources and sources[relative] is not None:
            text = sources[relative]
            break
        path = Path(root) / relative
        if relative.startswith('cFS/'):
            # NASA links optional modules from apps/ to subdirectories of the
            # same checkout. Read these aliases without allowing external paths.
            resolved = path.resolve()
            cfs = (Path(root) / 'cFS').resolve()
            if not resolved.is_relative_to(cfs) or '.git' in resolved.relative_to(cfs).parts:
                raise ValueError('Native module source must remain inside cFS: ' + name)
        else:
            path = _safe(root, relative)
        if path.is_file():
            text = path.read_text()
            break
    if text is None:
        return []
    text = re.sub(r"#\[(=*)\[.*?\]\1\]", "", text, flags=re.S)
    text = re.sub(r"#[^\n]*", "", text)
    if not re.search(r"\badd_cfe_app_dependency\s*\(", text):
        return []
    from project.cfs_config import build_profile
    from project.model import load_config
    config = load_config(root)
    architecture = build_profile(root, config)["architecture"]
    build = "build-flight" if config["board"] else "build-native"
    cache_path = _safe(root, f"cFS/{build}/cache/{architecture}/default_cpu1/CMakeCache.txt")
    cache = cache_path.read_text() if cache_path.is_file() else ""
    result = []
    for module, values in _dependency_values(text, cache):
        if module == name:
            for dependency in values:
                if not re.fullmatch(r"[a-z][a-z0-9_]*", dependency):
                    raise ValueError(f"Unresolved native dependency for {name}: {dependency}")
                if dependency not in result:
                    result.append(dependency)
    return result


def requirements(root, config, manifests=None, excluded=None, selected=None, sources=None):
    """Return dependency-ordered catalog drivers and their configuration owners."""
    from project.model import board_catalog
    root = Path(root)
    catalog = load_catalog(root)
    board = board_catalog(config["board"], root=root)
    family = (board.get("os_families", {}).get(config["os"], config["os"])
              if config["board"] else platform.system().lower())
    membership = selection(root)
    excluded = membership["removed"] if excluded is None else set(excluded)
    selected = membership["added"] if selected is None else set(selected)
    explicit = (_native_set(_safe(root, "cFS/sample_defs/libraries.cmake"), "MISSION_LIBRARIES") | selected) - excluded
    reasons, ordered, visiting = {}, [], set()

    def visit(name, reason):
        if name in visiting:
            raise ValueError("Library dependency cycle: " + " -> ".join([*sorted(visiting), name]))
        if name in catalog:
            if family not in catalog[name].get("systems", []):
                raise ValueError(f"{name} has no driver implementation for {config['board']}/{config['os']}")
            reasons.setdefault(name, set()).add(reason)
        visiting.add(name)
        for dependency in dependencies(root, name, sources):
            visit(dependency, reason)
        visiting.remove(name)
        if name in catalog and name not in ordered:
            ordered.append(name)

    for device in config["devices"]:
        library = board["models"][device["model"]].get("library")
        if library:
            visit(library, "sensor " + device["id"])
    apps = {app["name"] for app in manifests or []} | {app["name"] for app in config["apps"]}
    # Native startup records cover stock/custom apps configured without Studio.
    from project.appgen.native_startup import parse_startup
    startup = _safe(root, "cFS/sample_defs/cpu1_cfe_es_startup.scr")
    if startup.is_file():
        enabled, disabled = parse_startup(startup.read_text())
        apps.update(record.name for record in [*enabled, *disabled] if record.fields[0] == "CFE_APP"
                    and (record.name in apps or not _safe(root, f"project/apps/{record.name}.json").exists()))
    for name in sorted(apps - excluded):
        for dependency in dependencies(root, name, sources):
            visit(dependency, "app " + name)
    for name in sorted(explicit):
        visit(name, "library " + name)
    return [{"name": name, "entry_point": catalog[name]["entry_point"]} for name in ordered], {
        name: sorted(values) for name, values in reasons.items()}


def requirement_details(root, config, manifests=None, excluded=None, selected=None):
    return requirements(root, config, manifests, excluded, selected)[1]


def plan_drivers(root, libraries):
    """Materialize selected templates, preserving edited source-only libraries."""
    root = Path(root)
    catalog = load_catalog(root)
    state_path = _safe(root, STATE)
    previous = json.loads(state_path.read_text()) if state_path.is_file() else {"modules": {}, "retained": {}}
    old = previous.get("modules", {})
    wanted = {item["name"] for item in libraries if item["name"] in catalog}
    files, managed, retained = {}, {}, dict(previous.get("retained", {}))
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for name in sorted(set(catalog) | set(old)):
        template = _safe(root, f"project/drivers/{name}")
        destination = _safe(root, f"cFS/libs/{name}")
        templates = {path.relative_to(template).as_posix(): path.read_bytes()
                     for path in sorted(template.rglob("*")) if path.is_file() and not path.is_symlink()}
        recorded = old.get(name, {})
        if not recorded and destination.is_dir():
            # The first migration can adopt exact copies, never user-edited files.
            recorded = {relative: digest(data) for relative, data in templates.items()}
        actual = {path.relative_to(destination).as_posix(): path for path in destination.rglob("*") if path.is_file()}
        if name not in wanted:
            if not actual:
                retained.pop(name, None)
                continue
            unchanged = set(actual) == set(recorded) and all(
                not path.is_symlink() and digest(path.read_bytes()) == recorded[relative]
                for relative, path in actual.items())
            if unchanged:
                files.update({f"cFS/libs/{name}/{relative}": None for relative in actual})
                retained.pop(name, None)
            else:
                retained[name] = "Local source edits preserved; excluded from automatic driver selection"
            continue
        if not templates:
            raise ValueError(f"Missing source template for driver {name}")
        managed[name] = {}
        retained.pop(name, None)
        for relative, content in templates.items():
            path = _safe(root, f"cFS/libs/{name}/{relative}")
            current = path.read_bytes() if path.is_file() else None
            expected = recorded.get(relative)
            if current is not None and digest(current) not in {expected, digest(content)}:
                managed[name][relative] = expected or digest(content)
                continue
            files[f"cFS/libs/{name}/{relative}"] = content.decode()
            managed[name][relative] = digest(content)
    payload = {"modules": managed, "retained": retained}
    if payload["modules"] or payload["retained"] or state_path.exists():
        files[STATE] = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return files
