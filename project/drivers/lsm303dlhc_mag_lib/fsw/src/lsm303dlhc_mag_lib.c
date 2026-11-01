#include "lsm303dlhc_mag_lib_internal.h"
#include "lsm303dlhc_mag_lib_version.h"
#include "linux_i2c_lib.h"

#include <errno.h>

int32 LSM303DLHC_MAG_LIB_Init(void)
{
    OS_printf("LSM303DLHC magnetic library " LSM303DLHC_MAG_LIB_VERSION " initialized.\n");
    return CFE_SUCCESS;
}

int32 LSM303DLHC_MAG_Configure(const char *Device, uint16 Address)
{
    int32 Status;
    /* ST LSM303DLHC: CRA_REG_M, CRB_REG_M and MR_REG_M, respectively. */
    Status = LINUX_I2C_WriteRegister(Device, Address, LSM303DLHC_MAG_CONFIG_A, 0x10);
    if (Status == CFE_SUCCESS)
    {
        Status = LINUX_I2C_WriteRegister(Device, Address, LSM303DLHC_MAG_CONFIG_B, 0x20);
    }
    if (Status == CFE_SUCCESS)
    {
        Status = LINUX_I2C_WriteRegister(Device, Address, LSM303DLHC_MAG_MODE, 0x00);
    }
    return Status;
}

static int32 LSM303DLHC_MAG_Decode(uint8 High, uint8 Low)
{
    int32 Value = ((int32)High << 8) | Low;
    return (Value & 0x8000) != 0 ? Value - 65536 : Value;
}

int32 LSM303DLHC_MAG_Read(const char *Device, uint16 Address, LSM303DLHC_MAG_Vector_t *Vector)
{
    static const int32 XYGain[8] = {0, 1100, 855, 670, 450, 400, 330, 230};
    static const int32 ZGain[8] = {0, 980, 760, 600, 400, 355, 295, 205};
    uint8 Gain;
    uint8 Ready;
    uint8 Data[6];
    int32 Status;
    int32 X;
    int32 Y;
    int32 Z;
    LSM303DLHC_MAG_Vector_t Sample;

    if (Vector == NULL)
    {
        return -EINVAL;
    }
    Status = LINUX_I2C_ReadRegister(Device, Address, LSM303DLHC_MAG_STATUS, &Ready, 1);
    if (Status != CFE_SUCCESS)
    {
        return Status;
    }
    if ((Ready & 1) == 0)
    {
        return -EAGAIN;
    }
    Status = LINUX_I2C_ReadRegister(Device, Address, LSM303DLHC_MAG_CONFIG_B, &Gain, 1);
    if (Status != CFE_SUCCESS)
    {
        return Status;
    }
    Gain = (Gain >> 5) & 7;
    if (Gain == 0)
    {
        return -EINVAL;
    }
    Status = LINUX_I2C_ReadRegister(Device, Address, LSM303DLHC_MAG_OUTPUT_X_HIGH, Data, sizeof(Data));
    if (Status != CFE_SUCCESS)
    {
        return Status;
    }
    /* Register order is X, Z, Y (not X, Y, Z). */
    X = LSM303DLHC_MAG_Decode(Data[0], Data[1]);
    Z = LSM303DLHC_MAG_Decode(Data[2], Data[3]);
    Y = LSM303DLHC_MAG_Decode(Data[4], Data[5]);
    if (X == -4096 || Y == -4096 || Z == -4096)
    {
        return -ERANGE;
    }
    /* One gauss is 100 microtesla; multiply by 100000 for milli-microtesla. */
    Sample.X = (int32)((int64)X * 100000 / XYGain[Gain]);
    Sample.Y = (int32)((int64)Y * 100000 / XYGain[Gain]);
    Sample.Z = (int32)((int64)Z * 100000 / ZGain[Gain]);
    *Vector = Sample;
    return CFE_SUCCESS;
}
