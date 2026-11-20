"""Local infrastructure settings and preflight checks, separate from mission sources."""
from project.qemu.generate import fingerprint
from project.nasa_source import OFFICIAL_URL, source_status
from hardware.host_tools import package_manager
from hardware.targets import selected_target
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
import hashlib
import json
import platform
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import socket
import sys
import threading
import time

CODE_ROOT = Path(__file__).resolve().parents[1]
_port_probe_lock = threading.Lock()
_receipt_lock = threading.Lock()


def sources_ready(root):
    return source_status(root)["state"] == "ready"


def emulator_config(root):
    root = Path(root)
    defaults = {"ssh_port": 2222, "image": (root / "config/image").read_text().strip()}
    path = root / "hardware/.runtime/emulator.json"
    return validate_emulator({**defaults, **(json.loads(path.read_text()) if path.exists() else {})})


def validate_emulator(value):
    if not isinstance(value, dict) or set(value) != {"ssh_port", "image"}:
        raise ValueError("Select the emulator SSH port and image.")
    port, image = value["ssh_port"], value["image"]
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Emulator SSH port must be between 1024 and 65535.")
    if not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,255}", image):
        raise ValueError("Enter a Docker image reference.")
    return {"ssh_port": port, "image": image}


def save_emulator(hardware, value):
    """Persist the same settings used by workspace setup, boot and local builds."""
    value = validate_emulator(value)
    if emulator_config(hardware.root) != value:
        hardware.require_stopped_emulator_for_configuration()
        hardware._save("emulator.json", value)
    return value


def _source_inventory(root):
    """Inspect installation files without launching Git before the user asks for a check."""
    checkout = root / "cFS"
    if not checkout.is_symlink() and (not checkout.exists() or checkout.is_dir() and not any(checkout.iterdir())):
        state = "missing"
    elif checkout.is_symlink() or not (checkout / ".git").exists():
        state = "occupied"
    elif (checkout / "sample_defs/targets.cmake").is_file() and (checkout / "cfe/CMakeLists.txt").is_file():
        state = "installed"
    else:
        state = "incomplete"
    return {"state": state, "url": OFFICIAL_URL, "revision": None}


def snapshot(hardware, verify_source=False):
    config = json.loads((hardware.root / "project/config.json").read_text())
    keys = sorted(str(p.with_suffix("")) for p in (Path.home() / ".ssh").glob("*.pub")
                  if p.with_suffix("").is_file())
    connection = hardware._load("connection.json")
    commands = {"install_native": "./scripts/setup-native.sh"}
    if connection:
        connection = hardware.connection(connection)
        argv = hardware.ssh_argv("physical", connection, interactive=True)
        commands["ssh"] = shlex.join(argv)
        copy = ["ssh-copy-id", "-p", str(connection["port"])]
        if connection.get("identity_file"):
            copy += ["-i", connection["identity_file"] + ".pub"]
        key = Path(connection.get("identity_file") or Path.home() / ".ssh/id_ed25519")
        if not key.exists() and (connection.get("identity_file") or not keys):
            commands["create_key"] = shlex.join(["ssh-keygen", "-t", "ed25519", "-f", str(key), "-C", "flight-studio"])
        destination = (connection["user"] + "@" if connection["user"] else "") + connection["host"]
        commands["authorize_key"] = shlex.join(copy + [destination])
        probe = hardware._load("probe.json", {})
        if probe.get("admin_setup_command"):
            commands["authorize_service"] = probe["admin_setup_command"]
    source = source_status(hardware.root) if verify_source else _source_inventory(hardware.root)
    plans, results = {}, {}
    for mode in ("native", "qemu", "physical"):
        plan = list(_check_plan(hardware, mode))
        plans[mode] = [probe.describe() for probe in plan]
        receipt = hardware._load("checks-" + mode + ".json", {})
        if receipt.get("identity") == _identity(hardware, mode, plan):
            results[mode] = receipt.get("checks", {})
    target = selected_target(hardware.root)
    return {"source": source, "target_saved": target is not None, "check_plan": plans, "check_results": results, "build_jobs": hardware._load("native-build-settings.json", {}).get("jobs", 4), "sources_ready": source["state"] in {"installed", "ready"}, "project": hardware.root.name, "target": target,
            "board": config["board"], "os": config["os"], "profiles": hardware.profiles(),
            "host": {"os": platform.system(), "architecture": platform.machine(),
                     "package_manager": package_manager()},
            "connection": connection, "ssh_hosts": hardware.ssh_candidates(), "ssh_keys": keys,
            "emulator": emulator_config(hardware.root), "commands": commands}


