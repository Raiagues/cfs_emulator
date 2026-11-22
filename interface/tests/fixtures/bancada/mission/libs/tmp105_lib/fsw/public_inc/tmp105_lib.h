#ifndef TMP105_LIB_H
#define TMP105_LIB_H

#include "cfe.h"
#include "hal_sensor.h"


typedef struct { uint8_t Reserved; } TMP105_State_t;

int32 TMP105_LIB_Init(void);

/* Bind once per physical device. Storage belongs to the caller. Binding does no I/O. */
HAL_SENSOR_Device_t TMP105_Bind(HAL_SENSOR_Bus_t bus, TMP105_State_t *state);
int32 TMP105_Acquire(HAL_SENSOR_Device_t *device, int32 *sample);

int32 TMP105_Configure(const char *path, uint16 address);
int32 TMP105_LIB_ReadTemperature(const char *path, uint16 address, int32 *sample);


#endif
