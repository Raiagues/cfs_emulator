#ifndef LINUX_UART_LIB_H
#define LINUX_UART_LIB_H

#include "cfe.h"

typedef struct
{
    uint32 BaudRate; /* 1200, 2400, 4800, 9600, 19200, 38400, 57600 or 115200. */
    uint8 DataBits;  /* 7 or 8. */
    uint8 StopBits;  /* 1 or 2. */
    char Parity;     /* 'N', 'E' or 'O'. No hardware/software flow control. */
} LINUX_UART_Config_t;

int32 LINUX_UART_LIB_Init(void);
int32 LINUX_UART_Open(const char *Device, const LINUX_UART_Config_t *Config, int32 *Descriptor);
int32 LINUX_UART_Close(int32 Descriptor);

/* A single, possibly partial transfer. Bytes is set to zero on failure.
 * Readiness timeout is in milliseconds; zero polls immediately. Descriptors
 * remain nonblocking. Return CFE_SUCCESS or negative errno, including
 * -ETIMEDOUT when no readiness is reported and -EINTR when interrupted. */
int32 LINUX_UART_Read(int32 Descriptor, uint8 *Data, uint32 Capacity, uint32 *Bytes, uint32 TimeoutMs);
int32 LINUX_UART_Write(int32 Descriptor, const uint8 *Data, uint32 Length, uint32 *Bytes, uint32 TimeoutMs);

#endif
