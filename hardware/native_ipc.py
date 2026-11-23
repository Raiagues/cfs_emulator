"""Workspace-owned key files for the unmodified Linux PSP's persistent memory.

The PSP uses ftok on three relative filenames. Build installation must not change
those inodes, and an existing SysV segment is reusable only with our recorded
identity. This module never removes, resizes or attaches to shared memory.
"""
import ctypes
import errno
import os
from pathlib import Path
import re
import secrets
import stat

from hardware.state import RuntimeState

NAMES = ('.cdskeyfile', '.resetkeyfile', '.reservedkeyfile')
IDENTITY = ('key', 'shmid', 'ctime', 'size', 'uid', 'cpid')


def shared_segments():
    """Read kernel metadata; unlike shmget this cannot create or attach anything."""
    rows = Path('/proc/sysvipc/shm').read_text().splitlines()
    if not rows or not set((*IDENTITY, 'nattch')).issubset(rows[0].split()):
        raise RuntimeError('Cannot inspect native shared-memory identities on this host.')
    columns = rows[0].split()
    segments = {}
    for line in rows[1:]:
        values = line.split()
        if len(values) != len(columns):
            raise RuntimeError('Incomplete native shared-memory metadata.')
        row = {name: int(value) for name, value in zip(columns, values)}
        row['key'] &= 0xffffffff
        if row['key']:
            segments[row['key']] = row
    return segments


def file_key(path):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ftok.argtypes = (ctypes.c_char_p, ctypes.c_int)
    libc.ftok.restype = ctypes.c_int
    value = libc.ftok(os.fsencode(path), ord('R'))
    if value == -1:
        raise OSError(ctypes.get_errno(), 'Cannot derive the native PSP memory key', str(path))
    return value & 0xffffffff


def boot_identity():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


