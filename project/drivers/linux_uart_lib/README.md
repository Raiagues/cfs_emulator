# Linux UART transport

Native cFE library with `sample_lib` layout. The public header is
`fsw/public_inc/linux_uart_lib.h`; implementation is `fsw/src/linux_uart_lib.c`.

`LINUX_UART_Open` applies the caller's baud rate, data bits, stop bits and parity
through `termios`. It opens the supplied device with `O_NOCTTY` and uses raw,
nonblocking I/O without hardware or software flow control. Read/write calls wait
with `poll`, return a byte count for partial transfers, and report negative errno
on failure or timeout. The caller owns retry policy and descriptor lifetime.

Loading this library does not open a serial port or configure board pins. The
caller must choose an enabled UART device and ensure it is not occupied by the
Linux console. Raspberry Pi `/dev/serial0` mapping depends on boot configuration;
the transport intentionally does not hardcode `/dev/ttyAMA0` or take over it.

References: [Linux termios](https://man7.org/linux/man-pages/man3/termios.3.html),
[Raspberry Pi configuration](https://www.raspberrypi.com/documentation/computers/configuration.html).
