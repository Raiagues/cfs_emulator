"""Activate one Studio upload on a Linux board and retain its rollback release."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


RELEASE = re.compile(r"[0-9a-f]{16}(?:-sensorless)?-[0-9]+\Z")
MARKER = ".flight-studio-release"


def link_to(current, target):
    with tempfile.TemporaryDirectory(dir=current.parent) as directory:
        link = Path(directory) / "next"
        link.symlink_to(target)
        os.replace(link, current)


def activate(directory, release):
    directory = directory.resolve()
    if not RELEASE.fullmatch(release):
        raise ValueError("Invalid Studio release name")
    releases = directory / "releases"
    new = releases / release
    if releases.is_symlink() or new.is_symlink() or not (new / "cpu1/core-cpu1").is_file():
        raise ValueError("Incomplete Studio release")
    current = directory / "studio/current"
    with (current.parent / "release.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        processes = subprocess.run(["pgrep", "-x", "core-cpu1"], stdout=subprocess.DEVNULL)
        if processes.returncode != 1:
            raise RuntimeError("Could not confirm cFS is stopped on the board")
        if current.exists() and not current.is_symlink():
            raise ValueError("The current release path must be a symbolic link")
        previous = os.readlink(current) if current.is_symlink() else None
        keep = {new, current.resolve()}
        link_to(current, new)
        service = ["sudo", "-n", "systemctl"]
        try:
            subprocess.run([*service, "start", "cfs-studio.service"], check=True)
            time.sleep(2)
            subprocess.run([*service, "is-active", "--quiet", "cfs-studio.service"], check=True)
        except (subprocess.SubprocessError, OSError):
            if previous is None:
                current.unlink()
            else:
                link_to(current, previous)
            raise
        try:
            (new / MARKER).write_text(release)
            for candidate in releases.iterdir():
                if candidate in keep or candidate.is_symlink() or not RELEASE.fullmatch(candidate.name):
                    continue
                marker = candidate / MARKER
                if (candidate.is_dir() and not marker.is_symlink() and marker.is_file()
                        and marker.read_text() == candidate.name):
                    shutil.rmtree(candidate)
        except (OSError, UnicodeError) as error:
            print(f"Release running. Could not finish release cleanup: {error}", file=sys.stderr)


if __name__ == "__main__":
    activate(Path(sys.argv[1]), sys.argv[2])