class NativeIPC:
    RECORD = 'native-ipc.json'

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = RuntimeState(self.root)
        self.directory = self.store.directory / 'native-ipc'

    @staticmethod
    def _owned(path, directory=False, private=False):
        info = path.lstat()
        kind = stat.S_ISDIR if directory else stat.S_ISREG
        forbidden = 0o077 if private else (0o002 if directory else 0o022)
        if not kind(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & forbidden:
            raise ValueError('Unsafe native IPC path or permissions: ' + str(path))
        if not directory and info.st_size:
            raise ValueError('Native PSP key file must be empty: ' + str(path))
        return info

    def _payload(self, payload):
        payload = Path(payload)
        expected = self.root / 'mission/build-native/exe/cpu1'
        if payload != expected:
            raise ValueError('Native IPC payload must be this workspace native CPU1 directory.')
        for path in (self.root / 'mission', expected.parents[1], expected.parent, expected):
            if path.is_symlink():
                raise ValueError('Native IPC payload cannot follow a symbolic link.')
        self._owned(payload, directory=True)
        return payload

    def _anchors(self, record):
        generation = record.get('generation', '')
        if not re.fullmatch(r'[0-9a-f]{32}', generation):
            raise ValueError('Invalid native IPC generation.')
        directory = self.directory / generation
        self._owned(directory, directory=True, private=True)
        keys = record.get('keys', {})
        if set(keys) != set(NAMES):
            raise ValueError('Incomplete native IPC key record.')
        for name in NAMES:
            path = directory / name
            info = self._owned(path, private=True)
            if (info.st_dev, info.st_ino, file_key(path)) != (keys[name]['device'], keys[name]['inode'], keys[name]['key']):
                raise ValueError('Native IPC key identity changed: ' + name)
        return directory

    @staticmethod
    def _matches(row, known):
        return known and all(row.get(field) == known.get(field) for field in IDENTITY)

    def _generation(self, fingerprint, occupied, boot):
        generation = secrets.token_hex(16)
        directory = self.directory / generation
        directory.mkdir(mode=0o700)
        keys = {}
        for name in NAMES:
            for attempt in range(256):
                # Retain rejected inodes during allocation: deleting immediately
                # can make the filesystem hand the same colliding inode back.
                candidate = directory / (name + '-' + str(attempt))
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                os.close(fd)
                key = file_key(candidate)
                if key not in occupied:
                    candidate.rename(directory / name)
                    info = (directory / name).stat()
                    keys[name] = dict(key=key, device=info.st_dev, inode=info.st_ino)
                    occupied.add(key)
                    break
            else:
                raise RuntimeError('Could not allocate unused native PSP memory keys. No flight process was started.')
        return dict(workspace=str(self.root), build=fingerprint, boot=boot, generation=generation, keys=keys, segments={})

    def prepare(self, payload, fingerprint):
        """Install stable hardlinks after a build and recheck before every launch."""
        payload = self._payload(payload)
        if not isinstance(fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
            raise ValueError('Invalid native build fingerprint.')
        self.store.directory.mkdir(parents=True, exist_ok=True)
        self._owned(self.store.directory, directory=True)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self._owned(self.directory, directory=True, private=True)
        if self.directory.stat().st_dev != payload.stat().st_dev:
            raise OSError(errno.EXDEV, 'Native IPC runtime and payload must be on the same filesystem; hardlinks are required.')
        for name in NAMES:
            path = payload / name
            if path.exists() or path.is_symlink():
                self._owned(path)
        boot = boot_identity()
        with self.store.writer() as db:
            current = dict(self.store.lookup(db, self.RECORD, {}))
            table = shared_segments()
            reusable = bool(current and current.get('workspace') == str(self.root) and current.get('build') == fingerprint)
            if reusable:
                self._anchors(current)
                for name, info in current['keys'].items():
                    segment = table.get(info['key'])
                    if segment is None:
                        continue
                    known = current.get('segments', {}).get(name) if current.get('boot') == boot else None
                    if not self._matches(segment, known):
                        reusable = False
                    elif segment['nattch']:
                        raise RuntimeError('Native PSP memory is still attached to a process. Stop that workspace instance first.')
            if not reusable:
                current = self._generation(fingerprint, set(table), boot)
            elif current.get('boot') != boot:
                current.update(boot=boot, segments={})
            anchors = self._anchors(current)
            for name in NAMES:
                destination = payload / name
                source = anchors / name
                if destination.exists() and os.path.samefile(source, destination):
                    continue
                temporary = payload / (name + '.link-' + secrets.token_hex(8))
                try:
                    os.link(source, temporary, follow_symlinks=False)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
            # Fail closed if an unknown segment appeared during preparation.
            fresh = shared_segments()
            for name, info in current['keys'].items():
                row = fresh.get(info['key'])
                if row and not self._matches(row, current.get('segments', {}).get(name)):
                    raise RuntimeError('A native PSP memory key became occupied. Retry Run cFS; no process was started.')
            self._save(db, current)
        return current

    def _save(self, db, record):
        # Preserve every owned generation for future inspection; rotation never
        # removes its segments or discards their recorded identities.
        self.store.store(db, 'native-ipc-' + record['generation'] + '.json', record)
        self.store.store(db, self.RECORD, record)

    def capture(self, prepared, pid, started, *, complete=False):
        """Retain only identities created by this process or already proven ours."""
        table = shared_segments()
        found = {}
        errors = []
        for name, info in prepared['keys'].items():
            row = table.get(info['key'])
            if row is None:
                if complete:
                    errors.append('Native cFS did not create its expected PSP memory segment: ' + name)
                continue
            known = prepared.get('segments', {}).get(name)
            ours = row['cpid'] == pid and row['uid'] == os.geteuid() and row['ctime'] >= int(started)
            if not self._matches(row, known) and not ours:
                errors.append('Native PSP shared-memory identity is not owned by this execution: ' + name)
                continue
            found[name] = {field: row[field] for field in IDENTITY}
        with self.store.writer() as db:
            saved = self.store.lookup(db, self.RECORD, {})
            if saved.get('generation') != prepared['generation'] or saved.get('boot') != boot_identity():
                raise RuntimeError('Native PSP memory generation changed during startup.')
            saved['segments'] = found
            self._save(db, saved)
        if errors:
            raise RuntimeError('; '.join(errors))
