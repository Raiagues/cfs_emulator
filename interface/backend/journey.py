"""Project and flight evidence for the nine first-flight milestones."""
from pathlib import Path
import re

from hardware.infrastructure import target_verified
from interface.backend.first_boot import boot_observed
from project.appgen.source_tags import regions
from project.model import identifier, load_config


def mission_evidence(root, apps):
    created, commands = {}, {}
    for app in apps:
        name = identifier(app["name"])
        directory = root / "mission/apps" / name
        registration = directory / "CMakeLists.txt"
        if not registration.is_file():
            continue
        created[name] = registration.stat().st_mtime
        header = directory / "fsw/inc" / (name + "_fcncodes.h")
        if header.is_file():
            try:
                region = regions(header.read_text(), header).get("command.codes")
            except ValueError:
                continue  # An unfinished source edit is not an indexed command.
            if region:
                symbols = re.findall(r"^\s*#\s*define\s+(" + re.escape(name.upper()) +
                                     r"_\w+_CC)\s+\S+", region.body, re.M)
                for symbol in symbols:
                    commands[(name, symbol)] = header.stat().st_mtime
    return created, commands


def derive(target, verified, operational, apps, commands, linked, ground, jobs, passed_tests=(), signal_history=None):
    facts = dict(target=verified, boot=operational.get(target), event=None, app=max(apps.values(), default=None),
                 command=max(commands.values(), default=None), send=None, sensor=None, test=None,
                 board=operational.get("physical"))
    if ground.get("target") == target:
        coach = ground.get("first_flight") or {}
        if ground.get("connected") and coach.get("event"):
            facts["event"] = coach.get("event_at")
        passed = [r["finished_at"] for r in ground.get("runs", []) if r.get("status") == "passed"
                  and (r.get("sent", {}).get("app"), r.get("command")) in commands and r.get("finished_at")]
        facts["send"] = max(passed, default=None)
    for receipt in passed_tests:
        if (receipt.get("target") == target and (receipt.get("app"), receipt.get("command")) in commands
                and receipt.get("observations") and receipt.get("finished_at")):
            facts["send"] = max(facts["send"] or 0, receipt["finished_at"])
    history = signal_history or {}
    facts["sensor"] = max((when for device, when in history.get("devices", {}).items() if device in linked), default=None)
    facts["test"] = history.get("tested")
    for job in jobs:
        if job.get("action") == "simulate":
            samples = job.get("samples") or {}
            if any(d.get("id") in linked for d in samples.get("devices", [])):
                facts["sensor"] = max(facts["sensor"] or 0, samples.get("received_at", 0))
        if job.get("action") == "simulate-preview" and job.get("status") == "succeeded" and job.get("scenario_result"):
            facts["test"] = max(facts["test"] or 0, job.get("ended") or 0)
    return {"target": target, "steps": {step: {"done": bool(when), "observed_at": when}
                                        for step, when in facts.items()}}


def record_signal(hardware, job):
    """Under the job lock, write each confirmed QMP device once per sending session."""
    action = job["action"]
    if action == "simulate":
        samples = job.get("samples") or {}
        observed = sorted(d["id"] for d in samples.get("devices", []) if d.get("id"))
        if not observed or job.get("confirmed_devices") == observed:
            return
        history = hardware._load("signal-observations.json", {})
        history.setdefault("devices", {}).update(dict.fromkeys(observed, samples["received_at"]))
        job["confirmed_devices"] = observed
    elif action == "simulate-preview" and job.get("status") == "succeeded" and job.get("scenario_result"):
        history = hardware._load("signal-observations.json", {})
        history["tested"] = job["ended"]
    else:
        return
    hardware._save("signal-observations.json", history)


def snapshot(studio, target=None):
    hardware = studio.hardware
    target = target or hardware.default_target()
    if target not in {"native", "qemu", "physical"}:
        raise ValueError("Unknown execution target")
    root = Path(studio.workspace.root)
    config = load_config(root)
    apps, commands = mission_evidence(root, config["apps"])
    linked = {device for app in config["apps"] for device in app.get("sensors", {}).values()}
    operational = {mode: hardware._load("operational-" + mode + ".json", {}).get("time")
                   for mode in {target, "physical"} if boot_observed(hardware, mode)}
    receipt = root / "hardware/.runtime" / ("checks-" + target + ".json")
    verified = receipt.stat().st_mtime if receipt.is_file() and target_verified(hardware, target) else None
    return derive(target, verified, operational, apps, commands, linked,
                  studio.ground_snapshot(), (), studio.ground.passed_tests(target),
                  hardware._load("signal-observations.json", {}))
