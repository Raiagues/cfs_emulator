"""Correlate linked flight telemetry with the target and register write that produced it."""
from contextlib import closing, ExitStack
import errno
import fcntl
import json
from pathlib import Path
import selectors
import socket
import sqlite3
import time

from journey import Store
from project.defaults import sensor_timeout
from project.model import identifier, load_config, read_manifests
from project.sensor_models import load, model_paths


def fields(spec):
    names = spec.get("abi", {}).get("fields")
    scalar = spec.get("abi", {}).get("sample") == "int32"
    return {output["name"]: "Value" if scalar else "Value." + (names[i] if names else "Value_" + output["name"].replace("-", "_"))
            for i, output in enumerate(spec.get("outputs", []))}


def instance(root, target):
    path = Path(root) / f"hardware/.runtime/operational-{target}.json"
    try:
        return json.loads(path.read_bytes()).get("instance")
    except FileNotFoundError:
        return None


def remember_write(root, device, flight, expected, tolerance):
    path = Store(root).path
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS sensor_writes
                      (device TEXT, instance TEXT, at REAL, expected TEXT, tolerance TEXT)""")
        db.execute("INSERT INTO sensor_writes VALUES(?,?,?,?,?)", (device, flight, time.time(),
                   json.dumps(expected), json.dumps(tolerance)))
        db.execute("""DELETE FROM sensor_writes WHERE device=? AND rowid NOT IN
                      (SELECT rowid FROM sensor_writes WHERE device=? ORDER BY rowid DESC LIMIT 64)""", (device, device))


def matching_write(store, device, flight, at, values):
    if not store.path.exists():
        return None
    with closing(sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sensor_writes'").fetchone():
            return None
        rows = db.execute("""SELECT at,expected,tolerance FROM sensor_writes WHERE device=? AND instance=? AND at<=?
                             ORDER BY at DESC""", (device, flight, at))
        for when, expected, tolerance in rows:
            expected, tolerance = json.loads(expected), json.loads(tolerance)
            if expected and all(k in values and abs(values[k] - val) <= tolerance[k] for k, val in expected.items()):
                return when
    return None


def board_socket(root, device):
    return Path(root) / "hardware/.runtime" / ("board-sensor-" + identifier(device) + ".sock")


def send_reading(address, packet):
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        try:
            client.sendto(json.dumps(packet).encode(), str(address))
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.ECONNREFUSED):
                raise
            return False
    return True


class SensorTelemetry:
    def __init__(self, root, target):
        self.root, self.target = root, target
        self.store = Store(root)
        self.flight = instance(root, target)
        self.signals = {}
        self.confirmed = set()
        if self.flight is None or target not in ("native", "physical"):
            return
        paths = model_paths(root)
        config = load_config(root)
        manifests = {item["name"]: item for item in read_manifests(root, config)}
        for app in config["apps"]:
            name = identifier(app["name"])
            manifest = manifests[name]
            for sensor in manifest["sensors"]:
                device = app.get("sensors", {}).get(sensor["name"])
                if device and sensor.get("driver") in paths:
                    self.signals[name, sensor["tlm_mid"]] = (device, fields(load(paths[sensor["driver"]])))

    def received(self, packet):
        signal = self.signals.get((packet["app"], packet["mid"]))
        if not signal or packet["errors"]:
            return
        device, names = signal
        raw = packet["values"]
        if raw.get("Valid") != 1 or raw.get("Status") != 0:
            return
        values = {key: raw[field] for key, field in names.items() if type(raw.get(field)) in (int, float)}
        if not values:
            return
        at = packet["received_at"]
        reference = {"device": device, "app": packet["app"], "mid": packet["mid"], "sequence": packet["sequence"]}
        if self.target == "physical":
            if not send_reading(board_socket(self.root, device), {"at": at, "values": values}):
                return
        if device in self.confirmed or not any(ref["app"] == packet["app"] for ref in self.store.references(self.target, "app")):
            return
        if self.target == "native":
            written = matching_write(self.store, device, self.flight, at, values)
            if written is None or written <= self.store.snapshot(self.target)["reset_at"]:
                return
            reference["write_at"] = written
        self.store.observe(self.target, "sensor", reference, at)
        self.confirmed.add(device)


def read_board(root, devices, on_sample, steps):
    with ExitStack() as resources:
        selector = resources.enter_context(selectors.DefaultSelector())
        for device in devices:
            address = board_socket(root, device["id"])
            lock = resources.enter_context(address.with_suffix(".lock").open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError(f"Already reading {device['id']}") from None
            address.unlink(missing_ok=True)
            channel = resources.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM))
            channel.bind(str(address))
            resources.callback(address.unlink, missing_ok=True)
            selector.register(channel, selectors.EVENT_READ, device)
        print("Reading physical sensor telemetry from TO_LAB", flush=True)
        started, count = time.monotonic(), 0
        while steps is None or count < steps:
            events = selector.select(sensor_timeout())
            if not events:
                raise ValueError("No physical sensor telemetry. Connect the ground receiver and send TO_LAB ENABLE_OUTPUT.")
            for key, _ in events:
                sample = json.loads(key.fileobj.recv(65535))
                values = sample["values"]
                if on_sample:
                    on_sample(time.monotonic() - started, [(key.data, values)])
                else:
                    print(key.data["id"], values, flush=True)
                count += 1
