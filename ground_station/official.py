"""Headless adapters for the unmodified NASA cFS-GroundSystem modules.

Packet construction, checksum, UDP send, telemetry routing and field decoding
are executed by the official tools. This module supplies mission configuration
and the text sinks that replace their desktop widgets.
"""
import csv
import math
import pickle
import socket
import struct
import sys
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / 'cFS/tools/cFS-GroundSystem'
for directory in (ROOT, ROOT / 'Subsystems/cmdGui', ROOT / 'Subsystems/tlmGUI'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
try:
    import zmq
    from PyQt5.QtCore import QThread
    from MiniCmdUtil import MiniCmdUtil
    from RoutingService import RoutingService
    import GenericTelemetry
except ImportError as error:
    raise RuntimeError('The official cFS-GroundSystem requires PyQt5 and pyzmq. Install the dependencies in ground_station/requirements.txt.') from error

# Official MiniCmdUtil owns a class socket for its desktop dialogs; each web
# connection instead receives a socket with an explicit lifetime.
MiniCmdUtil.sock.close()
_DECODE_LOCK = threading.Lock()


def payload(command, values):
    """Validate user fields against compiler offsets; no CCSDS header here."""
    fields = command['fields']
    unknown = set(values) - {field['name'] for field in fields}
    if unknown:
        raise ValueError('Unknown fields: ' + ', '.join(sorted(unknown)))
    header = command.get('header_size', 8)
    if not header <= command['size'] <= 65507 or not 0 <= command['code'] <= 127:
        raise ValueError('Invalid command size or function code')
    result = bytearray(command['size'] - header)
    for field in fields:
        name, size, offset = field['name'], field['size'], field['offset'] - header
        if offset < 0 or offset + size > len(result):
            raise ValueError('Invalid field layout: ' + name)
        if name not in values:
            if name.rsplit('.', 1)[-1].lower().startswith(('padding', 'reserved', 'spare')):
                continue
            raise ValueError('Enter a value for ' + name)
        value, fmt, count = values[name], field['format'], field['count']
        try:
            if fmt == 's':
                data = str(value).encode('utf-8')
                if len(data) >= size:
                    raise ValueError(f'{name}: text must contain fewer than {size} bytes')
                data = data.ljust(size, b'\0')
            elif fmt == 'raw':
                data = bytes.fromhex(value)
            else:
                items = [value] if count == 1 else value
                if not isinstance(items, (list, tuple)) or len(items) != count:
                    raise ValueError(f'{name}: expected {count} values')
                if fmt in 'bBhHiIqQ':
                    items = [int(v, 0) if isinstance(v, str) and v.lower().startswith(('0x', '-0x', '+0x')) else int(v) if isinstance(v, str) else v for v in items]
                elif fmt in 'fd':
                    items = [float(v) for v in items]
                    if not all(math.isfinite(v) for v in items):
                        raise ValueError(f'{name}: numbers must be finite')
                elif fmt == '?' and any(type(v) is not bool for v in items):
                    raise ValueError(f'{name}: enter true or false')
                data = struct.pack('<' + fmt * count, *items)
            if len(data) != size:
                raise ValueError(f'{name}: expected {size} bytes')
            result[offset:offset + size] = data
        except (TypeError, struct.error) as error:
            raise ValueError(f'{name}: invalid value ({error})') from error
    return result


class Command(MiniCmdUtil):
    """Configure the official sender without its shared desktop mmap file."""
    def __init__(self, host, port, mid, code, parameters, header_size, sock):
        self.host, self.port, self.sock = host, int(port), sock
        self.endian = 'little'
        self.pkt_id, self.cmd_code = mid, code
        if self.pkt_id & 0xF800 != 0x1800 or not 0 <= code <= 127:
            raise ValueError('Invalid CCSDS v1 command identifier or function code')
        self.parameters = parameters
        self.payload, self.packet = bytearray(), bytearray()
        self.mm = bytes((0, 0, header_size - 8))
        self.cmd_offset_pri = self.cmd_offset_sec = 0
        self.checksum = 0xFF
        self.cfs_cmd_sec_hdr = bytearray(2)

    def send(self):
        if not self.send_packet():
            raise OSError('The official command sender did not send the packet')
        return len(self.packet)


def telemetry_rows(definition):
    """GroundSystem CSV fields are scalar; expand compiled arrays explicitly."""
    for field in definition['fields']:
        fmt, count = field['format'], field['count']
        if fmt == 's':
            yield [field['name'], field['offset'], field['size'], 's', 'Str']
            continue
        raw = fmt == 'raw'
        fmt, count = ('B', field['size']) if raw else (fmt, count)
        width = struct.calcsize('=' + fmt)
        for index in range(count):
            name = field['name'] if count == 1 and not raw else f'{field["name"]}[{index}]'
            yield [name, field['offset'] + index * width, width, fmt, 'Hex' if raw else 'Dec']


class Definitions:
    """Generate the same CommandFiles/ParameterFiles and telemetry CSVs as GS."""
    def __init__(self, directory, catalog, host='127.0.0.1', command_port=None):
        self.directory = Path(directory)
        command_dir = self.directory / 'Subsystems/cmdGui'
        telemetry_dir = self.directory / 'Subsystems/tlmGUI'
        for directory in (command_dir / 'CommandFiles', command_dir / 'ParameterFiles', telemetry_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.commands = {command['id']: command for command in catalog['commands']}
        self.command_files = {}
        groups = {}
        for command in catalog['commands']:
            groups.setdefault((command['app'], command['mid']), []).append(command)
        command_pages = []
        for group_index, ((app, mid), commands) in enumerate(groups.items()):
            name = f'commands-{group_index}-{mid:04x}'
            parameter_names = []
            for index, command in enumerate(commands):
                parameter_name = f'{name}-{index}'
                parameter_names.append(parameter_name)
                self.command_files[command['id']] = (name, index)
                # MiniCmdUtil accepts integer flags. Compiler-encoded byte fields
                # represent strings, floats, arrays and alignment without guessing.
                header = command.get('header_size', catalog['transport']['command_header_size'])
                size = command['size'] - header
                names = [f'Padding[{offset}]' for offset in range(size)]
                for field in command['fields']:
                    for offset in range(field['size']):
                        names[field['offset'] - header + offset] = f'{field["name"]}.byte[{offset}]'
                data = [['uint8'] * size, names, ['1'] * size, ['0'] * size, ['--uint8'] * size, [''] * size]
                (command_dir / 'ParameterFiles' / parameter_name).write_bytes(pickle.dumps(data))
            data = [[c['id'] for c in commands], [str(c['code']) for c in commands], parameter_names]
            (command_dir / 'CommandFiles' / name).write_bytes(pickle.dumps(data))
            command_pages.append([app, name, hex(mid), 'LE', 'UdpCommands.py', host, command_port or catalog['transport']['command_port']])
        self._csv(command_dir / 'command-pages.txt', command_pages)
        self.command_dir = command_dir
        with (command_dir / 'command-pages.txt').open(newline='') as file:
            self.command_pages = {row[1]: row for row in csv.reader(file)}
        telemetry_pages = []
        for definition in catalog['packets']:
            name = f'packet-{definition["mid"]:04x}.txt'
            file = telemetry_dir / name
            self._csv(file, telemetry_rows(definition))
            telemetry_pages.append([definition['name'], 'GenericTelemetry.py', hex(definition['mid']), name])
        self._csv(telemetry_dir / 'telemetry-pages.txt', telemetry_pages)
        definitions = {packet['mid']: packet for packet in catalog['packets']}
        with (telemetry_dir / 'telemetry-pages.txt').open(newline='') as file:
            self.pages = {int(row[2], 0): TelemetryPage(definitions[int(row[2], 0)], telemetry_dir / row[3])
                          for row in csv.reader(file)}

    def sender(self, command_id, values, sock):
        command = self.commands[command_id]
        name, index = self.command_files[command_id]
        page = self.command_pages[name]
        with (self.command_dir / 'CommandFiles' / name).open('rb') as file:
            names, codes, parameter_files = pickle.load(file)
        if names[index] != command_id:
            raise ValueError('GroundSystem command definition no longer matches the compiled catalog')
        parameter_file = self.command_dir / 'ParameterFiles' / parameter_files[index]
        if parameter_file.parent != self.command_dir / 'ParameterFiles':
            raise ValueError('Invalid GroundSystem parameter file')
        with parameter_file.open('rb') as file:
            flags = pickle.load(file)[4]
        data = payload(command, values)
        if len(flags) != len(data) or any(flag != '--uint8' for flag in flags):
            raise ValueError('GroundSystem parameters no longer match the compiled payload')
        parameters = ' '.join(f'{flag}={value}' for flag, value in zip(flags, data))
        return Command(page[5], int(page[6]), int(page[2], 0), int(codes[index]), parameters,
                       command.get('header_size', 8), sock)

    @staticmethod
    def _csv(path, rows):
        with path.open('w', newline='') as file:
            csv.writer(file).writerows(rows)


class TextSink:
    def __init__(self):
        self.text = ''

    def setText(self, value):
        self.text = value


class TelemetryPage:
    """Use the official desktop field decoder with web text sinks."""
    def __init__(self, definition, path):
        if sys.byteorder != 'little':
            raise RuntimeError('This ARM64 mission requires a little-endian ground host for the official telemetry decoder.')
        self.definition = definition
        with path.open(newline='') as file:
            self.rows = list(csv.reader(file))
        self.view = SimpleNamespace(mm=b'\0')

    def read(self, data):
        definition = self.definition
        variable = bool(definition.get('variable_size'))
        valid = definition['min_size'] <= len(data) <= definition['max_size'] if variable else len(data) == definition['size']
        if not valid:
            return {}, [f'Received size {len(data)}, catalog size {definition["size"]}']
        decoded = {}
        with _DECODE_LOCK:
            module = GenericTelemetry
            rows = self.rows
            module.tlm_item_is_valid = [True] * len(rows)
            module.tlm_item_desc = [row[0] for row in rows]
            module.tlm_item_start = [row[1] for row in rows]
            module.tlm_item_size = [row[2] for row in rows]
            module.tlm_item_format = [row[2] + 's' if row[3] == 's' else '=' + row[3] for row in rows]
            module.tlm_item_display_type = [row[4] for row in rows]
            for index, row in enumerate(rows):
                if int(row[1]) + int(row[2]) > len(data):
                    if variable:
                        continue
                    return {}, [row[0] + ': incomplete field']
                value = TextSink()
                module.SubsystemTelemetry.display_telemetry_item(self.view, data, index, TextSink(), value)
                if row[3] == 's':
                    parsed = value.text.split('\0')[0]
                elif row[3] in 'fd':
                    number = float(value.text)
                    parsed = number if math.isfinite(number) else None
                elif row[3] == '?':
                    parsed = value.text == 'True'
                else:
                    parsed = int(value.text, 16 if row[4] == 'Hex' else 10)
                    if abs(parsed) > 2**53 - 1:
                        parsed = str(parsed)
                decoded[row[0]] = parsed
        values = {}
        for field in definition['fields']:
            name = field['name']
            if field['format'] == 'raw':
                values[name] = bytes(decoded[f'{name}[{i}]'] for i in range(field['size']) if f'{name}[{i}]' in decoded).hex()
            elif field['count'] > 1 and field['format'] != 's':
                values[name] = [decoded[f'{name}[{i}]'] for i in range(field['count']) if f'{name}[{i}]' in decoded]
            elif name in decoded:
                values[name] = decoded[name]
        return values, []


class ReceiverStopped(Exception):
    pass


class RoutedSocket:
    """Configure upstream UDP binding/filtering without its fixed 4096-byte cap."""
    def __init__(self, owner):
        self.owner = owner
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # A specific return interface can coexist with the desktop wildcard receiver.
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(.2)

    def bind(self, unused):
        self.socket.bind((self.owner.listen_host, self.owner.port))
        self.owner.ready.set()

    def recvfrom(self, unused):
        while not self.owner.stop_event.is_set():
            try:
                data, source = self.socket.recvfrom(65535)
                if source[0] == self.owner.host:
                    return data, source
            except socket.timeout:
                pass
            except OSError as error:
                raise RuntimeError('Telemetry UDP socket failed: ' + str(error)) from error
        raise ReceiverStopped()

    def close(self):
        self.socket.close()


class Router(RoutingService):
    def __init__(self, receiver, publisher):
        QThread.__init__(self)
        self.ip_addresses_list, self.spacecraft_names = ['All'], ['All']
        self.special_pkt_id, self.special_pkt_name = [], []
        self.sock, self.publisher = RoutedSocket(receiver), publisher


class Receiver:
    def __init__(self, host, listen_host, port, accept, failed):
        self.host, self.listen_host, self.port = host, listen_host, port
        self.accept, self.failed = accept, failed
        self.context = zmq.Context()
        self.endpoint = 'inproc://flight-studio-' + uuid.uuid4().hex
        self.stop_event, self.ready = threading.Event(), threading.Event()
        self.router_thread = threading.Thread(target=self._route, daemon=True)
        self.reader_thread = threading.Thread(target=self._read, daemon=True)

    def start(self):
        self.reader_thread.start()
        self.router_thread.start()

    def _route(self):
        publisher = router = None
        try:
            publisher = self.context.socket(zmq.XPUB)
            publisher.setsockopt(zmq.LINGER, 0)
            publisher.bind(self.endpoint)
            router = Router(self, publisher)
            # Wait for the official GroundSystem subscription before accepting UDP.
            while not self.stop_event.is_set():
                if publisher.poll(200) and publisher.recv().startswith(b'\x01GroundSystem'):
                    router.run()
                    break
        except ReceiverStopped:
            pass
        except Exception as error:
            if not self.stop_event.is_set():
                self.failed(str(error))
        finally:
            if router:
                router.sock.close()
            if publisher is not None:
                publisher.close()
            self.ready.clear()

    def _read(self):
        subscriber = None
        try:
            subscriber = self.context.socket(zmq.SUB)
            subscriber.setsockopt(zmq.LINGER, 0)
            subscriber.setsockopt(zmq.SUBSCRIBE, b'GroundSystem')
            subscriber.connect(self.endpoint)
            while not self.stop_event.is_set():
                if subscriber.poll(200):
                    _, data = subscriber.recv_multipart()
                    self.accept(data)
        except Exception as error:
            if not self.stop_event.is_set():
                self.failed(str(error))
        finally:
            if subscriber is not None:
                subscriber.close()

    def connected(self):
        return self.ready.is_set() and not self.stop_event.is_set() and self.router_thread.is_alive() and self.reader_thread.is_alive()

    def stop(self):
        self.stop_event.set()
        for thread in (self.router_thread, self.reader_thread):
            if thread.ident is not None and thread is not threading.current_thread():
                thread.join(3)
        self.context.term()
