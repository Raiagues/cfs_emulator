# Linux I²C transport

Native cFE library built on Linux `i2c-dev`. The public API is in
`fsw/public_inc/linux_i2c_lib.h` and the implementation in `fsw/src/linux_i2c_lib.c`.

`LINUX_I2C_Transfer` submits up to two messages with `I2C_RDWR`. Register reads use a
combined write and read with a repeated START. Addresses are seven-bit values, and the
caller supplies the device path. Calls return `CFE_SUCCESS` or a negative Linux errno.
Sensor drivers stage their read buffers and publish a value only on success.

The library follows the CMake, public header and source layout of the local
`sample_lib`. Its cFE initializer opens no hardware. When a configured device needs
the library, the mission startup loads it before the sensor libraries that use it. The
kernel adapter must support `I2C_FUNC_I2C`, and the process needs access to the
selected `/dev/i2c-*` node.

See the [Linux userspace I²C interface](https://docs.kernel.org/i2c/dev-interface.html).
