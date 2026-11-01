#include "tmp105_lib_internal.h"
#include "tmp105_lib_version.h"
#include "linux_i2c_lib.h"

#include <errno.h>

int32 TMP105_LIB_Init(void)
{
    OS_printf("TMP105 library " TMP105_LIB_VERSION " initialized.\n");
    return CFE_SUCCESS;
}

int32 TMP105_LIB_ReadTemperature(const char *Device, uint16 Address, int32 *Temperature)
{
    int32   Status;
    int32   Raw;
    uint8   Data[2];

    if (Device == NULL || Temperature == NULL || Address > 0x7F)
    {
        return -EINVAL;
    }

    /* Select register 0 and read both bytes in one I2C transaction. */
    Status = LINUX_I2C_ReadRegister(Device, Address, TMP105_TEMPERATURE_REGISTER, Data, sizeof(Data));
    if (Status != CFE_SUCCESS)
    {
        return Status;
    }

    Raw = ((int32)Data[0] << 8) | Data[1];
    if ((Raw & TMP105_SIGN_BIT) != 0)
    {
        Raw -= TMP105_FULL_SCALE;
    }
    *Temperature = Raw * TMP105_MILLIDEGREES / TMP105_COUNTS_PER_CELSIUS;
    return CFE_SUCCESS;
}
