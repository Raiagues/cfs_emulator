"""Synthetic outputs for the mpu6050 register map."""
from sensors.schema import Sensor

SIGNALS = {'accel-x': {'initial': 1.044, 'function': 'constant'},
 'accel-y': {'initial': -0.005, 'function': 'constant'},
 'accel-z': {'initial': 0.178, 'function': 'constant'},
 'temperature': {'initial': 28.48, 'function': 'constant'},
 'gyro-x': {'initial': -2.06, 'function': 'constant'},
 'gyro-y': {'initial': 0.69, 'function': 'constant'},
 'gyro-z': {'initial': -0.54, 'function': 'constant'}}


def configure(device):
    return Sensor.from_model(device, __file__)


def sample(seconds, initial):
    return initial
