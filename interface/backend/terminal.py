"""Local interactive shells. PTYs belong to the Studio process, not to QEMU."""
import base64
from collections import deque
import fcntl
import os
from pathlib import Path
import pty
import re
import secrets
import select
import shlex
import signal
import struct
import subprocess
import sys
import termios
import threading
import time


SETUP_COMMANDS = {
    'clone-cfs': ('NASA cFS', ['./scripts/install-cfs.sh']),
    'board-key': ('Authorize SSH key', [sys.executable, '-m', 'hardware.infrastructure', 'authorize-key']),
    'board-service': ('Prepare cFS service', [sys.executable, '-m', 'hardware.infrastructure', 'prepare-service']),
    'native-tools': ('Install native tools', ['./scripts/setup-native.sh']),
    'dependencies': ('Install dependencies', ['./scripts/setup.sh', '--build-only']),
    'emulator-image': ('Install emulator image', ['./scripts/setup.sh']),
}


class Shell:
    LIMIT = 1024 * 1024

    def __init__(self, root, rows=24, cols=80, setup_action=None, target='local'):
        self.id = secrets.token_hex(12)
        self.setup_action = setup_action
        self.target = target
        self.started = time.time()
        self.progress = None
        self.lock = threading.RLock()
        self.input_lock = threading.Lock()
        self.chunks = deque()
        self.end = self.start = 0
        self.closed = False
        self.interrupted = False
        self.exit_code = None
        self.master, slave = pty.openpty()
        os.set_blocking(self.master, False)
        shell = os.environ.get('SHELL', '/bin/bash')
        if not Path(shell).is_file():
            shell = '/bin/bash'
        if setup_action:
            self.name, command = SETUP_COMMANDS[setup_action]
            child_args = ['--setup', *command]
        else:
            self.name = Path(shell).name
            child_args = ['--child', shell, '-i']
        try:
            self.resize(rows, cols)
            self.process = subprocess.Popen(
                [sys.executable, __file__, *child_args], cwd=root,
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
                env={**os.environ, 'TERM': 'xterm-256color', 'COLORTERM': 'truecolor'})
        except Exception:
            os.close(self.master)
            raise
        finally:
            os.close(slave)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while not self.closed:
                if not select.select([self.master], [], [], .2)[0]:
                    continue
                try:
                    data = os.read(self.master, 65536)
                except BlockingIOError:
                    continue
                if not data:
                    break
                with self.lock:
                    if self.setup_action:
                        for match in re.finditer(rb"(?<![\d.])(100|[1-9]?\d)%", data):
                            self.progress = int(match[1])
                    self.chunks.append(data)
                    self.end += len(data)
                    while self.end - self.start > self.LIMIT:
                        self.start += len(self.chunks.popleft())
        except OSError:
            pass  # Linux PTYs report EIO after the last slave closes.
        finally:
            self.exit_code = self.process.wait()

    def snapshot(self):
        code = self.process.poll()
        return {'id': self.id, 'action': 'shell', 'target': self.target, 'kind': 'shell',
                'name': self.name, 'started': self.started, 'streaming': True,
                'setup_action': self.setup_action, 'progress': self.progress, 'operation_complete': not self.setup_action or code is not None,
                'status': 'running' if code is None else 'succeeded' if code == 0 else 'cancelled' if self.interrupted else 'failed',
                'exit_code': code, 'lines': []}

    def read(self, cursor):
        if type(cursor) is not int or cursor < 0:
            raise ValueError('Invalid terminal cursor')
        with self.lock:
            if cursor > self.end:
                raise ValueError('Terminal cursor exceeds output')
            offset = max(cursor, self.start)
            skip = offset - self.start
            data = bytearray()
            for chunk in self.chunks:
                if skip < len(chunk):
                    data.extend(chunk[skip:skip + 65536 - len(data)])
                    if len(data) == 65536:
                        break
                skip = max(0, skip - len(chunk))
            return {'data': base64.b64encode(data).decode(), 'cursor': offset + len(data),
                    'truncated': cursor < self.start, 'exited': self.exit_code is not None, 'exit_code': self.exit_code}

    def write(self, data):
        if not isinstance(data, str) or len(data.encode()) > 65536:
            raise ValueError('Invalid terminal input')
        with self.input_lock:
            if self.closed or self.process.poll() is not None:
                raise ValueError('This shell has exited. Open a new terminal.')
            remaining = memoryview(data.encode())
            deadline = time.monotonic() + 5
            while remaining:
                if time.monotonic() >= deadline:
                    raise ValueError('The shell is not accepting input.')
                if self.closed:
                    raise ValueError('This shell has exited.')
                if not select.select([], [self.master], [], .1)[1]:
                    continue
                try:
                    remaining = remaining[os.write(self.master, remaining):]
                except BlockingIOError:
                    continue

    def resize(self, rows, cols):
        if any(type(n) is not int or not 2 <= n <= 1000 for n in (rows, cols)):
            raise ValueError('Invalid terminal size')
        with self.lock:
            if self.closed:
                return
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            groups = set()
            if self.process.poll() is None:
                groups.add(self.process.pid)
                try:
                    groups.add(os.tcgetpgrp(self.master))
                except OSError:
                    pass
            groups.discard(0)
            groups.discard(os.getpgrp())
            for group in groups:
                try:
                    os.killpg(group, signal.SIGHUP)
                    self.interrupted = True
                except ProcessLookupError:
                    pass
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            for group in groups:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.process.wait(timeout=2)
        self.reader.join(timeout=1)
        with self.input_lock:
            os.close(self.master)


class Shells:
    def __init__(self, root):
        self.root = root
        self.sessions = {}
        self.lock = threading.RLock()
        self.closing = False

    def create(self, rows=24, cols=80, setup_action=None, target=None):
        with self.lock:
            if self.closing:
                raise ValueError('The terminal server is closing.')
            if setup_action is not None:
                if not isinstance(setup_action, str) or setup_action not in SETUP_COMMANDS:
                    raise ValueError('Unknown installation command.')
                if target not in ('native', 'physical', 'qemu'):
                    raise ValueError('Select an installation target.')
                finished = []
                for session in self.sessions.values():
                    if not session.setup_action:
                        continue
                    if session.process.poll() is None:
                        if session.setup_action == setup_action and session.target == target:
                            return session.snapshot()
                        raise ValueError('Another installation is running.')
                    finished.append(session)
                for session in finished[:-8]:
                    session.close()
                    del self.sessions[session.id]
            if sum(s.process.poll() is None for s in self.sessions.values()) >= 16:
                raise ValueError('Close a shell before opening another (16 active).')
            shell = Shell(self.root, rows, cols, setup_action, target if setup_action else 'local')
            self.sessions[shell.id] = shell
            return shell.snapshot()

    def get(self, ident):
        with self.lock:
            if not isinstance(ident, str) or ident not in self.sessions:
                raise ValueError('Terminal session not found')
            return self.sessions[ident]

    def snapshots(self):
        with self.lock:
            return [shell.snapshot() for shell in self.sessions.values()]

    def close(self):
        with self.lock:
            self.closing = True
            for shell in self.sessions.values():
                shell.close()


if __name__ == '__main__' and sys.argv[1:2] in (['--child'], ['--setup']):
    # Set the controlling TTY in a fresh interpreter, never preexec_fn in a server thread.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    if sys.argv[1] == '--setup':
        print('$ ' + shlex.join(sys.argv[2:]), flush=True)
    os.execv(sys.argv[2], sys.argv[2:])
