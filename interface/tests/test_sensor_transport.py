import json
from pathlib import Path
import socket
import tempfile
import unittest

from journey import Store
from sensors.observations import board_socket, matching_write, remember_write, send_reading
from sensors.registers import initial_registers, encode_values
from project.sensor_models import load, model_paths


class SensorTransportTest(unittest.TestCase):
    def test_native_registers_match_each_model_identity_and_quantization(self):
        root = Path(__file__).resolve().parents[2]
        for name in ("tmp105", "mpu6050", "lsm303dlhc_mag"):
            spec = load(model_paths(root)[name])
            data = initial_registers(spec)
            if name == "mpu6050":
                self.assertEqual(data[117], 104)
            if name == "lsm303dlhc_mag":
                self.assertEqual(bytes(data[10:13]), b"H43")
            tolerance = encode_values(data, spec, {o['name']:o['initial'] for o in spec['outputs']})
            self.assertEqual(set(tolerance), {o['name'] for o in spec['outputs']})
            if name == 'tmp105':
                encode_values(data, spec, {'temperature': -16000})
                self.assertEqual(bytes(data[:2]), bytes.fromhex('f000'))

    def test_confirmation_requires_the_same_device_invocation_time_and_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root)
            store.observe('native','app',{'app':'own'})
            remember_write(root,'therm','run-1',{'temperature':20000},{'temperature':32})
            read = lambda device, run, at, value: matching_write(store, device, run, at, {'temperature':value})
            self.assertTrue(read('therm','run-1',float('inf'),20025))
            for args in [('other','run-1',float('inf'),20025),('therm','run-2',float('inf'),20025),
                         ('therm','run-1',1,20025),('therm','run-1',float('inf'),20033)]:
                self.assertIsNone(read(*args))

    def test_physical_readings_reach_only_an_explicit_local_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            address = board_socket(Path(directory), 'temp')
            address.parent.mkdir(parents=True)
            packet = {'at':12.0,'values':{'temperature':22000}}
            self.assertFalse(send_reading(address, packet))
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as listener:
                listener.bind(str(address))
                self.assertTrue(send_reading(address, packet))
                self.assertEqual(json.loads(listener.recv(2048)), packet)
