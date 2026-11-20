"""Install only missing Linux host tools using the distribution's package manager."""
import argparse
import os
import shutil
import subprocess
import sys


TOOLS = ("git", "cmake", "make", "cc", "stdbuf", "pgrep")
DISTRIBUTIONS = {
    "apt-get": (["apt-get", "install", "-y"], ("git", "cmake", "make", "build-essential", "coreutils", "procps")),
    "dnf": (["dnf", "install", "-y"], ("git", "cmake", "make", "gcc", "coreutils", "procps-ng")),
    "pacman": (["pacman", "-S", "--needed", "--noconfirm"], ("git", "cmake", "make", "gcc", "coreutils", "procps-ng")),
    "zypper": (["zypper", "--non-interactive", "install"], ("git", "cmake", "make", "gcc", "coreutils", "procps")),
}


def package_manager():
    return next((exe for exe in DISTRIBUTIONS if shutil.which(exe)), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report missing dependencies without installing")
    args = parser.parse_args()
    tools = TOOLS
    present = []
    for tool in tools:
        path = shutil.which(tool)
        print(f"{tool}: {path or 'missing'}", flush=True)
        present.append(bool(path))
    if all(present):
        print("Native build and runtime tools ready.")
        return 0
    missing = [name for name, ok in zip(tools, present) if not ok]
    print("Missing: " + ", ".join(missing), flush=True)
    if args.check:
        return 1
    manager = package_manager()
    native_missing = [i for i, ok in enumerate(present) if not ok]
    if native_missing:
        if manager is None:
            sys.exit("Install the missing tools with your Linux package manager and rerun setup.")
        install, names = DISTRIBUTIONS[manager]
        prefix = [] if os.geteuid() == 0 else ["sudo"]
        packages = [names[i] for i in native_missing]
        command = prefix + install + packages
        if manager == "apt-get":
            # Use existing signed package indexes when they already contain what we need.
            print("Checking package indexes for " + ", ".join(packages) + "...", flush=True)
            trial = subprocess.run(["apt-get", "--simulate", "install", *packages],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if trial.returncode:
                subprocess.run(prefix + ["apt-get", "update"], check=True)
        print("Installing " + ", ".join(packages) + "...", flush=True)
        subprocess.run(command, check=True)
    # Run a new interpreter so packages installed above are visible.
    return subprocess.call([sys.executable, "-m", "hardware.host_tools", "--check"])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
