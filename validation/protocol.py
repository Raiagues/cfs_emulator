"""Inputs fixed before measurement, expressed in each model's scaled integer units."""
SENSORS = (
    {'model': 'tmp105', 'device': 'eval_temp', 'app': 'eval_temp', 'address': 0x48},
    {'model': 'lsm303dlhc_mag', 'device': 'eval_mag', 'app': 'eval_mag', 'address': 0x1e},
    {'model': 'mpu6050', 'device': 'eval_mpu', 'app': 'eval_mpu', 'address': 0x68},
)
LEVELS = {
    'tmp105': [{'temperature': 21537}, {'temperature': -3241}, {'temperature': 31719}],
    'lsm303dlhc_mag': [
        {'mag-x': 18123, 'mag-y': -12457, 'mag-z': 38912},
        {'mag-x': -25317, 'mag-y': 8961, 'mag-z': 42133},
        {'mag-x': 11542, 'mag-y': 21489, 'mag-z': -32761}],
    'mpu6050': [
        {'accel-x': 13, 'accel-y': -21, 'accel-z': 998, 'temperature': 24137, 'gyro-x': 317, 'gyro-y': -541, 'gyro-z': 129},
        {'accel-x': 501, 'accel-y': -12, 'accel-z': 866, 'temperature': 27139, 'gyro-x': -1243, 'gyro-y': 731, 'gyro-z': -437},
        {'accel-x': -707, 'accel-y': 8, 'accel-z': 706, 'temperature': 29513, 'gyro-x': 2171, 'gyro-y': -1683, 'gyro-z': 563}],
}


def trace(model, scenario):
    if scenario not in ('constant', 'step', 'dropout'):
        raise ValueError('Choose constant, step or dropout')
    return [{'index': index, 'input': LEVELS[model][index // 5 if scenario == 'step' else 0].copy(),
             'disconnected': scenario == 'dropout' and 5 <= index < 10}
            for index in range(15)]
