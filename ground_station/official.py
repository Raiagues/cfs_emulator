"""CCSDS v1 commands for CI_LAB and telemetry from the compiled TO_LAB catalog."""
from contextlib import ExitStack
from functools import reduce
import math
from operator import xor
import selectors
import socket
import struct
import threading


def payload(command, values, endian):
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
                data = struct.pack(endian + fmt * count, *items)
            if len(data) != size:
                raise ValueError(f'{name}: expected {size} bytes')
            result[offset:offset + size] = data
        except (TypeError, struct.error) as error:
            raise ValueError(f'{name}: invalid value ({error})') from error
    return result


def endian(order):
    if order not in ("little", "big"):
        raise ValueError("Unknown byte order in the compiled catalog")
    return "<" if order == "little" else ">"


def encode(command, values, byte_order):
    """The CCSDS primary header is network order. The application payload uses the mission ABI."""
    mid, code, header = command["mid"], command["code"], command["header_size"]
    if mid & 0xF800 != 0x1800 or header < 8:
        raise ValueError("Unsupported CCSDS command header")
    data = payload(command, values, endian(byte_order))
    packet = bytearray(struct.pack(">HHHBB", mid, 0xC000, command["size"] - 7, code, 0))
    packet.extend(bytes(header - len(packet)))
    packet.extend(data)
    packet[7] = reduce(xor, packet, 0xFF)
    return bytes(packet)


def preview(command, values, byte_order):
    """Serialize a command without sending it, retaining compiler field offsets.

    Each segment is a slice of the exact bytes returned by encode(), including
    alignment gaps. Header integers are network order; field bytes follow the
    selected mission ABI, just as they do for a transmitted command.
    """
    packet = encode(command, values, byte_order)
    header = command['header_size']
    segments = []

    def segment(name, kind, offset, size, **metadata):
        segments.append(dict(name=name, kind=kind, offset=offset, size=size,
                             hex=packet[offset:offset + size].hex(), **metadata))

    for name, offset, size in (('MID', 0, 2), ('Sequence', 2, 2), ('Length', 4, 2),
                               ('Function code', 6, 1), ('Checksum', 7, 1)):
        segment(name, 'header', offset, size,
                value=int.from_bytes(packet[offset:offset + size], 'big'), byte_order='big')
    if header > 8:
        segment('Header padding', 'padding', 8, header - 8)
    decoded, errors = decode(command, packet, byte_order)
    if errors:
        raise ValueError('; '.join(errors))
    cursor = header
    for field in sorted(command['fields'], key=lambda item: item['offset']):
        offset, size = field['offset'], field['size']
        if offset < cursor:
            raise ValueError('Overlapping field layout: ' + field['name'])
        if offset > cursor:
            segment('Padding', 'padding', cursor, offset - cursor)
        metadata = {key: field[key] for key in ('type', 'format', 'count') if key in field}
        if field['name'] in decoded:
            metadata['value'] = decoded[field['name']]
        kind = ('padding' if field['name'].rsplit('.', 1)[-1].lower().startswith(('padding', 'reserved', 'spare'))
                else 'payload')
        segment(field['name'], kind, offset, size, byte_order=byte_order, **metadata)
        cursor = offset + size
    if cursor < len(packet):
        segment('Padding', 'padding', cursor, len(packet) - cursor)
    return dict(id=command['id'], app=command['app'], mid=command['mid'], code=command['code'],
                size=len(packet), header_size=header, byte_order=byte_order, hex=packet.hex(),
                header_hex=packet[:header].hex(), payload_hex=packet[header:].hex(),
                length_field=int.from_bytes(packet[4:6], 'big'), checksum=packet[7],
                checksum_valid=reduce(xor, packet, 0) == 0xFF, segments=segments)


def decode(definition, data, byte_order):
    variable = definition.get("variable_size")
    valid = definition["min_size"] <= len(data) <= definition["max_size"] if variable else len(data) == definition["size"]
    if not valid:
        return {}, [f"Received size {len(data)}, catalog size {definition['size']}"]
    result = {}
    for field in definition["fields"]:
        name, fmt, size, offset = (field[key] for key in ("name", "format", "size", "offset"))
        raw = data[offset:offset + size]
        if len(raw) != size and not variable:
            return {}, [name + ": incomplete field"]
        if fmt == "raw":
            result[name] = raw.hex()
        elif fmt == "s":
            if len(raw) == size:
                result[name] = raw.partition(b"\0")[0].decode("utf-8", errors="replace")
        else:
            form = struct.Struct(endian(byte_order) + fmt)
            values = []
            for (item,) in form.iter_unpack(raw[:len(raw) - len(raw) % form.size]):
                if type(item) is int and abs(item) > 2**53 - 1:
                    item = str(item)
                elif isinstance(item, float) and not math.isfinite(item):
                    item = None
                values.append(item)
            if field["count"] > 1:
                result[name] = values
            elif values:
                result[name] = values[0]
    return result, []


class Receiver:
    def __init__(self, host, address, port, accept, failed):
        self.host, self.address = host, (address, port)
        self.accept, self.failed = accept, failed
        self.resources = ExitStack()
        self.worker = None

    def start(self):
        try:
            self.socket = self.resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            self.socket.bind(self.address)
            reader, writer = socket.socketpair()
            self.signal = self.resources.enter_context(writer)
            self.wake = self.resources.enter_context(reader)
            self.worker = threading.Thread(target=self.receive, name="cFS telemetry", daemon=True)
            self.worker.start()
        except BaseException:
            self.resources.close()
            raise

    def receive(self):
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.socket, selectors.EVENT_READ)
                selector.register(self.wake, selectors.EVENT_READ)
                while True:
                    for key, _ in selector.select():
                        if key.fileobj is self.wake:
                            return
                        packet, source = self.socket.recvfrom(65535)
                        if source[0] == self.host:
                            self.accept(packet)
        except Exception as error:
            self.failed(str(error))

    def connected(self):
        return bool(self.worker and self.worker.is_alive())

    def stop(self):
        if self.connected():
            self.signal.sendall(b"\0")
            self.worker.join()
        self.resources.close()
