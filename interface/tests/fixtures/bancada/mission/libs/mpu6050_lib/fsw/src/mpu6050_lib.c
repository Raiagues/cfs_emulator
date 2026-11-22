#include "mpu6050_lib.h"
#include "linux_i2c_sensor.h"

#include <errno.h>
#include <string.h>

/* Derived from project/drivers/models/mpu6050/model.json. */
static const uint8_t Identity[] = {
    0x68
};

static const HAL_SENSOR_Write_t Setup[] = {
    {.Register = 0x6b, .Value = 0x01},
    {.Register = 0x6c, .Value = 0x00},
    {.Register = 0x1b, .Value = 0x00},
    {.Register = 0x1c, .Value = 0x00}
};

static const HAL_SENSOR_Range_t Ranges[] = {
    {.Register = 0x1c, .Shift = 3, .Mask = 3},
    {.Register = 0x1b, .Shift = 3, .Mask = 3}
};

static const HAL_SENSOR_Output_t Outputs[] = {
    {.ByteOffset = 0, .Numerator = 1000, .Counts = 16384, .Zero = 0, .RangeIndex = 0},
    {.ByteOffset = 2, .Numerator = 1000, .Counts = 16384, .Zero = 0, .RangeIndex = 0},
    {.ByteOffset = 4, .Numerator = 1000, .Counts = 16384, .Zero = 0, .RangeIndex = 0},
    {.ByteOffset = 6, .Numerator = 1000, .Counts = 340, .Zero = 36530, .RangeIndex = -1},
    {.ByteOffset = 8, .Numerator = 1000, .Counts = 131, .Zero = 0, .RangeIndex = 1},
    {.ByteOffset = 10, .Numerator = 1000, .Counts = 131, .Zero = 0, .RangeIndex = 1},
    {.ByteOffset = 12, .Numerator = 1000, .Counts = 131, .Zero = 0, .RangeIndex = 1}
};

static const HAL_SENSOR_Profile_t Profile = {
    .Identity = Identity, .IdentityRegister = 0x75, .IdentitySize = 1,
    .Setup = Setup, .SetupCount = 4,
    .ReadyRegister = 0x00, .ReadyMask = 0x00,
    .Ranges = Ranges, .RangeCount = 2,
    .FirstRegister = 0x3b, .BurstSize = 14,
    .Outputs = Outputs, .OutputCount = 7
};


HAL_SENSOR_Device_t MPU6050_Bind(HAL_SENSOR_Bus_t bus, MPU6050_State_t *state)
{
    if (state)
        memset(state, 0, sizeof(*state));
    return (HAL_SENSOR_Device_t){.Bus = bus, .Profile = &Profile, .Ops = NULL, .DriverContext = state};
}

int32 MPU6050_LIB_Init(void)
{
    return CFE_SUCCESS;
}

static int32 CopySample(HAL_SENSOR_Device_t *device, MPU6050_Sample_t *sample, bool configure)
{
    int32_t values[7];
    if (!sample || !device || device->Profile != &Profile)
        return -EINVAL;
    int32 status = configure ? HAL_SENSOR_Acquire(device, values, 7) : HAL_SENSOR_Read(device, values, 7);
    if (status == CFE_SUCCESS)
    {
        sample->Value_accel_x = values[0];
        sample->Value_accel_y = values[1];
        sample->Value_accel_z = values[2];
        sample->Value_temperature = values[3];
        sample->Value_gyro_x = values[4];
        sample->Value_gyro_y = values[5];
        sample->Value_gyro_z = values[6];
    }
    return status;
}

int32 MPU6050_Acquire(HAL_SENSOR_Device_t *device, MPU6050_Sample_t *sample)
{
    return CopySample(device, sample, true);
}

int32 MPU6050_Configure(const char *path, uint16 address)
{
    HAL_SENSOR_Device_t device = MPU6050_Bind(LINUX_I2C_SensorBus(path, address), NULL);
    return HAL_SENSOR_Configure(&device);
}

int32 MPU6050_Read(const char *path, uint16 address, MPU6050_Sample_t *sample)
{
    HAL_SENSOR_Device_t device = MPU6050_Bind(LINUX_I2C_SensorBus(path, address), NULL);
    return CopySample(&device, sample, false);
}

