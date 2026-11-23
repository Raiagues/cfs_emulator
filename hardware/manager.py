"""Build, deployment and runtime control for the native, QEMU and physical targets.

HardwareManager.execute is blocking: run it in a job worker and pass emit(line)
and an optional threading.Event as cancel. SSH runs in batch mode with the
user's OpenSSH configuration and agent, and sudo never prompts for a password.
"""
from __future__ import annotations

from contextlib import ExitStack
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
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time


from hardware import boot_trace
from hardware.readiness import StartupError, wait_native
from hardware.targets import selected_target
from hardware.state import RuntimeState, Selection
from project.defaults import BOARD_DIRECTORY, BOARD_PORT, boot_timeout, network
from journey import Store
from journey import mission as evidence


# Every field hardware/board_probe.py reports, with its JSON type.
PROBE_FIELDS = {"arch": str, "glibc": str, "model": str, "home": str, "hostname": str, "i2c": list, "sudo": bool,
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
        self.state = RuntimeState(self.root)
        self.runtime = self.state.directory
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.journey = Store(self.root)
        self._import_boot_receipts()
        self._fingerprint_cache = None
        self._last_probe = self.state.read("probe.json")
        self._observation_lock = threading.Lock()
        self._flight_observations = {}

    def _import_boot_receipts(self):
        """Older releases retained boot observations with time and invocation, before the event log."""
        for target in ("native", "qemu", "physical"):
            receipt = self.state.read("operational-" + target + ".json", {})
            stamp, run = receipt.get("time"), receipt.get("run_id")
            if not run or not stamp or "OPERATIONAL" not in receipt.get("flight", {}).get("states", []):
                continue
            if not any(event.ref.get("run") == run for event in self.journey.events(target)):
                self.journey.observe(target, "boot", {"run": run}, stamp)
                if target == "physical":
                    self.journey.observe(target, "board", {"run": run}, stamp)

    def select_target(self, target, *, board_visit=False):
        if not isinstance(target, str) or target not in {"native", "qemu", "physical"}:
            raise HardwareError("Invalid execution target.")
        saved = {"target": target}
        if board_visit:
            from hardware.infrastructure import checks_verified
            if target != "physical" or not checks_verified(self, target, self.state.read("checks-physical.json", {})):
                raise HardwareError("Check the board connection before using this board.")
            previous = self.state.read("target.json", {})
            saved["journey_origin"] = previous.get("journey_origin") or previous.get("target") or target
        self.state.choose(Selection(**saved))
        return {"target": target}

    @staticmethod
    def build_directory(target):
        return "mission/build-native" if target == "native" else "mission/build-flight"

    @staticmethod
    def build_state_file(target, sensorless=False):
        profile = "native" if target == "native" else "flight"
        return "build-" + profile + ("-sensorless" if sensorless else "") + ".json"

    def build_state(self, target, sensorless=False):
        return self.state.read(self.build_state_file(target, sensorless), {})

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
            last_line = ""
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
                            message = line.decode("utf-8", "replace")
                            last_line = message.strip() or last_line
                            emit(message)
                if pending:
                    last_line = pending.decode("utf-8", "replace")
                    emit(last_line)
                code = process.wait(timeout=5)
                if code:
                    raise HardwareError(last_line or f"Command exited with code {code}.", returncode=code)
            finally:
                selector.close()
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()

    def builds_status(self):
        fingerprint = self.fingerprint()
        builds = {}
        for target in ("native", "qemu", "physical"):
            build = self.build_state(target)
            no_sensors = self.build_state(target, True)
            exists = (self.root / self.build_directory(target) / "exe/cpu1/core-cpu1").is_file()
            recorded = build.get("fingerprint")
            builds[target] = {"exists": exists, "current": exists and recorded == fingerprint,
                              "stale": exists and bool(recorded) and recorded != fingerprint,
                              "fingerprint": fingerprint,
                              "sensorless_current": no_sensors.get("fingerprint") == fingerprint}
        return builds

    def fingerprint(self):
        """SHA-256 of every source file a build reads.

        Documentation, build output and the sensor values in project/config.json
        do not change it.
        """
        paths = []
        for directory in ("cFS", "mission", "project"):
            for base, dirs, files in os.walk(self.root / directory):
                if Path(base) == self.root / "mission":
                    # prepare() and the portability tests stage independent checkouts here.
                    dirs[:] = [d for d in dirs if not d.startswith(".prepare-")]
                    files = [name for name in files if name != ".prepare.lock"]
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
                # Bus activation and header wiring configure the board. Only mapped readers
                # and their generated sources change the compiled software.
                config.pop("buses", None)
                bound = {device for app in config["apps"] for device in app["sensors"].values()}
                config["devices"] = [device for device in config["devices"] if device["id"] in bound]
                for device in config.get("devices", []):
                    device.pop("values", None)
                    device.pop("pins", None)
                    device.pop("name", None)
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
        saved = self.state.read("connection.json")
        if saved:
            candidates.insert(0, dict(saved, source="saved"))
        return candidates

    def connection(self, value=None):
        value = value or self.state.read("connection.json", {})
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
            port = int(value.get("port", BOARD_PORT))
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
        directory = value.get("directory", BOARD_DIRECTORY)
        if not isinstance(directory, str):
            raise HardwareError("Invalid board installation folder.")
        directory = directory.strip().removeprefix("~/").rstrip("/")
        if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_./-]*", directory) or any(p in {".", ".."} for p in directory.split("/")):
            raise HardwareError("Choose an installation folder inside the board user's home, without '..'.")
        directory = str(Path(directory))
        if directory != BOARD_DIRECTORY:
            result["directory"] = directory
        return result

    def same_board(self, first, second):
        """An SSH identity authenticates a connection. The host and mission path identify its deployment."""
        if not first or not second:
            return first == second
        def destination(value):
            normalized = self.connection(value)
            return (normalized["host"].lower(), normalized["port"], normalized["user"], normalized.get("directory", BOARD_DIRECTORY))
        return destination(first) == destination(second)

    def ssh_argv(self, target="qemu", connection=None, interactive=False, *, connect_timeout=8):
        argv = ["ssh", "-t" if interactive else "-T", "-o", f"ConnectTimeout={connect_timeout}",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]
        if not interactive:
            argv += ["-o", "BatchMode=yes"]
        if target == "qemu":
            from hardware.infrastructure import emulator_config
            from hardware.emulator_ssh import ssh_options
            return argv + ssh_options(self.root, emulator_config(self.root)["ssh_port"])
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

    def agent_command(self, target, connection, operation, *args, connect_timeout=8):
        remote = shlex.join(["python3", "-u", "-", operation, json.dumps(args)])
        return self.ssh_argv(target, connection, connect_timeout=connect_timeout) + [remote]

    def remote_operation(self, target, connection, operation, args, emit, cancel=None, timeout=30):
        with Path(__file__).with_name("remote_agent.py").open("rb") as agent:
            return self._stream(self.agent_command(target, connection, operation, *args), emit, cancel,
                                stdin=agent, timeout=timeout)

    def copy_to(self, target, connection, source, destination, emit, cancel=None):
        ssh = self.ssh_argv(target, connection)
        # scp and ssh use different option letters for port and user.
        options = iter(ssh[2:-1])
        arguments = ["scp", "-q"]
        for option in options:
            value = next(options)
            if option == "-l":
                arguments.extend(["-o", "User=" + value])
            else:
                arguments.extend(["-P" if option == "-p" else option, value])
        host = ssh[-1]
        if ":" in host:
            host = "[" + host + "]"
        self._stream([*arguments, "--", str(source), host + ":" + destination], emit, cancel, timeout=180)

    def upload(self, target, connection, directory, files, emit, cancel):
        self.remote_operation(target, connection, "directory", [directory, True], emit, cancel)
        with tempfile.NamedTemporaryFile(dir=self.runtime, suffix=".tar") as archive:
            with tarfile.open(fileobj=archive, mode="w") as tar:
                for source, name in files:
                    tar.add(source, arcname=name)
            archive.flush()
            self.copy_to(target, connection, archive.name, directory + "/.flight-upload.tar", emit, cancel)
        self.remote_operation(target, connection, "unpack", [directory], emit, cancel, timeout=180)

    def board_directory(self, board, connection=None):
        return board["home"] + "/" + self.connection(connection).get("directory", BOARD_DIRECTORY)

    def observed_flight(self, target, connection=None):
        """Share the last remote probe across status views; startup guards always check afresh."""
        with self._observation_lock:
            cached = self._flight_observations.get(target)
            if cached and cached[0] == connection and time.monotonic() - cached[1] < 3:
                return cached[2]
            flight = dict(self._flight_state(target, connection), observed_at=time.time())
            self._flight_observations[target] = (connection, time.monotonic(), flight)
            return flight

    def _invalidate_observation(self, target):
        with self._observation_lock:
            self._flight_observations.pop(target, None)

    def _physical_status(self):
        previous = self.state.read("probe.json", self._last_probe)
        connection = self.state.read("connection.json")
        if not connection:
            return None
        flight = self.observed_flight("physical", connection)
        result = dict(previous or {})
        result.update(observed_at=flight["observed_at"], service=flight['service'], flight_running=flight['running'], pids=flight['pids'])
        result['connected'] = True if flight['running'] is not None else None
        result['observation_error'] = flight.get('error')
        return result

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
                if executable.is_relative_to(self.root / 'mission/build-native'):
                    pids.append(int(pid))
            except (OSError, RuntimeError):
                continue
        return {'running': bool(pids), 'pids': pids, 'service': 'native'}

    def _native_command_port(self, state):
        from ground_station.catalog import CATALOG_VERSION, build_catalog
        cached = self.state.read("catalog-native-" + state["fingerprint"] + ".json", {})
        if cached.get("catalog_version") != CATALOG_VERSION:
            cached = build_catalog(self.root, build_dir=state["build_dir"])
        transport = cached.get("transport") or {}
        if "command_port" not in transport:
            raise HardwareError("Cannot read the CI_LAB command port from this build: " + ", ".join(cached.get("errors", [])))
        return transport["command_port"]

    def _run_native(self, emit, cancel):
        _, payload, state = self._require_build(target="native")
        self.assert_can_start("native")
        port = self._native_command_port(state)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind(("", port))
            except OSError as error:
                raise HardwareError(f"CI_LAB cannot bind UDP port {port}: {error.strerror}. Stop the process using it.") from error
        argv = [str(payload / "core-cpu1")]
        if shutil.which("stdbuf"):
            argv = ["stdbuf", "-oL", "-eL", *argv]
        emit("$ " + shlex.join(argv))
        log = self.runtime / "native.log"
        started = time.time()
        from sensors.registers import prepare
        env = dict(os.environ, FLIGHT_STUDIO_NATIVE_DEVICES=str(prepare(self.root)))
        from hardware.native_ipc import NativeIPC
        ipc = NativeIPC(self.root)
        prepared = ipc.prepare(payload, state["fingerprint"])
        with log.open("wb") as output:
            process = subprocess.Popen(argv, cwd=payload, env=env, stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        instance = secrets.token_hex(16)
        try:
            self.state.write("native.json", {"pid": process.pid, "instance": instance, "started_at": started})
            emit("@cfs-instance " + instance)
            wait_native(process, log, emit, boot_timeout(), cancel)
            ipc.capture(prepared, process.pid, started, complete=True)
            return self._deploy_record("native", state, pid=process.pid, instance=instance, deployed_at=started)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            # A failed startup can still create segments. Inspect after the
            # process has stopped so its last allocations are accounted for.
            try:
                ipc.capture(prepared, process.pid, started)
            except (OSError, ValueError, RuntimeError) as error:
                emit("Native PSP memory identity was not retained: " + str(error))
            raise

    def _stop_native(self, emit):
        with ExitStack() as resources:
            selector = resources.enter_context(selectors.DefaultSelector())
            for pid in self._local_flight_state()["pids"]:
                try:
                    process = resources.enter_context(os.fdopen(os.pidfd_open(pid), "rb", buffering=0))
                    image = str(Path("/proc", str(pid), "exe").readlink()).removesuffix(" (deleted)")
                    if not Path(image).is_relative_to(self.root / "mission/build-native"):
                        continue
                    signal.pidfd_send_signal(process.fileno(), signal.SIGTERM)
                    selector.register(process, selectors.EVENT_READ)
                except (ProcessLookupError, FileNotFoundError):
                    continue
            deadline = time.monotonic() + 5
            while selector.get_map():
                events = selector.select(max(0, deadline - time.monotonic()))
                if not events:
                    for key in selector.get_map().values():
                        signal.pidfd_send_signal(key.fd, signal.SIGKILL)
                    events = selector.select()
                for key, _ in events:
                    selector.unregister(key.fileobj)
        emit("Native cFS stopped.")

    def _flight_state(self, target, connection=None, timeout=8):
        if target == "native":
            return self._local_flight_state()
        service = 'cfs.service' if target == 'qemu' else 'cfs-studio.service'
        command = self.agent_command(target, connection, "status", service, connect_timeout=timeout)
        code, output = self._capture(command, timeout, input=Path(__file__).with_name("remote_agent.py").read_text())
        try:
            state = json.loads(output.splitlines()[0]) if not code and output else None
            if not isinstance(state, dict) or set(state) != {'service', 'pids', 'running', 'instance'}:
                raise ValueError('Invalid state')
            return dict(state, reachable=True)
        except (ValueError, TypeError):
            return {'service': 'unknown', 'pids': [], 'running': None,
                    'reachable': code == 0, 'error': output or 'SSH unavailable'}

    def _flight_checks(self, target, connection):
        checks = [('native', None, self._local_flight_state())]
        target = target or selected_target(self.root)
        deployed = self.state.read('deployed.json', {})
        running = self._qemu_running()
        qemu_active = deployed.get('qemu') and not deployed['qemu'].get('stopped_at')
        if running:
            checks.append(('qemu', None, self._flight_state('qemu')))
        elif running is None and (target == 'qemu' or qemu_active):
            checks.append(('qemu', None, {'running': None}))
        previous = self.state.read('active.json', {})
        physical_active = deployed.get('physical') and not deployed['physical'].get('stopped_at')
        candidates = []
        if target == 'physical':
            candidates.append(connection or self.state.read('connection.json'))
        if physical_active:
            candidates.append(deployed['physical'].get('connection'))
        if previous.get('target') == 'physical' and previous.get('phase') != 'stopped':
            candidates.append(previous.get('connection'))
        connections = []
        for candidate in candidates:
            if candidate and not any(self.same_board(candidate, existing) for existing in connections):
                connections.append(candidate)
        for candidate in connections:
            checks.append(('physical', candidate, self._flight_state('physical', candidate)))
        return checks

    def stop_before_first_boot(self, target, connection, emit, cancel):
        for mode, destination, state in self._flight_checks(target, connection):
            if state['running']:
                emit(f'Stopping the previous cFS instance on {mode}.')
                self.execute('stop', emit, target=mode, connection=destination, cancel=cancel)
        self.assert_can_start(target, connection)

    def assert_can_start(self, target=None, connection=None):
        labels = {'native': 'this workspace on the local host', 'physical': 'the physical board', 'qemu': 'the emulator'}
        checks = [(labels[mode], state) for mode, _, state in self._flight_checks(target, connection)]
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
        code, output = self._capture(["docker", "inspect", "--format", "{{.State.Running}}", network(self.root).container], 30)
        if not code and output in {"true", "false"}:
            return output == "true"
        if "no such object" in output.lower() or "no such container" in output.lower():
            return False
        return None

    def require_stopped_emulator_for_configuration(self):
        if self._qemu_running() is True:
            raise HardwareError("Stop QEMU before changing its infrastructure.")

    def verify_running_emulator(self, emit, cancel):
        # Re-enrol the disk even if its previous incarnation used this same port.
        self._stream([sys.executable, "-m", "hardware.emulator_ssh", "wait", "600"], emit, cancel, timeout=620)
        self._invalidate_observation("qemu")

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
        self._stream(["docker", "wait", network(self.root).container], emit, cancel, timeout=timeout)
        emit("QEMU stopped.")

    def confirmed_remote_flight(self, target, connection=None, emit=None, cancel=None):
        state = self._flight_state(target, connection)
        if state["running"] is not None:
            return state
        if cancel and cancel.is_set():
            raise HardwareError("Operation cancelled while checking cFS.")
        if emit:
            emit("Could not read cFS process state over SSH. Retrying the check...")
        # A newly booted Linux guest can be slow to accept SSH and query systemd.
        return self._flight_state(target, connection, timeout=30)

    @staticmethod
    def _confirm_remote_stop(target, state):
        location = "the emulator" if target == "qemu" else "the board"
        if state["running"] is False:
            return
        if state["running"] is None:
            detail = state.get("error") or "Check the SSH connection and retry."
            raise HardwareError(f"Cannot confirm that cFS has stopped on {location}. {detail}")
        if state["pids"] and state["service"] not in ACTIVE_STATES:
            raise HardwareError(f"Stop the unmanaged core-cpu1 process on {location} before switching targets.")
        raise HardwareError(f"The cFS service on {location} is still active.")

    def _stop_physical(self, connection, emit, cancel=None, required=True):
        state = self._flight_state("physical", connection)
        if state["running"] is None:
            if required:
                raise HardwareError("Cannot check cFS on the board. " + state.get("error", "Restore its SSH connection."))
            return
        if state["service"] in ACTIVE_STATES:
            emit("Stopping cFS on the board...")
            self._stream(self.ssh_argv("physical", connection) + [shlex.join(["sudo", "-n", "systemctl", "stop", "cfs-studio.service"])],
                         emit, cancel, timeout=30)
            state = self.confirmed_remote_flight("physical", connection, emit, cancel)
        self._confirm_remote_stop("physical", state)
        self._invalidate_observation("physical")
        emit("Board cFS stopped.")

    def _switch_target(self, target, connection, emit, cancel=None):
        """Stop cFS on the other targets before booting this one."""
        previous = self.state.read("active.json", {})
        deployed = self.state.read("deployed.json", {})
        previous_running = previous.get("phase") != "stopped"
        previous_board = previous.get("connection") if previous.get("target") == "physical" else None
        deployed_board = deployed.get("physical", {}).get("connection")
        boards = []
        for candidate in (self.state.read("connection.json"), previous_board, deployed_board):
            other = target == "qemu" or not self.same_board(candidate, connection)
            if candidate and other and not any(self.same_board(candidate, existing) for existing in boards):
                boards.append(candidate)
        for candidate in boards:
            # Only the last active board must answer; other saved boards are stopped when reachable.
            was_running = previous_running and self.same_board(candidate, previous_board)
            last_deployed = not previous and self.same_board(candidate, deployed_board)
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
        self.state.write("active.json", active)

    def _mark_stopped(self, target, connection=None):
        self._invalidate_observation(target)
        previous = self.state.read("active.json", {})
        if previous.get("target") == target and (target != "physical" or self.same_board(previous.get("connection"), connection)):
            self.state.write("active.json", dict(previous, phase="stopped", updated_at=time.time()))
        with self.state.edit("deployed.json") as deployed:
            if target in deployed and (target != "physical" or self.same_board(deployed[target].get("connection"), connection)):
                deployed[target]["stopped_at"] = time.time()

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
                flight = self.observed_flight('qemu')
                service, flight_running, qemu_pids = flight['service'], flight['running'], flight['pids']
                linux_ready = flight.get('reachable', flight_running is not None)
                boot_error = flight.get('error') if not linux_ready else None
            elif running is False:
                flight_running = False
                service = "inactive"
                linux_ready = False
        default_target = selected_target(self.root)
        active = self.state.read("active.json", {})
        deployed = self.state.read("deployed.json", {})
        physical_active = deployed.get('physical') and not deployed['physical'].get('stopped_at')
        physical = self._physical_status() if default_target == 'physical' or physical_active or self.state.read('connection.json') else None
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
        builds = self.builds_status()
        tools = {tool: bool(shutil.which(tool)) for tool in ("docker", "ssh", "scp", "make", "cmake", "cc")}
        from hardware.infrastructure import emulator_config
        from project.qemu.generate import fingerprint as model_fingerprint
        image_ready = None
        if running is False and default_target == 'qemu':
            status, label = self._capture(["docker", "image", "inspect", "--format",
                '{{index .Config.Labels "org.flight-studio.register-models"}}', emulator_config(self.root)["image"]], 10)
            image_ready = not status and label == model_fingerprint(self.root)
        qemu = {"image_ready": image_ready, "running": running, "service": service, "flight_running": flight_running,
                "linux_ready": linux_ready, "can_boot": running is False,
                "can_retry_boot": running is True and linux_ready is False, "boot_error": boot_error,
                "ssh_configured": (Path(network(self.root).keys) / "config").is_file()}
        board = {"connection": self.state.read("connection.json"), "candidates": self.ssh_candidates(), "last_probe": physical}
        from hardware.deployment import next_action
        snapshot = {"board": config["board"], "os": config["os"], "profiles": self.profiles(),
                "execution": execution, "tools": tools,
                "native": dict(local, last_operational=self.state.read("operational-native.json", {}).get("time"), log_path="hardware/.runtime/native.log", os=platform.system(), architecture=platform.machine()),
                "docker": {"available": code == 0, "error": docker if code else None},
                "qemu": qemu, "build": builds.get(default_target), "builds": builds,
                "physical": board, "deployed": deployed}
        snapshot["launch"] = {target: next_action(snapshot, target) for target in builds}
        return snapshot

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
        self.state.write("connection.json", self.connection(connection))
        directory = self.board_directory(result, connection) + "/studio/current/cpu1"
        result["ready"] = result["authorized"] and result["service_installed"] and result["service_directory"] == directory
        result["service_ready"] = result["ready"]
        self._last_probe = result
        self.state.write("probe.json", result)
        self._invalidate_observation("physical")
        emit(f"SSH connected: {result['model']} · {result['arch']} · cFS {result['service']}")
        return result

    def prepare_board(self, connection=None, emit=print, cancel=None, authorize=None, board=None):
        if board is None:
            board = self.probe(connection, emit, cancel)
        remote = self.board_directory(board, connection) + "/studio/setup_board.py"
        self.remote_operation("physical", connection, "directory", [str(Path(remote).parent), False], emit, cancel)
        self.copy_to("physical", connection, self.root / "hardware/setup_board.py", remote, emit, cancel)
        argv = self.ssh_argv("physical", connection)
        config = self.connection(connection)
        install = ["python3", remote, "--directory", config.get("directory", BOARD_DIRECTORY)]
        interactive = self.ssh_argv("physical", connection, interactive=True) + [shlex.join(["sudo", *install])]
        if authorize is None:
            authorize = board["sudo"]
        result = {"setup_command": shlex.join(interactive), "script": remote}
        if authorize:
            self._stream(argv + [shlex.join(["sudo", "-n", *install])], emit, cancel, timeout=30)
            board = self.probe(connection, emit, cancel)
        result["setup_required"] = not board["ready"]
        board["admin_setup_command"] = result["setup_command"] if not board["ready"] or not board.get("shutdown_authorized") else None
        self._last_probe = board
        self.state.write("probe.json", board)
        emit(json.dumps(result, ensure_ascii=False))
        return result

    def _sensorless_root(self, emit):
        from project.appgen.native_startup import reconcile_generated_modules, reconcile_removed_modules
        from project.flight_sources import prepare_mission
        prepare_mission(self.root)
        destination = self.runtime / "sensorless"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir()
        def ignore(directory, names):
            return [name for name in names if name in (".git", ".runtime", ".state", "__pycache__")
                    or (name.startswith("build") and (Path(directory) / name).is_dir())]
        for directory in ("cFS", "mission", "project", "scripts", "sensors", "config", "journey", "hardware", "ground_station"):
            shutil.copytree(self.root / directory, destination / directory, ignore=ignore, symlinks=True)
        for path in destination.rglob("*"):
            if path.is_symlink() and (Path(os.readlink(path)).is_absolute() or not path.resolve().is_relative_to(destination)):
                raise HardwareError("Link outside the isolated profile: " + str(path.relative_to(destination)))
        shutil.copy2(self.root / "Dockerfile", destination / "Dockerfile")
        shutil.copy2(self.root / ".dockerignore", destination / ".dockerignore")
        config = json.loads((destination / "project/config.json").read_text())
        removed = [app["name"] for app in config["apps"] if app["sensors"]]
        fragment = destination / "mission/sample_defs/generated/appgen_startup.scr"
        previous_fragment = fragment.read_text() if fragment.exists() else ""
        generator = str(destination / "project/appgen/appgen.py")
        for name in removed:
            delete = [sys.executable, generator, "--root", str(destination / "mission"), "delete-app", name]
            self._stream(delete, emit, cwd=destination)
        config["apps"] = [app for app in config["apps"] if app["name"] not in removed]
        config["devices"] = []
        (destination / "project/config.json").write_text(json.dumps(config, indent=2) + "\n")
        # Sensor libraries follow the configured devices, so sync drops them from the copy.
        self._stream([sys.executable, str(destination / "project/manage.py"), "sync"], emit, cwd=destination)
        startup = destination / "mission/cpu1_cfe_es_startup.scr"
        if startup.exists():
            current_fragment = fragment.read_text() if fragment.exists() else ""
            updated = reconcile_removed_modules(startup.read_text(), removed)
            updated = reconcile_generated_modules(updated, previous_fragment, current_fragment)
            startup.write_text(updated)
        emit("Isolated sensorless profile; apps excluded from this build: " + ", ".join(removed))
        return destination

    def _require_build(self, sensorless=False, target=None):
        target = target or selected_target(self.root)
        state = self.build_state(target, sensorless)
        if state.get("fingerprint") != self.fingerprint():
            raise HardwareError("Build this profile before running; some changes have not been compiled.")
        root = self.runtime / "sensorless" if sensorless else self.root
        payload = root / self.build_directory(target) / "exe/cpu1"
        if not (payload / "core-cpu1").is_file() or not (payload / "cf").is_dir():
            raise HardwareError("Incomplete cFS build. Build again.")
        return root, payload, state

    def _deploy_record(self, target, state, **extra):
        self._invalidate_observation(target)
        with self.state.edit("deployed.json") as records:
            records[target] = {**state, "target": target, "deployed_at": time.time(), **extra}
        return records[target]

    def _run_physical(self, emit, cancel, connection, sensorless, board):
        started = time.time()
        root, payload, state = self._require_build(sensorless, target="physical")
        if not board["systemd"]:
            raise HardwareError("The board requires systemd.")
        if not board["ready"]:
            prepared = self.prepare_board(connection, emit, cancel, board=board)
            if prepared["setup_required"]:
                raise HardwareError("Authorize the service once in your terminal: " + prepared["setup_command"])
        from hardware.abi import check_payload
        check_payload(payload, board["glibc"])
        argv = self.ssh_argv("physical", connection)
        if not sensorless:
            config = json.loads((root / "project/config.json").read_text())
            if any(app["sensors"] for app in config["apps"]):
                self._stream(argv + ["sudo -n modprobe i2c-dev"], emit, cancel, timeout=20)
                emit("The driver will read physical sensors. QEMU devices are not provisioned on the board. I2C failures appear in logs and telemetry.")
        release = state["fingerprint"][:16] + ("-sensorless" if sensorless else "") + "-" + str(time.time_ns())
        directory = self.board_directory(board, connection)
        releases = directory + "/releases"
        remote = releases + "/" + release
        # Each upload is a new release directory; the running service keeps its own.
        files = [(payload, "cpu1"), *((self.root / "hardware" / name, name)
                                      for name in ("readiness.py", "activate_release.py"))]
        self.upload("physical", connection, remote, files, emit, cancel)
        emit("[deploy] Release uploaded")
        self.assert_can_start('physical', connection)
        command = shlex.join(["python3", "-u", remote + "/activate_release.py", directory, release, str(boot_timeout())])
        self._stream(argv + [command], emit, cancel, timeout=boot_timeout() + 30)
        return self._deploy_record("physical", state, connection=self.connection(connection), release=remote, deployed_at=started)

    def _run_qemu(self, emit, cancel):
        started = time.time()
        root, payload, state = self._require_build(target="qemu")
        running = self._qemu_running()
        if running is None:
            raise HardwareError("Cannot read QEMU's state. Check Docker before running cFS.")
        if running is False:
            emit("Starting the emulator to run this build...")
            self._stream(["bash", "boot.sh"], emit, cancel, timeout=1860)
        self._stream([sys.executable, "project/manage.py", "check-build", "--target", "qemu"], emit, cancel)
        self._stream([sys.executable, "sensors/runtime.py", "prepare"], emit, cancel, timeout=30)
        argv = self.ssh_argv()
        service = (self.root / "cfs.service").read_text()
        working = re.search(r"^WorkingDirectory=(.+)$", service, re.M).group(1)
        self.assert_can_start('qemu')
        staging = working + ".upload-" + str(time.time_ns())
        self.upload("qemu", None, staging, [(payload, ".")], emit, cancel)
        self.assert_can_start("qemu")
        self.remote_operation("qemu", None, "start-emulator", [working, staging], emit, cancel)
        with (self.root / "hardware/readiness.py").open("rb") as monitor:
            self._stream(argv + [shlex.join(["python3", "-u", "-", "cfs.service", str(boot_timeout())])],
                         emit, cancel, stdin=monitor, timeout=boot_timeout() + 10)
        return self._deploy_record("qemu", state, deployed_at=started)

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
        preview = action == "simulate-preview" and options.get("model")
        target = target or selected_target(self.root, required=not preview)
        if not preview and target not in ("native", "qemu", "physical"):
            raise HardwareError("Invalid target.")
        if sensorless and target != "physical":
            raise HardwareError("The sensorless profile applies only to a physical board.")
        if target == "native" and action in {"boot", "shutdown", "connect", "probe", "values"}:
            raise HardwareError("Native cFS runs on this computer. Use Build, Run cFS, Stop or Output.")
        if action in {"build", "check-app", "boot", "run"}:
            self._validate_profile(target, options.get("board"), options.get("os"))
        if action == "model-test":
            from hardware.sensor_probe import validate_model
            return validate_model(self, options.get("device"), emit, cancel)
        if action == "sensor-test":
            from hardware.sensor_probe import probe
            return probe(self, target, options.get("device"), connection, emit)
        if action in ("connect", "probe"):
            board = self.probe(connection, emit, cancel)
            if action == "connect" and (not board["ready"] or not board.get("shutdown_authorized")):
                self.prepare_board(connection, emit, cancel)
            return self._last_probe
        if action == "logs":
            return self._logs(target, connection, options.get("kind"), options.get("tail", 100), emit, cancel, options.get("on_invocation"))
        if action in {"simulate", "simulate-preview"}:
            return self._simulate(action, target, options.get("device"), options.get("model"), emit, cancel, options.get("scenario"))
        with ExitStack() as locks:
            # QEMU and Board consume the same ARM build. Only flight transitions
            # need the checkout-wide guard that enforces a single running instance.
            names = [f"target-{target}"]
            if action in {"build", "check-app", "run"}:
                names.append("payload-native" if target == "native" else "payload-flight")
            if action in {"boot", "run", "stop", "shutdown"}:
                names.append("execution")
            for name in names:
                resource = locks.enter_context((self.runtime / (name + ".lock")).open("a"))
                try:
                    fcntl.flock(resource, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise HardwareError(f"Another operation is using {name}.") from None
            if action == "setup" and target == "physical":
                return self.prepare_board(connection, emit, cancel)
            if action == "setup":
                return self._stream(["bash", "scripts/setup-native.sh" if target == "native" else "scripts/setup.sh"], emit, cancel)
            if action == "build":
                return self._build(target, sensorless, emit, cancel, reuse=options.get("reuse_build", False))
            if action == "check-app":
                from project.model import identifier
                app = identifier(options.get("app", ""))
                return self._stream(["bash", "scripts/build-cfs.sh", "--target", target, "--check-app", app],
                                    emit, cancel, cwd=self.root)
            if action == "boot":
                return self._boot(target, connection, bool(options.get("retry")), emit, cancel)
            if action == "run":
                return self._run(target, connection, sensorless, emit, cancel, on_start)
            if action == "stop":
                return self._stop(target, connection, emit, cancel)
            if action == "shutdown":
                return self._shutdown(target, connection, emit, cancel)
            if action == "values" and target == "qemu":
                return self._stream([sys.executable, "sensors/runtime.py", "values"], emit, cancel, timeout=30)
            raise HardwareError("Unsupported hardware action: " + str(action))

    def _logs(self, target, connection, kind, tail, emit, cancel, on_invocation=None):
        """Follow the flight software output, or the Linux boot log when kind is "boot"."""
        if target == "native":
            log = self.runtime / "native.log"
            if not log.exists():
                raise HardwareError("Run native cFS before opening its output.")
            return self._stream(["tail", "-n", "+1" if kind == "current-flight" else "100", "-F", str(log)], emit, cancel)
        if kind == "boot" and target == "qemu":
            return self._stream(["bash", "logs.sh", "--tail", str(tail)], emit, cancel)
        argv = self.ssh_argv(target, connection)
        if kind == "boot":
            return self._stream(argv + ["journalctl -b -n 100 -f -o short-monotonic"], emit, cancel)
        if kind == "current-flight":
            service = "cfs-studio.service" if target == "physical" else "cfs.service"
            code, invocation = self._capture(argv + [f"systemctl show --property=InvocationID --value {service}"], 15)
            invocation = invocation.strip()
            if code or not re.fullmatch(r"[0-9a-f]{32}", invocation):
                raise HardwareError("Current cFS service invocation unavailable.")
            if on_invocation:
                on_invocation(invocation)
            if target == "physical":
                # Fixed journal arguments keep the board's sudo authorization limited to this service.
                def flight_message(line):
                    if not line.startswith("{"):
                        emit(line)
                        return
                    entry = json.loads(line)
                    if entry.get("_SYSTEMD_INVOCATION_ID") == invocation and isinstance(entry.get("MESSAGE"), str):
                        emit(entry["MESSAGE"])
                return self._stream(argv + ["sudo -n journalctl -u cfs-studio.service -n all -f -o json"],
                                    flight_message, cancel)
            command = f"journalctl -n all -f -o cat _SYSTEMD_INVOCATION_ID={invocation}"
        elif target == "physical":
            command = "sudo -n journalctl -u cfs-studio.service -n 100 -f -o cat"
        else:
            command = "journalctl -u cfs.service -n 100 -f -o cat"
        return self._stream(argv + [command], emit, cancel)

    def _simulate(self, action, target, device, model, emit, cancel, scenario=None):
        """Run the selected sensor transport or a local register-level test."""
        preview = action == "simulate-preview"
        if model is not None:
            from sensors.simulator import simulation_scripts
            if not preview or model not in simulation_scripts(self.root):
                raise HardwareError("Select a Python sensor model to preview.")
            return self._stream([sys.executable, "-u", "-m", "sensors." + model, "--steps", "8", "--events"], emit, cancel)
        self.simulation_script(device)
        if scenario is not None:
            from sensors.scenarios import SCENARIOS
            if not preview or scenario not in SCENARIOS or not device:
                raise HardwareError("Select a local sensor scenario")
            return self._stream([sys.executable, "-u", "-m", "sensors.scenarios", device, scenario, "--target", target], emit, cancel)
        if not preview and target == "native" and not self._local_flight_state()["running"]:
            raise HardwareError("Run native cFS before starting synthetic data.")
        if not preview and target == "qemu" and not self._qemu_running():
            raise HardwareError("Boot QEMU Linux before running synthetic data.")
        if preview:
            command = [sys.executable, "-u", "-m", "sensors.session", "--dry-run", "--events", "--steps", "24"]
            if device is not None:
                command += ["--device", device]
        elif device is not None:
            command = [sys.executable, "-u", "-m", "sensors.session", "--events", "--device", device]
        else:
            command = [sys.executable, "-u", "-m", "sensors.session", "--events"]
        return self._stream([*command, "--target", target], emit, cancel)

    def _installed_digest(self, root, target):
        """Identify the exact deployable tree, permissions and generated build configuration."""
        directory = self.build_directory(target)
        payload = root / directory / "exe/cpu1"
        stamp = root / "project/generated" / (Path(directory).name + ".json")
        try:
            binary = payload / "core-cpu1"
            if payload.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
                return None
            if not stamp.is_file() or not (payload / "cf/cfe_es_startup.scr").is_file():
                return None
            digest = hashlib.sha256()
            for path in [stamp, payload, *sorted(payload.rglob("*"))]:
                mode = path.lstat().st_mode
                # Device nodes and links can depend on files outside the deployed tree.
                if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                    return None
                digest.update(os.fsencode(path.relative_to(root)) + b"\0" + str(mode).encode() + b"\0")
                if stat.S_ISREG(mode):
                    content = hashlib.sha256()
                    with path.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            content.update(chunk)
                    digest.update(content.digest())
            return digest.hexdigest()
        except OSError:
            return None

    def _build(self, target, sensorless, emit, cancel, *, reuse=False):
        if target == "native" and self._local_flight_state()["running"]:
            raise HardwareError("Stop native cFS before replacing its installed binaries.")
        if not sensorless:
            self._stream([sys.executable, "project/manage.py", "sync"], emit, cancel)
        source = self.fingerprint()
        if reuse:
            state = self.build_state(target, sensorless)
            existing_root = self.runtime / "sensorless" if sensorless else self.root
            if (state.get("fingerprint") == source and state.get("target") == target
                    and state.get("sensorless") == sensorless and state.get("installed_sha256")
                    and self._installed_digest(existing_root, target) == state["installed_sha256"]):
                emit("Build ready: verified installed payload")
                return state
        root = self._sensorless_root(emit) if sensorless else self.root
        self._stream(["bash", "scripts/build-cfs.sh", "--target", target], emit, cancel, cwd=root)
        # An edit saved while compiling is not in these binaries.
        if self.fingerprint() != source:
            raise HardwareError("Sources changed during the build; build again.")
        if target == "native":
            from hardware.native_ipc import NativeIPC
            NativeIPC(self.root).prepare(root / self.build_directory(target) / "exe/cpu1", source)
        state = {"fingerprint": source, "built_at": time.time(), "sensorless": sensorless, "target": target,
                 "build_dir": self.build_directory(target), "installed_sha256": self._installed_digest(root, target)}
        self.state.write(self.build_state_file(target, sensorless), state)
        evidence.built(root, state)
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
            self.verify_running_emulator(emit, cancel)
            emit("QEMU Linux connection restored.")
            result = {"linux_ready": True}
        else:
            self._stream(["bash", "boot.sh"], emit, cancel, timeout=1860)
            self._stop_qemu(emit, cancel)
            result = {"linux_ready": True}
        self._save_active(target, connection, "ready")
        return result

    def _run(self, target, connection, sensorless, emit, cancel, on_start):
        self.assert_can_start(target, connection)
        build = self._require_build(sensorless, target=target)
        if on_start:
            on_start()
        board = None
        if target == "physical":
            connection = self.connection(connection)
            board = self.probe(connection, emit, cancel)
        self._save_active(target, connection, "starting")
        record = {"action": "run", "id": secrets.token_hex(16), "target": target, "connection": connection,
                  "started": time.time(), "phase": "run"}
        last_line = None

        def log(line):
            nonlocal last_line
            last_line = line
            if line.startswith("@cfs-instance "):
                record["instance"] = line.split()[1]
                record["boot_apps"] = boot_trace.app_records((build[1] / "cf/cfe_es_startup.scr").read_text())
            else:
                boot_trace.observe(self, record, line)
            emit(line)

        try:
            if target == "native":
                result = self._run_native(log, cancel)
            elif target == "physical":
                result = self._run_physical(log, cancel, connection, sensorless, board)
            else:
                result = self._run_qemu(log, cancel)
        except (StartupError, HardwareError, OSError) as error:
            self._save_active(target, connection, "failed")
            if isinstance(error, HardwareError) and error.returncode and last_line:
                raise HardwareError(last_line, returncode=error.returncode) from error
            raise HardwareError(str(error)) from error
        self._save_active(target, connection, "running")
        return result

    def _stop_qemu(self, emit, cancel):
        self._stream(self.ssh_argv(connect_timeout=30) + [shlex.join(["systemctl", "stop", "cfs.service"])],
                     emit, cancel, timeout=45)
        self._confirm_remote_stop("qemu", self.confirmed_remote_flight("qemu", emit=emit, cancel=cancel))

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
        self._invalidate_observation("physical")
        emit("Linux accepted the shutdown request. SSH will disconnect as the board powers off.")
        return {"shutdown_requested": True}
