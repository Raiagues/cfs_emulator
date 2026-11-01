#ifndef LINUX_I2C_LIB_H
#define LINUX_I2C_LIB_H

#include "cfe.h"

int32 LINUX_I2C_LIB_Init(void);

/* Linux i2c-dev combined transaction, using a 7-bit address. A nonempty write
 * followed by a read uses a repeated START, with no STOP between messages.
 * Returns CFE_SUCCESS or negative errno. Each call opens/closes Device. */
int32 LINUX_I2C_Transfer(const char *Device, uint16 Address,
                       const uint8 *WriteData, uint16 WriteLength,
                       uint8 *ReadData, uint16 ReadLength);
int32 LINUX_I2C_ReadRegister(const char *Device, uint16 Address, uint8 Register,
                           uint8 *Data, uint16 Length);
int32 LINUX_I2C_WriteRegister(const char *Device, uint16 Address, uint8 Register, uint8 Value);

#endif
