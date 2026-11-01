"""Local interactive shells. PTYs belong to the Studio process, not to QEMU."""
import base64
from collections import deque
import fcntl
import os
from pathlib import Path
import pty
import secrets
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time


class Shell:
    LIMIT = 1024 * 1024

    def __init__(self, root, rows=24, cols=80):
        self.id = secrets.token_hex(12)
        self.started = time.time()
        self.lock = threading.RLock()
        self.input_lock = threading.Lock()
        self.chunks = deque()
        self.end = self.start = 0
        self.closed = False
        self.exit_code = None
        self.master, slave = pty.openpty()
        os.set_blocking(self.master, False)
        shell = os.environ.get('SHELL', '/bin/bash')
        if not Path(shell).is_file():
            shell = '/bin/bash'
        self.name = Path(shell).name
        try:
            self.resize(rows, cols)
            self.process = subprocess.Popen(
                [sys.executable, __file__, '--child', shell], cwd=root,
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
                    self.chunks.append(data)
                    self.end += len(data)
                    while self.end - self.start > self.LIMIT:
                        self.start += len(self.chunks.popleft())
        except OSError:
            pass  # Linux PTYs report EIO after the last slave closes.
        finally:
            self.exit_code = self.process.wait()

    def snapshot(self):
        return {'id': self.id, 'action': 'shell', 'target': 'local', 'kind': 'shell',
                'name': self.name, 'started': self.started, 'streaming': True,
                'operation_complete': True, 'status': 'running' if self.process.poll() is None else 'succeeded' if self.process.returncode == 0 else 'cancelled' if self.closed else 'failed',
                'exit_code': self.process.returncode, 'lines': []}

    def read(self, cursor):
        if type(cursor) is not int or cursor < 0:
            raise ValueError('Invalid terminal cursor')
        with self.lock:
            if cursor > self.end:
                raise ValueError('Terminal cursor exceeds output')
            offset = max(cursor, self.start)
            data = b''.join(self.chunks)[offset - self.start:offset - self.start + 65536]
            return {'data': base64.b64encode(data).decode(), 'cursor': offset + len(data),
                    'truncated': cursor < self.start, 'exited': self.exit_code is not None}

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
            groups = {self.process.pid}
            try:
                groups.add(os.tcgetpgrp(self.master))
            except OSError:
                pass
            groups.discard(0)
            groups.discard(os.getpgrp())
            for group in groups:
                try:
                    os.killpg(group, signal.SIGHUP)
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

    def create(self, rows=24, cols=80):
        with self.lock:
            if self.closing:
                raise ValueError('The terminal server is closing.')
            if sum(s.process.poll() is None for s in self.sessions.values()) >= 16:
                raise ValueError('Close a shell before opening another (16 active).')
            shell = Shell(self.root, rows, cols)
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


if __name__ == '__main__' and sys.argv[1:2] == ['--child']:
    # Set the controlling TTY in a fresh interpreter, never preexec_fn in a server thread.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.execv(sys.argv[2], [sys.argv[2], '-i'])
