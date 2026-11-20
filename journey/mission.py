"""Evidence produced by mission creation, compilation and linked sensor writes."""
import re

from journey import SHIPPED_APPS, Store
from project.appgen.source_tags import regions
from project.model import identifier, load_config


def created(root, target, name):
    if target and name not in SHIPPED_APPS and (root / "mission/apps" / identifier(name) / "CMakeLists.txt").is_file():
        Store(root).observe(target, "app", {"app": name})


def implemented(root, app):
    if app in SHIPPED_APPS:
        return
    directory = root / "mission/apps" / identifier(app)
    header = directory / "fsw/inc" / (app + "_fcncodes.h")
    if not header.is_file():
        return
    region = regions(header.read_text(), header).get("command.codes")
    if not region:
        return
    for name in re.findall(r"^\s*#\s*define\s+" + re.escape(app.upper()) + r"_(\w+)_CC\s+\S+", region.body, re.M):
        handler = directory / "fsw/src/commands" / f"{app}_{name.lower()}_cmd.c"
        if handler.is_file():
            body = re.sub(r"/\*.*?\*/|//[^\n]*", "", handler.read_text(), flags=re.S)
            if "CFE_STATUS_NOT_IMPLEMENTED" not in body and re.search(r"\breturn\b", body):
                yield f"{app.upper()}_{name}_CC"


def built(root, state):
    target = state["target"]
    store = Store(root)
    for name in {ref["app"] for ref in store.references(target, "app")}:
        installed = root / state["build_dir"] / "exe/cpu1/cf" / (name + ".so")
        if installed.is_file():
            for command in implemented(root, name):
                store.observe(target, "command", {"app": name, "command": command, "build": state["fingerprint"]},
                              state["built_at"])


def linked_devices(root, target):
    authored = {ref["app"] for ref in Store(root).references(target, "app")}
    return {device for app in load_config(root)["apps"] if app["name"] in authored
            for device in app.get("sensors", {}).values()}


def record_writes(root, target, writes):
    if writes:
        linked = linked_devices(root, target)
        for device, at in writes.items():
            if device in linked:
                Store(root).observe(target, "sensor", {"device": device}, at)


def record_signal(root, job):
    target = job["target"]
    if job["action"] == "simulate" and target == "qemu":
        sample = job.get("samples") or {}
        devices = {device["id"] for device in sample.get("devices", [])}
        fresh = devices.difference(job.get("confirmed_devices", []))
        if fresh:
            record_writes(root, target, dict.fromkeys(fresh, sample["received_at"]))
            job["confirmed_devices"] = sorted(devices)
    if job["action"] == "simulate-preview" and job.get("status") == "succeeded":
        scenario = job.get("scenario_result") or {}
        checks = scenario.get("checks")
        if checks and all(result is True for result in checks.values()) and scenario["device"] in linked_devices(root, target):
            Store(root).observe(target, "test", {"scenario": scenario["scenario"], "device": scenario["device"]}, job["ended"])
