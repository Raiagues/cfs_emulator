# LSM303DLHC magnetic sensor library

Native cFE sensor library with the same CMake/public-header/source organization
as the local `sample_lib`. It depends on `linux_i2c_lib` for transactions.

`LSM303DLHC_MAG_Configure` explicitly selects normal measurement at 15 Hz,
±1.3 gauss and continuous conversion. `LSM303DLHC_MAG_Read` reads the current
gain and the signed X/Z/Y output register pairs, then returns X/Y/Z in
milli-microtesla. It supports all seven documented gain settings and reports the
sensor's overflow value as `-ERANGE`. Failed reads leave the caller's vector
unchanged. Hardware configuration is an explicit caller action; loading the
library does not touch a device.

Only the magnetic component is implemented. Its default seven-bit I²C address
is `0x1E`; the actual bus path/address remain caller parameters. The project
includes this library whenever an `lsm303dlhc_mag` device is present, independently
of application bindings.

Reference: [ST LSM303DLHC datasheet, magnetic interface and registers](https://www.st.com/resource/en/datasheet/lsm303dlhc.pdf),
sections 5.1.3 and 7.2, and sensitivity table 75.
