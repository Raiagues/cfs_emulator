"""Local source workspace. The existing project CLI remains the app generator."""

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading


class Workspace:
    """Filesystem operations and cFS metadata, serialized against source mutations."""

    HIDDEN = {".git", ".ssh", ".aws", ".agents", ".codex", "__pycache__", "node_modules", ".state", ".runtime"}
    EDIT_ROOTS = {"cFS", "project", "sensors", "ground_station", "hardware", "interface"}
    MAX_TEXT = 2 * 1024 * 1024

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(self.root))
        from project import model
        from interface.backend.source_index import SourceIndex
        from interface.backend.mission_config import MissionConfig
        self.model = model
        self.source_index = SourceIndex(self.root)
        self.mission = MissionConfig(self.root)

    def path(self, relative=""):
        if not isinstance(relative, str) or "\x00" in relative:
            raise ValueError("Invalid path")
        parts = Path(relative).parts
        if Path(relative).is_absolute() or ".." in parts or any(
                part in self.HIDDEN or part == ".env" or part.startswith(".env.") or
                part.endswith((".pem", ".key")) for part in parts):
            raise ValueError("Path is private or outside the project")
        return self.model.safe_path(self.root, relative)

    def editable(self, relative):
        parts = Path(relative).parts
        return bool(parts and parts[0] in self.EDIT_ROOTS and
                    not any(part.startswith("build") or part in (".venv", "dist") for part in parts))

    def tree(self, path=""):
        directory = self.path(path)
        if not directory.is_dir():
            raise ValueError("Expected a directory")
        entries = []
        for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            relative = item.relative_to(self.root).as_posix()
            try:
                self.path(relative)
            except ValueError:
                continue
            entries.append({"name": item.name, "path": relative,
                            "type": "directory" if item.is_dir() else "file",
                            "size": item.stat().st_size if item.is_file() else None,
                            "editable": self.editable(relative)})
        return {"path": path, "entries": entries}

    def read_file(self, path):
        target = self.path(path)
        if not target.is_file():
            if path == self.mission.STARTUP:
                content = self.mission.startup_text()
                data = content.encode()
                return {"path": path, "content": content, "hash": hashlib.sha256(data).hexdigest(),
                        "size": len(data), "editable": True, "binary": False, "virtual": True}
            raise ValueError("File not found")
        if target.stat().st_size > self.MAX_TEXT:
            return {"path": path, "content": None, "binary": True, "editable": False,
                    "size": target.stat().st_size, "reason": "File exceeds 2 MiB"}
        data = target.read_bytes()
        result = {"path": path, "hash": hashlib.sha256(data).hexdigest(), "size": len(data)}
        try:
            content = data.decode("utf-8")
            if "\x00" in content:
                raise UnicodeError()
        except UnicodeError:
            return dict(result, content=None, binary=True, editable=False)
        return dict(result, content=content, binary=False, editable=self.editable(path))

    def search_files(self, root, query):
        if root not in ('cFS', 'sensors') or not isinstance(query, str) or len(query) > 200:
            raise ValueError('Invalid file search')
        query = query.strip().lower()
        results = []
        if not query:
            return {'files': results, 'limited': False}
        for directory, dirs, files in os.walk(self.path(root), followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in self.HIDDEN and not d.startswith(('build', '.venv')))
            for name in sorted(files):
                relative = (Path(directory) / name).relative_to(self.root).as_posix()
                if query not in relative.lower():
                    continue
                try:
                    self.path(relative)
                except ValueError:
                    continue
                results.append(relative)
                if len(results) == 100:
                    return {'files': results, 'limited': True}
        return {'files': results, 'limited': False}

    def write_file(self, path, content, expected_hash=None):
        if not isinstance(content, str) or len(content.encode()) > self.MAX_TEXT:
            raise ValueError("Invalid content or content exceeds 2 MiB")
        with self.lock:
            target = self.path(path)
            current = self.read_file(path)
            if not current["editable"]:
                raise ValueError("File is not editable")
            if not expected_hash or expected_hash != current["hash"]:
                raise ValueError("File changed on disk; reopen it before saving")
            if current.get('virtual') or path == self.mission.STARTUP:
                from project.cfs_config import bootstrap_plan
                from project.manage import commit
                plan = bootstrap_plan(self.root)
                plan[path] = content
                commit(self.root, plan)
            else:
                self._atomic_write(target, content.encode())
            return self.read_file(path)

    @staticmethod
    def _atomic_write(path, data):
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".studio-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        try:
            temporary.chmod(mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def snapshot(self):
        from sensors.simulator import simulation_scripts, binding
        from interface.backend.architecture import summarize_application
        from interface.backend.library_index import inspect_libraries, hardware_changes
        with self.lock:
            config = self.model.load_config(self.root)
            generator = self.model.appgen(self.root)
            manifests = self.model.read_manifests(self.root, config)
            self.model.validate_config(self.root, config, manifests)
            catalog = copy.deepcopy(self.model.board_catalog(config["board"], self.root))
            for model, details in catalog["models"].items():
                existing = next((d for d in config["devices"] if d["model"] == model), None)
                details["default_address"] = existing["address"] if existing else details.get("default_address")
                details["can_add"] = details["default_address"] is not None
            registered = {manifest["name"]: manifest for manifest in manifests}
            apps = []
            mission = self.mission.snapshot()
            enabled = set(mission["enabled"])
            installed = set(mission["installed_enabled"])
            recipes = {app["name"]: app for app in mission["available"]}
            for directory in sorted((self.root / "cFS/apps").iterdir()):
                if not directory.is_dir() or directory.is_symlink():
                    continue
                name = directory.name
                manifest = registered.get(name)
                paths = sorted(directory.glob("fsw/src/*_user.c")) or sorted(directory.glob("fsw/src/*app.c"))
                entry = paths[0] if paths else directory / "CMakeLists.txt"
                app = {"name": name, "path": directory.relative_to(self.root).as_posix(),
                       "entry": entry.relative_to(self.root).as_posix(), "managed": bool(manifest),
                       "built": name in installed, "enabled": name in enabled,
                       "manifest": manifest, "locations": []}
                if manifest:
                    locations = generator.locations(self.root / "cFS", manifest)["locations"]
                    app["locations"] = [dict(location, path="cFS/" + location["path"]) for location in locations]
                app.update(self.source_index.application(directory, app["locations"]))
                app["behavior"] = summarize_application(app, recipes.get(name, {}).get("entry_point"), root=self.root)
                apps.append(app)
            libraries = inspect_libraries(self.root, apps, self.source_index, mission)
            return {"name": self.root.name, "core_modules": [{"name": p.name, "path": p.relative_to(self.root).as_posix(), "type": "directory"} for p in sorted((self.root / "cFS/cfe/modules").glob("*")) if (p / "CMakeLists.txt").is_file() and (p / "fsw/src").is_dir()], "project": config, "catalog": catalog, "apps": apps,
                    "mission": mission, "libraries": libraries, "changes": hardware_changes(self.root, config),
                    "simulation": {"root": "sensors", "scripts": simulation_scripts(self.root),
                                   "bindings": {device["id"]: binding(device) for device in config["devices"]}}}

    def mission_app(self, action, name, expected_hash):
        with self.lock:
            return self.mission.change_app(action, name, expected_hash)

    def mission_library(self, action, name, expected_hash):
        with self.lock:
            return self.mission.change_library(action, name, expected_hash)

    def delete_app(self, name, expected_hash):
        with self.lock, self.mission.transaction(expected_hash):
            self.mission.assert_can_remove(name)
            result = self._remove('remove-app', {'app': name}, self.model.load_config(self.root))
            return {**result, 'mission': self.mission.snapshot()}

    def simulation_snapshot(self):
        from sensors.session import load_session
        with self.lock:
            return load_session(self.root)

    def save_simulation(self, settings, expected_hash):
        from sensors.session import load_session, planned_settings
        from project.manage import commit
        with self.lock:
            if expected_hash != load_session(self.root)['hash']:
                raise ValueError('Sensor code or settings changed. Reload before saving widgets.')
            changed = commit(self.root, planned_settings(self.root, settings))
            return {**self.simulation_snapshot(), 'changed': changed}

    def _mission_draft_plan(self, kind, name, settings, expected_hash, mode="create"):
        """Build a deterministic preview entirely in memory."""
        from project.appgen.native_startup import parse_startup, render_startup
        if kind not in ("app", "library") or mode not in ("create", "edit"):
            raise ValueError("Choose an app or library creation mode")
        if not isinstance(settings, dict):
            raise ValueError("Invalid draft settings")
        name = self.model.identifier(name)
        revision = self.mission.assert_revision(expected_hash)
        inputs = {"project/config.json": self.path("project/config.json").read_bytes()}
        config = copy.deepcopy(self.model.load_config(self.root))
        self.model.validate_config(self.root, config)
        for item in config["apps"]:
            path = f"project/apps/{item['name']}.json"
            inputs[path] = self.path(path).read_bytes()
        generator = self.model.appgen(self.root)
        manifests = self.model.read_manifests(self.root, config)
        target = next((item for item in manifests if item["name"] == name), None)
        if mode == "create":
            if name in self.model.protected_apps(self.root) or name in self.mission._evaluate(revision)["compiled"]:
                raise ValueError("A mission module already uses this name: " + name)
            if any(self.path(f"cFS/{directory}/{name}").exists() for directory in ("apps", "libs")):
                raise ValueError("A source directory already uses this name: " + name)
        elif kind != "app" or target is None:
            raise ValueError("Edit this module's native source files to change its configuration")
        native = self.mission.STARTUP
        original = self.mission.startup_text()
        active, archived = parse_startup(original)
        native_entry = next((item for item in active + archived if item.name == name), None)
        schedule = None
        blocks = []
        if kind == "app":
            if set(settings) - {"priority", "stack_size", "wakeup_hz", "hk_hz"}:
                raise ValueError("Unknown application draft setting")
            if mode == "create":
                target = generator.new_app(name, manifests)
                manifests.append(target)
                config["apps"].append({"name": name, "sensors": {}, "telemetry_bindings": {}, "command_bindings": {}})
            elif native_entry:
                target["priority"], target["stack_size"] = int(native_entry.fields[4], 0), int(native_entry.fields[5], 0)
            scheduler = self.mission.schedule_config()
            tick_hz = scheduler["tick_hz"]
            if not tick_hz:
                raise ValueError("The scheduler TickRate must be a numeric value before configuring application frequencies")
            schedule_path = self.path(scheduler["generated_path"])
            if mode == "edit" and schedule_path.is_file():
                source_schedule = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', '', schedule_path.read_text())
                for suffix, field in (("WAKEUP_MID", "period_ticks"), ("SEND_HK_MID", "hk_period_ticks")):
                    match = re.search(r'\bCFE_SB_MSGID_WRAP_VALUE\(\s*' + re.escape(name.upper() + "_" + suffix) +
                                      r'\s*\)\s*,\s*(\d+)\s*,', source_schedule)
                    if match and int(match[1]) > 0:
                        target[field] = int(match[1])
            normalized = {"priority": target["priority"], "stack_size": target["stack_size"],
                          "wakeup_hz": tick_hz / target["period_ticks"],
                          "hk_hz": tick_hz / target["hk_period_ticks"]}
            normalized.update(settings)
            for key, field in (("wakeup_hz", "period_ticks"), ("hk_hz", "hk_period_ticks")):
                value = normalized[key]
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("Frequency must be a positive finite number")
                ticks = tick_hz / value
                if ticks > 65535 or ticks < 1 or abs(ticks - round(ticks)) > 0.000001:
                    raise ValueError(f"{key} must correspond to a whole number of scheduler ticks ({tick_hz} Hz)")
                target[field] = int(round(ticks))
                normalized[key] = tick_hz / target[field]
            target["priority"], target["stack_size"] = normalized["priority"], normalized["stack_size"]
            self.model.validate_config(self.root, config, manifests, [name] if mode == "create" else [])
            self.model.mapped_manifests(config, manifests, self.root)
            plan = self.model.planned_project_files(self.root, config, manifests)
            if mode == "create":
                plan["project/config.json"] = json.dumps(config, indent=2) + "\n"
            fragment = "cFS/sample_defs/generated/appgen_startup.scr"
            previous = self.path(fragment).read_text() if self.path(fragment).exists() else ""
            content = self.mission.reconcile_generated_modules(previous, plan[fragment], original)
            active, archived = parse_startup(content)
            recipes, _ = parse_startup(plan[fragment])
            entry = next((item for item in recipes if item.kind == "CFE_APP" and item.name == name), native_entry)
            if native_entry and mode == "edit":
                fields = list(native_entry.fields)
                fields[4:6] = [str(target["priority"]), str(target["stack_size"])]
                entry = parse_startup(", ".join(fields) + ";")[0][0]
            if mode == "create":
                active.append(entry)
            else:
                active = [entry if item.name == name else item for item in active]
                archived = [entry if item.name == name else item for item in archived]
            path = f"cFS/apps/{name}"
            source = path + f"/fsw/src/{name}_user.c"
            prefix = name.upper()
            blocks = [{"id": "initialize", "title": "Initialize", "symbol": prefix + "_UserInit"},
                      {"id": "wakeup", "title": "Wakeup", "symbol": prefix + "_UserWakeup", "frequency_hz": normalized["wakeup_hz"]},
                      {"id": "housekeeping", "title": "Housekeeping", "symbol": prefix + "_SendHkCmd", "frequency_hz": normalized["hk_hz"]},
                      {"id": "commands", "title": "Commands", "symbol": prefix + "_ProcessGroundCommand"}]
            schedule = {"path": fragment.replace("appgen_startup.scr", "appgen_schedule.inc"),
                        "tick_hz": tick_hz, "wakeup_ticks": target["period_ticks"], "hk_ticks": target["hk_period_ticks"],
                        "scheduler_enabled": any(item.name == "sch_lab" for item in active)}
            build = {"path": "cFS/sample_defs/targets.cmake", "module": name,
                     "statement": "list(APPEND cpu1_APPLIST ${APPGEN_LIBS} ${APPGEN_APPS})"}
        else:
            if settings:
                raise ValueError("Libraries do not have application scheduler settings")
            generated = generator.plan_library(self.root / "cFS", name)
            from project.cfs_config import bootstrap_plan
            plan = bootstrap_plan(self.root, config)
            plan.update({"cFS/" + path: content for path, content in generated["files"].items()})
            entry = parse_startup(", ".join(str(value) for value in generated["startup"]["fields"]) + ";")[0][0]
            first_app = next((index for index, item in enumerate(active) if item.kind == "CFE_APP"), len(active))
            active.insert(first_app, entry)
            cmake = "cFS/sample_defs/libraries.cmake"
            previous = self.path(cmake).read_text() if self.path(cmake).exists() else "set(MISSION_LIBRARIES)\n"
            plan[cmake] = previous.rstrip() + f"\nlist(APPEND MISSION_LIBRARIES {name})\n"
            path = f"cFS/libs/{name}"
            source = path + f"/fsw/src/{name}.c"
            normalized = {}
            blocks = [{"id": "initialize", "title": "Library initialization", "symbol": entry.fields[2]},
                      {"id": "interface", "title": "Public interface", "symbol": generated["include"]}]
            build = {"path": cmake, "statement": f"list(APPEND MISSION_LIBRARIES {name})"}
        plan[native] = render_startup(active, archived)
        parse_startup(plan[native])
        from project.cfs_config import module_limits_plan
        plan.update(module_limits_plan(self.root, plan))
        for relative in plan:
            path_on_disk = self.path(relative)
            inputs.setdefault(relative, path_on_disk.read_bytes() if path_on_disk.exists() else None)
        self.mission.assert_revision(revision)
        for relative, content in inputs.items():
            path_on_disk = self.path(relative)
            current = path_on_disk.read_bytes() if path_on_disk.exists() else None
            if current != content:
                raise ValueError("Project source changed while preparing the draft. Reload it before saving.")
        payload = {"revision": revision, "kind": kind, "mode": mode, "name": name,
                   "settings": normalized, "files": plan,
                   "inputs": {path: hashlib.sha256(value).hexdigest() if value is not None else None
                              for path, value in inputs.items()}}
        plan_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        public = {"draft": {"kind": kind, "mode": mode, "name": name, "settings": normalized},
                  "preview": {"entry_point": entry.fields[2], "blocks": blocks,
                              "startup": {"path": native, "record": entry.raw}, "build": build,
                              "schedule": schedule, "source": {"path": source, "content": plan.get(source) or self.path(source).read_text()}},
                  "plan_hash": plan_hash, "expected_hash": revision}
        return public, plan, inputs, {"name": name, "path": path, "entry": source}

    def mission_draft(self, kind, name, settings, expected_hash, mode="create"):
        with self.lock:
            return self._mission_draft_plan(kind, name, {} if settings is None else settings, expected_hash, mode)[0]

    def save_mission_draft(self, kind, name, settings, expected_hash, plan_hash, mode="create"):
        from project.manage import commit
        with self.lock, self.mission.transaction(expected_hash):
            public, plan, inputs, module = self._mission_draft_plan(kind, name, {} if settings is None else settings, expected_hash, mode)
            if not isinstance(plan_hash, str) or plan_hash != public["plan_hash"]:
                raise ValueError("The draft or source has changed. Preview the updated configuration before saving.")
            for relative, content in inputs.items():
                path = self.path(relative)
                if (path.read_bytes() if path.exists() else None) != content:
                    raise ValueError("Project source changed. Preview the draft again before saving.")
            changed = commit(self.root, plan, library_names=[name] if kind == "library" else [])
            return {"mission": self.mission.snapshot(), "changed": changed,
                    "deleted": [path for path, content in plan.items() if content is None], kind: module}

    def select_profile(self, board, os_name, expected_hash=None):
        """Persist a supported hardware profile and its native library inputs."""
        from project.manage import commit
        with self.lock, self.mission.transaction(expected_hash or self.mission._revision()) as revision:
            config_path = "project/config.json"
            previous_config = self.path(config_path).read_bytes()
            config = copy.deepcopy(self.model.load_config(self.root))
            if (board, os_name) == (config["board"], config["os"]):
                return {"mission": self.mission.snapshot(), "changed": [], "deleted": []}
            config["board"], config["os"] = board, os_name
            generator = self.model.appgen(self.root)
            before = {f"project/apps/{app['name']}.json": self.path(f"project/apps/{app['name']}.json").read_bytes()
                      for app in config["apps"]}
            manifests = self.model.read_manifests(self.root, config)
            self.model.validate_config(self.root, config, manifests)
            self.model.mapped_manifests(config, manifests, self.root)
            plan = self.model.planned_project_files(self.root, config, manifests)
            plan[config_path] = json.dumps(config, indent=2) + "\n"
            fragment = "cFS/sample_defs/generated/appgen_startup.scr"
            plan[self.mission.STARTUP] = self.mission.reconcile_generated_modules(
                self.path(fragment).read_text() if self.path(fragment).exists() else "", plan[fragment],
                plan.get(self.mission.STARTUP, self.mission.startup_text()))
            if self.path(config_path).read_bytes() != previous_config or any(
                    self.path(path).read_bytes() != content for path, content in before.items()):
                raise ValueError("Project configuration changed. Reload it before selecting a profile.")
            self.mission.assert_revision(revision)
            changed = commit(self.root, plan)
            return {"mission": self.mission.snapshot(), "changed": changed,
                    "deleted": [path for path, content in plan.items() if content is None]}

    def mutate(self, action, payload):
        """Run a fixed CLI operation; no shell command or caller-supplied options."""
        if not isinstance(payload, dict):
            raise ValueError("Invalid parameters")
        with self.lock:
            config = self.model.load_config(self.root)
            self.model.validate_config(self.root, config)
            if action.startswith("remove-"):
                return self._remove(action, payload, config)
            args = [action]
            if action == "add-app":
                args.append(self.model.identifier(payload.get("name", "")))
            elif action == "add-device":
                model = payload.get("model")
                catalog = self.snapshot()["catalog"]
                details = catalog["models"].get(model)
                if not details or not details["can_add"]:
                    raise ValueError("This model has no default address validated by the platform")
                name = payload.get("id") or model
                self.model.identifier(name)
                bus = payload.get("bus") or next(iter(catalog["buses"]))
                address = payload.get("address", details["default_address"])
                if isinstance(address, str):
                    address = int(address, 16 if address.lower().startswith('0x') else 10)
                if any(d["id"] == name for d in config["devices"]):
                    raise ValueError("Choose a unique sensor ID")
                if any(d["bus"] == bus and d["address"] == address for d in config["devices"]):
                    raise ValueError("This bus/address is already occupied")
                args += [model, "--id", name, "--model", model, "--bus", bus, "--address", str(address)]
                for prop, value in details.get("default_values", {}).items():
                    args += ["--value", f"{prop}={value}"]
            elif action in ("add-sensor", "add-command", "add-telemetry"):
                args += [self.model.identifier(payload.get("app", "")), self.model.identifier(payload.get("name", ""))]
                if action == "add-sensor":
                    args += ["--device", self.model.identifier(payload.get("device", ""))]
                if action == "add-telemetry" and payload.get("sensor"):
                    args += ["--sensor", self.model.identifier(payload["sensor"])]
            else:
                raise ValueError("Unknown operation")
            result = subprocess.run(["bash", str(self.root / "scripts/project.sh"), *args],
                                    cwd=self.root, text=True, capture_output=True, timeout=60)
            if result.returncode:
                raise ValueError(result.stderr.strip() or result.stdout.strip())
            return json.loads(result.stdout)

    def _remove(self, action, payload, config):
        """Compose appgen's planned files with the project registry in one transaction."""
        from project.manage import commit
        generator = self.model.appgen(self.root)
        manifests = self.model.read_manifests(self.root, config)
        deleted = []
        if action == "remove-device":
            device_id = self.model.identifier(payload.get("id", ""))
            if any(device_id in app["sensors"].values() for app in config["apps"]):
                raise ValueError("Remove the sensor readers from the apps first")
            if not any(d["id"] == device_id for d in config["devices"]):
                raise ValueError("Device not found")
            config["devices"] = [d for d in config["devices"] if d["id"] != device_id]
        elif action in ("remove-app", "remove-sensor", "remove-command", "remove-telemetry"):
            name = self.model.identifier(payload.get("app", payload.get("name", "")))
            registry = next((app for app in config["apps"] if app["name"] == name), None)
            if registry is None:
                raise ValueError("Only registered apps can be removed")
            manifest = generator.app_by_name(manifests, name)
            if action == "remove-app":
                self.mission.assert_can_remove(name)
                config["apps"].remove(registry)
                manifests.remove(manifest)
                deleted.append(f"project/apps/{name}.json")
                for target in self.path("cFS/apps/" + name).rglob("*"):
                    relative = target.relative_to(self.root).as_posix()
                    self.path(relative)
                    if target.is_file():
                        deleted.append(relative)
            else:
                kind = action.removeprefix("remove-")
                entity = self.model.identifier(payload.get("name", ""))
                collection = generator.KINDS[kind]
                found = next((item for item in manifest[collection] if item["name"] == entity), None)
                if not found:
                    raise ValueError("Component not found")
                if kind == "sensor" and entity in registry["telemetry_bindings"].values():
                    raise ValueError("Remove the telemetry linked to this reader first")
                manifest[collection].remove(found)
                registry[{"sensor": "sensors", "command": "command_bindings", "telemetry": "telemetry_bindings"}[kind]].pop(entity, None)
                deleted = ["cFS/" + path for path in generator.entity_files(name, kind, entity)]
        else:
            raise ValueError("Unknown operation")
        self.model.validate_config(self.root, config, manifests)
        membership = self.mission.selection()
        plan = self.model.planned_project_files(self.root, config, manifests,
                    excluded=membership['removed'] | ({name} if action == 'remove-app' else set()),
                    selected=membership['added'] - ({name} if action == 'remove-app' else set()))
        plan["project/config.json"] = json.dumps(config, indent=2) + "\n"
        if action == 'remove-app':
            plan.update(self.mission.selection_plan(forget=[name], sources=plan))
            from interface.backend.mission_tables import table_membership_plan
            plan.update(table_membership_plan(self.root, sources=plan))
        fragment = "cFS/sample_defs/generated/appgen_startup.scr"
        native = self.mission.STARTUP
        if fragment in plan and self.path(native).is_file():
            startup = self.path(native).read_text()
            if action == "remove-app":
                startup = self.mission.reconcile_removed_modules([name], startup)
            plan[native] = self.mission.reconcile_generated_modules(
                self.path(fragment).read_text() if self.path(fragment).exists() else "", plan[fragment], startup)
        plan.update({path: None for path in deleted})
        changed = commit(self.root, plan)
        if action == "remove-app":
            directory = self.path("cFS/apps/" + name)
            for child in sorted(directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if child.is_dir() and not any(child.iterdir()):
                    child.rmdir()
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
        return {"changed": changed, "deleted": [path for path, content in plan.items() if content is None]}
