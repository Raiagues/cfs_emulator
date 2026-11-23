"""Interpret cFS startup output and retain the first observed milestones."""
import re
import time

from project.appgen.native_startup import parse_startup

STATES = ("EARLY_INIT", "CORE_STARTUP", "CORE_READY", "APPS_INIT", "OPERATIONAL")
SERVICES = ("ES", "EVS", "SB", "TBL", "TIME", "FS")
ES = re.compile(r"(?:^|\bCFE_ES_Main:\s*)CFE_ES_Main (?:in|entering) (" + "|".join(STATES) + r") state\b")
EVENT = re.compile(r"\bEVS Port\d+\s+\S+\s+(\d+)/(\d+)/([A-Za-z_]\w*)\s+(\d+):\s*(.*)")
INITIALIZED = re.compile(r"^(?:(?P<subject>[\w ]+?)\s+)?(?:initialized|initialization complete)\b", re.I)
PERCENT = re.compile(r"\[\s*(\d{1,3})%\]")
CATALOG_ACTIVITY = "Preparing the communication catalog for this build..."
# The guest writes terminal instructions (colour, cursor positioning, OSC) to its serial port.
TERMINAL_ESCAPE = re.compile(r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\|$)|\[[0-?]*[ -/]*[@-~]|.)")
CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def console_text(line):
    return CONTROLS.sub("", TERMINAL_ESCAPE.sub("", line.replace("␛", "\x1b").replace("␇", "\x07")))


def guest_milestone(line):
    """Ordered milestones from the emulator driver and the guest's own serial log."""
    if line == "[emulator] Linux SSH ready.":
        return 6
    if " login:" in line or ("Started" in line and "OpenBSD Secure Shell server" in line):
        return 5
    if "Booting Linux on physical CPU" in line or "Linux version " in line or "systemd[1]:" in line:
        return 4
    for index, marker in enumerate(("Image ready.", "Disk copied.", "Disk ready."), 1):
        if line.startswith("[emulator] " + marker):
            return index
    return 0


def parse_boot_line(line):
    match = ES.search(line)
    if match:
        if match[1] == "OPERATIONAL" and "entering OPERATIONAL state" not in match[0]:
            return None
        return {"state": match[1]}
    if line.startswith("SCH Lab Initialized."):
        return {"app": "SCH_LAB"}
    match = EVENT.search(line)
    if match:
        message = INITIALIZED.match(match[5])
        if message and not re.search(r"\b(?:not|failed|errors?)\b", match[5], re.I):
            subject = re.sub(r"[\s_]", "", message["subject"] or "").casefold()
            app = match[3].replace("_", "").casefold()
            if subject in {"", "app", "application", app, app + "app"}:
                return {"spacecraft": int(match[1]), "processor": int(match[2]), "app": match[3], "eid": int(match[4])}
    if line.startswith("CFE_PSP:"):
        return {"process_started": True, "layer": "psp"}
    if line.startswith(("OS_BSP_Initialize(", "OS_Posix_", "OS_API_Init(")):
        return {"process_started": True, "layer": "osal"}
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
    line = console_text(line)
    if job.get("phase") == "build":
        match = PERCENT.search(line)
        activity = None
        if line == CATALOG_ACTIVITY:
            activity = "Indexing catalog"
        elif line.startswith("Build ready:"):
            activity = "Build installed"
        elif line.startswith(("-- Configuring", "-- Generating", "-- The C compiler identification")):
            activity = "Configuring"
        elif line.startswith(("-- Installing:", "-- Up-to-date:", "Install the project")):
            activity = "Installing"
        elif match and job.get("build_activity") not in {"Installing", "Build installed", "Indexing catalog"}:
            activity = "Compiling"
        update = {}
        if activity and activity != job.get("build_activity"):
            job["build_activity"] = update["activity"] = activity
            if job.get("build_percent") is not None:
                job["build_percent"] = update["percent"] = None
        # A make subtarget may print 100% before installation and catalog extraction.
        # In those phases there is no measured fraction of the remaining work.
        if match and activity == "Compiling":
            percent = int(match[1])
            if percent < 100 and percent > (job.get("build_percent") or 0):
                job["build_percent"] = update["percent"] = percent
            elif percent == 100 and job.get("build_percent") is not None:
                job["build_percent"] = update["percent"] = None
        trace = job.get("boot_trace", [])
        if update or (line.strip() and (not trace or len(trace) == 1 and not trace[0]["line"])):
            _record(job, line, **update)
        return
    if job.get("phase") == "boot":
        milestone = guest_milestone(line)
        if milestone > job.get("guest_stage", 0):
            job["guest_stage"] = milestone
            _record(job, line, guest_stage=milestone)
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
    if "layer" in fact and fact["layer"] not in facts.setdefault("platform_layers", []):
        facts["platform_layers"].append(fact["layer"])
        changed = True
    if "app" in fact:
        changed |= fact["app"] not in facts["initialized"]
        facts["initialized"].setdefault(fact["app"], fact)
    new_state = "state" in fact and fact["state"] not in facts["states"]
    if new_state:
        facts["states"].append(fact["state"])
    if changed or new_state:
        _record(job, line, fact=fact)
    if new_state and fact["state"] == "OPERATIONAL":
        run = job.get("instance") or job["id"]
        previous = hardware.state.read("operational-" + job["target"] + ".json", {})
        at = previous["time"] if previous.get("run_id") == run else time.time()
        reference = {"run": run, "line": line}
        if job.get("started"):
            reference["started"] = job["started"]
        hardware.journey.observe(job["target"], "boot", reference, at)
        if job["target"] == "physical":
            hardware.journey.observe("physical", "board", reference, at)
            origin = hardware.state.read("target.json", {}).get("journey_origin")
            if origin in ("native", "qemu"):
                hardware.journey.observe(origin, "board", reference, at)
        hardware.state.write("operational-" + job["target"] + ".json",
                       {"run_id": run, "time": at, "target": job["target"],
                        "started": job.get("started"), "boot_trace": job["boot_trace"],
                        "connection": job.get("connection"), "instance": job.get("instance"),
                        "apps": job.get("boot_apps"), "flight": facts})


def app_records(startup):
    active, _ = parse_startup(startup)
    return [{"name": entry.name, "task": entry.fields[3]} for entry in active if entry.kind == "CFE_APP"]


def boot_observed(hardware, target):
    if target not in {"native", "physical", "qemu"}:
        return False
    receipt = hardware.state.read("operational-" + target + ".json", {})
    return "OPERATIONAL" in receipt.get("flight", {}).get("states", []) and (
        target != "physical" or hardware.same_board(receipt.get("connection"), hardware.state.read("connection.json")))


