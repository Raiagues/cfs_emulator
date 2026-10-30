import math

from qmp import set_property


DEVICE = "lsm303dlhc_mag"


def update(qmp, sensor_id, t):
    x = 30 + 20 * math.cos(t)
    y = 30 + 20 * math.sin(t)
    z = 40

    path = f"/machine/peripheral/{sensor_id}"

    set_property(qmp, path, "mag-x", round(x * 1000))
    set_property(qmp, path, "mag-y", round(y * 1000))
    set_property(qmp, path, "mag-z", round(z * 1000))

    print(f"{sensor_id} = ({x:.2f}, {y:.2f}, {z:.2f}) µT")