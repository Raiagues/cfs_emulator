#include "tmp105_lib.h"
#include "linux_i2c_sensor.h"

#include <errno.h>
#include <string.h>

/* Derived from project/drivers/models/tmp105/model.json. */
static const HAL_SENSOR_Output_t Outputs[] = {
    {.ByteOffset = 0, .Numerator = 1000, .Counts = 256, .Zero = 0, .RangeIndex = -1, .ReservedMask = 0x000f}
};

static const HAL_SENSOR_Profile_t Profile = {
    .Identity = NULL, .IdentityRegister = 0x00, .IdentitySize = 0,
    .Setup = NULL, .SetupCount = 0,
    .ReadyRegister = 0x00, .ReadyMask = 0x00,
    .Ranges = NULL, .RangeCount = 0,
    .FirstRegister = 0x00, .BurstSize = 2,
    .Outputs = Outputs, .OutputCount = 1
};


HAL_SENSOR_Device_t TMP105_Bind(HAL_SENSOR_Bus_t bus, TMP105_State_t *state)
{
    if (state)
        memset(state, 0, sizeof(*state));
    return (HAL_SENSOR_Device_t){.Bus = bus, .Profile = &Profile, .Ops = NULL, .DriverContext = state};
}

int32 TMP105_LIB_Init(void)
{
    return CFE_SUCCESS;
}

static int32 CopySample(HAL_SENSOR_Device_t *device, int32 *sample, bool configure)
{
    int32_t values[1];
    if (!sample || !device || device->Profile != &Profile)
        return -EINVAL;
    int32 status = configure ? HAL_SENSOR_Acquire(device, values, 1) : HAL_SENSOR_Read(device, values, 1);
    if (status == CFE_SUCCESS)
    {
        *sample = values[0];
    }
    return status;
}

int32 TMP105_Acquire(HAL_SENSOR_Device_t *device, int32 *sample)
{
    return CopySample(device, sample, true);
}

int32 TMP105_Configure(const char *path, uint16 address)
{
    HAL_SENSOR_Device_t device = TMP105_Bind(LINUX_I2C_SensorBus(path, address), NULL);
    return HAL_SENSOR_Configure(&device);
}

int32 TMP105_LIB_ReadTemperature(const char *path, uint16 address, int32 *sample)
{
    HAL_SENSOR_Device_t device = TMP105_Bind(LINUX_I2C_SensorBus(path, address), NULL);
    return CopySample(&device, sample, false);
}

