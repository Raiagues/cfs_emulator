"""Versioned runtime records shared by the CLI, jobs and HTTP adapter."""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
import fcntl
import json
from pathlib import Path
import re
import sqlite3

from project.defaults import runtime_dir


@dataclass(frozen=True)
class Selection:
    target: str
    journey_origin: str | None = None

    def __post_init__(self):
        targets = ('native', 'qemu', 'physical')
        if self.target not in targets or self.journey_origin is not None and self.journey_origin not in targets:
            raise ValueError('Invalid saved execution target')


@dataclass(frozen=True)
class NativeFlight:
    pid: int
    instance: str
    started_at: float


@dataclass(frozen=True)
class Emulator:
    image: str
    ssh_port: int


@dataclass(frozen=True)
class BuildSettings:
    jobs: int = 1

    def __post_init__(self):
        if type(self.jobs) is not int or not 1 <= self.jobs <= 64:
            raise ValueError('Choose 1 to 64 parallel build jobs')


class RuntimeState:
    VERSION = 1

    def __init__(self, root):
        self.directory = runtime_dir(root)
        self.database = self.directory / 'runtime.sqlite3'

    @staticmethod
    def key(name):
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+\.json', name):
            raise ValueError('Invalid runtime record name')
        return name.removesuffix('.json')

    def legacy(self, name, fallback):
        try:
            return json.loads((self.directory / name).read_bytes())
        except FileNotFoundError:
            return fallback

    def lookup(self, db, name, fallback):
        row = db.execute('SELECT version, value FROM records WHERE name=?', (self.key(name),)).fetchone()
        if row is None:
            return self.legacy(name, fallback)
        if row[0] != self.VERSION:
            raise ValueError(f'Unsupported version of runtime record {name}: {row[0]}')
        return json.loads(row[1]) if row[1] is not None else fallback

    def read(self, name, fallback=None):
        self.key(name)
        if not self.database.exists():
            return self.legacy(name, fallback)
        with closing(sqlite3.connect(self.database, timeout=30)) as db:
            # A new database may be visible while its creator is acquiring its first transaction.
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone():
                return self.legacy(name, fallback)
            return self.lookup(db, name, fallback)

    @contextmanager
    def writer(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.database.with_suffix('.lock').open('a') as writer:
            fcntl.flock(writer, fcntl.LOCK_EX)
            with closing(sqlite3.connect(self.database, timeout=30)) as db, db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS records(name TEXT PRIMARY KEY, version INTEGER NOT NULL, value TEXT)')
                yield db

    def store(self, db, name, value):
        if value is not None and not isinstance(value, dict):
            raise ValueError('A runtime record must be an object')
        db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)',
                   (self.key(name), self.VERSION, None if value is None else json.dumps(value, allow_nan=False)))

    def write(self, name, value):
        with self.writer() as db:
            self.store(db, name, value)

    @contextmanager
    def edit(self, name):
        with self.writer() as db:
            data = self.lookup(db, name, {})
            yield data
            self.store(db, name, data)

    def selection(self):
        data = self.read('target.json')
        return Selection(**data) if data is not None else None

    def choose(self, selection):
        self.write('target.json', {key: value for key, value in asdict(selection).items() if value is not None})

    def build_settings(self):
        return BuildSettings(**self.read('native-build-settings.json', {}))

    def native_flight(self):
        return NativeFlight(**self.read('native.json', {}))

    def emulator(self, defaults):
        return Emulator(**{**asdict(defaults), **self.read('emulator.json', {})})
