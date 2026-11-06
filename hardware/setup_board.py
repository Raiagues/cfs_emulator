#!/usr/bin/env python3
"""One-time Raspberry Pi authorization: sudo python3 setup_board.py.

Installs an on-demand cFS service and grants only its exact control commands.
The calling user's flight binary runs as root, as with sudo ./core-cpu1.
"""
import argparse
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile


def install(path, content, mode):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        file.write(content)
        temporary = Path(file.name)
    try:
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="cfs-arm64", help="Installation folder relative to the SSH user's home")
    directory = parser.parse_args().directory
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_./-]*", directory) or any(p in {".", ".."} for p in directory.split("/")):
        raise SystemExit("Choose a relative installation folder without '..'.")
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo from your regular Raspberry Pi account.")
    user = os.environ.get("SUDO_USER", "")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*", user) or user == "root":
        raise SystemExit("SUDO_USER must identify the SSH user that will run cFS.")
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise SystemExit("Use an SSH account without root UID.")
    model = Path("/proc/device-tree/model").read_bytes().decode().strip("\0")
    if "Raspberry Pi 4 Model B" not in model or os.uname().machine != "aarch64":
        raise SystemExit("Supported board: Raspberry Pi 4B ARM64.")
    home = Path(account.pw_dir)
    if not re.fullmatch(r"/[a-zA-Z0-9_./-]+", str(home)):
        raise SystemExit("The home directory is incompatible with the safe service unit format.")
    commands = {name: shutil.which(name) for name in ("systemctl", "journalctl", "modprobe", "visudo", "stdbuf")}
    if not all(commands.values()):
        raise SystemExit("The board requires systemd, sudo, kmod and coreutils.")
    marker = f"# Flight Studio managed; account={user}\n"
    destinations = ("/etc/systemd/system/cfs-studio.service", "/etc/sudoers.d/cfs-studio")
    for name in destinations:
        path = Path(name)
        if path.is_symlink() or (path.exists() and not path.read_text().startswith(marker)):
            raise SystemExit(f"An existing file does not belong to this Flight Studio user: {name}. No files were replaced.")
    current = home / directory / "studio/current/cpu1"
    service = Path(destinations[0])
    if service.exists() and f"WorkingDirectory={current}\n" not in service.read_text():
        if subprocess.run([commands["systemctl"], "is-active", "--quiet", "cfs-studio.service"]).returncode == 0:
            raise SystemExit("Stop cFS before changing its installation folder.")
    unit = marker + f'''[Unit]
Description=cFS Flight Studio (on demand)
After=network.target

[Service]
Type=simple
WorkingDirectory={current}
ExecStart={commands['stdbuf']} -oL -eL {current}/core-cpu1
StandardOutput=journal
StandardError=journal
KillSignal=SIGINT
TimeoutStopSec=15
Restart=no
'''
    allowed = [f"{commands['systemctl']} start cfs-studio.service",
               f"{commands['systemctl']} stop cfs-studio.service",
               f"{commands['systemctl']} is-active --quiet cfs-studio.service",
               f"{commands['systemctl']} poweroff --no-block",
               f"{commands['journalctl']} -u cfs-studio.service -n 60 --no-pager -o cat",
               f"{commands['journalctl']} -u cfs-studio.service -n 100 -f -o cat",
               f"{commands['modprobe']} i2c-dev"]
    policy = marker + "# Flight service, I2C module and explicit Linux shutdown.\n"
    policy += f"{user} ALL=(root) NOPASSWD: " + ", ".join(allowed) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", prefix="cfs-studio-sudoers-") as check:
        check.write(policy)
        check.flush()
        subprocess.run([commands["visudo"], "-cf", check.name], check=True)
    install("/etc/systemd/system/cfs-studio.service", unit, 0o644)
    install("/etc/sudoers.d/cfs-studio", policy, 0o440)
    subprocess.run([commands["systemctl"], "daemon-reload"], check=True)
    print("Authorization ready. The cFS service is installed, stopped, and disabled at boot.")
    print("The cFS service, modprobe i2c-dev and Linux shutdown are authorized; unrestricted sudo still requires authentication.")


if __name__ == "__main__":
    main()
