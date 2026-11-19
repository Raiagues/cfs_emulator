"""First flight runs the normal build/deploy pipeline and interprets its own flight log."""
import platform
import re
import time

from hardware import infrastructure
from project.appgen.native_startup import parse_startup
from project.model import load_config

STATES = ("EARLY_INIT", "CORE_STARTUP", "CORE_READY", "APPS_INIT", "OPERATIONAL")
SERVICES = ("ES", "EVS", "SB", "TBL", "TIME", "FS")
ES = re.compile(r"(?:^|\bCFE_ES_Main:\s*)CFE_ES_Main (?:in|entering) (" + "|".join(STATES) + r") state\b")
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


def _record(job, line="", **change):
    """Only record transitions. Repeated compiler and EVS output stays in the console."""
    now = time.time()
    elapsed = round(1000 * max(0, now - job.get("started", now)))
    trace = job.setdefault("boot_trace", [])
    if trace and trace[-1].get("fact", {}).get("state") == "OPERATIONAL":
        return
    trace.append({"ms": max(elapsed, trace[-1]["ms"] if trace else 0), "line": line, **change})


def observe(hardware, job, line):
    """Called under the job lock. Preserve observations as console scrollback rolls over."""
    if job["action"] not in {"first-boot", "run"}:
        return
    if job.get("phase") == "build":
        match = PERCENT.search(line)
        activity = None
        if line.startswith(("-- Configuring", "-- Generating", "-- The C compiler identification")):
            activity = "Configuring"
        elif line.startswith(("-- Installing:", "-- Up-to-date:", "Install the project")):
            activity = "Installing"
        elif match and job.get("build_activity") != "Installing":
            activity = "Compiling"
        update = {}
        if activity and activity != job.get("build_activity"):
            job["build_activity"] = update["activity"] = activity
        if match and min(100, int(match[1])) > job.get("build_percent", -1):
            job["build_percent"] = update["percent"] = min(100, int(match[1]))
        trace = job.get("boot_trace", [])
        if update or (line.strip() and (not trace or len(trace) == 1 and not trace[0]["line"])):
            _record(job, line, **update)
        return
    if job["action"] == "first-boot" and job.get("phase") not in ("copy", "run"):
        return
    if line == "[deploy] Release uploaded":
        job["phase"] = "run"
        _record(job, line, phase="run")
        return
    fact = parse_boot_line(line)
    if not fact:
        return
    # Journal output is scoped to the new systemd invocation by HardwareManager.
    facts = job.setdefault("flight", {"states": [], "initialized": {}, "process_started": False})
    changed = not facts["process_started"]
    facts["process_started"] = True
    if "app" in fact:
        changed |= fact["app"] not in facts["initialized"]
        facts["initialized"].setdefault(fact["app"], fact)
    new_state = "state" in fact and fact["state"] not in facts["states"]
    if new_state:
        facts["states"].append(fact["state"])
    if changed or new_state:
        _record(job, line, fact=fact)
    if new_state and fact["state"] == "OPERATIONAL":
        hardware._save("operational-" + job["target"] + ".json",
                       {"run_id": job["id"], "time": time.time(), "target": job["target"],
                        "started": job.get("started"), "boot_trace": job["boot_trace"],
                        "connection": job.get("connection"), "instance": job.get("instance"),
                        "apps": job.get("boot_apps"), "flight": facts})


def _app_records(startup):
    active, _ = parse_startup(startup)
    return [{"name": entry.name, "task": entry.fields[3]} for entry in active if entry.kind == "CFE_APP"]


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
    connection = hardware._load("connection.json") if target == "physical" else None
    jobs = [j for j in studio.jobs_snapshot(boot_trace=True)
            if j["target"] == target and j["action"] in {"first-boot", "run"}
            and (target != "physical" or hardware.same_board(j.get("connection"), connection))]
    job = jobs[-1] if jobs else {}
    config_data = load_config(hardware.root)
    profile = next((p for p in hardware.profiles() if target in p["targets"]
                    and (p["board"], p["os"]) == (config_data.get("board"), config_data.get("os"))), {})
    receipt = hardware._load("operational-" + target + ".json", {})
    # A stopped or superseded deployment is still journey history, never a live completion.
    deployed = hardware._load("deployed.json", {}).get(target, {})
    stopped_at = deployed.get("stopped_at") or 0
    stopped = stopped_at > (job.get("started") or receipt.get("time") or 0)
    matching_receipt = bool(receipt.get("time") and receipt["time"] >= deployed.get("deployed_at", 0)
                        and boot_observed(hardware, target))
    flight = job.get("flight", {}) if job else receipt.get("flight", {}) if matching_receipt else {}
    live = "OPERATIONAL" in flight.get("states", []) and not stopped
    unknown = False
    if live:
        if target == "native":
            current = hardware._local_flight_state()
            live = deployed.get("pid") in current["pids"]
            unknown = not live and current.get("running", False) is None
        else:
            instance = (job or receipt).get("instance")
            current = hardware.observed_flight(target, connection)
            # A journal receipt may outlive SSH, the service, or an entire guest.
            service_active = current["service"] == "active"
            unknown = (current["service"] not in {"active", "inactive", "failed"} or
                       service_active and not (instance and current.get("instance")))
            live = bool(instance and service_active and current.get("instance") == instance)
        stopped = not live and not unknown
    apps = job.get("boot_apps") if job else receipt.get("apps")
    if apps is None:
        # Before the first checkout there is no mission script to evaluate.
        has_source = (hardware.root / "cFS/sample_defs/targets.cmake").is_file()
        apps = _app_records(studio.workspace.mission.startup_text()) if has_source else []
    lines = job.get("lines", [])
    return {"target": target, "verified": infrastructure.target_verified(hardware, target),
            "hardware": "This computer" if target == "native" else profile.get("board_label", "Board"),
            "architecture": platform.machine() if target == "native" else profile.get("board", ""),
            "os": platform.system() if target == "native" else profile.get("os_label", "Linux"),
            "apps": apps,
            "services": [name for name in SERVICES if (hardware.root / "cFS/cfe/modules" / name.lower()).is_dir()], "es_states": STATES, "flight": flight, "stopped": stopped,
            "running": live, "unverified": bool(unknown),
            "job": {k: job[k] for k in ("id", "status", "action", "phase", "build_percent", "build_activity", "error", "started") if k in job},
            "trace": (job or (receipt if matching_receipt else {})).get("boot_trace", []),
            "lines": lines[-300:]}


def execute(studio, record, options, emit):
    """One exclusive operation survives browser navigation. Use the same builders and deployers as the toolbar."""
    hardware, target, cancel = studio.hardware, record["target"], record["cancel"]
    if not infrastructure.target_verified(hardware, target):
        raise ValueError("Complete the target checks")
    def phase(name):
        with studio.lock:
            record["phase"] = name
            _record(record, phase=name)
    hardware.assert_can_start(target, record.get("connection"))
    studio.ground.stop()
    phase("build")
    build = hardware.execute("build", emit, cancel=cancel, **options)
    if cancel.is_set():
        raise ValueError("Build cancelled")
    emit("Preparing the communication catalog for this build...")
    sensorless = bool(options.get("sensorless"))
    studio.freeze_catalog(build, sensorless)
    build_root = hardware.runtime / "sensorless" if sensorless else hardware.root
    installed = build_root / hardware.build_directory(target) / "exe/cpu1/cf/cfe_es_startup.scr"
    with studio.lock:
        record["boot_apps"] = _app_records(installed.read_text())
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
