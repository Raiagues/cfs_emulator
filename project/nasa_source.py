"""Install and identify the independently versioned NASA cFS checkout."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from project.flight_sources import prepare_mission

OFFICIAL_URL = "https://github.com/nasa/cFS.git"
REVISION = "a4d305dc06fb7d468f5b45214d9f730b97d4bd77"


def _git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, check=True).stdout.strip()


def _has_nasa_base(source, revision):
    if revision == REVISION:
        return True
    prefix = ["git", "-C", str(source)]
    if subprocess.run([*prefix, "merge-base", "--is-ancestor", REVISION, revision],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        return False
    changes = subprocess.check_output([*prefix, "diff", "--name-status", "-z", "--no-renames",
                                       REVISION, revision]).split(b"\0")[:-1]
    return all(status == b"A" and path.startswith((b"apps/", b"libs/"))
               for status, path in zip(changes[::2], changes[1::2]))


def source_status(root):
    source = Path(root) / "cFS"
    status = {"state": "missing", "url": OFFICIAL_URL, "revision": None}
    if not source.is_symlink() and (not source.exists() or (source.is_dir() and not any(source.iterdir()))):
        return status
    status["state"] = "occupied"
    if source.is_symlink() or not (source / ".git").exists():
        return status
    try:
        origin = _git(source, "config", "--local", "--get", "remote.origin.url").lower().rstrip("/").removesuffix(".git")
        if origin not in ("https://github.com/nasa/cfs", "git@github.com:nasa/cfs", "ssh://git@github.com/nasa/cfs"):
            return status
        status["revision"] = _git(source, "rev-parse", "HEAD")
        if not _has_nasa_base(source, status["revision"]):
            status["state"] = "revision-mismatch"
            return status
        # The index records installed modules. An upstream .gitmodules can also
        # describe optional paths with no gitlink at this revision.
        modules = _git(source, "submodule", "status", "--recursive").splitlines()
        populated = bool(modules) and all(line and line[0] not in "-+U" for line in modules)
        status["state"] = "ready" if populated and (source / "sample_defs/targets.cmake").is_file() else "incomplete"
    except (OSError, subprocess.CalledProcessError) as error:
        status["error"] = str(error)
    return status


def _checkout(source):
    if not _has_nasa_base(source, _git(source, "rev-parse", "HEAD")):
        if _git(source, "status", "--porcelain"):
            raise ValueError("Save your NASA checkout changes before selecting the pinned revision.")
        subprocess.run(["git", "-C", str(source), "fetch", "--depth=1", "origin", REVISION], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", REVISION], check=True)
    subprocess.run(["git", "-C", str(source), "submodule", "update", "--init", "--recursive",
                    "--depth=1", "--jobs=1", "--progress"], check=True)


def install(root):
    root = Path(root).resolve()
    source = root / "cFS"
    runtime = root / "hardware/.runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "clone-cfs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = source_status(root)["state"]
        if state == "occupied":
            raise ValueError("cFS is occupied by a different checkout or directory. Move it aside before cloning NASA cFS.")
        if state == "missing":
            with tempfile.TemporaryDirectory(prefix=".nasa-cfs-", dir=root) as temporary:
                staged = Path(temporary) / "cFS"
                subprocess.run(["git", "clone", "--depth=1", "--no-tags", "--progress", OFFICIAL_URL, str(staged)], check=True)
                _checkout(staged)
                if source_status(temporary)["state"] != "ready":
                    raise ValueError("NASA cFS download is incomplete. Run the clone step again.")
                staged.rename(source)
        elif state in {"incomplete", "revision-mismatch"}:
            _checkout(source)
        if source_status(root)["state"] != "ready":
            raise ValueError("Missing NASA mission sources. Check the checkout and rerun setup.")
        prepare_mission(root)
        return {"state": "ready", "revision": REVISION, "url": OFFICIAL_URL, "mission": "mission"}


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--status":
            source = source_status(Path(sys.argv[2]))
            print(json.dumps(source))
            sys.exit(0 if source["state"] == "ready" else 1)
        if len(sys.argv) != 1:
            sys.exit("Usage: python3 -m project.nasa_source [--status PROJECT]")
        print(json.dumps(install(Path.cwd())))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
