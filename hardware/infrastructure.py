"""Local infrastructure settings and preflight checks, separate from mission sources."""
import importlib.util
import json
import platform
from pathlib import Path
import re
import shlex
import shutil
import socket
import sys


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


def snapshot(hardware):
    config = json.loads((hardware.root / "project/config.json").read_text())
    keys = sorted(str(p.with_suffix("")) for p in (Path.home() / ".ssh").glob("*.pub")
                  if p.with_suffix("").is_file())
    connection = hardware._load("connection.json")
    commands = {}
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
    return {"project": hardware.root.name, "target": hardware.default_target(),
            "board": config["board"], "os": config["os"], "profiles": hardware.profiles(),
            "host": {"os": platform.system(), "architecture": platform.machine(),
                     "package_manager": "apt" if shutil.which("apt-get") else None},
            "connection": connection, "ssh_hosts": hardware.ssh_candidates(), "ssh_keys": keys,
            "emulator": emulator_config(hardware.root), "commands": commands}


def save(studio, body):
    hardware = studio.hardware
    target = body.get("target")
    if target not in ("native", "qemu", "physical"):
        raise ValueError("Select an execution target.")
    config = json.loads((hardware.root / "project/config.json").read_text())
    board, system = body.get("board"), body.get("os")
    if target != "native" and not any(p["board"] == board and p["os"] == system and target in p["targets"] for p in hardware.profiles()):
        raise ValueError("Select a supported board and operating system.")
    emulator = validate_emulator(body.get("emulator")) if target == "qemu" else None
    value = body.get("connection", {})
    if not isinstance(value, dict):
        raise ValueError("Invalid SSH connection.")
    connection = hardware.connection(value) if target == "physical" and value.get("host") else None
    previous = hardware._load("connection.json")
    if target == "physical" and connection != previous:
        deployed = hardware._load("deployed.json", {}).get("physical", {})
        if deployed and not deployed.get("stopped_at"):
            raise ValueError("Stop cFS on the board before changing its connection or installation folder.")
    profile_changed = target != "native" and (board, system) != (config["board"], config["os"])
    emulator_changed = emulator is not None and emulator != emulator_config(hardware.root)
    if (profile_changed or emulator_changed) and hardware._qemu_running() is True:
        raise ValueError("Stop QEMU before changing its infrastructure.")
    if profile_changed:
        studio.workspace.select_profile(board, system)
    if emulator is not None:
        hardware._save("emulator.json", emulator)
    if target == "physical" and connection != previous:
        if connection:
            hardware._save("connection.json", connection)
        else:
            (hardware.runtime / "connection.json").unlink(missing_ok=True)
        (hardware.runtime / "probe.json").unlink(missing_ok=True)
        hardware._last_probe = None
        hardware._physical_observation = None
    hardware.select_target(target)
    return snapshot(hardware)


def check(hardware, target):
    if target not in ("native", "qemu", "physical"):
        raise ValueError("Select an execution target.")
    checks = []
    def add(label, ready, detail, command=None):
        checks.append({"label": label, "ready": bool(ready), "detail": detail, "command": command})
    tools = ("git", "cmake", "make", "cc") if target == "native" else ("git", "docker", "ssh", "scp")
    for tool in tools:
        path = shutil.which(tool)
        add(tool, path, path or "Not installed")
    code, output = hardware._capture(["git", "-C", str(hardware.root), "submodule", "status", "--recursive"], 20)
    missing = [line.split()[1] for line in output.splitlines() if line.startswith("-") and len(line.split()) > 1]
    add("Repository dependencies", not code and not missing, ", ".join(missing) if missing else "Submodules available" if not code else output,
        "git submodule update --init --recursive" if code or missing else None)
    modules = [name for name in ("PyQt5", "zmq") if importlib.util.find_spec(name) is None]
    add("Ground Station Python packages", not modules, ", ".join(modules) if modules else "PyQt5 · pyzmq",
        shlex.join([sys.executable, "-m", "pip", "install", "-r", "ground_station/requirements.txt"]) if modules else None)
    if target != "native":
        code, output = hardware._capture(["docker", "version", "--format", "{{.Server.Version}}"], 30)
        version = re.match(r"(\d+)\.", output)
        add("Docker engine ≥ 23", not code and version and int(version[1]) >= 23,
            output if not code else "Start Docker and grant your user access")
        code, output = hardware._capture(["docker", "buildx", "version"], 15)
        version = re.search(r"v?(\d+)\.(\d+)\.", output)
        add("Docker Buildx ≥ 0.10", not code and version and tuple(map(int, version.groups())) >= (0, 10), output)
        if target == "physical":
            connection = hardware._load("connection.json", {})
            if connection.get("identity_file"):
                key = Path(connection["identity_file"])
                add("Board SSH identity", key.is_file(), str(key))
        if target == "qemu":
            running = hardware._qemu_running()
            emulator = emulator_config(hardware.root)
            code, label = hardware._capture(["docker", "image", "inspect", "--format",
                                            '{{index .Config.Labels "org.flight-studio.qemu-lsm-signed"}}', emulator["image"]], 30)
            add("Emulator image", not code and label == "1", emulator["image"])
            ssh_dir = Path.home() / ".ssh/cfs-emulator"
            add("Emulator SSH identity", all((ssh_dir / name).is_file() for name in ("config", "id_ed25519", "id_ed25519.pub")), str(ssh_dir))
            available = True
            if not running:
                try:
                    with socket.socket() as sock:
                        sock.bind(("127.0.0.1", emulator["ssh_port"]))
                except OSError:
                    available = False
            add("Local SSH port", available, f"127.0.0.1:{emulator['ssh_port']}" + (" · QEMU running" if running else ""))
    return {"target": target, "checks": checks, "ready": all(c["ready"] for c in checks)}


if __name__ == "__main__":
    settings = emulator_config(Path(__file__).resolve().parents[1])
    if len(sys.argv) != 2 or sys.argv[1] not in settings:
        raise SystemExit("Usage: python3 -m hardware.infrastructure ssh_port|image")
    print(settings[sys.argv[1]])