def save(hardware, body):
    target = body.get("target")
    if target not in ("native", "qemu", "physical"):
        raise ValueError("Select an execution target.")
    emulator = validate_emulator(body.get("emulator")) if target == "qemu" else None
    jobs = body.get("build_jobs", hardware._load("native-build-settings.json", {}).get("jobs", 4))
    if type(jobs) is not int or not 1 <= jobs <= 64:
        raise ValueError("Choose 1 to 64 parallel build jobs.")
    value = body.get("connection", {})
    if not isinstance(value, dict):
        raise ValueError("Invalid SSH connection.")
    connection = hardware.connection(value) if target == "physical" and value.get("host") else None
    previous = hardware._load("connection.json")
    if target == "physical" and connection != previous:
        deployed = hardware._load("deployed.json", {}).get("physical", {})
        prior_board = deployed.get("connection") or previous
        if deployed and not deployed.get("stopped_at") and not hardware.same_board(connection, prior_board):
            if not prior_board or hardware._flight_state("physical", prior_board)["running"] is not False:
                raise ValueError("Stop cFS on the previous board before changing its connection.")
            hardware._mark_stopped("physical", prior_board)
    if emulator is not None:
        save_emulator(hardware, emulator)
    if target == "physical" and connection != previous:
        if connection:
            hardware._save("connection.json", connection)
        else:
            (hardware.runtime / "connection.json").unlink(missing_ok=True)
        (hardware.runtime / "probe.json").unlink(missing_ok=True)
        hardware._last_probe = None
        hardware._invalidate_observation("physical")
    if target == "native":
        hardware._save("native-build-settings.json", {"jobs": jobs})
    return snapshot(hardware)


