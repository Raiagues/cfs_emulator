"""Pin the SSH identity reached by QEMU inside this workspace's Docker container."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from hardware.infrastructure import emulator_config


ALIAS = "flight-studio-qemu"
ROOT = Path(__file__).resolve().parents[1]


def trust_settings(root):
    # OpenSSH parses and expands filenames in -o just like an ssh_config file.
    filename = str(root.resolve() / "board/known_hosts").replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return [f'UserKnownHostsFile="{filename}"', "GlobalKnownHostsFile=none",
            "StrictHostKeyChecking=yes", "UpdateHostKeys=no", "HostKeyAlgorithms=ssh-ed25519",
            "HostKeyAlias=" + ALIAS, "HostName=127.0.0.1"]


def ssh_options(root, port):
    options = ["-F", str(Path.home() / ".ssh/cfs-emulator/config")]
    for setting in trust_settings(root):
        options.extend(["-o", setting])
    return [*options, "-p", str(port), "pi4-cfs"]


def container_id(root, port):
    result = subprocess.run(["docker", "container", "inspect", "pi4-cfs"], capture_output=True,
                            text=True, timeout=10, check=True)
    item = json.loads(result.stdout)[0]
    disk = root.resolve() / "board"
    mounted = any(m["Type"] == "bind" and m["Destination"] == "/work/board"
                  and Path(m["Source"]).resolve() == disk for m in item["Mounts"])
    binding = item["NetworkSettings"]["Ports"].get("2222/tcp")
    if not (mounted and item["State"]["Running"] and item["HostConfig"]["NetworkMode"] in {"bridge", "default"}
            and binding == [{"HostIp": "127.0.0.1", "HostPort": str(port)}]):
        raise ValueError("The running emulator does not match this workspace, network and SSH port.")
    return item["Id"]


def public_key(line):
    # ssh-keyscan reads the guest port *inside* the verified Docker namespace.
    # Require one ED25519 key, with its RFC 4253 wire type and exact key length.
    records = [row.strip() for row in line.splitlines() if row.strip() and not row.lstrip().startswith("#")]
    if len(records) != 1:
        raise ValueError("Expected one emulator host key.")
    fields = records[0].split()
    if len(fields) != 3 or fields[:2] != ["[127.0.0.1]:2222", "ssh-ed25519"]:
        raise ValueError("Unexpected emulator host key record.")
    blob = base64.b64decode(fields[2], validate=True)
    prefix = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
    if not blob.startswith(prefix) or len(blob) != len(prefix) + 32:
        raise ValueError("Invalid emulator ED25519 host key.")
    return f"{ALIAS} ssh-ed25519 {fields[2]}\n"


def pin_guest(root, ident):
    scan = subprocess.run(["docker", "exec", ident, "ssh-keyscan", "-T", "3", "-p", "2222",
                           "-t", "ed25519", "127.0.0.1"], capture_output=True, text=True, timeout=10)
    if scan.returncode == 1 and all(not row.strip() or row.lstrip().startswith("#")
                                    for row in scan.stdout.splitlines()):
        if "error response from daemon" in scan.stderr.lower():
            raise RuntimeError(scan.stderr.strip())
        return False  # sshd has not started.
    scan.check_returncode()
    record = public_key(scan.stdout)
    path = root / "board/known_hosts"
    if path.is_file() and path.read_text() == record:
        return True
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        try:
            f.write(record)
            f.flush()
            os.replace(f.name, path)
        finally:
            Path(f.name).unlink(missing_ok=True)
    return True


def wait_for_guest(root, port, timeout):
    ident = container_id(root, port)
    started = time.monotonic()
    next_status = started
    while True:
        try:
            enrolled = pin_guest(root, ident)
        except subprocess.TimeoutExpired:
            enrolled = False
        if enrolled:
            # The forwarded endpoint must prove possession of the private key.
            argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", *ssh_options(root, port), "true"]
            try:
                probe = subprocess.run(argv, capture_output=True, text=True, timeout=10, env=dict(os.environ, LC_ALL="C"))
            except subprocess.TimeoutExpired:
                pass  # sshd may still be bringing up the guest login session.
            else:
                if not probe.returncode:
                    print("[emulator] Linux SSH ready.", flush=True)
                    return
                error = probe.stderr.strip()
                if "Host key verification failed" in error or "Permission denied" in error:
                    raise ValueError(error)
        now = time.monotonic()
        if now - started >= timeout:
            raise ValueError("Linux SSH did not become ready before the boot timeout.")
        if now >= next_status:
            print(f"[Boot: {now-started:.0f}s] Waiting for guest SSH", flush=True)
            next_status = now + 10
        time.sleep(1)


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
        lines = [f"Port {port}", "User root", "IdentityFile ~/.ssh/cfs-emulator/id_ed25519",
                 "IdentitiesOnly yes", "BatchMode yes", "ConnectTimeout 5", *trust_settings(ROOT)]
        print("Host pi4-cfs")
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
