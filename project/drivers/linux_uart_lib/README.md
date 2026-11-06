# Linux UART transport

Native cFE library with the `sample_lib` layout. The public header is
`fsw/public_inc/linux_uart_lib.h` and the implementation is `fsw/src/linux_uart_lib.c`.

`LINUX_UART_Open` applies the caller's baud rate, data bits, stop bits and parity
through `termios`. It opens the supplied device with `O_NOCTTY` and uses raw,
nonblocking I/O without hardware or software flow control. Read and write calls wait
with `poll`, return a byte count for partial transfers, and report negative errno
on failure or timeout. The caller owns retry policy and descriptor lifetime.

Loading this library opens no serial port and configures no board pins. The caller
chooses an enabled UART device that the Linux console is not using. On a Raspberry
Pi, the device behind `/dev/serial0` depends on the boot configuration.

See [Linux termios](https://man7.org/linux/man-pages/man3/termios.3.html) and the
[Raspberry Pi configuration](https://www.raspberrypi.com/documentation/computers/configuration.html)
documentation.
