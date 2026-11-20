"""First flight runs the normal build/deploy pipeline and interprets its own flight log."""
import platform
import time

from hardware import infrastructure
from project.model import load_config

from hardware.boot_trace import (CATALOG_ACTIVITY, SERVICES, STATES, _record, app_records, boot_observed,
                                 console_text, observe, parse_boot_line)


def snapshot(studio, target, *, journal=None):
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
        apps = app_records(studio.workspace.mission.startup_text()) if has_source else []
    trace = (job or (receipt if matching_receipt else {})).get("boot_trace", [])
    # Older receipts accepted subsystem messages such as "Dwell Tables Initialized".
    # Revalidate those EVS entries against their original line before replaying them.
    invalid = {i for i, entry in enumerate(trace) if entry.get("fact", {}).get("app")
               and entry.get("line") and not parse_boot_line(entry["line"])}
    if invalid:
        withdrawn = {trace[i]["fact"]["app"] for i in invalid}
        initialized = dict(flight.get("initialized", {}))
        for name in withdrawn:
            initialized.pop(name, None)
        for line in job.get("lines", []):
            observed = parse_boot_line(line)
            if observed and observed.get("app") in withdrawn:
                initialized[observed["app"]] = observed
        flight = dict(flight, initialized=initialized)
        trace = [({k: v for k, v in entry.items() if k != "fact"} if i in invalid else entry)
                 for i, entry in enumerate(trace)]
    output = job.get("lines") if job else [event["line"] for event in trace if event.get("line")]
    if journal and target != "native":
        instance = (job or receipt).get("instance") if live else None
        journal_lines, journal_apps = journal(target, connection, instance)
        if journal_lines:
            output = journal_lines
        if journal_apps:
            flight = dict(flight, initialized={**flight.get("initialized", {}), **journal_apps})
    lines = [clean for line in (output or [])[-300:] if (clean := console_text(line)).strip()]
    return {"target": target, "verified": infrastructure.target_verified(hardware, target),
            "hardware": "This computer" if target == "native" else profile.get("board_label", "Board"),
            "architecture": platform.machine() if target == "native" else profile.get("board", ""),
            "os": platform.system() if target == "native" else profile.get("os_label", "Linux"),
            "apps": apps,
            "services": [name for name in SERVICES if (hardware.root / "cFS/cfe/modules" / name.lower()).is_dir()], "es_states": STATES, "flight": flight, "stopped": stopped,
            "running": live, "unverified": bool(unknown),
            "job": {k: job[k] for k in ("id", "status", "action", "phase", "guest_stage", "build_percent", "build_activity", "error", "started") if k in job},
            "trace": trace,
            "lines": lines}


def execute(studio, record, options, emit):
    """One exclusive operation survives browser navigation. Use the same builders and deployers as the toolbar."""
    hardware, target, cancel = studio.hardware, record["target"], record["cancel"]
    if not infrastructure.target_verified(hardware, target):
        raise ValueError("Complete the target checks")
    def phase(name):
        with studio.lock:
            record["phase"] = name
            _record(record, phase=name)
    resume_emulator = target == "qemu" and hardware._qemu_running() is True
    if resume_emulator:
        hardware.verify_running_emulator(emit, cancel)
    hardware.assert_can_start(target, record.get("connection"))
    studio.ground.stop()
    phase("build")
    build = hardware.execute("build", emit, cancel=cancel, reuse_build=resume_emulator, **options)
    if cancel.is_set():
        raise ValueError("Build cancelled")
    emit(CATALOG_ACTIVITY)
    sensorless = bool(options.get("sensorless"))
    studio.freeze_catalog(build, sensorless)
    build_root = hardware.runtime / "sensorless" if sensorless else hardware.root
    installed = build_root / hardware.build_directory(target) / "exe/cpu1/cf/cfe_es_startup.scr"
    with studio.lock:
        record["boot_apps"] = app_records(installed.read_text())
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
