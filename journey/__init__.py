"""The first-flight journey is a fold of observed evidence in one checkout."""
from contextlib import closing
from dataclasses import dataclass
import json
import fcntl
import math
from pathlib import Path
import sqlite3
import time

STEPS = ("target", "boot", "event", "app", "command", "send", "sensor", "test", "board")
TARGETS = ("native", "qemu", "physical")
RUNTIME_STEPS = frozenset(("boot", "event", "send", "sensor", "test", "board"))
SHIPPED_APPS = frozenset(("hal_temp", "hal_mag", "hal_mpu"))


def shipped_apps(root):
    """Identify the preinstalled readers still present in a legacy mission."""
    from project.flight_sources import module_alias
    root = Path(root)
    directory = root / "mission/apps"
    if not directory.is_dir() or module_alias(root, directory):
        return frozenset()
    return frozenset(name for name in SHIPPED_APPS if (directory / name / "CMakeLists.txt").is_file())


@dataclass(frozen=True)
class Observation:
    step: str
    target: str
    at: float
    ref: dict


def route(step, target):
    if step == "target":
        return "/#target"
    if step == "board":
        return "/?target=physical#board"
    return f"/studio?target={target}#{step}"


def derive(target, events):
    """Fold in commit order. A delayed observation cannot predate the last reset."""
    facts = {}
    cutoff = 0
    attempt = None
    contact_completed = False
    for event in events:
        if event.target != target:
            continue
        if event.step == "reset":
            cutoff = max(cutoff, event.at)
            facts.clear()
            attempt = None
            contact_completed = False
        elif event.step == "boot-start" and event.at > cutoff:
            if attempt and event.at < attempt["started"]:
                continue
            attempt = {"id": event.ref["job"], "started": event.at, "status": "running"}
            for step in RUNTIME_STEPS:
                facts.pop(step, None)
        elif event.step == "boot-finish":
            if attempt and event.ref.get("job") == attempt["id"]:
                attempt["status"] = event.ref["status"]
        else:
            boundary = max(cutoff, attempt["started"] if attempt and event.step in RUNTIME_STEPS else 0)
            if (event.at > boundary and (event.ref.get("sent_at") or event.at) > boundary
                    and event.ref.get("started", boundary) >= boundary and event.step not in facts):
                facts[event.step] = event
        if all(step in facts for step in ("target", "boot", "event")) and (not attempt or attempt["status"] == "succeeded"):
            contact_completed = True
    current, reachable, steps = None, True, {}
    for step in STEPS:
        done = reachable and step in facts and (step != "boot" or not attempt or attempt["status"] == "succeeded")
        fact = facts.get(step)
        steps[step] = {"done": done, "observed_at": fact.at if fact else None, "reachable": reachable,
                       "ref": fact.ref if fact else None,
                       "route": route(step, target)}
        if reachable and not done:
            current = step
        reachable = done
    return {"target": target, "steps": steps, "current": current, "reset_at": cutoff, "boot_attempt": attempt, "contact_completed": contact_completed,
            "next_route": route(current, target) if current else None}


class Store:
    def __init__(self, root):
        from project.defaults import runtime_dir
        self.path = runtime_dir(root) / "journey.sqlite3"

    def observe(self, target, step, ref, at=None):
        if target not in TARGETS or step not in (*STEPS, "reset", "boot-start", "boot-finish"):
            raise ValueError("Unknown journey target or step")
        if not isinstance(ref, dict) or not ref:
            raise ValueError("An observation needs a reference")
        at = time.time() if at is None else at
        if not math.isfinite(at) or at <= 0:
            raise ValueError("Invalid observation time")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("a") as writer:
            fcntl.flock(writer, fcntl.LOCK_EX)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""CREATE TABLE IF NOT EXISTS evidence
                              (target TEXT NOT NULL, step TEXT NOT NULL, at REAL NOT NULL, ref TEXT NOT NULL,
                               UNIQUE (target, step, at, ref))""")
                db.execute("INSERT OR IGNORE INTO evidence VALUES (?, ?, ?, ?)",
                           (target, step, at, json.dumps(ref, sort_keys=True)))
        return at

    def events(self, target):
        if target is not None and target not in TARGETS:
            raise ValueError("Unknown journey target")
        if target is None or not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='evidence'").fetchone():
                return []
            rows = db.execute("SELECT step, target, at, ref FROM evidence WHERE target=? ORDER BY rowid", (target,))
            return [Observation(step, target_id, at, json.loads(ref)) for step, target_id, at, ref in rows]

    def snapshot(self, target):
        state = derive(target, self.events(target))
        native = state if target == "native" else derive("native", self.events("native"))
        state["remote_unlocked"] = native["contact_completed"]
        state["optional_board"] = (state["current"] == "board" and target != "physical"
                                   and not self.references("physical", "target"))
        return state

    def begin_boot(self, target, job, started):
        """A new execution keeps source work but requires fresh runtime evidence."""
        self.observe(target, "boot-start", {"job": job}, started)

    def finish_boot(self, target, job, status):
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("Invalid boot outcome")
        self.observe(target, "boot-finish", {"job": job, "status": status})

    def reset(self, target):
        if target is not None:
            self.observe(target, "reset", {"action": "start over"})
        return self.snapshot(target)

    def references(self, target, step):
        latest = {}
        cutoff = 0
        for event in self.events(target):
            if event.step == "reset":
                latest.clear()
                cutoff = max(cutoff, event.at)
            elif event.step == "boot-start" and step in RUNTIME_STEPS and event.at > cutoff:
                latest.clear()
                cutoff = event.at
            elif (event.step == step and event.at > cutoff and (event.ref.get("sent_at") or event.at) > cutoff
                  and event.ref.get("started", cutoff) >= cutoff):
                latest[json.dumps(event.ref, sort_keys=True)] = event.ref
        return list(latest.values())
