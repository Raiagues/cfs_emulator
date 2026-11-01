#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif

#include "linux_i2c_lib_internal.h"
#include "linux_i2c_lib_version.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <unistd.h>

int32 LINUX_I2C_LIB_Init(void)
{
    /* A loaded transport library does not claim or open physical hardware. */
    OS_printf("Linux I2C library " LINUX_I2C_LIB_VERSION " initialized.\n");
    return CFE_SUCCESS;
}

int32 LINUX_I2C_Transfer(const char *Device, uint16 Address,
                       const uint8 *WriteData, uint16 WriteLength,
                       uint8 *ReadData, uint16 ReadLength)
{
    int Bus;
    int Result;
    int32 Status;
    struct i2c_msg Messages[LINUX_I2C_MAX_MESSAGES];
    struct i2c_rdwr_ioctl_data Transfer = {.msgs = Messages, .nmsgs = 0};

    if (Device == NULL || Device[0] == '\0' || Address > LINUX_I2C_MAX_ADDRESS ||
        (WriteLength == 0 && ReadLength == 0) ||
        (WriteLength != 0 && WriteData == NULL) || (ReadLength != 0 && ReadData == NULL))
    {
        return -EINVAL;
    }
    if (WriteLength != 0)
    {
        Messages[Transfer.nmsgs++] = (struct i2c_msg){
            .addr = Address, .flags = 0, .len = WriteLength, .buf = (uint8 *)WriteData};
    }
    if (ReadLength != 0)
    {
        Messages[Transfer.nmsgs++] = (struct i2c_msg){
            .addr = Address, .flags = I2C_M_RD, .len = ReadLength, .buf = ReadData};
    }
    Bus = open(Device, O_RDWR | O_CLOEXEC);
    if (Bus < 0)
    {
        return -errno;
    }
    Result = ioctl(Bus, I2C_RDWR, &Transfer);
    Status = Result < 0 ? -errno : ((unsigned int)Result == Transfer.nmsgs ? CFE_SUCCESS : -EIO);
    close(Bus);
    return Status;
}

int32 LINUX_I2C_ReadRegister(const char *Device, uint16 Address, uint8 Register,
                           uint8 *Data, uint16 Length)
{
    if (Length == 0)
    {
        return -EINVAL;
    }
    return LINUX_I2C_Transfer(Device, Address, &Register, 1, Data, Length);
}

int32 LINUX_I2C_WriteRegister(const char *Device, uint16 Address, uint8 Register, uint8 Value)
{
    const uint8 Data[2] = {Register, Value};
    return LINUX_I2C_Transfer(Device, Address, Data, sizeof(Data), NULL, 0);
}