@dataclass(frozen=True)
class Probe:
    label: str
    argv: tuple[str, ...]
    interpret: Callable[[dict, str], None] | None = None
    repair: str | None = None

    def describe(self):
        return {"label": self.label, "probe": shlex.join(self.argv)}

    def run(self):
        started = time.monotonic_ns()
        row = dict(self.describe(), command=self.repair, exit_code=None)
        try:
            process = subprocess.run(self.argv, cwd=CODE_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace", timeout=30)
            output = process.stdout.strip()
            row.update(ready=process.returncode == 0, exit_code=process.returncode)
            if self.interpret:
                self.interpret(row, output)
            if "detail" not in row:
                lines = output.splitlines()
                row["detail"] = (lines[0] if row["ready"] else lines[-1])[:500] if lines else ""
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            row.update(ready=False, detail=str(error))
        if row["ready"]:
            row["command"] = None
        return dict(row, status="passed" if row["ready"] else "failed",
                    duration_ms=(time.monotonic_ns() - started) // 1_000_000)


def _source_result(row, output):
    if output.startswith("{"):
        source = json.loads(output)
        row["source"] = source
        messages = {"missing": "Clone the official NASA repository",
                    "incomplete": "Complete the NASA submodule download",
                    "revision-mismatch": "Select the pinned NASA revision",
                    "occupied": "The cFS directory contains a different checkout"}
        row["detail"] = source["revision"] if row["ready"] else messages[source["state"]]


def _tool_version(row, output):
    if row["ready"] and not re.search(r"\d+\.\d+", output):
        row.update(ready=False, detail="Version could not be read")


def _version_at_least(minimum, row, output):
    if row["ready"]:
        version = re.search(r"(?<![A-Za-z0-9])v?(\d+)\.(\d+)(?:\.\d+)?", output)
        row["ready"] = bool(version and tuple(map(int, version.groups())) >= minimum)
        if version:
            row["detail"] = version[0]


def _image_result(image, row, output):
    if row["ready"]:
        row["ready"] = output == fingerprint()
        row["detail"] = image if row["ready"] else image + " · Register models differ"


def _scp_check():
    # OpenSSH scp has no version option. Exercise its local copy path using two
    # disposable files, so a successful status also verifies the copied bytes.
    with tempfile.TemporaryDirectory() as directory:
        source, dest = Path(directory) / "source", Path(directory) / "copy"
        source.write_bytes(b"Flight Studio SCP verification")
        result = subprocess.run(["scp", str(source), str(dest)], stdin=subprocess.DEVNULL)
        if result.returncode:
            return result.returncode
        if not dest.is_file() or dest.read_bytes() != source.read_bytes():
            print("Local copy did not match the source")
            return 1
        print("Local file transfer verified")
        return 0


def _check_plan(hardware, target):
    if target not in ("native", "qemu", "physical"):
        raise ValueError("Select an execution target.")
    local = (sys.executable, "-m", "hardware.infrastructure")
    for tool in ("git", "cmake", "make", "cc", "stdbuf", "pgrep"):
        yield Probe(tool, (tool, "--version"), _tool_version)
    if target != "native":
        yield Probe("docker", ("docker", "--version"), _tool_version)
        yield Probe("ssh", ("ssh", "-V"), _tool_version)
        yield Probe("scp", (*local, "check-scp"))
    yield Probe("Python", (sys.executable, "--version"), _tool_version)
    if target != "native":
        yield Probe("Docker engine ≥ 23", ("docker", "version", "--format", "{{.Server.Version}}"),
                    partial(_version_at_least, (23, 0)))
        yield Probe("Docker Buildx ≥ 0.10", ("docker", "buildx", "version"), partial(_version_at_least, (0, 10)))
    if target == "physical":
        connection = hardware._load("connection.json", {}) or {}
        key = connection.get("identity_file")
        if key:
            yield Probe("Board SSH identity", ("ssh-keygen", "-lf", key))
        for label, action in (("Board network", "network"), ("Board login", "login"), ("cFS service", "service")):
            yield Probe(label, (*local, "check-board", action, str(hardware.root)))
    if target == "qemu":
        emulator = emulator_config(hardware.root)
        image = emulator["image"]
        yield Probe("Emulator image", ("docker", "image", "inspect", "--format",
                    '{{index .Config.Labels "org.flight-studio.register-models"}}', image), partial(_image_result, image))
        yield Probe("Emulator SSH identity", (*local, "check-emulator-key"))
        yield Probe("Local SSH port", (*local, "check-port", str(emulator["ssh_port"])))
    yield Probe("NASA cFS source", (sys.executable, "-m", "project.nasa_source", "--status", str(hardware.root)),
                _source_result, "./scripts/install-cfs.sh")


def _identity(hardware, target, plan=None):
    # The board host, guest image and profile are inputs to the verified plan.
    plan = [probe.describe() for probe in (plan or _check_plan(hardware, target))]
    profile = hardware.root / "project/config.json"
    config = json.loads(profile.read_text()) if profile.is_file() else {}
    specific = hardware._load("connection.json") if target == "physical" else None
    data = [target, plan, specific, [config.get("board"), config.get("os")] if target != "native" else None]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _receipt(hardware, target, identity, row):
    with _receipt_lock:
        path = "checks-" + target + ".json"
        if _identity(hardware, target) != identity:
            return  # A concurrent settings change superseded this result.
        receipt = hardware._load(path, {})
        if receipt.get("identity") != identity:
            receipt = {"identity": identity, "checks": {}}
        receipt["checks"][row["label"]] = row["ready"]
        if selected_target(hardware.root) == target:
            receipt["selected"] = True
        hardware._save(path, receipt)
        if row["ready"] and receipt.get("selected") and target_verified(hardware, target):
            hardware.journey.observe(target, "target", {"checks": identity})


def checks_verified(hardware, target, receipt):
    if target not in ("native", "qemu", "physical") or _source_inventory(hardware.root)["state"] != "installed":
        return False
    plan = list(_check_plan(hardware, target))
    return receipt.get("identity") == _identity(hardware, target, plan) and all(
        receipt.get("checks", {}).get(p.label) is True for p in plan)


def target_verified(hardware, target):
    if target not in ("native", "qemu", "physical") or selected_target(hardware.root) != target:
        return False
    return checks_verified(hardware, target, hardware._load("checks-" + target + ".json", {}))


def _run(probe):
    if probe.label == "Local SSH port":
        # Concurrent setup pages must not trip over each other's temporary bind.
        with _port_probe_lock:
            return probe.run()
    return probe.run()


def check_one(hardware, target, label):
    plan = list(_check_plan(hardware, target))
    for probe in plan:
        if probe.label == label:
            identity = _identity(hardware, target, plan)
            result = _run(probe)
            _receipt(hardware, target, identity, result)
            return result
    raise ValueError("Select a check for this target.")


def check_progress(hardware, target):
    """Capture settings once, then publish each actual start and finish."""
    plan = list(_check_plan(hardware, target))
    identity = _identity(hardware, target, plan)
    checks = [dict(probe.describe(), status="pending", ready=None, detail="", command=None,
                   exit_code=None, duration_ms=None) for probe in plan]
    started = time.monotonic_ns()

    def snapshot(done=False):
        return {"target": target, "status": "complete" if done else "running",
                "ready": all(item["ready"] for item in checks) if done else None,
                "checks": checks.copy(), "duration_ms": (time.monotonic_ns() - started) // 1_000_000}

    yield snapshot()
    for index, probe in enumerate(plan):
        checks[index] = dict(checks[index], status="running")
        yield snapshot()
        checks[index] = _run(probe)
        _receipt(hardware, target, identity, checks[index])
        yield snapshot(done=index == len(plan) - 1)


def check(hardware, target):
    """Compatibility response for single JSON requests."""
    for report in check_progress(hardware, target):
        if report["status"] == "complete":
            checks = [{key: item[key] for key in ("label", "ready", "detail", "command")}
                      for item in report["checks"]]
            return {"target": target, "checks": checks, "ready": report["ready"]}


def _cli(args):
    if len(args) == 3 and args[0] == "check-board":
        from hardware.manager import HardwareManager
        hardware = HardwareManager(args[2])
        argv = hardware.ssh_argv("physical")
        if args[1] == "network":
            # Honor OpenSSH's HostName and Port for saved aliases.
            result = subprocess.run([*argv[:1], "-G", *argv[1:]], capture_output=True, text=True, check=True)
            resolved = dict(line.split(" ", 1) for line in result.stdout.splitlines() if " " in line)
            with socket.create_connection((resolved["hostname"], int(resolved["port"])), timeout=5):
                print(resolved["hostname"], resolved["port"])
            return 0
        if args[1] == "login":
            return subprocess.call([*argv, "id -un"])
        if args[1] == "service":
            board = hardware.probe(emit=print)
            print("cFS service ready" if board["ready"] else "Service requires setup")
            return 0 if board["ready"] else 1
    if len(args) == 1 and args[0] in {"authorize-key", "prepare-service"}:
        from hardware.manager import HardwareManager
        hardware = HardwareManager(Path.cwd())
        if args[0] == "prepare-service":
            result = hardware.prepare_board()
            if not result["setup_required"]:
                return 0
            return subprocess.call(shlex.split(result["setup_command"]))
        commands = snapshot(hardware)["commands"]
        if "create_key" in commands:
            code = subprocess.call(shlex.split(commands["create_key"]))
            if code:
                return code
        return subprocess.call(shlex.split(commands["authorize_key"]))
    if args == ["check-scp"]:
        return _scp_check()
    if args == ["check-emulator-key"]:
        directory = Path.home() / ".ssh/cfs-emulator"
        for filename in ("config", "id_ed25519", "id_ed25519.pub"):
            if not (directory / filename).is_file():
                print(f"Missing {directory / filename}")
                return 1
        return subprocess.call(["ssh-keygen", "-lf", str(directory / "id_ed25519")], stdin=subprocess.DEVNULL)
    if len(args) == 2 and args[0] == "check-port":
        port = int(args[1])
        address = f"127.0.0.1:{port}"
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", port))
            print(address)
            return 0
        except OSError as error:
            # A busy port is also valid when the selected emulator owns the mapping.
            try:
                result = subprocess.run(["docker", "port", "pi4-cfs", "2222/tcp"],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and address in result.stdout.splitlines():
                    print(address + " · QEMU running")
                    return 0
            except (OSError, subprocess.TimeoutExpired):
                pass
            print(f"{address} · {error.strerror}")
            return 1
    if len(args) == 1 and args[0] in {"ssh_port", "image"}:
        print(emulator_config(CODE_ROOT)[args[0]])
        return 0
    raise SystemExit("Usage: python3 -m hardware.infrastructure ssh_port|image|check-scp|check-emulator-key|check-port PORT")


if __name__ == "__main__":
    try:
        sys.exit(_cli(sys.argv[1:]))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
