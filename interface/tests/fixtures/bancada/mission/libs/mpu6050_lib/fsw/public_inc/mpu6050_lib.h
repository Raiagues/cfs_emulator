#ifndef MPU6050_LIB_H
#define MPU6050_LIB_H

#include "cfe.h"
#include "hal_sensor.h"

typedef struct
{
    int32 Value_accel_x; /**< @unit millig @range -2000..1999 */
    int32 Value_accel_y; /**< @unit millig @range -2000..1999 */
    int32 Value_accel_z; /**< @unit millig @range -2000..1999 */
    int32 Value_temperature; /**< @unit millidegrees Celsius @range -59846..132903 */
    int32 Value_gyro_x; /**< @unit millidegrees per second @range -250137..250129 */
    int32 Value_gyro_y; /**< @unit millidegrees per second @range -250137..250129 */
    int32 Value_gyro_z; /**< @unit millidegrees per second @range -250137..250129 */
} MPU6050_Sample_t;

typedef struct { uint8_t Reserved; } MPU6050_State_t;

int32 MPU6050_LIB_Init(void);

/* Bind once per physical device. Storage belongs to the caller. Binding does no I/O. */
HAL_SENSOR_Device_t MPU6050_Bind(HAL_SENSOR_Bus_t bus, MPU6050_State_t *state);
int32 MPU6050_Acquire(HAL_SENSOR_Device_t *device, MPU6050_Sample_t *sample);

int32 MPU6050_Configure(const char *path, uint16 address);
int32 MPU6050_Read(const char *path, uint16 address, MPU6050_Sample_t *sample);

/* Deprecated sample-library entry point kept for existing cFS callers. */
int32 MPU6050_LIB_Function(void);

#endif
