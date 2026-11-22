#ifndef LSM303DLHC_MAG_LIB_H
#define LSM303DLHC_MAG_LIB_H

#include "cfe.h"
#include "hal_sensor.h"

typedef struct
{
    int32 X; /**< @unit milli-microtesla @range -180000..180000 */
    int32 Y; /**< @unit milli-microtesla @range -180000..180000 */
    int32 Z; /**< @unit milli-microtesla @range -180000..180000 */
} LSM303DLHC_MAG_Vector_t;

typedef struct { uint8_t Reserved; } LSM303DLHC_MAG_State_t;

int32 LSM303DLHC_MAG_LIB_Init(void);

/* Bind once per physical device. Storage belongs to the caller. Binding does no I/O. */
HAL_SENSOR_Device_t LSM303DLHC_MAG_Bind(HAL_SENSOR_Bus_t bus, LSM303DLHC_MAG_State_t *state);
int32 LSM303DLHC_MAG_Acquire(HAL_SENSOR_Device_t *device, LSM303DLHC_MAG_Vector_t *sample);

int32 LSM303DLHC_MAG_Configure(const char *path, uint16 address);
int32 LSM303DLHC_MAG_Read(const char *path, uint16 address, LSM303DLHC_MAG_Vector_t *sample);


#endif
