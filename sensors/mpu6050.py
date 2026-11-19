"""Synthetic outputs for the mpu6050 register map."""
from sensors.schema import Sensor, Signal

SIGNALS = {'accel-x': {'function': 'constant'}, 'accel-y': {'function': 'constant'}, 'accel-z': {'function': 'constant'}, 'temperature': {'function': 'constant'}, 'gyro-x': {'function': 'constant'}, 'gyro-y': {'function': 'constant'}, 'gyro-z': {'function': 'constant'}}


def configure(device):
    return Sensor.from_device(device, (
        Signal('accel-x', 'g', 1000),
        Signal('accel-y', 'g', 1000),
        Signal('accel-z', 'g', 1000),
        Signal('temperature', '°C', 1000),
        Signal('gyro-x', '°/s', 1000),
        Signal('gyro-y', '°/s', 1000),
        Signal('gyro-z', '°/s', 1000),
    ))


def sample(seconds, initial):
    return initial
