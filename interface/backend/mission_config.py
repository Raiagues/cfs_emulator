"""Read and edit CPU1's native cFE startup selection, without changing sources.

APPLIST describes compiled/installed modules; CFE_APP startup records describe
what starts on the next boot. Neither is evidence of an app running right now.
"""

from contextlib import contextmanager
import fcntl
import hashlib
from pathlib import Path
import re
import threading

from project.appgen.native_startup import (
    parse_startup, render_startup, reconcile_removed_modules, reconcile_generated_modules,
)


class MissionConfig:
    STARTUP = "cFS/sample_defs/cpu1_cfe_es_startup.scr"
    MODULES = "cFS/sample_defs/modules.cmake"
    @property
    def INSTALLED(self):
        from project.model import load_config
        build = 'build-flight' if load_config(self.root)['board'] else 'build-native'
        return f"cFS/{build}/exe/cpu1/cf/cfe_es_startup.scr"

    CORE = {"es": "Executive services", "evs": "Events", "fs": "Files",
            "sb": "Software bus", "tbl": "Tables", "time": "Time"}
    WARNINGS = {
        "ci_lab": "Disabling CI removes the mission's ground command uplink.",
        "to_lab": "Disabling TO removes the mission's ground telemetry downlink.",
        "sch_lab": "Disabling SCH stops its periodic wakeups and housekeeping requests.",
    }

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self._evaluation_cache = None

    def _path(self, relative):
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Mission configuration must remain inside this project")
        return path

    def _inputs(self):
        inputs = [self._path("cFS/cfe/cmake/mission_defaults.cmake")]
        definitions = self._path("cFS/sample_defs")
        inputs.extend(sorted(p for p in definitions.rglob("*")
                             if p.is_file() and p.suffix in (".cmake", ".scr", ".c", ".h", ".inc")))
        project = self._path("project")
        inputs.extend(sorted(p for p in project.rglob("*") if p.is_file()
                             and (p.suffix in (".json", ".cmake", ".c", ".h") or p.name == "CMakeLists.txt")))
        for group in ("apps", "libs"):
            inputs.extend(sorted(self._path("cFS/" + group).glob("*/CMakeLists.txt")))
        return inputs

    def selection(self):
        """Explicit CPU1 membership overrides, expressed in native CMake."""
        path = self._path(self.MODULES)
        text = re.sub(r'#[^\n]*', '', path.read_text()) if path.exists() else ''
        result = {}
        for key, variable in (("added", "MISSION_CPU1_ADDED_MODULES"), ("removed", "MISSION_CPU1_REMOVED_MODULES")):
            matches = re.findall(r'\bset\s*\(\s*' + variable + r'\s*([^)]*)\)', text, re.I)
            if len(matches) > 1:
                raise ValueError("Declare " + variable + " once in " + self.MODULES)
            names = matches[0].split() if matches else []
            if not all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) for name in names):
                raise ValueError(variable + " must contain module names")
            result[key] = set(names)
        return result

    def selection_plan(self, add=(), remove=(), forget=(), sources=None):
        """Return native list changes for a larger atomic mission transaction."""
        selection = self.selection()
        added, removed = selection["added"], selection["removed"]
        for names in (add, remove, forget):
            if not all(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) for name in names):
                raise ValueError("Invalid native module name")
        added.difference_update(forget); removed.difference_update(forget)
        added.difference_update(remove); removed.update(remove)
        removed.difference_update(add); added.update(add)
        content = "\n".join([
            "# CPU1 module selection. Startup controls which installed modules are loaded.",
            "set(MISSION_CPU1_ADDED_MODULES " + " ".join(sorted(added)) + ")",
            "set(MISSION_CPU1_REMOVED_MODULES " + " ".join(sorted(removed)) + ")", "",
            "# Preserve each CPU's global modules before changing CPU1 membership.",
            "foreach(CPU IN LISTS MISSION_CPUNAMES)",
            "    list(APPEND ${CPU}_APPLIST ${MISSION_GLOBAL_APPLIST})",
            "endforeach()", "set(MISSION_GLOBAL_APPLIST)",
            "list(APPEND cpu1_APPLIST ${MISSION_CPU1_ADDED_MODULES})",
            "if(MISSION_CPU1_REMOVED_MODULES)",
            "    list(REMOVE_ITEM cpu1_APPLIST ${MISSION_CPU1_REMOVED_MODULES})", "endif()",
            "list(REMOVE_DUPLICATES cpu1_APPLIST)", "",
        ])
        plan = {self.MODULES: content}
        path = "cFS/sample_defs/targets.cmake"
        source = (sources or {}).get(path, self._path(path).read_text())
        if not re.search(r'\binclude\s*\([^)]*[/]modules\.cmake', source, re.I):
            plan[path] = source.rstrip() + "\n\ninclude(${CMAKE_CURRENT_LIST_DIR}/modules.cmake OPTIONAL)\n"
        return plan

    def dependents(self, name, compiled=None):
        """Find included native CMake/API consumers before removing a module."""
        from interface.backend.source_index import SourceIndex
        from interface.backend.library_index import inspect_libraries
        from project.driver_catalog import dependencies
        compiled = set(compiled if compiled is not None else self._evaluate(self._revision())["compiled"])
        index = SourceIndex(self.root)
        apps, declared = [], set()
        for group in ("apps", "libs"):
            for path in sorted(self._path("cFS/" + group).glob("*/CMakeLists.txt")):
                if path.parent.name not in compiled or path.parent.name == name:
                    continue
                if name in dependencies(self.root, path.parent.name):
                    declared.add(path.parent.name)
                if group == "apps":
                    app = {"name": path.parent.name, "path": path.parent.relative_to(self.root).as_posix(),
                           "enabled": True, **index.application(path.parent)}
                    apps.append(app)
        mission = {"compiled": list(compiled), "libraries": []}
        for library in inspect_libraries(self.root, apps, index, mission):
            if library["name"] == name:
                declared.update(user["name"] for user in library["used_by"] if user["name"] in compiled)
        return sorted(declared)

    def removal_blockers(self, name):
        from project.model import load_config, read_manifests
        from project.driver_catalog import requirement_details
        config = load_config(self.root)
        required = requirement_details(self.root, config, read_manifests(self.root, config))
        blockers = {("app " if self._path(f"cFS/apps/{module}/CMakeLists.txt").is_file() else "library ") + module
                    for module in self.dependents(name)}
        blockers.update(reason for reason in required.get(name, []) if reason != "library " + name)
        return sorted(blockers)

    def assert_can_remove(self, name):
        blockers = self.removal_blockers(name)
        if blockers:
            raise ValueError(name + " is required by: " + ", ".join(blockers))

    def _library_deletable(self, name, evaluated=None):
        from project.driver_catalog import load_catalog
        if name in load_catalog(self.root):
            return False
        source = self._path("cFS/libs/" + name)
        roots = (evaluated or self._evaluate(self._revision()))["library_roots"]
        selection = self.selection()
        return (name in set(roots) | selection["added"] | selection["removed"] and source.is_dir()
                and not (source / ".git").exists() and not source.is_symlink()
                and not any(path.is_symlink() for path in source.rglob("*")))

    def _dependency_order(self, name):
        from project.driver_catalog import dependencies
        ordered, visiting = [], set()
        def visit(module):
            if module in visiting:
                raise ValueError("Native library dependency cycle at " + module)
            if module in ordered:
                return
            visiting.add(module)
            for dependency in dependencies(self.root, module):
                # cFE/PSP components are linked by the platform, not loaded as
                # standalone CFE_LIB startup records.
                if any(self._path(f"cFS/{group}/{dependency}/CMakeLists.txt").is_file()
                       for group in ("cfe/modules", "psp/fsw/modules")):
                    continue
                visit(dependency)
            visiting.remove(module)
            ordered.append(module)
        visit(name)
        return ordered

    def _change_membership(self, kind, action, name, expected_hash):
        from project.model import load_config, read_manifests, planned_project_files
        from project.driver_catalog import load_catalog
        from project.manage import commit
        with self.transaction(expected_hash) as revision:
            _, evaluated, active, archived, defaults = self._read()
            compiled = set(evaluated["compiled"])
            recipes = {entry.name: entry for entry in defaults + archived + active}
            catalog = load_catalog(self.root)
            if kind == "CFE_LIB" and name in catalog and name not in recipes:
                recipes[name] = parse_startup(", ".join(("CFE_LIB", "/cf/" + name + ".so",
                    catalog[name]["entry_point"], name.upper(), "0", "0", "0", "0")) + ";")[0][0]
            entry = recipes.get(name)
            if not entry or entry.kind != kind:
                raise ValueError("No native startup recipe for " + name)
            included = (name in compiled and (kind == "CFE_LIB" or any(item.name == name for item in archived))
                        or any(item.name == name for item in active))
            if action == "add" and included:
                raise ValueError("Module is already included in the mission")
            if action != "add" and not included and action != "delete":
                raise ValueError("Module is not included in the mission")
            selection = self.selection()
            added, removed = selection["added"].copy(), selection["removed"].copy()
            if action in {"remove", "delete"}:
                self.assert_can_remove(name)
                if action == "delete" and not self._library_deletable(name, evaluated):
                    raise ValueError("Only project-created library sources can be deleted")
                added.discard(name)
                removed.add(name)
                active = [item for item in active if item.name != name]
                archived = [item for item in archived if item.name != name]
                if action != "delete":
                    archived.append(entry)
                dependencies = []
            else:
                dependencies = self._dependency_order(name)
                for dependency in dependencies:
                    if dependency not in catalog and not any(self._path(f"cFS/{group}/{dependency}/CMakeLists.txt").is_file()
                                                              for group in ("apps", "libs")):
                        raise ValueError("Missing native module source: " + dependency)
                    removed.discard(dependency)
                    if dependency == name or dependency not in compiled and dependency not in catalog:
                        added.add(dependency)
            config = load_config(self.root)
            plan = planned_project_files(self.root, config, read_manifests(self.root, config),
                                         excluded=removed, selected=added)
            if kind == "CFE_APP" and action == "remove":
                from interface.backend.mission_tables import table_membership_plan
                plan.update(table_membership_plan(self.root, sources=plan))
            plan.update(self.selection_plan(add=added, remove=removed,
                                           forget=selection["added"] - added | selection["removed"] - removed, sources=plan))
            fragment = "cFS/sample_defs/generated/appgen_startup.scr"
            generated, _ = parse_startup(plan[fragment])
            recipes.update({item.name: item for item in generated})
            if action == "add":
                present = {item.name for item in active}
                libraries = []
                for dependency in dependencies:
                    if dependency in present:
                        continue
                    candidate = recipes.get(dependency)
                    if candidate is None:
                        raise ValueError("No native startup recipe for dependency " + dependency)
                    if candidate.kind == "CFE_LIB":
                        libraries.append(candidate)
                    elif dependency != name:
                        raise ValueError("Application dependency must be added first: " + dependency)
                first_app = next((i for i, item in enumerate(active) if item.kind == "CFE_APP"), len(active))
                active[first_app:first_app] = libraries
                if kind == "CFE_APP":
                    active.append(entry)
                restored = set(dependencies)
                archived = [item for item in archived if item.name not in restored]
            plan[self.STARTUP] = render_startup(active, archived)
            if action == "delete":
                roots = [item for item in evaluated["library_roots"] if item != name]
                plan["cFS/sample_defs/libraries.cmake"] = (
                    "# Mission libraries built for CPU1. Native CFE_LIB startup entries load them.\n"
                    "set(MISSION_LIBRARIES " + " ".join(roots) + ")\n")
                plan.update(self.selection_plan(forget=[name], sources=plan))
                source = self._path("cFS/libs/" + name)
                plan.update({path.relative_to(self.root).as_posix(): None
                             for path in source.rglob("*") if path.is_file()})
            self.assert_revision(revision)
            changed = commit(self.root, plan, mutable_libraries=[name] if action == "delete" else [])
            return {"mission": self.snapshot(), "changed": changed,
                    "deleted": [path for path in changed if path in plan and plan[path] is None]}

    def schedule_config(self):
        """Use cfe_locate_implementation_file's CPU1 table precedence."""
        filename = "sch_lab_table.c"
        candidates = [f"cFS/sample_defs/cpu1/tables/{filename}",
                      f"cFS/sample_defs/tables/cpu1_{filename}",
                      f"cFS/sample_defs/tables/{filename}",
                      f"cFS/sample_defs/cpu1/{filename}",
                      f"cFS/sample_defs/cpu1_{filename}", f"cFS/sample_defs/{filename}",
                      f"cFS/apps/sch_lab/fsw/tables/{filename}"]
        relative = next((name for name in candidates if self._path(name).is_file()), None)
        if relative is None:
            return {"path": None, "line": 1, "tick_hz": None}
        text = self._path(relative).read_text()
        clean = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', lambda match: '\n' * match[0].count('\n'), text)
        match = re.search(r'\.TickRate\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\s*[,}]', clean)
        rate = int(match[1], 16 if match[1].lower().startswith("0x") else 10) if match else None
        return {"path": relative, "line": clean.count('\n', 0, match.start()) + 1 if match else 1,
                "tick_hz": (rate or 1) if rate is not None else None,
                "generated_path": "cFS/sample_defs/generated/appgen_schedule.inc"}

    def _revision(self):
        digest = hashlib.sha256()
        for path in self._inputs():
            relative = path.relative_to(self.root).as_posix()
            self._path(relative)
            digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
        return digest.hexdigest()

    def _evaluate(self, revision):
        if self._evaluation_cache and self._evaluation_cache[0] == revision:
            return self._evaluation_cache[1]
        from project.cfs_config import evaluate_mission
        result = evaluate_mission(self.root)
        self._evaluation_cache = (revision, result)
        return result

    def _read(self):
        revision = self._revision()
        evaluated = self._evaluate(revision)
        path = self._path(self.STARTUP)
        text = path.read_text() if path.exists() else evaluated["default"]
        active, archived = parse_startup(text)
        defaults, _ = parse_startup(evaluated["default"])
        return revision, evaluated, active, archived, defaults

    def startup_text(self):
        return self._path(self.STARTUP).read_text() if self._path(self.STARTUP).is_file() else self._evaluate(self._revision())["default"]

    def reconcile_removed_modules(self, names, startup=None):
        """Return a native script for an explicit module deletion transaction."""
        if startup is None:
            startup = self.startup_text()
        return reconcile_removed_modules(startup, names)

    def reconcile_generated_modules(self, previous, replacement, startup=None):
        """Return native dependency updates for the caller's atomic file plan."""
        if startup is None:
            startup = self.startup_text()
        return reconcile_generated_modules(startup, previous, replacement)

    def snapshot(self):
        with self.lock:
            revision, evaluated, active, archived, defaults = self._read()
            enabled = [entry.name for entry in active if entry.kind == "CFE_APP"]
            compiled = set(evaluated["compiled"])
            included = list(dict.fromkeys(entry.name for entry in active + archived
                                          if entry.kind == "CFE_APP" and entry.name in compiled))
            # Keep invalid active entries visible so the user can remove them.
            included += [name for name in enabled if name not in included]
            recipes = {entry.name: entry for entry in defaults + archived + active if entry.kind == "CFE_APP"}
            # Catalog only applications with usable startup recipes. Library
            # plugins and arbitrary source directories are not launchable apps.
            names = {name for name in recipes if name in compiled or name in included
                     or self._path(f"cFS/apps/{name}/CMakeLists.txt").is_file()}
            available = []
            for name in sorted(names):
                entry = recipes.get(name)
                # An invalid active entry must still be removable; only adding
                # an entry requires a corresponding binary in APPLIST.
                editable = bool(entry and (name in included or self._path(f"cFS/apps/{name}/CMakeLists.txt").is_file()))
                warnings = [self.WARNINGS[name]] if name in self.WARNINGS else []
                if not entry:
                    warnings.append("No native startup entry is defined for this module.")
                source = self.STARTUP if any(item.name == name for item in active + archived) else "cFS/sample_defs/generate_startup.cmake"
                available.append({"name": name, "entry_point": entry.fields[2] if entry else None,
                                  "enabled": name in enabled, "included": name in included,
                                  "build_included": name in compiled,
                                  "editable": editable, "warnings": warnings,
                                  "priority": int(entry.fields[4], 0) if entry else None,
                                  "stack_size": int(entry.fields[5], 0) if entry else None,
                                  "source": {"path": source, "line": entry.line if source == self.STARTUP and entry else 1}})
            library_recipes = {entry.name: entry for entry in defaults + archived + active if entry.kind == "CFE_LIB"}
            from project.driver_catalog import load_catalog, requirement_details, dependencies
            from project.model import load_config, read_manifests
            config = load_config(self.root)
            catalog = load_catalog(self.root)
            required = requirement_details(self.root, config, read_manifests(self.root, config))
            for module in sorted(compiled):
                label = ("app " if self._path(f"cFS/apps/{module}/CMakeLists.txt").is_file() else "library ") + module
                for dependency in dependencies(self.root, module):
                    if label not in required.setdefault(dependency, []):
                        required[dependency].append(label)
            available_libraries = []
            for name in sorted(library_recipes.keys() | catalog.keys()):
                entry = library_recipes.get(name)
                available_libraries.append({
                    "name": name, "entry_point": entry.fields[2] if entry else catalog[name]["entry_point"],
                    "included": name in compiled, "loaded": any(item.name == name for item in active),
                    "editable": name in catalog or self._path(f"cFS/libs/{name}/CMakeLists.txt").is_file(),
                    "deletable": self._library_deletable(name, evaluated),
                    "required_by": [reason for reason in required.get(name, []) if reason != "library " + name],
                    "source": {"path": self.STARTUP, "line": entry.line if entry else 1},
                })
            installed = self._path(self.INSTALLED)
            built_entries = None
            warnings = []
            if installed.exists():
                try:
                    built_entries, _ = parse_startup(installed.read_text())
                except ValueError as error:
                    warnings.append("Installed startup could not be compared: " + str(error))
            missing = [entry.name for entry in active if entry.name not in compiled]
            if missing:
                warnings.append("Startup modules missing from APPLIST: " + ", ".join(missing))
            schedule = self.schedule_config()
            from project.model import appgen
            seed = appgen(self.root).new_app("draft_app", []) if self._path("project/appgen/appgen.py").is_file() else None
            defaults = {"priority": seed["priority"], "stack_size": seed["stack_size"],
                        "wakeup_hz": schedule["tick_hz"] / seed["period_ticks"] if schedule["tick_hz"] else None,
                        "hk_hz": schedule["tick_hz"] / seed["hk_period_ticks"] if schedule["tick_hz"] else None} if seed else None
            build_path = "cFS/sample_defs/targets.cmake"
            build_text = self._path(build_path).read_text()
            app_list = re.search(r'\b(?:set|list)\s*\(\s*(?:APPEND\s+)?cpu1_APPLIST\b', build_text, re.IGNORECASE)
            return {
                "enabled": enabled, "included": included, "available": available,
                "compiled": evaluated["compiled"],
                "source": {"path": self.STARTUP, "hash": revision},
                "libraries": [{"name": entry.name, "entry_point": entry.fields[2]} for entry in active if entry.kind == "CFE_LIB"],
                "available_libraries": available_libraries,
                "installed_enabled": [entry.name for entry in built_entries or [] if entry.kind == "CFE_APP"],
                "pending_build": built_entries is None or [entry.fields for entry in active] != [entry.fields for entry in built_entries],
                "build_source": self.INSTALLED if installed.exists() else None,
                "build_config": {"path": build_path, "line": build_text.count('\n', 0, app_list.start()) + 1 if app_list else 1,
                                 "modules": evaluated["compiled"],
                                 "selection_path": self.MODULES,
                                 "libraries_path": "cFS/sample_defs/libraries.cmake"},
                "schedule_config": schedule,
                "creation_defaults": {"app": defaults, "library": {}},
                "core_services": [{"name": name.upper(), "title": title, "path": f"cFS/cfe/modules/{name}"}
                                  for name, title in self.CORE.items() if name in evaluated["core"]],
                "warnings": warnings,
            }

    @contextmanager
    def _write_lock(self):
        directory = self._path("interface/.runtime")
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "mission.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def assert_revision(self, expected_hash):
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ValueError("Reload the mission configuration before saving")
        revision = self._revision()
        if expected_hash != revision:
            raise ValueError("Mission configuration changed. Reload it before saving.")
        return revision

    @contextmanager
    def transaction(self, expected_hash):
        """Serialize a larger source plan that also changes native membership."""
        with self.lock, self._write_lock():
            yield self.assert_revision(expected_hash)

    def _write_startup(self, content, revision):
        from project.cfs_config import bootstrap_plan
        from project.manage import commit
        parse_startup(content)
        self.assert_revision(revision)
        path = self._path(self.STARTUP)
        if path.exists() and path.read_text() == content:
            return
        plan = bootstrap_plan(self.root)
        plan[self.STARTUP] = content
        self.assert_revision(revision)
        commit(self.root, plan)

    def change_app(self, action, name, expected_hash):
        if not isinstance(action, str) or action not in {"add", "enable", "disable", "remove"}:
            raise ValueError("Unknown mission application action")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("Invalid application name")
        if action in {"add", "remove"}:
            return self._change_membership("CFE_APP", action, name, expected_hash)
        snapshot = self.snapshot()
        self.assert_revision(expected_hash)
        included = name in snapshot["included"]
        if action == "add" and included:
            raise ValueError("Application is already included in the mission")
        if action != "add" and not included:
            raise ValueError("Application is not included in the mission")
        selected = [item for item in snapshot["enabled"] if item != name]
        if action in {"add", "enable"}:
            selected.append(name)
        result = self.set_enabled_apps(selected, expected_hash)
        return {"mission": result, "changed": [self.STARTUP] if result["source"]["hash"] != expected_hash else [],
                "deleted": []}

    def change_library(self, action, name, expected_hash):
        if action not in {"add", "remove", "delete"}:
            raise ValueError("Unknown mission library action")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("Invalid library name")
        return self._change_membership("CFE_LIB", action, name, expected_hash)

    def set_enabled_apps(self, names, expected_hash):
        if not isinstance(names, list) or not all(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_]+", name) for name in names):
            raise ValueError("Expected a list of application names")
        if len(names) != len(set(names)):
            raise ValueError("Application selection contains duplicates")
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ValueError("Reload the mission configuration before saving")
        with self.lock, self._write_lock():
            revision, evaluated, active, archived, defaults = self._read()
            if expected_hash != revision:
                raise ValueError("Mission configuration changed. Reload it before saving.")
            compiled = set(evaluated["compiled"])
            recipes = {entry.name: entry for entry in defaults + archived + active if entry.kind == "CFE_APP"}
            selected = set(names)
            unavailable = selected - recipes.keys() | (selected - compiled)
            if unavailable:
                raise ValueError("No built startup entry for: " + ", ".join(sorted(unavailable)))
            # Never remove/reorder libraries. Only app startup membership changes.
            retained = [entry for entry in active if entry.kind == "CFE_LIB" or entry.name in selected]
            retained_names = {entry.name for entry in retained}
            for entry in defaults + archived:
                if entry.kind == "CFE_APP" and entry.name in selected and entry.name not in retained_names:
                    retained.append(recipes[entry.name])
                    retained_names.add(entry.name)
            library_recipes = {entry.name: entry for entry in defaults + archived if entry.kind == "CFE_LIB"}
            new_libraries = []
            for name in selected - {entry.name for entry in active if entry.kind == "CFE_APP"}:
                for dependency in self._dependency_order(name):
                    if dependency != name and dependency not in retained_names:
                        if dependency not in compiled or dependency not in library_recipes:
                            raise ValueError("Required library is not included: " + dependency)
                        new_libraries.append(library_recipes[dependency])
                        retained_names.add(dependency)
            retained = new_libraries + retained
            disabled = {entry.name: entry for entry in archived if entry.name not in retained_names}
            disabled.update({entry.name: entry for entry in active if entry.kind == "CFE_APP" and entry.name not in selected})
            content = render_startup(retained, [disabled[name] for name in sorted(disabled)])
            self._write_startup(content, revision)
            return self.snapshot()
