"""Observe one Linux process or systemd invocation until cFE ES reports startup."""
from contextlib import closing
import ctypes
import json
import os
import re
import selectors
import subprocess
import time


OPERATIONAL = re.compile(r"(?:^|\bCFE_ES_Main:\s*)CFE_ES_Main entering OPERATIONAL state\b")
QUEUE_ERROR = re.compile(r"OS_QueueCreate(?:_Impl)?\b.*\b(?:error|fail\w*)\b", re.I)
BIND_ERROR = re.compile(r"CI(?:_LAB)?:\s*bind socket failed", re.I)


class StartupError(RuntimeError):
    pass


def startup_line(line):
    if QUEUE_ERROR.search(line):
        raise StartupError(f"{line} — check fs.mqueue.msg_max and run cFS as a normal user.")
    if BIND_ERROR.search(line):
        raise StartupError(f"{line} — free the CI_LAB UDP command port before retrying.")
    if re.search(r"CFE_PSP: Exiting cFE|CFE_ES_ResetCFE: PROCESSOR RESET|Application Init Failed", line, re.I):
        raise StartupError(f"{line} — cFS stopped during initialization.")
    return bool(OPERATIONAL.search(line))


def wait_events(selector, deadline, cancel=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise StartupError("Timed out waiting for CFE_ES_Main entering OPERATIONAL state.")
    if cancel is not None and cancel.is_set():
        raise StartupError("cFS startup cancelled.")
    return selector.select(min(.25, remaining) if cancel is not None else remaining)


def watch_file(path):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "Cannot open the Linux file notification queue")
    if libc.inotify_add_watch(fd, os.fsencode(path), 0x00000002 | 0x00000008) < 0:  # IN_MODIFY | IN_CLOSE_WRITE
        error = ctypes.get_errno()
        os.close(fd)
        raise OSError(error, "Cannot watch the cFS startup log", path)
    return os.fdopen(fd, "rb", buffering=0)


def wait_native(process, log, emit, timeout, cancel=None):
    deadline = time.monotonic() + timeout
    pending = b""
    with watch_file(log) as changes, log.open("rb") as stream, selectors.DefaultSelector() as selector:
        with os.fdopen(os.pidfd_open(process.pid), "rb", buffering=0) as pid:
            selector.register(pid, selectors.EVENT_READ)
            selector.register(changes, selectors.EVENT_READ)
            while True:
                code = process.poll()
                pending += stream.read()
                lines = pending.split(b"\n")
                pending = lines.pop()
                if code is not None and pending:
                    lines.append(pending)
                    pending = b""
                ready = False
                for raw in lines:
                    line = raw.decode(errors="replace").rstrip("\r")
                    emit(line)
                    ready |= startup_line(line)
                if code is not None:
                    raise StartupError(f"core-cpu1 exited with status {code} during startup.")
                if ready:
                    return
                for key, _ in wait_events(selector, deadline, cancel):
                    if key.fileobj is changes:
                        changes.read(65536)


def service_state(unit):
    properties = ["InvocationID", "MainPID", "ExecMainPID", "ExecMainStartTimestampMonotonic", "ExecMainStatus", "ActiveState"]
    command = ["systemctl", "show", "--property=" + ",".join(properties), unit]
    return dict(line.split("=", 1) for line in subprocess.check_output(command, text=True).splitlines())


def messages(data, invocation):
    for line in data.splitlines():
        entry = json.loads(line)
        if entry.get("_SYSTEMD_INVOCATION_ID") == invocation and isinstance(entry.get("MESSAGE"), str):
            yield entry["MESSAGE"]


def wait_service(unit, timeout, emit=print):
    """Read the current invocation only, including messages journaled before attaching."""
    physical = unit == "cfs-studio.service"
    if not physical and unit != "cfs.service":
        raise ValueError("Unknown cFS service")
    state = service_state(unit)
    invocation = state.get("InvocationID", "")
    journal = (["sudo", "-n"] if physical else []) + ["journalctl", "-u", unit, "-n", "all"]
    if invocation and not re.fullmatch("[0-9a-f]{32}", invocation):
        raise StartupError(f"Invalid invocation identifier from {unit}.")

    def exited():
        history = subprocess.check_output([*journal, "--no-pager", "-o", "json"])
        with open("/proc/sys/kernel/random/boot_id") as identity:
            boot = identity.read().strip().replace("-", "")
        for row in history.splitlines():
            entry = json.loads(row)
            if invocation:
                matches = entry.get("_SYSTEMD_INVOCATION_ID") == invocation
            else:
                matches = (entry.get("_BOOT_ID") == boot and entry.get("_PID") == state["ExecMainPID"] and
                           int(entry.get("__MONOTONIC_TIMESTAMP", 0)) >= int(state["ExecMainStartTimestampMonotonic"] or 0))
            if matches and isinstance(entry.get("MESSAGE"), str):
                emit(entry["MESSAGE"])
                startup_line(entry["MESSAGE"])
        current = service_state(unit)
        raise StartupError(f"{unit} exited during startup (status {current['ExecMainStatus']}).")

    if not invocation:
        exited()
    emit("@cfs-instance " + invocation)
    main_pid = int(state["MainPID"])
    if not main_pid:
        exited()
    try:
        fd = os.pidfd_open(main_pid)
    except ProcessLookupError:
        exited()
    deadline = time.monotonic() + timeout
    with os.fdopen(fd, "rb", buffering=0) as pid, selectors.DefaultSelector() as selector:
        observer = subprocess.Popen([*journal, "-f", "-o", "json"], stdout=subprocess.PIPE)
        with closing(observer.stdout):
            try:
                selector.register(observer.stdout, selectors.EVENT_READ)
                selector.register(pid, selectors.EVENT_READ)
                pending = b""
                while True:
                    events = wait_events(selector, deadline)
                    if any(key.fileobj is pid for key, _ in events):
                        exited()
                    for _, _mask in events:
                        chunk = os.read(observer.stdout.fileno(), 65536)
                        if not chunk:
                            raise StartupError(f"Journal reader for {unit} exited with status {observer.wait()}.")
                        pending += chunk
                        complete, separator, pending = pending.rpartition(b"\n")
                        if not separator:
                            continue
                        ready = False
                        for line in messages(complete, invocation):
                            emit(line)
                            ready |= startup_line(line)
                        if ready:
                            current = service_state(unit)
                            if current["InvocationID"] != invocation or current["MainPID"] != state["MainPID"]:
                                exited()
                            return
            finally:
                observer.terminate()
                observer.wait()


if __name__ == "__main__":
    import sys
    try:
        wait_service(sys.argv[1], float(sys.argv[2]), lambda line: print(line, flush=True))
    except (OSError, ValueError, subprocess.SubprocessError, StartupError) as error:
        sys.exit(str(error))
