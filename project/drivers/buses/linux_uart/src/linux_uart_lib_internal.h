#ifndef LINUX_UART_LIB_INTERNAL_H
#define LINUX_UART_LIB_INTERNAL_H

#include "linux_uart_lib.h"
#include <termios.h>

static speed_t LINUX_UART_Baud(uint32 BaudRate);
static int32 LINUX_UART_Ready(int32 Descriptor, short Event, uint32 TimeoutMs);

#endif
