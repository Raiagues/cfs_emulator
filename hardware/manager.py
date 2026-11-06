"""Build, deployment and runtime control for the native, QEMU and physical targets.

HardwareManager.execute is blocking: run it in a job worker and pass emit(line)
and an optional threading.Event as cancel. SSH runs in batch mode with the
user's OpenSSH configuration and agent, and sudo never prompts for a password.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import platform
from pathlib import Path
import re
import secrets
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time


# Every field hardware/board_probe.py reports, with its JSON type.
PROBE_FIELDS = {"arch": str, "model": str, "home": str, "hostname": str, "i2c": list, "sudo": bool,
                "authorized": bool, "shutdown_authorized": bool, "service_installed": bool,
                "service": str, "service_directory": str, "systemd": bool, "os": str, "raspios": bool}
# systemd states in which a service may still have a running process.
ACTIVE_STATES = {"active", "activating", "deactivating", "reloading"}


class HardwareError(RuntimeError):
    def __init__(self, message, returncode=None):
        super().__init__(message)
        self.returncode = returncode


class HardwareManager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.runtime = self.root / "hardware/.runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fingerprint_cache = None
        self._last_probe = self._load("probe.json")
        self._observation_lock = threading.Lock()
        self._physical_observation = None

    def _load(self, name, fallback=None):
        try:
            return json.loads((self.runtime / name).read_text())
        except (OSError, ValueError):
            return fallback

    def _save(self, name, value):
        with tempfile.NamedTemporaryFile(mode="w", dir=self.runtime, delete=False) as file:
            json.dump(value, file, indent=2)
            temp = Path(file.name)
        temp.replace(self.runtime / name)

    def default_target(self):
        selected = self._load("target.json", {}).get("target")
        if selected in {"native", "qemu", "physical"}:
            return selected
        config = json.loads((self.root / "project/config.json").read_text())
        return "native" if config.get("board") is None and config.get("os") is None else "qemu"

    def select_target(self, target):
        if not isinstance(target, str) or target not in {"native", "qemu", "physical"}:
            raise HardwareError("Invalid execution target.")
        self._save("target.json", {"target": target})
        return {"target": target}

    @staticmethod
    def build_directory(target):
        return "cFS/build-native" if target == "native" else "cFS/build-flight"

    @staticmethod
    def build_state_file(target, sensorless=False):
        profile = "native" if target == "native" else "flight"
        return "build-" + profile + ("-sensorless" if sensorless else "") + ".json"

    def build_state(self, target, sensorless=False):
        return self._load(self.build_state_file(target, sensorless), {})

    @staticmethod
    def _capture(argv, timeout=10, input=None):
        try:
            result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, input=input)
            return result.returncode, (result.stdout + result.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)

    def _stream(self, argv, emit, cancel=None, cwd=None, timeout=None, stdin=None):
        """Emit each output line until argv exits; carriage returns also end a line.

        Cancellation and timeout terminate the whole process group.
        """
        emit("$ " + shlex.join(str(arg) for arg in argv))
        started = time.monotonic()
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
        # sudo fails instead of waiting for a password.
        env["SUDO_ASKPASS"] = "/bin/false"
        directory = cwd or self.root
        source = subprocess.DEVNULL if stdin is None else stdin
        with subprocess.Popen(argv, cwd=directory, env=env, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True) as process:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            pending = b""
            try:
                while selector.get_map():
                    if cancel and cancel.is_set():
                        raise HardwareError("Operation cancelled; services already started may remain running.")
                    if timeout and time.monotonic() - started > timeout:
                        raise HardwareError("Operation timed out.")
                    for key, _ in selector.select(0.2):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        pending += chunk.replace(b"\r", b"\n")
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            emit(line.decode("utf-8", "replace"))
                if pending:
                    emit(pending.decode("utf-8", "replace"))
                code = process.wait(timeout=5)
                if code:
                    raise HardwareError(f"Command exited with code {code}.", returncode=code)
            finally:
                selector.close()
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()

    def fingerprint(self):
        """SHA-256 of every source file a build reads.

        Documentation, build output and the sensor values in project/config.json
        do not change it.
        """
        paths = []
        for directory in ("cFS", "project"):
            for base, dirs, files in os.walk(self.root / directory):
                sources = [d for d in dirs if d not in {".git", "__pycache__"} and not d.startswith("build")]
                dirs[:] = sorted(d for d in sources if not (Path(base) / d).is_symlink())
                for name in sorted(files):
                    path = Path(base) / name
                    if path.suffix.lower() in {".md", ".rst"}:
                        continue
                    if path.parent == self.root / "project/generated" and name in {"build.json", "build-native.json", "build-flight.json"}:
                        continue  # Written by the build itself.
                    if name != ".git" and not path.is_symlink() and not name.endswith(".pyc"):
                        paths.append(path)
        paths.append(self.root / "scripts/build-cfs.sh")
        if json.loads((self.root / "project/config.json").read_text()).get("board"):
            paths.append(self.root / "Dockerfile")
        signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
        if self._fingerprint_cache and self._fingerprint_cache[0] == signature:
            return self._fingerprint_cache[1]
        digest = hashlib.sha256()
        for path in paths:
            digest.update(str(path.relative_to(self.root)).encode())
            data = path.read_bytes()
            if path == self.root / "project/config.json":
                config = json.loads(data)
                for device in config.get("devices", []):
                    device.pop("values", None)
                data = json.dumps(config, sort_keys=True).encode()
            digest.update(data)
        result = digest.hexdigest()
        self._fingerprint_cache = (signature, result)
        return result

    def ssh_candidates(self):
        candidates = []
        config = Path.home() / ".ssh/config"
        if config.is_file():
            for match in re.finditer(r"^\s*Host\s+(.+)$", config.read_text(), re.M | re.I):
                for alias in shlex.split(match.group(1), comments=True):
                    if not any(char in alias for char in "*?!"):
                        candidates.append({"host": alias, "source": "ssh_config"})
        saved = self._load("connection.json")
        if saved:
            candidates.insert(0, dict(saved, source="saved"))
        return candidates

    def connection(self, value=None):
        value = value or self._load("connection.json", {})
        if not isinstance(value, dict):
            raise HardwareError("Enter the board's SSH connection.")
        host = str(value.get("host", "")).strip()
        user = str(value.get("user", "")).strip()
        if "@" in host and not user:
            user, host = host.rsplit("@", 1)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-]*", host):
            raise HardwareError("Enter the Raspberry Pi hostname, IP address or SSH alias.")
        if user and not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*", user):
            raise HardwareError("Invalid SSH user.")
        try:
            port = int(value.get("port", 22))
        except (TypeError, ValueError):
            raise HardwareError("Invalid SSH port.") from None
        if not 1 <= port <= 65535:
            raise HardwareError("Invalid SSH port.")
        result = {"host": host, "user": user, "port": port}
        identity = value.get("identity_file", "")
        if not isinstance(identity, str) or any(c in identity for c in '\r\n\0'):
            raise HardwareError("Invalid SSH identity path.")
        if identity.strip():
            key = Path(identity.strip()).expanduser()
            if not key.is_absolute():
                raise HardwareError("Use an absolute SSH key path on this computer, or a path starting with '~/'.")
            result["identity_file"] = str(key)
        directory = value.get("directory", "cfs-arm64")
        if not isinstance(directory, str):
            raise HardwareError("Invalid board installation folder.")
        directory = directory.strip().removeprefix("~/").rstrip("/")
        if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_./-]*", directory) or any(p in {".", ".."} for p in directory.split("/")):
            raise HardwareError("Choose an installation folder inside the board user's home, without '..'.")
        directory = str(Path(directory))
        if directory != "cfs-arm64":
            result["directory"] = directory
        return result

    def ssh_argv(self, target="qemu", connection=None, interactive=False):
        argv = ["ssh", "-t" if interactive else "-T", "-o", "ConnectTimeout=8",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]
        if not interactive:
            argv += ["-o", "BatchMode=yes"]
        if target == "qemu":
            from hardware.infrastructure import emulator_config
            return argv + ["-F", str(Path.home() / ".ssh/cfs-emulator/config"),
                           "-p", str(emulator_config(self.root)["ssh_port"]), "pi4-cfs"]
        if target != "physical":
            raise HardwareError("Invalid target.")
        config = self.connection(connection)
        # The user's OpenSSH config, agent and known_hosts apply. accept-new
        # enrolls new hosts but refuses changed host keys.
        argv += ["-o", "StrictHostKeyChecking=accept-new"]
        argv += ["-p", str(config["port"])]
        if config["user"]:
            argv += ["-l", config["user"]]
        if config.get("identity_file"):
            argv += ["-i", config["identity_file"], "-o", "IdentitiesOnly=yes"]
        return argv + [config["host"]]

    def board_directory(self, board, connection=None):
        return board["home"] + "/" + self.connection(connection).get("directory", "cfs-arm64")

    def _physical_status(self):
        """The saved board's last probe plus its live cFS service state, cached for 3 s."""
        previous = self._load("probe.json", self._last_probe)
        connection = self._load("connection.json")
        if not connection:
            return None
        with self._observation_lock:
            cached = self._physical_observation
            if cached and cached[0] == connection and time.monotonic() - cached[1] < 3:
                return dict(cached[2])
            flight = self._flight_state("physical", connection)
            recognized = flight['running'] is not None
            result = dict(previous or {})
            result.update(observed_at=time.time(), service=flight['service'], flight_running=flight['running'], pids=flight['pids'])
            result['connected'] = True if recognized else None
            result['observation_error'] = flight.get('error')
            self._physical_observation = (connection, time.monotonic(), result)
            return dict(result)

    def _local_flight_state(self):
        """core-cpuN processes whose executable is inside this checkout's cFS directory."""
        code, output = self._capture(['pgrep', '-x', 'core-cpu[0-9]+'], 3)
        if code not in (0, 1):
            return {'running': None, 'pids': [], 'service': 'unknown'}
        pids = []
        for pid in output.split():
            if not pid.isdigit():
                continue
            try:
                executable = Path(str(Path('/proc', pid, 'exe').readlink()).removesuffix(' (deleted)'))
                if executable.is_relative_to(self.root / 'cFS'):
                    pids.append(int(pid))
            except (OSError, RuntimeError):
                continue
        return {'running': bool(pids), 'pids': pids, 'service': 'native'}

    def _run_native(self, emit, cancel):
        _, payload, state = self._require_build(target="native")
        self.assert_can_start("native")
        argv = [str(payload / "core-cpu1")]
        if shutil.which("stdbuf"):
            argv = ["stdbuf", "-oL", "-eL", *argv]
        emit("$ " + shlex.join(argv))
        with (self.runtime / "native.log").open("wb") as output:
            process = subprocess.Popen(argv, cwd=payload, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        instance = secrets.token_hex(16)
        self._save("native.json", {"pid": process.pid, "instance": instance, "started_at": time.time()})
        time.sleep(1)
        if process.poll() is not None:
            for line in (self.runtime / "native.log").read_text(errors="replace").splitlines():
                emit(line)
            raise HardwareError("Native cFS exited during startup.", returncode=process.returncode)
        return self._deploy_record("native", state, pid=process.pid, instance=instance)

    def _stop_native(self, emit):
        pids = self._local_flight_state()["pids"]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            remaining = set(pids) & set(self._local_flight_state()["pids"])
            if not remaining:
                break
            time.sleep(.1)
        for pid in set(pids) & set(self._local_flight_state()["pids"]):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        emit("Native cFS stopped.")

    def _flight_state(self, target, connection=None):
        if target == "native":
            return self._local_flight_state()
        service = 'cfs.service' if target == 'qemu' else 'cfs-studio.service'
        script = '''import json,subprocess,sys
s=subprocess.run(['systemctl','show',sys.argv[1],'--property=ActiveState','--value'],capture_output=True,text=True)
p=subprocess.run(['pgrep','-x','core-cpu[0-9]+'],capture_output=True,text=True)
state=s.stdout.strip()
known=state in ('active','inactive','failed','activating','deactivating','reloading') and p.returncode in (0,1)
pids=[int(pid) for pid in p.stdout.split() if pid.isdigit()]
running=True if pids or state in ('active','activating','deactivating','reloading') else False if known else None
print(json.dumps({'service':state or 'unknown','pids':pids,'running':running}))'''
        command = 'python3 -c ' + shlex.quote(script) + ' ' + shlex.quote(service)
        argv = self.ssh_argv(target, connection) + [command]
        code, output = self._capture(argv, 8)
        try:
            state = json.loads(output) if not code else None
            if not isinstance(state, dict) or set(state) != {'service', 'pids', 'running'}:
                raise ValueError('Invalid state')
            return dict(state, reachable=True)
        except (ValueError, TypeError):
            return {'service': 'unknown', 'pids': [], 'running': None,
                    'reachable': code == 0, 'error': output or 'SSH unavailable'}

    def assert_can_start(self, target=None, connection=None):
        """Raise unless cFS is confirmed stopped on every target this checkout may have started.

        Callers hold execution.lock and call this before changing a deployment.
        """
        checks = [('this workspace on the local host', self._local_flight_state())]
        target = target or self.default_target()
        deployed = self._load('deployed.json', {})
        running = self._qemu_running()
        qemu_active = deployed.get('qemu') and not deployed['qemu'].get('stopped_at')
        if running:
            checks.append(('the emulator', self._flight_state('qemu')))
        elif running is None and (target == 'qemu' or qemu_active):
            checks.append(('the emulator', {'running': None}))
        previous = self._load('active.json', {})
        physical_active = deployed.get('physical') and not deployed['physical'].get('stopped_at')
        candidates = []
        if target == 'physical':
            candidates.append(connection or self._load('connection.json'))
        if physical_active:
            candidates.append(deployed['physical'].get('connection'))
        if previous.get('target') == 'physical' and previous.get('phase') != 'stopped':
            candidates.append(previous.get('connection'))
        connections = []
        for candidate in candidates:
            if candidate and candidate not in connections:
                connections.append(candidate)
        for candidate in connections:
            checks.append(('the physical board', self._flight_state('physical', candidate)))
        for label, state in checks:
            if state['running']:
                raise HardwareError(f'cFS is already running on {label}. Stop that instance before Run cFS.')
        for label, state in checks:
            if state['running'] is None:
                raise HardwareError(f'Cannot confirm that cFS on {label} is stopped. Restore its connection before Run cFS.')

    def profiles(self):
        # Catalogs explicitly declare the supported deployment targets/OS matrix.
        from project.model import board_catalogs
        return [{"board": catalog["board"], "board_label": catalog.get("name", catalog["board"]),
                 "os": system, "os_label": catalog.get("os_labels", {}).get(system, system),
                 "targets": catalog["targets"]} for catalog in board_catalogs(root=self.root)
                if catalog.get("targets") for system in catalog["os"]]

    def _validate_profile(self, target, board=None, os=None):
        config = json.loads((self.root / "project/config.json").read_text())
        if target == "native":
            return {"board": None, "os": None}
        selected = (board or config["board"], os or config["os"])
        if not any((p["board"], p["os"]) == selected and target in p["targets"] for p in self.profiles()):
            raise HardwareError("This board and operating system do not have a validated build profile.")
        if selected != (config["board"], config["os"]):
            raise HardwareError("The selected board and operating system do not match the mission configuration.")
        return {"board": selected[0], "os": selected[1]}

    def _qemu_running(self):
        code, output = self._capture(["docker", "inspect", "--format", "{{.State.Running}}", "pi4-cfs"], 30)
        if not code and output in {"true", "false"}:
            return output == "true"
        if "no such object" in output.lower() or "no such container" in output.lower():
            return False
        return None

    def assert_can_boot(self, retry=False):
        """True when QEMU runs and boot only retries its SSH connection; raise when boot is not possible."""
        running = self._qemu_running()
        if running is None:
            raise HardwareError("Cannot read QEMU's state. Check Docker access before starting it.")
        if running is False:
            return False
        code, _ = self._capture(self.ssh_argv() + ['true'], 10)
        if not code:
            raise HardwareError("QEMU and Linux are already running. Stop QEMU before starting it again.")
        if not retry:
            raise HardwareError("QEMU is running, but Linux is not reachable. Retry its connection or stop QEMU first.")
        return True

    def _wait_qemu_stopped(self, emit, cancel=None, timeout=180):
        running = self._qemu_running()
        if running is False:
            emit("QEMU is already stopped.")
            return
        if running is None:
            raise HardwareError("Cannot read QEMU's state. Check Docker access and retry Shut down.")
        emit("Shutting down QEMU Linux. Waiting for services and the persistent disk to close...")
        serial = self.root / "logs/latest.log"
        offset = serial.stat().st_size if serial.exists() else 0
        started = time.monotonic()
        try:
            self._stream(["bash", "stop.sh"], emit, cancel, timeout=30)
        except HardwareError as error:
            if cancel and cancel.is_set():
                raise
            if self._qemu_running() is False:
                emit("QEMU stopped.")
                return
            # SSH exits with 255 when the guest closes it during poweroff.
            if error.returncode != 255:
                raise
            emit("SSH disconnected; checking QEMU until shutdown completes.")
        next_progress = 0
        while time.monotonic() - started < timeout:
            if cancel and cancel.is_set():
                raise HardwareError("Stopped waiting for shutdown; Linux may still be shutting down.")
            try:
                with serial.open("rb") as log:
                    log.seek(offset)
                    chunk = log.read()
                    offset = log.tell()
                for line in chunk.decode("utf-8", "replace").replace("\r", "\n").splitlines():
                    if line.strip():
                        emit(line)
            except OSError:
                pass
            if self._qemu_running() is False:
                emit("QEMU stopped.")
                return
            elapsed = time.monotonic() - started
            if elapsed >= next_progress:
                emit(f"Waiting for QEMU to exit · {int(elapsed)}s / {timeout}s")
                next_progress = elapsed + 5
            time.sleep(.5)
        raise HardwareError(f"QEMU shutdown was not confirmed within {timeout}s. Check the Linux log; no forced power-off was performed.")

    def _stop_physical(self, connection, emit, cancel=None, required=True):
        argv = self.ssh_argv("physical", connection)
        check = "systemctl is-active cfs-studio.service; if pgrep -x core-cpu1 >/dev/null; then echo process-running; else echo process-stopped; fi"
        code, output = self._capture(argv + [check], 15)
        lines = output.splitlines()
        if code or not lines or lines[-1] not in {"process-running", "process-stopped"}:
            if required:
                raise HardwareError("Cannot confirm that cFS on the physical board is stopped. Restore its SSH connection before switching targets. " + output)
            return
        if ACTIVE_STATES.intersection(lines):
            emit("Stopping cFS on the board...")
            self._stream(argv + ["sudo -n systemctl stop cfs-studio.service"], emit, cancel, timeout=30)
            code, output = self._capture(argv + [check], 15)
            lines = output.splitlines()
        if code or not lines or lines[-1] != "process-stopped" or ACTIVE_STATES.intersection(lines):
            raise HardwareError("cFS is still running on the physical board. Stop any unmanaged core-cpu1 process before switching targets.")
        self._physical_observation = None
        emit("Board cFS is stopped; its Linux remains on.")

    def _switch_target(self, target, connection, emit, cancel=None):
        """Stop cFS on the other targets before booting this one."""
        previous = self._load("active.json", {})
        deployed = self._load("deployed.json", {})
        previous_running = previous.get("phase") != "stopped"
        previous_board = previous.get("connection") if previous.get("target") == "physical" else None
        deployed_board = deployed.get("physical", {}).get("connection")
        boards = []
        for candidate in (previous_board, deployed_board, self._load("connection.json")):
            other = target == "qemu" or candidate != connection
            if candidate and candidate not in boards and other:
                boards.append(candidate)
        for candidate in boards:
            # Only the last active board must answer; other saved boards are stopped when reachable.
            was_running = previous_running and candidate == previous_board
            last_deployed = not previous and candidate == deployed_board
            self._stop_physical(candidate, emit, cancel, was_running or last_deployed)
        if target == "physical":
            running = self._qemu_running()
            qemu_was_running = previous.get("target") == "qemu" and previous_running
            qemu_deployed = not previous and bool(deployed.get("qemu"))
            if running or (running is None and (qemu_was_running or qemu_deployed)):
                emit("Stopping the emulator before starting cFS on the board.")
                try:
                    self._wait_qemu_stopped(emit, cancel)
                except HardwareError as error:
                    raise HardwareError(f"Cannot start on the board: {error}") from error
        if cancel and cancel.is_set():
            raise HardwareError("Target switch cancelled.")
        self._save_active(target, connection, "starting")

    def _save_active(self, target, connection, phase):
        """Record the target before and after starting it; an interrupted start can leave a live service."""
        active = {"target": target, "connection": connection, "phase": phase, "updated_at": time.time()}
        self._save("active.json", active)

    def _mark_stopped(self, target, connection=None):
        previous = self._load("active.json", {})
        if previous.get("target") == target and (target != "physical" or previous.get("connection") == connection):
            self._save("active.json", dict(previous, phase="stopped", updated_at=time.time()))
        deployed = self._load("deployed.json", {})
        if target in deployed:
            deployed[target]["stopped_at"] = time.time()
            self._save("deployed.json", deployed)

    def status(self):
        config = json.loads((self.root / "project/config.json").read_text())
        running = self._qemu_running()
        code = 0 if running is not None else 1
        docker = "Docker did not respond. Check that its service is running." if code else ""
        service = None
        flight_running = None
        linux_ready = None
        boot_error = None
        qemu_pids = []
        if not code:
            if running:
                flight = self._flight_state('qemu')
                service, flight_running, qemu_pids = flight['service'], flight['running'], flight['pids']
                linux_ready = flight.get('reachable', flight_running is not None)
                boot_error = flight.get('error') if not linux_ready else None
            elif running is False:
                flight_running = False
                service = "inactive"
                linux_ready = False
        fingerprint = self.fingerprint()
        default_target = self.default_target()
        active = self._load("active.json", {})
        deployed = self._load("deployed.json", {})
        physical_active = deployed.get('physical') and not deployed['physical'].get('stopped_at')
        physical = self._physical_status() if default_target != 'native' or physical_active else None
        local = self._local_flight_state()
        qemu_active = deployed.get("qemu") and not deployed["qemu"].get("stopped_at")
        if flight_running is None and not qemu_active and running is not True:
            flight_running = False
        states = {'qemu': {'running': flight_running, 'pids': qemu_pids}, 'native': local}
        if physical and (physical.get('flight_running') is not None or physical_active or default_target == 'physical'):
            states['physical'] = {'running': physical.get('flight_running'), 'pids': physical.get('pids', [])}
        targets = [target for target, state in states.items() if state['running']]
        unknown = [target for target, state in states.items() if state['running'] is None]
        labels = {'qemu': 'the emulator', 'physical': 'the physical board', 'native': 'this workspace on the local host'}
        if targets:
            reason = 'cFS is already running on ' + ', '.join(labels[t] for t in targets) + '. Stop it before starting another instance.'
        elif unknown:
            reason = 'Cannot confirm cFS state on ' + ', '.join(labels[t] for t in unknown) + '.'
        else:
            reason = ''
        preferred = active.get("target") if active.get("target") in targets else default_target
        # A target without a PID list still counts as one instance.
        instances = sum(max(1, len(states[t]['pids'])) for t in targets)
        execution = {"target": targets[0] if len(targets) == 1 else None, "preferred_target": preferred,
                     "conflict": instances > 1, "can_start": not targets and not unknown,
                     "block_reason": reason, "running_targets": targets}
        builds = {}
        for target in ("native", "qemu", "physical"):
            build = self.build_state(target)
            no_sensors = self.build_state(target, True)
            builds[target] = {"exists": (self.root / self.build_directory(target) / "exe/cpu1/core-cpu1").is_file(),
                              "current": build.get("fingerprint") == fingerprint,
                              "fingerprint": fingerprint,
                              "sensorless_current": no_sensors.get("fingerprint") == fingerprint}
        tools = {tool: bool(shutil.which(tool)) for tool in ("docker", "ssh", "scp", "make", "cmake", "cc")}
        qemu = {"running": running, "service": service, "flight_running": flight_running,
                "linux_ready": linux_ready, "can_boot": running is False,
                "can_retry_boot": running is True and linux_ready is False, "boot_error": boot_error,
                "ssh_configured": (Path.home() / ".ssh/cfs-emulator/config").is_file()}
        board = {"connection": self._load("connection.json"), "candidates": self.ssh_candidates(), "last_probe": physical}
        return {"board": config["board"], "os": config["os"], "profiles": self.profiles(),
                "execution": execution, "tools": tools,
                "native": dict(local, log_path="hardware/.runtime/native.log", os=platform.system(), architecture=platform.machine()),
                "docker": {"available": code == 0, "error": docker if code else None},
                "qemu": qemu, "build": builds[default_target], "builds": builds,
                "physical": board, "deployed": deployed}

    def probe(self, connection=None, emit=lambda line: None, cancel=None):
        argv = self.ssh_argv("physical", connection)
        # The script travels on stdin, so no shell quoting is involved.
        # JSON avoids locale-dependent parsing of diagnostic tools.
        script = (self.root / "hardware/board_probe.py").read_text()
        code, output = self._capture(argv + ["python3 -"], 20, input=script)
        if code:
            raise HardwareError("SSH failed. Check that the board is on the same network and the key is authorized. " + output)
        try:
            result = json.loads(next(line for line in reversed(output.splitlines()) if line.startswith("{")))
        except (ValueError, IndexError, StopIteration):
            raise HardwareError("Invalid SSH response: " + output) from None
        if any(not isinstance(result.get(field), kind) for field, kind in PROBE_FIELDS.items()):
            raise HardwareError("Invalid SSH response: " + output)
        if "Raspberry Pi 4 Model B" not in result["model"] or result["arch"] != "aarch64" or not result["raspios"]:
            raise HardwareError("The platform supports Raspberry Pi 4B with Raspberry Pi OS ARM64: " + str(result))
        result["connected"] = True
        result["checked_at"] = time.time()
        self._save("connection.json", self.connection(connection))
        directory = self.board_directory(result, connection) + "/studio/current/cpu1"
        result["ready"] = result["authorized"] and result["service_installed"] and result["service_directory"] == directory
        result["service_ready"] = result["ready"]
        self._last_probe = result
        self._save("probe.json", result)
        self._physical_observation = None
        emit(f"SSH connected: {result['model']} · {result['arch']} · cFS {result['service']}")
        return result

    def prepare_board(self, connection=None, emit=print, cancel=None, authorize=None):
        board = self.probe(connection, emit, cancel)
        remote = self.board_directory(board, connection) + "/studio/setup_board.py"
        command = "mkdir -p " + shlex.quote(str(Path(remote).parent)) + " && cat > " + shlex.quote(remote)
        with (self.root / "hardware/setup_board.py").open("rb") as source:
            self._stream(self.ssh_argv("physical", connection) + [command], emit, cancel, stdin=source, timeout=30)
        argv = self.ssh_argv("physical", connection)
        config = self.connection(connection)
        install = "python3 " + shlex.quote(remote) + " --directory " + shlex.quote(config.get("directory", "cfs-arm64"))
        interactive = self.ssh_argv("physical", connection, interactive=True) + ["sudo " + install]
        if authorize is None:
            authorize = board["sudo"]
        result = {"setup_command": shlex.join(interactive), "script": remote, "setup_required": not authorize}
        if authorize:
            self._stream(argv + ["sudo -n " + install], emit, cancel, timeout=30)
            board = self.probe(connection, emit, cancel)
        board["admin_setup_command"] = result["setup_command"] if not board["ready"] or not board.get("shutdown_authorized") else None
        self._last_probe = board
        self._save("probe.json", board)
        emit(json.dumps(result, ensure_ascii=False))
        return result

    def _sensorless_root(self, emit):
        from project.appgen.native_startup import reconcile_generated_modules, reconcile_removed_modules
        destination = self.runtime / "sensorless"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir()
        def ignore(directory, names):
            return [name for name in names if name in (".git", "__pycache__")
                    or (name.startswith("build") and (Path(directory) / name).is_dir())]
        for directory in ("cFS", "project", "scripts", "sensors", "config"):
            shutil.copytree(self.root / directory, destination / directory, ignore=ignore, symlinks=True)
        for path in destination.rglob("*"):
            if path.is_symlink() and (Path(os.readlink(path)).is_absolute() or not path.resolve().is_relative_to(destination)):
                raise HardwareError("Link outside the isolated profile: " + str(path.relative_to(destination)))
        shutil.copy2(self.root / "Dockerfile", destination / "Dockerfile")
        shutil.copy2(self.root / ".dockerignore", destination / ".dockerignore")
        config = json.loads((destination / "project/config.json").read_text())
        removed = [app["name"] for app in config["apps"] if app["sensors"]]
        fragment = destination / "cFS/sample_defs/generated/appgen_startup.scr"
        previous_fragment = fragment.read_text() if fragment.exists() else ""
        generator = str(destination / "project/appgen/appgen.py")
        for name in removed:
            delete = [sys.executable, generator, "--root", str(destination / "cFS"), "delete-app", name]
            self._stream(delete, emit, cwd=destination)
        config["apps"] = [app for app in config["apps"] if app["name"] not in removed]
        config["devices"] = []
        (destination / "project/config.json").write_text(json.dumps(config, indent=2) + "\n")
        # Sensor libraries follow the configured devices, so sync drops them from the copy.
        self._stream([sys.executable, str(destination / "project/manage.py"), "sync"], emit, cwd=destination)
        startup = destination / "cFS/sample_defs/cpu1_cfe_es_startup.scr"
        if startup.exists():
            current_fragment = fragment.read_text() if fragment.exists() else ""
            updated = reconcile_removed_modules(startup.read_text(), removed)
            updated = reconcile_generated_modules(updated, previous_fragment, current_fragment)
            startup.write_text(updated)
        emit("Isolated sensorless profile; apps excluded from this build: " + ", ".join(removed))
        return destination

    def _require_build(self, sensorless=False, target=None):
        target = target or self.default_target()
        state = self.build_state(target, sensorless)
        if state.get("fingerprint") != self.fingerprint():
            raise HardwareError("Build this profile before running; some changes have not been compiled.")
        root = self.runtime / "sensorless" if sensorless else self.root
        payload = root / self.build_directory(target) / "exe/cpu1"
        if not (payload / "core-cpu1").is_file() or not (payload / "cf").is_dir():
            raise HardwareError("Incomplete cFS build. Build again.")
        return root, payload, state

    def _deploy_record(self, target, state, **extra):
        records = self._load("deployed.json", {})
        records[target] = dict(state, target=target, deployed_at=time.time(), **extra)
        self._save("deployed.json", records)
        return records[target]

    def _run_physical(self, emit, cancel, connection, sensorless):
        root, payload, state = self._require_build(sensorless, target="physical")
        board = self.probe(connection, emit, cancel)
        if not board["systemd"]:
            raise HardwareError("The board requires systemd.")
        if not board["ready"]:
            if board["sudo"]:
                self.prepare_board(connection, emit, cancel, authorize=True)
                board = self.probe(connection, emit, cancel)
            else:
                prepared = self.prepare_board(connection, emit, cancel)
                raise HardwareError("Authorize the service once in your terminal: " + prepared["setup_command"])
        argv = self.ssh_argv("physical", connection)
        if not sensorless:
            config = json.loads((root / "project/config.json").read_text())
            if any(app["sensors"] for app in config["apps"]):
                self._stream(argv + ["sudo -n modprobe i2c-dev"], emit, cancel, timeout=20)
                emit("The driver will read physical sensors. QEMU devices are not provisioned on the board. I2C failures appear in logs and telemetry.")
        release = state["fingerprint"][:16] + ("-sensorless" if sensorless else "") + "-" + str(time.time_ns())
        remote = self.board_directory(board, connection) + "/releases/" + release
        # Each upload is a new release directory; the running service keeps its own.
        unpack = "mkdir -p " + shlex.quote(remote) + " && tar -xmf - -C " + shlex.quote(remote)
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode="w") as tar:
                tar.add(payload, arcname="cpu1")
            archive.seek(0)
            self._stream(argv + [unpack], emit, cancel, stdin=archive, timeout=180)
        current = self.board_directory(board, connection) + "/studio/current"
        self.assert_can_start('physical', connection)
        command = ("set -e; "
                   "if pgrep -x core-cpu1 >/dev/null; then echo 'Another cFS instance is running. Stop it before starting this one.'; exit 1; fi; "
                   "test ! -e " + shlex.quote(current) + " || test -L " + shlex.quote(current) + "; "
                   "ln -sfn " + shlex.quote(remote) + " " + shlex.quote(current + ".new") +
                   " && mv -Tf " + shlex.quote(current + ".new") + " " + shlex.quote(current) +
                   " && sudo -n systemctl start cfs-studio.service" +
                   " && sleep 2 && sudo -n systemctl is-active --quiet cfs-studio.service")
        self._stream(argv + [command], emit, cancel, timeout=30)
        self.probe(connection, emit, cancel)
        return self._deploy_record("physical", state, sensorless=sensorless, connection=self.connection(connection), release=remote)

    def _run_qemu(self, emit, cancel):
        root, payload, state = self._require_build(target="qemu")
        running = self._qemu_running()
        if running is None:
            raise HardwareError("Cannot read QEMU's state. Check Docker before running cFS.")
        if running is False:
            emit("Starting the emulator to run this build...")
            self._stream(["bash", "boot.sh"], emit, cancel, timeout=660)
        self._stream([sys.executable, "project/manage.py", "check-build", "--target", "qemu"], emit, cancel)
        self._stream([sys.executable, "sensors/runtime.py", "prepare"], emit, cancel, timeout=30)
        argv = self.ssh_argv()
        service = (self.root / "cfs.service").read_text()
        working = re.search(r"^WorkingDirectory=(.+)$", service, re.M).group(1)
        self.assert_can_start('qemu')
        staging = working + ".upload-" + str(time.time_ns())
        previous = working + ".previous"
        unpack = "mkdir -p " + shlex.quote(staging) + " && tar -xmf - -C " + shlex.quote(staging)
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode="w") as tar:
                tar.add(payload, arcname=".")
            archive.seek(0)
            self._stream(argv + [unpack], emit, cancel, stdin=archive, timeout=180)
        self.assert_can_start('qemu')
        # Swap the complete installation; merging cf/ would retain removed libraries.
        command = ("set -e; if pgrep -x 'core-cpu[0-9]+' >/dev/null; then "
                   "echo 'Another cFS instance is running. Stop it before starting this one.'; exit 1; fi; "
                   "rm -rf -- " + shlex.quote(previous) + "; "
                   "if test -e " + shlex.quote(working) + "; then mv -- " + shlex.quote(working) + " " + shlex.quote(previous) + "; fi; "
                   "mv -- " + shlex.quote(staging) + " " + shlex.quote(working) + "; "
                   "systemctl start cfs.service && sleep 2 && systemctl is-active --quiet cfs.service")
        self._stream(argv + [command], emit, cancel, timeout=30)
        return self._deploy_record("qemu", state)

    def simulation_script(self, device_id):
        if device_id is None:
            return 'sensors/signals.py'
        from project.model import load_config
        from sensors.simulator import simulation_scripts

        device = next((item for item in load_config(self.root)["devices"] if item["id"] == device_id), None)
        if device is None:
            raise HardwareError("Select a configured sensor to run synthetic data.")
        script = simulation_scripts(self.root).get(device["model"])
        if script is None:
            raise HardwareError("This sensor does not have a Python waveform script.")
        return script

    def execute(self, action, emit=print, *, target=None, connection=None, sensorless=False, cancel=None, on_start=None, **options):
        """Run one Studio action.

        Build, boot, run, stop and shutdown also hold hardware/.runtime/execution.lock,
        shared by every Studio process that uses this checkout.
        """
        target = target or self.default_target()
        if target not in ("native", "qemu", "physical"):
            raise HardwareError("Invalid target.")
        if sensorless and target != "physical":
            raise HardwareError("The sensorless profile applies only to a physical board.")
        if target == "native" and action in {"boot", "shutdown", "connect", "probe", "setup", "values", "simulate"}:
            raise HardwareError("Native cFS runs on this computer. Use Build, Run cFS, Stop or Output.")
        if action in {"build", "boot", "run"}:
            self._validate_profile(target, options.get("board"), options.get("os"))
        if action in ("connect", "probe"):
            board = self.probe(connection, emit, cancel)
            if action == "connect" and (not board["ready"] or not board.get("shutdown_authorized")):
                self.prepare_board(connection, emit, cancel)
            return self._last_probe
        if action == "logs":
            return self._logs(target, connection, options.get("kind"), options.get("tail", 100), emit, cancel)
        if action in {"simulate", "simulate-preview"}:
            return self._simulate(action, target, options.get("device"), options.get("model"), emit, cancel)
        if not self._lock.acquire(blocking=False):
            raise HardwareError("Another build or runtime operation is running.")
        execution_lock = None
        try:
            if action in {"build", "boot", "run", "stop", "shutdown"}:
                execution_lock = (self.runtime / "execution.lock").open("a")
                try:
                    fcntl.flock(execution_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise HardwareError("Another Flight Studio instance is building or changing runtime state.") from None
            if action == "setup" and target == "physical":
                return self.prepare_board(connection, emit, cancel)
            if action == "setup":
                return self._stream(["bash", "scripts/setup.sh"], emit, cancel)
            if action == "build":
                return self._build(target, sensorless, emit, cancel)
            if action == "boot":
                return self._boot(target, connection, bool(options.get("retry")), emit, cancel)
            if action == "run":
                return self._run(target, connection, sensorless, emit, cancel, on_start)
            if action == "stop":
                return self._stop(target, connection, emit, cancel)
            if action == "shutdown":
                return self._shutdown(target, connection, emit, cancel)
            if action == "values" and target == "qemu":
                return self._stream(["bash", "scripts/project.sh", "values"], emit, cancel, timeout=30)
            raise HardwareError("Unsupported hardware action: " + str(action))
        finally:
            if execution_lock:
                execution_lock.close()
            self._lock.release()

    def _logs(self, target, connection, kind, tail, emit, cancel):
        """Follow the flight software output, or the Linux boot log when kind is "boot"."""
        if target == "native":
            log = self.runtime / "native.log"
            if not log.exists():
                raise HardwareError("Run native cFS before opening its output.")
            return self._stream(["tail", "-n", "100", "-F", str(log)], emit, cancel)
        if kind == "boot" and target == "qemu":
            return self._stream(["bash", "logs.sh", "--tail", str(tail)], emit, cancel)
        argv = self.ssh_argv(target, connection)
        if kind == "boot":
            return self._stream(argv + ["journalctl -b -n 100 -f -o short-monotonic"], emit, cancel)
        if target == "physical":
            command = "sudo -n journalctl -u cfs-studio.service -n 100 -f -o cat"
        else:
            command = "journalctl -u cfs.service -n 100 -f -o cat"
        return self._stream(argv + [command], emit, cancel)

    def _simulate(self, action, target, device, model, emit, cancel):
        """Write synthetic sensor values to QEMU, or print a local preview for simulate-preview."""
        preview = action == "simulate-preview"
        if not preview and target != "qemu":
            raise HardwareError("Sensor simulation is only available on QEMU.")
        if model is not None:
            from sensors.simulator import simulation_scripts
            if not preview or model not in simulation_scripts(self.root):
                raise HardwareError("Select a Python sensor model to preview.")
            return self._stream([sys.executable, "-u", "-m", "sensors." + model, "--steps", "8"], emit, cancel)
        self.simulation_script(device)
        if not preview and not self._qemu_running():
            raise HardwareError("Boot QEMU Linux before running synthetic data.")
        if preview:
            command = [sys.executable, "-u", "-m", "sensors.session", "--dry-run", "--steps", "8", "--events"]
            if device is not None:
                command += ["--device", device]
        elif device is not None:
            command = [sys.executable, "-u", "-m", "sensors.simulator", device]
        else:
            command = [sys.executable, "-u", "-m", "sensors.session", "--events"]
        return self._stream(command, emit, cancel)

    def _build(self, target, sensorless, emit, cancel):
        if target == "native" and self._local_flight_state()["running"]:
            raise HardwareError("Stop native cFS before replacing its installed binaries.")
        if not sensorless:
            self._stream([sys.executable, "project/manage.py", "sync"], emit, cancel)
        source = self.fingerprint()
        root = self._sensorless_root(emit) if sensorless else self.root
        self._stream(["bash", "scripts/build-cfs.sh", "--target", target], emit, cancel, cwd=root)
        # An edit saved while compiling is not in these binaries.
        if self.fingerprint() != source:
            raise HardwareError("Sources changed during the build; build again.")
        state = {"fingerprint": source, "built_at": time.time(), "sensorless": sensorless, "target": target, "build_dir": self.build_directory(target)}
        self._save(self.build_state_file(target, sensorless), state)
        return state

    def _boot(self, target, connection, retry, emit, cancel):
        """Start QEMU Linux with cFS stopped, or confirm that the board's Linux answers over SSH."""
        qemu_retry = self.assert_can_boot(retry) if target == "qemu" else False
        if target == "physical":
            connection = self.connection(connection)
            try:
                self.probe(connection, emit, cancel)
            except HardwareError as error:
                if not str(error).startswith("SSH failed"):
                    raise
                message = "Linux is not reachable on this board. Power it on with the selected OS and SSH enabled; SSH cannot power on a board that is off. " + str(error)
                raise HardwareError(message) from error
        if not qemu_retry:
            self._switch_target(target, connection, emit, cancel)
        if target == "physical":
            emit("Linux is already booted and reachable over SSH. Use Run cFS to start the flight software.")
            result = dict(self._last_probe, linux_ready=True)
        elif qemu_retry:
            self._stream(self.ssh_argv() + ["true"], emit, cancel, timeout=20)
            emit("QEMU Linux connection restored.")
            result = {"linux_ready": True}
        else:
            self._stream(["bash", "boot.sh"], emit, cancel, timeout=660)
            self._stop_qemu(emit, cancel)
            result = {"linux_ready": True}
        self._save_active(target, connection, "ready")
        return result

    def _run(self, target, connection, sensorless, emit, cancel, on_start):
        self.assert_can_start(target, connection)
        self._require_build(sensorless, target=target)
        if on_start:
            on_start()
        if target == "physical":
            connection = self.connection(connection)
            self.probe(connection, emit, cancel)
        self._save_active(target, connection, "starting")
        if target == "native":
            result = self._run_native(emit, cancel)
        elif target == "physical":
            result = self._run_physical(emit, cancel, connection, sensorless)
        else:
            result = self._run_qemu(emit, cancel)
        self._save_active(target, connection, "running")
        return result

    def _stop_qemu(self, emit, cancel):
        self._stream(self.ssh_argv() + ["systemctl stop cfs.service && ! pgrep -x core-cpu1"], emit, cancel, timeout=30)

    def _stop(self, target, connection, emit, cancel):
        if target == "native":
            self._stop_native(emit)
        elif target == "physical":
            connection = self.connection(connection)
            self._stop_physical(connection, emit, cancel)
        else:
            self._stop_qemu(emit, cancel)
        self._mark_stopped(target, connection)
        return {"stopped": True}

    def _shutdown(self, target, connection, emit, cancel):
        """Power off QEMU and wait for it to exit, or request the board's Linux poweroff."""
        if target == "qemu":
            self._wait_qemu_stopped(emit, cancel)
            self._mark_stopped(target)
            return {"stopped": True}
        connection = self.connection(connection)
        argv = self.ssh_argv(target, connection)
        code, _ = self._capture(argv + ["sudo -n -l systemctl poweroff --no-block"], 15)
        if code:
            raise HardwareError("Linux shutdown is not authorized or SSH is unavailable. Open the board connection to check access and update its authorization.")
        self._stop_physical(connection, emit, cancel)
        self._mark_stopped(target, connection)
        emit("Requesting Linux shutdown over SSH...")
        self._stream(argv + ["sudo -n systemctl poweroff --no-block"], emit, cancel, timeout=20)
        self._physical_observation = None
        emit("Linux accepted the shutdown request. SSH will disconnect as the board powers off.")
        return {"shutdown_requested": True}
