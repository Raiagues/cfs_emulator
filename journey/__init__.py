"""The first-flight journey is a fold of observed evidence in one checkout."""
from contextlib import closing
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sqlite3
import time

STEPS = ("target", "boot", "event", "app", "command", "send", "sensor", "test", "board")
TARGETS = ("native", "qemu", "physical")
SHIPPED_APPS = frozenset(("hal_temp", "hal_mag", "hal_mpu"))


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
    for event in events:
        if event.target != target:
            continue
        if event.step == "reset":
            cutoff = max(cutoff, event.at)
            facts.clear()
        elif event.at > cutoff and (event.ref.get("sent_at") or event.at) > cutoff and event.step not in facts:
            facts[event.step] = event.at
    current, reachable, steps = None, True, {}
    for step in STEPS:
        done = reachable and step in facts
        steps[step] = {"done": done, "observed_at": facts.get(step), "reachable": reachable,
                       "route": route(step, target)}
        if reachable and not done:
            current = step
        reachable = done
    return {"target": target, "steps": steps, "current": current, "reset_at": cutoff,
            "next_route": route(current, target) if current else None}


class Store:
    def __init__(self, root):
        self.path = Path(root).resolve() / "hardware/.runtime/journey.sqlite3"

    def observe(self, target, step, ref, at=None):
        if target not in TARGETS or step not in (*STEPS, "reset"):
            raise ValueError("Unknown journey target or step")
        if not isinstance(ref, dict) or not ref:
            raise ValueError("An observation needs a reference")
        at = time.time() if at is None else at
        if not math.isfinite(at) or at <= 0:
            raise ValueError("Invalid observation time")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
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
        return derive(target, self.events(target))

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
            elif event.step == step and event.at > cutoff:
                latest[json.dumps(event.ref, sort_keys=True)] = event.ref
        return list(latest.values())
