# TMP105 sensor library

`model.json` supplies the register and conversion constants to `hal_sensor`.
`TMP105_LIB_ReadTemperature` reads register `0x00` and converts its signed
big-endian result into millidegrees Celsius. The output remains unchanged after
a failed read. Data with any of the always-zero bits D3–D0 set, such as the
all-ones pattern of an unanswered read on a bus that reports no NACK, fails
with `-EIO` instead of decoding as a temperature. The caller passes the device path
and the seven-bit address. The library never writes the configuration register,
so the sensor keeps its power-on resolution of 0.5 °C.

`linux_i2c_lib` owns Linux `I2C_RDWR`. The HAL decodes the value using the model.
`TMP105_LIB_Init` opens no hardware. Adding a TMP105 to the project includes this
library even before an application uses it.
