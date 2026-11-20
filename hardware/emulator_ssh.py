"""Pin the SSH identity reached by QEMU inside this workspace's Docker container."""
import argparse
import base64
import json
import os
import selectors
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from hardware.infrastructure import emulator_config
from project.defaults import loopback, network


ALIAS = "flight-studio-qemu"
ROOT = Path(__file__).resolve().parents[1]


def trust_settings(root):
    # OpenSSH parses and expands filenames in -o just like an ssh_config file.
    filename = str(root.resolve() / "board/known_hosts").replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return [f'UserKnownHostsFile="{filename}"', "GlobalKnownHostsFile=none",
            "StrictHostKeyChecking=yes", "UpdateHostKeys=no", "HostKeyAlgorithms=ssh-ed25519",
            "HostKeyAlias=" + ALIAS, "HostName=" + loopback()]


def ssh_options(root, port):
    options = ["-F", str(Path(network(root).keys) / "config")]
    for setting in trust_settings(root):
        options.extend(["-o", setting])
    return [*options, "-p", str(port), network(root).ssh_alias]


def container_id(root, port):
    result = subprocess.run(["docker", "container", "inspect", network(root).container], capture_output=True,
                            text=True, timeout=10, check=True)
    item = json.loads(result.stdout)[0]
    disk = (root / "board").resolve()
    mounted = any(m["Type"] == "bind" and m["Destination"] == "/work/board"
                  and Path(m["Source"]).resolve() == disk for m in item["Mounts"])
    binding = item["NetworkSettings"]["Ports"].get(f"{network(root).internal_ssh}/tcp")
    if not (mounted and item["State"]["Running"] and item["HostConfig"]["NetworkMode"] in {"bridge", "default"}
            and binding == [{"HostIp": loopback(), "HostPort": str(port)}]):
        raise ValueError("The running emulator does not match this workspace, network and SSH port.")
    return item["Id"]


def public_key(line, port=None):
    port = port or network(ROOT).internal_ssh
    # ssh-keyscan reads the guest port *inside* the verified Docker namespace.
    # Require one ED25519 key, with its RFC 4253 wire type and exact key length.
    records = [row.strip() for row in line.splitlines() if row.strip() and not row.lstrip().startswith("#")]
    if len(records) != 1:
        raise ValueError("Expected one emulator host key.")
    fields = records[0].split()
    if len(fields) != 3 or fields[:2] != [f"[{loopback()}]:{port}", "ssh-ed25519"]:
        raise ValueError("Unexpected emulator host key record.")
    blob = base64.b64decode(fields[2], validate=True)
    prefix = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
    if not blob.startswith(prefix) or len(blob) != len(prefix) + 32:
        raise ValueError("Invalid emulator ED25519 host key.")
    return f"{ALIAS} ssh-ed25519 {fields[2]}\n"


def pin_guest(root, ident):
    scan = subprocess.run(["docker", "exec", ident, "ssh-keyscan", "-T", "3", "-p", str(network(root).internal_ssh),
                           "-t", "ed25519", loopback()], capture_output=True, text=True, timeout=10)
    if scan.returncode == 1 and all(not row.strip() or row.lstrip().startswith("#")
                                    for row in scan.stdout.splitlines()):
        if "error response from daemon" in scan.stderr.lower():
            raise RuntimeError(scan.stderr.strip())
        return False  # sshd has not started.
    scan.check_returncode()
    record = public_key(scan.stdout, network(root).internal_ssh)
    path = root / "board/known_hosts"
    if path.is_file() and path.read_text() == record:
        return True
    if path.exists():
        print("[emulator] Updating the SSH pin from the verified container for this disk.", flush=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        try:
            f.write(record)
            f.flush()
            os.replace(f.name, path)
        finally:
            Path(f.name).unlink(missing_ok=True)
    return True


def ssh_milestones(ident, timeout):
    started = time.monotonic()
    deadline = started + timeout
    progress = started
    with subprocess.Popen(["docker", "logs", "--follow", ident], stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as console:
        with selectors.DefaultSelector() as ready:
            ready.register(console.stdout, selectors.EVENT_READ)
            pending, last = b"", ""
            try:
                while time.monotonic() < deadline:
                    now = time.monotonic()
                    if now >= progress:
                        print(f"[Boot: {now-started:.0f}s] Waiting for guest SSH", flush=True)
                        progress = now + 10
                    if not ready.select(max(0, min(progress, deadline) - now)):
                        continue
                    data = os.read(console.stdout.fileno(), 65536)
                    if not data:
                        raise ValueError("Emulator exited before SSH was ready. " + last)
                    pending += data
                    lines = pending.split(b"\n")
                    pending = lines.pop()
                    for line in lines:
                        last = line.decode(errors="replace").strip() or last
                        if "FLIGHT_STUDIO_SSH_READY" in last or " login:" in last or (
                                "Started" in last and "OpenBSD Secure Shell server" in last):
                            yield last
                raise ValueError("Linux SSH did not become ready before the boot timeout. " + last)
            finally:
                console.terminate()
                console.wait()


def wait_for_guest(root, port, timeout):
    from contextlib import closing
    ident = container_id(root, port)
    if not pin_guest(root, ident):
        with closing(ssh_milestones(ident, timeout)) as milestones:
            for event in milestones:
                if pin_guest(root, ident):
                    break
                if "FLIGHT_STUDIO_SSH_READY" in event:
                    raise ValueError("Guest sshd started but did not present an ED25519 key.")
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", *ssh_options(root, port), "true"]
    probe = subprocess.run(argv, capture_output=True, text=True, timeout=30, env=dict(os.environ, LC_ALL="C"))
    if probe.returncode:
        raise ValueError(probe.stderr.strip() or "The guest did not accept its checkout SSH identity.")
    print("[emulator] Linux SSH ready.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    commands.add_parser("config")
    commands.add_parser("pin")
    commands.add_parser("wait").add_argument("timeout", type=int)
    commands.add_parser("ssh").add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    port = emulator_config(ROOT)["ssh_port"]
    if args.mode == "config":
        key = str(Path(network(ROOT).keys) / 'id_ed25519').replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"')
        lines = [f"Port {port}", "User root", f'IdentityFile "{key}"',
                 "IdentitiesOnly yes", "BatchMode yes", "ConnectTimeout 5", *trust_settings(ROOT)]
        print("Host " + network(ROOT).ssh_alias)
        for line in lines:
            print("    " + line)
    elif args.mode == "wait":
        wait_for_guest(ROOT, port, args.timeout)
    elif args.mode == "pin":
        if not pin_guest(ROOT, container_id(ROOT, port)):
            raise ValueError("The guest SSH service is still starting.")
    else:
        os.execvp("ssh", ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                          "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
                          *ssh_options(ROOT, port), *args.command])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
