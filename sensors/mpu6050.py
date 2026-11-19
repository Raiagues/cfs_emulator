"""Synthetic outputs for the mpu6050 register map."""
from sensors.schema import Sensor

SIGNALS = {'accel-x': {'function': 'constant'}, 'accel-y': {'function': 'constant'}, 'accel-z': {'function': 'constant'}, 'temperature': {'function': 'constant'}, 'gyro-x': {'function': 'constant'}, 'gyro-y': {'function': 'constant'}, 'gyro-z': {'function': 'constant'}}


def configure(device):
    return Sensor.from_model(device, __file__)


def sample(seconds, initial):
    return initial
