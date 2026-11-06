# TMP105 sensor library

Native cFE sensor library with the public header and source layout of `sample_lib`.
`TMP105_LIB_ReadTemperature` reads register `0x00` and converts its signed
big-endian result into millidegrees Celsius. The output remains unchanged after
a failed read. Data with any of the always-zero bits D3–D0 set, such as the
all-ones pattern of an unanswered read on a bus that reports no NACK, fails
with `-EIO` instead of decoding as a temperature. The caller passes the device path
and the seven-bit address. The library never writes the configuration register,
so the sensor keeps its power-on resolution of 0.5 °C.

The CMake dependency and C calls point to `linux_i2c_lib`, which owns Linux
`I2C_RDWR`. The sensor library owns register selection and temperature decoding.
`TMP105_LIB_Init` opens no hardware. Adding a TMP105 to the project includes this
library even before an application uses it.
