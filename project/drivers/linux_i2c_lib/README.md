# Linux I²C transport

Native cFE library using Linux `i2c-dev`. Public API:
`fsw/public_inc/linux_i2c_lib.h`; implementation: `fsw/src/linux_i2c_lib.c`.

`LINUX_I2C_Transfer` submits up to two messages with `I2C_RDWR`. Register reads
use a combined write/read with a repeated START. Addresses are seven-bit values;
the device path is supplied by the caller, rather than fixed inside the driver.
Calls return `CFE_SUCCESS` or a negative Linux errno. Sensor drivers stage their
read buffers and publish a value only on success.

The library follows the local `sample_lib` CMake/public-header/source layout.
Its cFE initializer opens no hardware. The selected board/OS catalog includes it
before sensor libraries in the mission startup. The kernel adapter must support
`I2C_FUNC_I2C`, and the process needs access to the selected `/dev/i2c-*` node.

Reference: [Linux userspace I²C interface](https://docs.kernel.org/i2c/dev-interface.html).
