# LSM303DLHC magnetic sensor library

Native cFE sensor library with the CMake, public header and source layout of the
local `sample_lib`. It depends on `linux_i2c_lib` for bus transfers.

`LSM303DLHC_MAG_Configure` selects normal measurement at 15 Hz,
±1.3 gauss and continuous conversion. `LSM303DLHC_MAG_Read` reads the current
gain and the signed X/Z/Y output register pairs, then returns X/Y/Z in
milli-microtesla. It supports all seven documented gain settings and reports the
sensor's overflow value as `-ERANGE`. Failed reads leave the caller's vector
unchanged. The library accesses the device only when the caller configures or
reads it.

Only the magnetic component is implemented. Its default seven-bit I²C address
is `0x1E`, and the caller passes the bus path and address. The project includes
this library whenever an `lsm303dlhc_mag` device is configured, even when no app
reads it.

See sections 5.1.3 and 7.2 and table 75 of the
[ST LSM303DLHC datasheet](https://www.st.com/resource/en/datasheet/lsm303dlhc.pdf) for
the magnetic interface, the registers and the sensitivity.
