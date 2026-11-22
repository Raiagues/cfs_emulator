#ifndef HAL_SENSOR_H
#define HAL_SENSOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HAL_SENSOR_MAX_OUTPUTS 16
#define HAL_SENSOR_MAX_BURST 32

/* A combined transaction is atomic on the transport. Context belongs to the
 * caller and must outlive the bound device. Zero means success. */
typedef int32_t (*HAL_SENSOR_Transfer_t)(const void *context, uint16_t address,
    const uint8_t *tx, uint16_t tx_size, uint8_t *rx, uint16_t rx_size);

typedef struct
{
    HAL_SENSOR_Transfer_t Transaction;
    const void *Context;
    uint16_t Address;
} HAL_SENSOR_Bus_t;

typedef struct { uint8_t Register, Value; } HAL_SENSOR_Write_t;
typedef struct { uint8_t Register, Shift, Mask; } HAL_SENSOR_Range_t;

typedef struct
{
    uint8_t ByteOffset;
    int32_t Numerator, Counts, Zero;
    int8_t RangeIndex;              /* -1 for fixed sensitivity */
    const int32_t *GainCounts;      /* NULL for power-of-two ranges */
    uint16_t ReservedMask;
    bool HasInvalidRaw;
    int32_t InvalidRaw;
} HAL_SENSOR_Output_t;

typedef struct
{
    const uint8_t *Identity;
    uint8_t IdentityRegister, IdentitySize;
    const HAL_SENSOR_Write_t *Setup;
    size_t SetupCount;
    uint8_t ReadyRegister, ReadyMask;
    const HAL_SENSOR_Range_t *Ranges;
    size_t RangeCount;
    uint8_t FirstRegister, BurstSize;
    const HAL_SENSOR_Output_t *Outputs;
    size_t OutputCount;
} HAL_SENSOR_Profile_t;

typedef struct HAL_SENSOR_Device HAL_SENSOR_Device_t;

/* Optional model-local operations. A NULL operation uses the register profile. */
typedef struct
{
    int32_t (*Configure)(HAL_SENSOR_Device_t *device);
    int32_t (*Read)(const HAL_SENSOR_Device_t *device, int32_t *values);
} HAL_SENSOR_Ops_t;

struct HAL_SENSOR_Device
{
    HAL_SENSOR_Bus_t Bus;
    const HAL_SENSOR_Profile_t *Profile;
    const HAL_SENSOR_Ops_t *Ops;
    void *DriverContext; /* Optional caller-owned state, unique to this instance. */
    bool Configured;
};

int32_t HAL_SENSOR_LibInit(void);
int32_t HAL_SENSOR_ReadRegister(const HAL_SENSOR_Bus_t *bus, uint8_t reg, uint8_t *data, uint16_t size);
int32_t HAL_SENSOR_WriteRegister(const HAL_SENSOR_Bus_t *bus, uint8_t reg, uint8_t value);
int32_t HAL_SENSOR_ConfigureRegisters(const HAL_SENSOR_Bus_t *bus, const HAL_SENSOR_Profile_t *profile);
int32_t HAL_SENSOR_ReadRegisters(const HAL_SENSOR_Bus_t *bus, const HAL_SENSOR_Profile_t *profile, int32_t *values);

/* Configure once per device on first Acquire. Failed setup is retried.
 * A failed read leaves the caller's entire sample untouched. */
int32_t HAL_SENSOR_Configure(HAL_SENSOR_Device_t *device);
int32_t HAL_SENSOR_Read(const HAL_SENSOR_Device_t *device, int32_t *values, size_t capacity);
/** @brief Configure the device on its first read and deliver one complete sample. */
int32_t HAL_SENSOR_Acquire(HAL_SENSOR_Device_t *device, int32_t *values, size_t capacity);

#endif
