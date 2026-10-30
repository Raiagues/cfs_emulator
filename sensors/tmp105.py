import math

from qmp import set_property


DEVICE = "tmp105"


def update(qmp, sensor_id, t):
    temperature = 25 + 5 * math.sin(t)

    # search the temp0 device and configure the temperature to 25ºC 
    set_property(qmp, f"/machine/peripheral/{sensor_id}", "temperature", round(temperature * 1000))

    print(f"{sensor_id} = {temperature:.2f} °C")