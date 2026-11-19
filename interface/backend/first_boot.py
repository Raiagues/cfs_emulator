"""First flight runs the normal build/deploy pipeline and interprets its own flight log."""
import platform
import re
import time

from hardware import infrastructure
from project.appgen.native_startup import parse_startup
from project.model import load_config

STATES = ("EARLY_INIT", "CORE_STARTUP", "CORE_READY", "APPS_INIT", "OPERATIONAL")
SERVICES = ("ES", "EVS", "SB", "TBL", "TIME", "FS")
ES = re.compile(r"\bCFE_ES_Main:\s*CFE_ES_Main (?:in|entering) (" + "|".join(STATES) + r") state\b")
EVENT = re.compile(r"\bEVS Port\d+\s+\S+\s+(\d+)/(\d+)/([A-Za-z_]\w*)\s+(\d+):\s*(.*)")
INITIALIZED = re.compile(r"\b(?:initialized|initialization complete)\b", re.I)
PERCENT = re.compile(r"\[\s*(\d{1,3})%\]")


def parse_boot_line(line):
    match = ES.search(line)
    if match:
        return {"state": match[1]}
    match = EVENT.search(line)
    if match and INITIALIZED.search(match[5]) and not re.search(r"\b(?:not|failed|error)\b", match[5], re.I):
        return {"spacecraft": int(match[1]), "processor": int(match[2]), "app": match[3], "eid": int(match[4])}
    if line.startswith(("OS_BSP_Initialize(", "CFE_PSP:")):
        return {"process_started": True}
    return None


def observe(hardware, job, line):
    """Called under the job lock. Preserve observations as console scrollback rolls over."""
    if job["action"] not in {"first-boot", "run"}:
        return
    if job.get("phase") == "build":
        match = PERCENT.search(line)
        if match:
            job["build_percent"] = min(100, max(job.get("build_percent", 0), int(match[1])))
        return
    if job["action"] == "first-boot" and job.get("phase") not in ("copy", "run"):
        return
    if line == "[deploy] Release uploaded":
        job["phase"] = "run"
        return
    fact = parse_boot_line(line)
    if not fact:
        return
    # Journal output is scoped to the new systemd invocation by HardwareManager.
    facts = job.setdefault("flight", {"states": [], "initialized": {}, "process_started": False})
    facts["process_started"] = True
    if "app" in fact:
        facts["initialized"].setdefault(fact["app"], fact)
    if "state" in fact and fact["state"] not in facts["states"]:
        facts["states"].append(fact["state"])
        if fact["state"] == "OPERATIONAL":
            hardware._save("operational-" + job["target"] + ".json",
                           {"run_id": job["id"], "time": time.time(), "target": job["target"],
                            "connection": job.get("connection"), "flight": facts})


def boot_observed(hardware, target):
    if target not in {"native", "physical", "qemu"}:
        return False
    receipt = hardware._load("operational-" + target + ".json", {})
    return "OPERATIONAL" in receipt.get("flight", {}).get("states", []) and (
        target != "physical" or hardware.same_board(receipt.get("connection"), hardware._load("connection.json")))


def snapshot(studio, target):
    hardware = studio.hardware
    if target not in {"native", "physical", "qemu"}:
        raise ValueError("Invalid boot target")
    jobs = [j for j in studio.jobs_snapshot() if j["target"] == target and j["action"] in {"first-boot", "run"}]
    job = jobs[-1] if jobs else {}
    config = studio.workspace.mission
    startup_entries, _ = parse_startup(config.startup_text())
    config_data = load_config(hardware.root)
    profile = next((p for p in hardware.profiles() if target in p["targets"]
                    and (p["board"], p["os"]) == (config_data.get("board"), config_data.get("os"))), {})
    receipt = hardware._load("operational-" + target + ".json", {})
    # A stopped or superseded deployment is still journey history, never a live completion.
    deployed = hardware._load("deployed.json", {}).get(target, {})
    stopped_at = deployed.get("stopped_at") or 0
    stopped = stopped_at > (job.get("started") or receipt.get("time") or 0)
    live_receipt = bool(receipt.get("time") and receipt["time"] >= deployed.get("deployed_at", 0)
                        and not stopped and boot_observed(hardware, target))
    flight = job.get("flight", {}) if job else receipt.get("flight", {}) if live_receipt else {}
    live = "OPERATIONAL" in flight.get("states", []) and not stopped
    if live and target == "native":
        local_state = hardware._local_flight_state()
        live = deployed.get("pid") in local_state["pids"]
        stopped = not live
    lines = job.get("lines", [])
    return {"target": target, "verified": infrastructure.target_verified(hardware, target),
            "hardware": "This computer" if target == "native" else profile.get("board_label", "Board"),
            "architecture": platform.machine() if target == "native" else profile.get("board", ""),
            "os": platform.system() if target == "native" else profile.get("os_label", "Linux"),
            "apps": [{"name": a.name, "task": a.fields[3]} for a in startup_entries if a.kind == "CFE_APP"],
            "services": [name for name in SERVICES if (hardware.root / "cFS/cfe/modules" / name.lower()).is_dir()], "es_states": STATES, "flight": flight, "stopped": stopped,
            "running": live,
            "job": {k: job[k] for k in ("id", "status", "action", "phase", "build_percent", "error", "started") if k in job},
            "lines": lines[-300:]}


def execute(studio, record, options, emit):
    """One exclusive operation survives browser navigation. Use the same builders and deployers as the toolbar."""
    hardware, target, cancel = studio.hardware, record["target"], record["cancel"]
    if not infrastructure.target_verified(hardware, target):
        raise ValueError("Complete the target checks")
    def phase(name):
        with studio.lock:
            record["phase"] = name
    hardware.assert_can_start(target, record.get("connection"))
    studio.ground.stop()
    phase("build")
    build = hardware.execute("build", emit, cancel=cancel, **options)
    if cancel.is_set():
        raise ValueError("Build cancelled")
    emit("Preparing the communication catalog for this build...")
    studio.freeze_catalog(build)
    if target == "qemu":
        phase("boot")
        if not hardware._qemu_running():
            hardware.execute("boot", emit, cancel=cancel, **options)
        else:
            hardware._stream(hardware.ssh_argv() + ["true"], emit, cancel, timeout=20)
    phase("copy" if target == "physical" else "run")
    def replace_readers():
        studio._cancel_readers(target, record["connection"], kind="flight", elsewhere=True)
    return hardware.execute("run", emit, cancel=cancel, on_start=replace_readers, **options)
