"""Local deployment adapter for the existing cFS scripts and Raspberry Pi OS.

HardwareManager.execute is blocking: run it in a job worker and pass emit(line)
and an optional threading.Event as cancel. No passwords or private keys are read.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
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
        config = json.loads((self.root / "project/config.json").read_text())
        return "native" if config.get("board") is None and config.get("os") is None else "qemu"

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
    def _capture(argv, timeout=10):
        try:
            result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
            return result.returncode, (result.stdout + result.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as error:
            return 1, str(error)

    def _stream(self, argv, emit, cancel=None, cwd=None, timeout=None, stdin=None):
        """Forward real output, including carriage-return progress, without shell input."""
        emit("$ " + shlex.join(str(arg) for arg in argv))
        started = time.monotonic()
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
        # Never hang an HTTP job on a hidden sudo/password prompt.
        env["SUDO_ASKPASS"] = "/bin/false"
        with subprocess.Popen(argv, cwd=cwd or self.root, env=env,
                              stdin=stdin if stdin is not None else subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              start_new_session=True) as process:
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
        """Include source edits, not just app manifests as check-build currently does."""
        paths = []
        for directory in ("cFS", "project"):
            for base, dirs, files in os.walk(self.root / directory):
                dirs[:] = sorted(d for d in dirs if d != ".git" and d != "__pycache__"
                                 and not d.startswith("build") and not (Path(base) / d).is_symlink())
                for name in sorted(files):
                    path = Path(base) / name
                    if path.suffix.lower() in {".md", ".rst"}:
                        continue
                    if path.parent == self.root / "project/generated" and name in {"build.json", "build-native.json", "build-flight.json"}:
                        continue  # Build output must not invalidate its own source fingerprint.
                    if name != ".git" and not path.is_symlink() and not name.endswith(".pyc"):
                        paths.append(path)
        paths.append(self.root / "scripts/build-cfs.sh")
        if self.default_target() != "native":
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
        return {"host": host, "user": user, "port": port}

    def ssh_argv(self, target="qemu", connection=None):
        argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]
        if target == "qemu":
            return argv + ["-F", str(Path.home() / ".ssh/cfs-emulator/config"), "pi4-cfs"]
        if target != "physical":
            raise HardwareError("Invalid target.")
        config = self.connection(connection)
        # OpenSSH's normal config, agent and known_hosts remain authoritative.
        # accept-new enrolls new hosts but refuses changed host keys.
        argv += ["-o", "StrictHostKeyChecking=accept-new"]
        if config["port"] != 22:
            argv += ["-p", str(config["port"])]
        if config["user"]:
            argv += ["-l", config["user"]]
        return argv + [config["host"]]

    def _physical_status(self):
        """Refresh only service reachability; saved hardware discovery is not live state."""
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
            result = dict(previous or {}, observed_at=time.time(),
                          service=flight['service'], flight_running=flight['running'], pids=flight['pids'],
                          connected=True if recognized else None)
            result['observation_error'] = flight.get('error')
            self._physical_observation = (connection, time.monotonic(), result)
            return dict(result)

    def _local_flight_state(self):
        """Only native binaries inside this checkout belong to this workspace."""
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
            process = subprocess.Popen(argv, cwd=payload, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
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
        code, output = self._capture(self.ssh_argv(target, connection) + [
            'python3 -c ' + shlex.quote(script) + ' ' + shlex.quote(service)], 8)
        try:
            state = json.loads(output) if not code else None
            if not isinstance(state, dict) or set(state) != {'service', 'pids', 'running'}:
                raise ValueError('Invalid state')
            return dict(state, reachable=True)
        except (ValueError, TypeError):
            return {'service': 'unknown', 'pids': [], 'running': None,
                    'reachable': code == 0, 'error': output or 'SSH unavailable'}

    def assert_can_start(self, target=None, connection=None):
        """Fresh process checks, under execution.lock, before any deployment mutation."""
        checks = [('this workspace on the local host', self._local_flight_state())]
        target = target or self.default_target()
        deployed = self._load('deployed.json', {})
        running = self._qemu_running()
        if running:
            checks.append(('the emulator', self._flight_state('qemu')))
        elif running is None and (target == 'qemu' or deployed.get('qemu') and not deployed['qemu'].get('stopped_at')):
            checks.append(('the emulator', {'running': None}))
        connections = []
        previous = self._load('active.json', {})
        physical_active = deployed.get('physical') and not deployed['physical'].get('stopped_at')
        for candidate in (connection if target == 'physical' else None,
                          self._load('connection.json') if self.default_target() != 'native' else None,
                          deployed.get('physical', {}).get('connection') if physical_active else None,
                          previous.get('connection') if previous.get('target') == 'physical' and previous.get('phase') != 'stopped' else None):
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
            if config.get("board") is not None or config.get("os") is not None:
                raise HardwareError("Select the native profile without a board to run on this computer.")
            return {"board": None, "os": None}
        selected = (board or config["board"], os or config["os"])
        if not any((p["board"], p["os"]) == selected and target in p["targets"] for p in self.profiles()):
            raise HardwareError("This board and operating system do not have a validated build profile.")
        if selected != (config["board"], config["os"]):
            raise HardwareError("The selected board and operating system do not match the mission configuration.")
        return {"board": selected[0], "os": selected[1]}

    def _qemu_running(self):
        code, output = self._capture(["docker", "inspect", "--format", "{{.State.Running}}", "pi4-cfs"], 5)
        if not code and output in {"true", "false"}:
            return output == "true"
        if "no such object" in output.lower() or "no such container" in output.lower():
            return False
        return None

    def assert_can_boot(self, retry=False):
        """Check the existing emulator before boot or an explicit SSH retry."""
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
            # The guest normally closes SSH during poweroff. Other command errors
            # must remain visible instead of being hidden behind a later timeout.
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
        if any(line in {"active", "activating", "deactivating", "reloading"} for line in lines):
            emit("Stopping cFS on the board...")
            self._stream(argv + ["sudo -n systemctl stop cfs-studio.service"], emit, cancel, timeout=30)
            code, output = self._capture(argv + [check], 15)
            lines = output.splitlines()
        if code or not lines or lines[-1] != "process-stopped" or any(line in {"active", "activating", "deactivating", "reloading"} for line in lines):
            raise HardwareError("cFS is still running on the physical board. Stop any unmanaged core-cpu1 process before switching targets.")
        self._physical_observation = None
        emit("Board cFS is stopped; its Linux remains on.")

    def _switch_target(self, target, connection, emit, cancel=None):
        previous = self._load("active.json", {})
        deployed = self._load("deployed.json", {})
        physical = []
        for candidate in (previous.get("connection") if previous.get("target") == "physical" else None,
                          deployed.get("physical", {}).get("connection"), self._load("connection.json")):
            if candidate and candidate not in physical and (target == "qemu" or candidate != connection):
                physical.append(candidate)
        for candidate in physical:
            required = (previous.get("target") == "physical" and previous.get("phase") != "stopped"
                        and candidate == previous.get("connection")) or (not previous and candidate == deployed.get("physical", {}).get("connection"))
            self._stop_physical(candidate, emit, cancel, required)
        if target == "physical":
            running = self._qemu_running()
            required = previous.get("target") == "qemu" and previous.get("phase") != "stopped" or not previous and bool(deployed.get("qemu"))
            if running is not False and (running is not None or required):
                emit("Stopping the emulator before starting cFS on the board.")
                try:
                    self._wait_qemu_stopped(emit, cancel)
                except HardwareError as error:
                    raise HardwareError(f"Cannot start on the board: {error}") from error
        if cancel and cancel.is_set():
            raise HardwareError("Target switch cancelled.")
        # Write before starting: interrupted deployments can leave a live service.
        self._save("active.json", {"target": target, "connection": connection,
                                    "phase": "starting", "updated_at": time.time()})

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
        code, docker = self._capture(["docker", "info", "--format", "{{.ServerVersion}}"], 3)
        running = None
        service = None
        flight_running = None
        linux_ready = None
        boot_error = None
        if not code:
            running = self._qemu_running()
            if running:
                flight = self._flight_state('qemu')
                service, flight_running = flight['service'], flight['running']
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
        if flight_running is None and not qemu_active:
            flight_running = False
        states = {'qemu': {'running': flight_running, 'pids': flight.get('pids', []) if running else []},
                  'native': local}
        if physical:
            states['physical'] = {'running': physical.get('flight_running'), 'pids': physical.get('pids', [])}
        targets = [target for target, state in states.items() if state['running']]
        unknown = [target for target, state in states.items() if state['running'] is None]
        labels = {'qemu': 'the emulator', 'physical': 'the physical board', 'native': 'this workspace on the local host'}
        reason = ('cFS is already running on ' + ', '.join(labels[t] for t in targets) + '. Stop it before starting another instance.' if targets else
                  'Cannot confirm cFS state on ' + ', '.join(labels[t] for t in unknown) + '.' if unknown else '')
        preferred = active.get("target") if active.get("target") in targets else default_target
        builds = {}
        for target in ("native", "qemu", "physical"):
            build = self.build_state(target)
            no_sensors = self.build_state(target, True)
            builds[target] = {"exists": (self.root / self.build_directory(target) / "exe/cpu1/core-cpu1").is_file(),
                              "current": build.get("fingerprint") == fingerprint,
                              "fingerprint": fingerprint,
                              "sensorless_current": no_sensors.get("fingerprint") == fingerprint}
        return {"board": config["board"], "os": config["os"], "profiles": self.profiles(),
                "execution": {"target": targets[0] if len(targets) == 1 else None,
                              "preferred_target": preferred, "conflict": sum(max(1, len(states[t]['pids'])) for t in targets) > 1,
                              "can_start": not targets and not unknown, "block_reason": reason, "running_targets": targets},
                "tools": {tool: bool(shutil.which(tool)) for tool in ("docker", "ssh", "scp", "make", "cmake", "cc")},
                "native": dict(local, log_path="hardware/.runtime/native.log"),
                "docker": {"available": code == 0, "error": docker if code else None},
                "qemu": {"running": running, "service": service, "flight_running": flight_running,
                         "linux_ready": linux_ready, "can_boot": running is False,
                         "can_retry_boot": running is True and linux_ready is False,
                         "boot_error": boot_error,
                         "ssh_configured": (Path.home() / ".ssh/cfs-emulator/config").is_file()},
                "build": builds[default_target], "builds": builds,
                "physical": {"connection": self._load("connection.json"), "candidates": self.ssh_candidates(),
                             "last_probe": physical},
                "deployed": deployed}

    def probe(self, connection=None, emit=lambda line: None, cancel=None):
        argv = self.ssh_argv("physical", connection)
        # JSON avoids locale-dependent parsing of diagnostic tools.
        script = '''import json,os,platform,subprocess,pathlib,shutil,pwd
p=pathlib.Path('/proc/device-tree/model')
def run(args):
 r=subprocess.run(args,capture_output=True,text=True);return {'ok':r.returncode==0,'output':r.stdout.strip()}
print(json.dumps({'arch':platform.machine(),'model':p.read_bytes().decode().strip('\\x00') if p.exists() else '', 'home':os.path.expanduser('~'),'hostname':platform.node(),'i2c':sorted(str(x) for x in pathlib.Path('/dev').glob('i2c-*')),'sudo':run(['sudo','-n','true'])['ok'],'authorized':run(['sudo','-n','-l','systemctl','start','cfs-studio.service'])['ok'],'shutdown_authorized':run(['sudo','-n','-l','systemctl','poweroff','--no-block'])['ok'],'service_installed':pathlib.Path('/etc/systemd/system/cfs-studio.service').is_file() and pathlib.Path('/etc/systemd/system/cfs-studio.service').read_text().startswith('# Flight Studio managed; account='+pwd.getpwuid(os.getuid()).pw_name+'\\n'),'service':run(['systemctl','is-active','cfs-studio.service'])['output'],'systemd':bool(shutil.which('systemd-run')),'os':platform.freedesktop_os_release().get('PRETTY_NAME',''),'raspios':pathlib.Path('/etc/rpi-issue').exists()}))'''
        code, output = self._capture(argv + ["python3 -c " + shlex.quote(script)], 20)
        if code:
            raise HardwareError("SSH failed. Check that the board is on the same network and the key is authorized. " + output)
        try:
            result = json.loads(next(line for line in reversed(output.splitlines()) if line.startswith("{")))
        except (ValueError, IndexError, StopIteration):
            raise HardwareError("Invalid SSH response: " + output) from None
        if "Raspberry Pi 4 Model B" not in result["model"] or result["arch"] != "aarch64" or not result["raspios"]:
            raise HardwareError("The platform supports Raspberry Pi 4B with Raspberry Pi OS ARM64: " + str(result))
        result["connected"] = True
        result["checked_at"] = time.time()
        self._save("connection.json", self.connection(connection))
        result["ready"] = result["authorized"] and result["service_installed"]
        result["service_ready"] = result["ready"]
        self._last_probe = result
        self._save("probe.json", result)
        self._physical_observation = None
        emit(f"SSH connected: {result['model']} · {result['arch']} · cFS {result['service']}")
        return result

    def prepare_board(self, connection=None, emit=print, cancel=None, authorize=None):
        board = self.probe(connection, emit, cancel)
        remote = board["home"] + "/cfs-arm64/studio/setup_board.py"
        command = "mkdir -p " + shlex.quote(str(Path(remote).parent)) + " && cat > " + shlex.quote(remote)
        with (self.root / "hardware/setup_board.py").open("rb") as source:
            self._stream(self.ssh_argv("physical", connection) + [command], emit, cancel, stdin=source, timeout=30)
        argv = self.ssh_argv("physical", connection)
        host = argv[-1]
        config = self.connection(connection)
        interactive = ["ssh", "-t"]
        if config["port"] != 22:
            interactive += ["-p", str(config["port"])]
        if config["user"]:
            interactive += ["-l", config["user"]]
        interactive += [host, "sudo python3 " + shlex.quote(remote)]
        if authorize is None:
            authorize = board["sudo"]
        result = {"setup_command": shlex.join(interactive), "script": remote, "setup_required": not authorize}
        if authorize:
            self._stream(argv + ["sudo -n python3 " + shlex.quote(remote)], emit, cancel, timeout=30)
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
        for name in removed:
            self._stream([sys.executable, str(destination / "project/appgen/appgen.py"),
                          "--root", str(destination / "cFS"), "delete-app", name], emit, cwd=destination)
        config["apps"] = [app for app in config["apps"] if app["name"] not in removed]
        config["devices"] = []
        (destination / "project/config.json").write_text(json.dumps(config, indent=2) + "\n")
        # Hardware owns sensor-library inclusion independently of app bindings.
        # Refresh generated dependencies after clearing this isolated profile.
        self._stream([sys.executable, str(destination / "project/manage.py"), "sync"], emit, cwd=destination)
        startup = destination / "cFS/sample_defs/cpu1_cfe_es_startup.scr"
        if startup.exists():
            updated = reconcile_removed_modules(startup.read_text(), removed)
            updated = reconcile_generated_modules(updated, previous_fragment,
                                                   fragment.read_text() if fragment.exists() else "")
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
            raise HardwareError("Incomplete ARM64 payload. Build again.")
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
        remote = board["home"] + "/cfs-arm64/releases/" + release
        # Upload to a staging release without touching any running service.
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode="w") as tar:
                tar.add(payload, arcname="cpu1")
            archive.seek(0)
            self._stream(argv + ["mkdir -p " + shlex.quote(remote) + " && tar -xmf - -C " + shlex.quote(remote)],
                         emit, cancel, stdin=archive, timeout=180)
        current = board["home"] + "/cfs-arm64/studio/current"
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
        code, output = self._capture(["docker", "inspect", "--format", "{{.State.Running}}", "pi4-cfs"], 3)
        if code or output != "true":
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
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode="w") as tar:
                tar.add(payload, arcname=".")
            archive.seek(0)
            self._stream(argv + ["mkdir -p " + shlex.quote(staging) + " && tar -xmf - -C " + shlex.quote(staging)],
                         emit, cancel, stdin=archive, timeout=180)
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
            if target == "native":
                log = self.runtime / "native.log"
                if not log.exists():
                    raise HardwareError("Run native cFS before opening its output.")
                return self._stream(["tail", "-n", "100", "-F", str(log)], emit, cancel)
            argv = self.ssh_argv(target, connection)
            service = "cfs-studio.service" if target == "physical" else "cfs.service"
            command = ("sudo -n " if target == "physical" else "") + f"journalctl -u {service} -n 100 -f -o cat"
            if options.get("kind") == "boot":
                if target == "qemu":
                    return self._stream(["bash", "logs.sh", "--tail", str(options.get("tail", 100))], emit, cancel)
                return self._stream(argv + ["journalctl -b -n 100 -f -o short-monotonic"], emit, cancel)
            return self._stream(argv + [command], emit, cancel)
        if action in {"simulate", "simulate-preview"}:
            if action == "simulate" and target != "qemu":
                raise HardwareError("Sensor simulation is only available on QEMU.")
            model = options.get("model")
            if model is not None:
                from sensors.simulator import simulation_scripts
                if action != "simulate-preview" or model not in simulation_scripts(self.root):
                    raise HardwareError("Select a Python sensor model to preview.")
                return self._stream([sys.executable, '-u', '-m', 'sensors.' + model, '--steps', '8'], emit, cancel)
            self.simulation_script(options.get("device"))
            if action == "simulate" and not self._qemu_running():
                raise HardwareError("Boot QEMU Linux before running synthetic data.")
            device = options.get('device')
            if action == "simulate-preview":
                command = [sys.executable, '-u', '-m', 'sensors.session', '--dry-run', '--steps', '8', '--events']
                if device is not None:
                    command += ['--device', device]
            else:
                command = [sys.executable, '-u', '-m', 'sensors.simulator', device] if device is not None else [sys.executable, '-u', '-m', 'sensors.session', '--events']
            return self._stream(command, emit, cancel)
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
            qemu_retry = self.assert_can_boot(bool(options.get('retry'))) if action == 'boot' and target == 'qemu' else False
            if action in {"boot", "run"}:
                if action == "run":
                    self.assert_can_start(target, connection)
                    self._require_build(sensorless, target=target)
                    if on_start:
                        on_start()
                if target == "physical":
                    connection = self.connection(connection)
                    try:
                        self.probe(connection, emit, cancel)
                    except HardwareError as error:
                        if action == "boot" and str(error).startswith("SSH failed"):
                            raise HardwareError("Linux is not reachable on this board. Power it on with the selected OS and SSH enabled; SSH cannot power on a board that is off. " + str(error)) from error
                        raise
                if action == 'boot' and not qemu_retry:
                    self._switch_target(target, connection, emit, cancel)
                elif action == 'run':
                    self._save('active.json', {'target': target, 'connection': connection, 'phase': 'starting', 'updated_at': time.time()})
            if action == "setup":
                if target == "physical":
                    return self.prepare_board(connection, emit, cancel)
                return self._stream(["bash", "scripts/setup.sh"], emit, cancel)
            if action == "build":
                if target == "native" and self._local_flight_state()["running"]:
                    raise HardwareError("Stop native cFS before replacing its installed binaries.")
                if not sensorless:
                    self._stream([sys.executable, "project/manage.py", "sync"], emit, cancel)
                source = self.fingerprint()
                root = self._sensorless_root(emit) if sensorless else self.root
                self._stream(["bash", "scripts/build-cfs.sh", "--target", target], emit, cancel, cwd=root)
                # A saved edit during the build must never be marked as compiled.
                final = self.fingerprint()
                state = {"fingerprint": source if sensorless else final, "built_at": time.time(),
                         "sensorless": sensorless, "target": target, "build_dir": self.build_directory(target)}
                if source != final:
                    raise HardwareError("Sources changed during the build; build again.")
                self._save(self.build_state_file(target, sensorless), state)
                return state
            if action == "boot":
                if target == "physical":
                    emit("Linux is already booted and reachable over SSH. Use Run cFS to start the flight software.")
                    result = dict(self._last_probe, linux_ready=True)
                elif qemu_retry:
                    self._stream(self.ssh_argv() + ["true"], emit, cancel, timeout=20)
                    emit("QEMU Linux connection restored.")
                    result = {"linux_ready": True}
                else:
                    self._stream(["bash", "boot.sh"], emit, cancel, timeout=660)
                    self._stream(self.ssh_argv() + ["systemctl stop cfs.service && ! pgrep -x core-cpu1"], emit, cancel, timeout=30)
                    result = {"linux_ready": True}
                self._save("active.json", {"target": target, "connection": connection,
                                            "phase": "ready", "updated_at": time.time()})
                return result
            if action == "run":
                if target == "native":
                    result = self._run_native(emit, cancel)
                elif target == "physical":
                    result = self._run_physical(emit, cancel, connection, sensorless)
                else:
                    result = self._run_qemu(emit, cancel)
                self._save("active.json", {"target": target, "connection": connection,
                                            "phase": "running", "updated_at": time.time()})
                return result
            if action == "stop":
                if target == "native":
                    self._stop_native(emit)
                elif target == "physical":
                    connection = self.connection(connection)
                    self._stop_physical(connection, emit, cancel)
                else:
                    self._stream(self.ssh_argv() + ["systemctl stop cfs.service && ! pgrep -x core-cpu1"], emit, cancel, timeout=30)
                self._mark_stopped(target, connection)
                return {"stopped": True}
            if action == "shutdown":
                if target == "qemu":
                    self._wait_qemu_stopped(emit, cancel)
                    self._mark_stopped(target)
                    return {"stopped": True}
                connection = self.connection(connection)
                code, _ = self._capture(self.ssh_argv(target, connection) + ["sudo -n -l systemctl poweroff --no-block"], 15)
                if code:
                    raise HardwareError("Linux shutdown is not authorized or SSH is unavailable. Open the board connection to check access and update its authorization.")
                self._stop_physical(connection, emit, cancel)
                self._mark_stopped(target, connection)
                emit("Requesting Linux shutdown over SSH...")
                self._stream(self.ssh_argv(target, connection) + ["sudo -n systemctl poweroff --no-block"], emit, cancel, timeout=20)
                self._physical_observation = None
                emit("Linux accepted the shutdown request. SSH will disconnect as the board powers off.")
                return {"shutdown_requested": True}
            if action == "values" and target == "qemu":
                return self._stream(["bash", "scripts/project.sh", "values"], emit, cancel, timeout=30)
            raise HardwareError("Unsupported hardware action: " + str(action))
        finally:
            if execution_lock:
                execution_lock.close()
            self._lock.release()
