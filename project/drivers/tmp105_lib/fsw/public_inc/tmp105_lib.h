#ifndef TMP105_LIB_H
#define TMP105_LIB_H

#include "cfe.h"

int32 TMP105_LIB_Init(void);

/* Read millidegrees Celsius. Returns CFE_SUCCESS or negative Linux errno;
 * -EIO also reports register data a TMP105 cannot produce.
 * Each call opens/closes the bus; on failure, Temperature is unchanged. */
int32 TMP105_LIB_ReadTemperature(const char *Device, uint16 Address, int32 *Temperature);

#endif
