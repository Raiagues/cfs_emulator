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
    'emulator-image': ('Install emulator image', ['./start', '--no-ui', 'emulator', 'image']),
    'emulator-key': ('Prepare SSH identity', ['./start', '--no-ui', 'emulator', 'key']),
}


class Shell:
    LIMIT = 1024 * 1024

    def __init__(self, root, rows=24, cols=80, setup_action=None, target='local', on_change=lambda: None):
        self.on_change = on_change
        self.id = secrets.token_hex(12)
        self.setup_action = setup_action
        self.target = target
        self.started = time.time()
        self.prompt_tail = b""
        self.lock = threading.RLock()
        self.output = threading.Condition(self.lock)
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
                        # Interactive confirmations usually end without a newline.
                        tail = (self.prompt_tail + data[-256:])[-256:]
                        self.prompt_tail = re.split(rb"[\r\n]", tail)[-1]
                    self.chunks.append(data)
                    self.end += len(data)
                    while self.end - self.start > self.LIMIT:
                        self.start += len(self.chunks.popleft())
                    self.output.notify_all()
                    self.on_change()
        except OSError:
            pass  # Linux PTYs report EIO after the last slave closes.
        finally:
            status = self.process.wait()
            with self.output:
                self.exit_code = status
                self.output.notify_all()
            self.on_change()

    def waiting_for_input(self):
        try:
            if not (termios.tcgetattr(self.master)[3] & termios.ECHO):
                return True  # sudo and SSH temporarily disable terminal echo.
        except (OSError, termios.error):
            return False
        return bool(re.search(rb"(?:\(yes/no(?:/\[fingerprint\])?\)|\[y/n\])\??\s*$",
                              self.prompt_tail, re.IGNORECASE))

    def snapshot(self):
        code = self.process.poll()
        return {'id': self.id, 'action': 'shell', 'target': self.target, 'kind': 'shell',
                'name': self.name, 'started': self.started, 'streaming': True,
                'setup_action': self.setup_action, 'progress': None,
                'input_required': bool(self.setup_action and code is None and self.waiting_for_input()),
                'operation_complete': not self.setup_action or code is not None,
                'status': 'running' if code is None else 'succeeded' if code == 0 else 'cancelled' if self.interrupted else 'failed',
                'exit_code': code, 'error': self.last_diagnostic() if self.setup_action and code else None, 'lines': []}

    def last_diagnostic(self):
        with self.lock:
            tail = b"".join(list(self.chunks)[-4:])[-8192:]
        plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", tail.decode(errors="replace"))
        lines = [line.strip() for line in plain.splitlines() if line.strip()]
        return next((line for line in reversed(lines) if re.search(r"(error|failed|denied|unable|^E:)", line, re.I)),
                    lines[-1] if lines else "")[:360]

    def wait_read(self, cursor):
        with self.output:
            if type(cursor) is not int or cursor < 0:
                raise ValueError('Invalid terminal cursor')
            self.output.wait_for(lambda: self.end != cursor or self.exit_code is not None or self.closed, timeout=20)
            return self.read(cursor)

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
    def __init__(self, root, on_change=lambda: None):
        self.on_change = on_change
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
            shell = Shell(self.root, rows, cols, setup_action, target if setup_action else 'local', self.on_change)
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
