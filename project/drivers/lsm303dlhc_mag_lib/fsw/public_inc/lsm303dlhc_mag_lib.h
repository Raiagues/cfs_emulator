#ifndef LSM303DLHC_MAG_LIB_H
#define LSM303DLHC_MAG_LIB_H

#include "cfe.h"

typedef struct
{
    int32 X; /* milli-microtesla */
    int32 Y;
    int32 Z;
} LSM303DLHC_MAG_Vector_t;

int32 LSM303DLHC_MAG_LIB_Init(void);

/* Explicitly set 15 Hz, normal measurement, gain 1.3 gauss and continuous mode.
 * The cFE library initializer never configures attached hardware. */
int32 LSM303DLHC_MAG_Configure(const char *Device, uint16 Address);

/* Read the configured gain and signed X/Z/Y register pairs, then convert to
 * milli-microtesla. Gain codes 1..7 follow ST's sensitivity table. Returns
 * CFE_SUCCESS or negative errno; -EAGAIN means no new sample is ready and
 * -ERANGE reports sensor overflow (-4096).
 * Vector is unchanged on any failure. */
int32 LSM303DLHC_MAG_Read(const char *Device, uint16 Address, LSM303DLHC_MAG_Vector_t *Vector);

#endif
