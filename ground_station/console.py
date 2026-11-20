"""Keep the terminal's UDP receiver alive between explicit operator commands."""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import subprocess
import sys
import threading

from hardware.targets import selected_target
from project.defaults import runtime_dir, sensor_timeout


def address(root):
    # Linux abstract sockets disappear with the last file descriptor, even after a crash.
    identity = hashlib.sha256(os.fsencode(Path(root).resolve())).hexdigest()
    return '\0flight-studio-ground-' + str(os.getuid()) + '-' + identity


def same_user(sock):
    credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    return struct.unpack('3i', credentials)[1] == os.getuid()


def send_frame(stream, data):
    stream.write(json.dumps(data, ensure_ascii=False).encode() + b'\n')
    stream.flush()


class Receiver(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = False

    def verify_request(self, request, client_address):
        return same_user(request)


class Operator(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(65537)
            if len(raw) > 65536:
                raise ValueError('Ground request too large')
            request = json.loads(raw)
            for result in self.dispatch(request):
                send_frame(self.wfile, {'result': result})
        except (ConnectionResetError, BrokenPipeError):
            return
        except (ValueError, OSError, RuntimeError, KeyError) as error:
            if not self.server.lab.ground_snapshot()['connected']:
                self.server.shutdown()
            send_frame(self.wfile, {'error': str(error)})

    def dispatch(self, request):
        lab = self.server.lab
        station = lab.ground
        action = request['action']
        if action == 'stop':
            with self.server.selection:
                if request.get('target') and lab.ground_target and request['target'] != lab.ground_target:
                    if request.get('if_active'):
                        yield {'connected': True}
                        return
                    raise ValueError('The ground receiver is connected to another target')
                station.stop()
                self.server.shutdown()
            yield {'connected': False}
            return
        target = request['target']
        with self.server.selection:
            current = lab.ground_snapshot()
            if not current['connected'] or current['target'] != target:
                if action not in ('connect', 'send'):
                    raise ValueError('Connect the ground receiver first')
                current = lab.ground_start({'target': target})
            if action == 'connect':
                yield {'target': target, 'connected': True, 'return_host': current['first_flight']['return_host']}
                return
            timeout = request['timeout']
            if action == 'send':
                yield station.send_observed(request['app'], request['command'], request['args'], timeout)
                return
            if action == 'test':
                for app, command in station.noops():
                    yield station.send_observed(app, command, {}, timeout)
                return
        if action != 'listen':
            raise ValueError('Unknown ground operation')
        cursor = count = 0
        while not request['count'] or count < request['count']:
            for packet in station.observations_since(cursor, request['events'], timeout):
                yield packet
                cursor = packet['event_id']
                count += 1
                if count == request['count']:
                    return


def serve(root, ready):
    from jobs.service import Laboratory
    with os.fdopen(ready, 'w') as signal:
        try:
            server = Receiver(address(root), Operator)
            server.lab = Laboratory(root)
            server.selection = threading.Lock()
        except (OSError, RuntimeError, ValueError) as error:
            signal.write(str(error) + '\n')
            return 1
        signal.write('ready\n')
    try:
        with server:
            server.serve_forever()
    finally:
        server.lab.close()
    return 0


def connect(sock, root):
    sock.connect(address(root))
    if not same_user(sock):
        raise PermissionError('Ground receiver belongs to another user')


@contextmanager
def channel(root, start):
    root = Path(root)
    with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as sock:
        try:
            connect(sock, root)
        except ConnectionRefusedError:
            if not start:
                yield None
                return
        else:
            yield sock
            return
    runtime = runtime_dir(root)
    runtime.mkdir(exist_ok=True, parents=True)
    with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as sock:
        with (runtime / 'ground-cli.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                connect(sock, root)
            except ConnectionRefusedError:
                reader, writer = os.pipe()
                with os.fdopen(reader) as signal:
                    try:
                        subprocess.Popen([sys.executable, '-m', 'ground_station.console', '--receiver', str(writer)],
                                         pass_fds=(writer,), cwd=root, start_new_session=True, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    finally:
                        os.close(writer)
                    status = signal.readline().strip()
                if status != 'ready':
                    raise ValueError(status or 'Ground receiver could not start')
                connect(sock, root)
        yield sock


def exchange(root, request):
    with channel(root, request['action'] in {'send', 'connect'}) as sock:
        if sock is None:
            if request['action'] == 'stop':
                yield {'connected': False}
                return
            raise ValueError('Connect the ground receiver first')
        with sock.makefile('rwb') as stream:
            send_frame(stream, request)
            for line in stream:
                frame = json.loads(line)
                if 'error' in frame:
                    raise ValueError(frame['error'])
                yield frame['result']


def field_value(value):
    name, equals, text = value.partition('=')
    if not name or not equals:
        raise argparse.ArgumentTypeError('Use --arg field=value')
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = text
    return name, decoded


def main(root, argv):
    cli = argparse.ArgumentParser(prog='./start --no-ui ground')
    commands = cli.add_subparsers(dest='action', required=True)
    for name in ('connect', 'send', 'listen', 'test', 'stop'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--target', choices=('native', 'qemu', 'physical'))
        cmd.add_argument('--json', action='store_true')
        cmd.add_argument('--timeout', type=float, default=sensor_timeout(), help='Seconds to wait for a reply')
        if name == 'send':
            cmd.add_argument('app')
            cmd.add_argument('command')
            cmd.add_argument('--arg', type=field_value, action='append', default=[])
        if name == 'listen':
            cmd.add_argument('--events', action='store_true')
            cmd.add_argument('--count', type=int, default=0, help='Number of packets, or zero to follow until interrupted')
        if name == 'test':
            cmd.add_argument('--all-noop', action='store_true', required=True)
    args = cli.parse_args(argv)
    result = vars(args).copy()
    result['target'] = args.target or selected_target(root, required=args.action != 'stop')
    result['args'] = dict(result.pop('arg', []))
    if not 0 < args.timeout <= 3600 or result.get('count', 0) < 0:
        cli.error('Choose a positive timeout up to one hour and a nonnegative packet count')
    try:
        last = None
        cases = []
        for last in exchange(root, result):
            if args.json and args.action == 'test':
                cases.append(last)
            elif args.json:
                print(json.dumps(last, ensure_ascii=False), flush=True)
            elif 'sent' in last:
                lines = [last['sent']['id'], last.get('event')]
                if 'before' in last:
                    lines.append(f'CommandCounter {last["before"]} → {last["after"]}')
                print(' · '.join(filter(None, lines)), flush=True)
            elif args.action == 'listen':
                print(last['name'], last['values'].get('Message') or json.dumps(last['values']), flush=True)
            else:
                print('Connected · ' + last['return_host'] if last['connected'] else 'Disconnected', flush=True)
        if cases:
            print(json.dumps({'passed': True, 'tests': cases}, ensure_ascii=False))
        if last is None:
            cli.exit(1, 'No ground result received\n')
    except (OSError, ValueError, RuntimeError) as error:
        cli.exit(1, f'Error: {error}\n')
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--receiver':
        sys.exit(serve(Path.cwd(), int(sys.argv[2])))
    sys.exit(main(Path.cwd(), sys.argv[1:]))
