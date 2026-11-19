"""Check a sensor through the emulated Pi 4 BSC1 controller, without a guest image."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from project.sensor_models import validate


def verify(binary, model):
    model = validate(model)
    device = f"{model['name']},id=sensor,bus=i2c-bus.1,address={model['address']}"
    argv = [binary, '-M', 'raspi4b', '-S', '-display', 'none', '-serial', 'none',
            '-monitor', 'none', '-device', device, '-qtest', 'stdio', '-qtest-log', '/dev/null']
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as proc:
        def command(op, offset, *args):
            base = 0xfe804000  # BCM2711 ARM physical address of BSC1.
            print(op, hex(base + offset), *args, file=proc.stdin, flush=True)
            answer = proc.stdout.readline().split()
            if not answer or answer[0] != 'OK':
                raise RuntimeError('QTest failed: ' + ' '.join(answer))
            return int(answer[1], 0) if len(answer) > 1 else None

        def write(register, *values):
            command('writel', 4, 0x302)
            command('writel', 8, 1 + len(values))
            command('writel', 0, 0x8080)
            for value in (register, *values):
                command('writel', 16, value)
            if command('readl', 4) & 0x302 != 2:
                raise RuntimeError('I²C write failed')

        def read(register, length):
            write(register)
            command('writel', 4, 0x302)
            command('writel', 8, length)
            command('writel', 0, 0x8081)
            data = bytes(command('readl', 16) for _ in range(length))
            if command('readl', 4) & 0x302 != 2:
                raise RuntimeError('I²C read failed')
            return data

        try:
            command('writel', 12, model['address'])
            identity = read(model['id_register'], 1)[0]
            if identity != model['id_value']:
                raise ValueError(f'Unexpected device ID {identity:#04x}')
            print(f"{model['name']} @ {model['address']:#04x}, identity {identity:#04x}")
            for control in model['controls']:
                if read(control['register'], 1)[0] != control['reset']:
                    raise ValueError('Incorrect power-on control value')
                write(control['register'], control['setup'])
            outputs = model['outputs']
            first = min(out['register'] for out in outputs)
            burst = read(first, max(out['register'] for out in outputs) - first + 2)
            print('Burst:', burst.hex(' '))
            for out in outputs:
                raw, = struct.unpack_from('>h', burst, out['register'] - first)
                expected = int((out['initial'] - out['offset']) * out['counts'] / out['divisor'])
                if raw != expected:
                    raise ValueError(f"{out['name']}: got {raw}, expected {expected}")
                print(f"{out['name']} = {raw*out['divisor']/out['counts']+out['offset']:.2f} {out['unit']}")
            for out in outputs:
                if 'range_register' not in out:
                    continue
                reg = out['range_register']
                original = read(reg, 1)[0]
                write(reg, original | (1 << out['range_shift']))
                sample = int.from_bytes(read(out['register'], 2), 'big', signed=True)
                base, = struct.unpack_from('>h', burst, out['register'] - first)
                if sample != int(base / 2):
                    raise ValueError('Incorrect sensitivity for ' + out['name'])
                write(reg, original)
            for control in model['controls']:
                if control.get('reset_mask'):
                    write(control['register'], control['reset_mask'])
                    if any(read(c['register'], 1)[0] != c['reset'] for c in model['controls']):
                        raise ValueError('Incorrect software reset')
        finally:
            proc.terminate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('--qemu', default='qemu-system-aarch64')
    args = parser.parse_args()
    verify(args.qemu, json.loads(args.model.read_text()))
