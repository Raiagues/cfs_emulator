#include "lsm303dlhc_mag_lib.h"
#include "linux_i2c_sensor.h"

#include <errno.h>
#include <string.h>

/* Derived from project/drivers/models/lsm303dlhc_mag/model.json. */
static const uint8_t Identity[] = {
    0x48,
    0x34,
    0x33
};

static const HAL_SENSOR_Write_t Setup[] = {
    {.Register = 0x00, .Value = 0x10},
    {.Register = 0x01, .Value = 0x20},
    {.Register = 0x02, .Value = 0x00}
};

static const int32_t Gain0[] = {
    0,
    1100,
    855,
    670,
    450,
    400,
    330,
    230
};

static const int32_t Gain2[] = {
    0,
    980,
    760,
    600,
    400,
    355,
    295,
    205
};

static const HAL_SENSOR_Range_t Ranges[] = {
    {.Register = 0x01, .Shift = 5, .Mask = 7}
};

static const HAL_SENSOR_Output_t Outputs[] = {
    {.ByteOffset = 0, .Numerator = 100000, .Counts = 0, .Zero = 0, .GainCounts = Gain0, .RangeIndex = 0, .HasInvalidRaw = true, .InvalidRaw = -4096},
    {.ByteOffset = 4, .Numerator = 100000, .Counts = 0, .Zero = 0, .GainCounts = Gain0, .RangeIndex = 0, .HasInvalidRaw = true, .InvalidRaw = -4096},
    {.ByteOffset = 2, .Numerator = 100000, .Counts = 0, .Zero = 0, .GainCounts = Gain2, .RangeIndex = 0, .HasInvalidRaw = true, .InvalidRaw = -4096}
};

static const HAL_SENSOR_Profile_t Profile = {
    .Identity = Identity, .IdentityRegister = 0x0a, .IdentitySize = 3,
    .Setup = Setup, .SetupCount = 3,
    .ReadyRegister = 0x09, .ReadyMask = 0x01,
    .Ranges = Ranges, .RangeCount = 1,
    .FirstRegister = 0x03, .BurstSize = 6,
    .Outputs = Outputs, .OutputCount = 3
};


HAL_SENSOR_Device_t LSM303DLHC_MAG_Bind(HAL_SENSOR_Bus_t bus, LSM303DLHC_MAG_State_t *state)
{
    if (state)
        memset(state, 0, sizeof(*state));
    return (HAL_SENSOR_Device_t){.Bus = bus, .Profile = &Profile, .Ops = NULL, .DriverContext = state};
}

int32 LSM303DLHC_MAG_LIB_Init(void)
{
    return CFE_SUCCESS;
}

static int32 CopySample(HAL_SENSOR_Device_t *device, LSM303DLHC_MAG_Vector_t *sample, bool configure)
{
    int32_t values[3];
    if (!sample || !device || device->Profile != &Profile)
        return -EINVAL;
    int32 status = configure ? HAL_SENSOR_Acquire(device, values, 3) : HAL_SENSOR_Read(device, values, 3);
    if (status == CFE_SUCCESS)
    {
        sample->X = values[0];
        sample->Y = values[1];
        sample->Z = values[2];
    }
    return status;
}

int32 LSM303DLHC_MAG_Acquire(HAL_SENSOR_Device_t *device, LSM303DLHC_MAG_Vector_t *sample)
{
    return CopySample(device, sample, true);
}

int32 LSM303DLHC_MAG_Configure(const char *path, uint16 address)
{
    HAL_SENSOR_Device_t device = LSM303DLHC_MAG_Bind(LINUX_I2C_SensorBus(path, address), NULL);
    return HAL_SENSOR_Configure(&device);
}

int32 LSM303DLHC_MAG_Read(const char *path, uint16 address, LSM303DLHC_MAG_Vector_t *sample)
{
    HAL_SENSOR_Device_t device = LSM303DLHC_MAG_Bind(LINUX_I2C_SensorBus(path, address), NULL);
    return CopySample(&device, sample, false);
}

