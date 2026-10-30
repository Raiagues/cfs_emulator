import importlib
import sys
import time

from qmp import connect


if len(sys.argv) < 2:
    sys.exit("Usage: python3 sensors/simulator.py sensor:id ...")

sensors = []

for argument in sys.argv[1:]:
    name, sensor_id = argument.split(":")
    sensors.append((importlib.import_module(name), sensor_id))

qmp = connect("/tmp/qemu.sock")

t = 0

while True:
    for sensor, sensor_id in sensors:
        sensor.update(qmp, sensor_id, t)

    t += 0.2
    time.sleep(1)