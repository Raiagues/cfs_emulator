"""Find and gracefully stop this checkout's local Studio server on Linux."""
import argparse
from dataclasses import dataclass
import http.client
import os
from pathlib import Path
import signal
import socket
import sys
import time

from project.defaults import http_port, loopback


@dataclass(frozen=True)
class Instance:
    pid: int
    started: str


def listeners(host, port):
    """Return listening socket inodes for the exact IPv4 loopback endpoint."""
    address = int.from_bytes(socket.inet_aton(host), sys.byteorder)
    endpoints = {f'{address:08X}:{port:04X}', f'00000000:{port:04X}'}
    try:
        rows = Path('/proc/net/tcp').read_text().splitlines()[1:]
    except OSError:
        return set()
    return {row.split()[9] for row in rows
            if row.split()[1] in endpoints and row.split()[3] == '0A'}


def script_argument(argv):
    """Read Python's script argument, never a positional argument to another script."""
    flags = {b'-b', b'-bb', b'-B', b'-d', b'-E', b'-i', b'-I', b'-O', b'-OO',
             b'-P', b'-q', b'-s', b'-S', b'-u', b'-v', b'-vv', b'-x', b'-R'}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == b'--':
            return argv[index + 1] if index + 1 < len(argv) else None
        if arg in flags:
            index += 1
        elif arg in {b'-W', b'-X', b'--check-hash-based-pycs'}:
            index += 2
        elif arg.startswith((b'-W', b'-X')) and len(arg) > 2:
            index += 1
        elif not arg or arg.startswith(b'-'):
            return None
        else:
            return arg
    return None


def identity(root, pid):
    process = Path('/proc') / str(pid)
    try:
        if process.stat().st_uid != os.getuid():
            return None
        fields = (process / 'stat').read_text().rsplit(') ', 1)[1].split()
        if fields[0] == 'Z':
            return None
        if (process / 'exe').resolve() != Path(sys.executable).resolve():
            return None
        argv = (process / 'cmdline').read_bytes().split(b'\0')[1:]
        argument = script_argument(argv)
        if argument is None:
            return None
        cwd = (process / 'cwd').resolve()
        script = (Path(root) / 'interface/server.py').resolve()
        if (cwd / os.fsdecode(argument)).resolve() != script:
            return None
        return Instance(int(pid), fields[19])
    except (OSError, ValueError, IndexError):
        return None


def owner(root, host, port):
    inodes = listeners(host, port)
    if not inodes:
        return None
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():
            continue
        instance = identity(root, process.name)
        if instance is None:
            continue
        owns_socket = False
        sockets = {f'socket:[{inode}]' for inode in inodes}
        try:
            descriptors = list((process / 'fd').iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                if os.readlink(descriptor) in sockets:
                    owns_socket = True
                    break
            except OSError:
                continue  # A worker may close another descriptor during discovery.
        if owns_socket and identity(root, process.name) == instance:
            return instance
    return None


def running_url(root, host, port, timeout=3):
    """Recognize an existing server, including versions without a PID file."""
    if not sys.platform.startswith('linux'):
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        instance = owner(root, host, port)
        if instance is None:
            return None
        client = http.client.HTTPConnection(host, port, timeout=.3)
        try:
            client.request('GET', '/')
            response = client.getresponse()
            if response.status == 200 and response.getheader('Server', '').split()[0:1] == ['FlightStudio/1']:
                if owner(root, host, port) == instance:
                    return f'http://{host}:{port}/'
                return None
        except (OSError, http.client.HTTPException):
            pass
        finally:
            client.close()
        time.sleep(.05)
    return None


def stop(root, host, port, timeout=10):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Stop Studio with Ctrl+C in its terminal on this operating system.')
    instance = owner(root, host, port)
    if instance is None:
        if listeners(host, port):
            raise RuntimeError(f'Port {port} belongs to another service or workspace; no process was stopped.')
        return False
    handle = None
    try:
        if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
            handle = os.pidfd_open(instance.pid)
        if owner(root, host, port) != instance:
            raise RuntimeError('The listener changed; no process was stopped. Run the command again.')
        if handle is not None:
            signal.pidfd_send_signal(handle, signal.SIGINT)
        else:
            os.kill(instance.pid, signal.SIGINT)
    except ProcessLookupError:
        return False
    finally:
        if handle is not None:
            os.close(handle)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if identity(root, instance.pid) != instance:
            return True
        time.sleep(.05)
    raise RuntimeError('Studio is still closing its jobs. Wait, then run the stop command again.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Stop this workspace’s Flight Studio web server.')
    parser.add_argument('--port', type=int, default=http_port())
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    try:
        stopped = stop(Path(__file__).resolve().parents[1], loopback(), args.port)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f'Error: {error}\n')
    print('Flight Studio stopped.' if stopped else 'Flight Studio is already stopped.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
