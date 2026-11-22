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
#ifdef FLIGHT_STUDIO_NATIVE_I2C
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/file.h>
#endif
#include <unistd.h>

int32 LINUX_I2C_LIB_Init(void)
{
    /* A loaded transport library does not claim or open physical hardware. */
    OS_printf("Linux I2C library " LINUX_I2C_LIB_VERSION " initialized.\n");
    return CFE_SUCCESS;
}

#ifdef FLIGHT_STUDIO_NATIVE_I2C
static int32 RegisterTransfer(const char *device, uint16 address, const uint8 *tx, uint16 tx_len, uint8 *rx, uint16 rx_len)
{
    const char *directory = getenv("FLIGHT_STUDIO_NATIVE_DEVICES");
    unsigned int bus;
    char suffix;
    char path[PATH_MAX];
    if (directory == NULL || sscanf(device, "/dev/i2c-%u%c", &bus, &suffix) != 1 || tx_len == 0)
    {
        return -EINVAL;
    }
    unsigned int offset = tx[0];
    if (offset + tx_len - 1U + rx_len > 256U)
    {
        return -EINVAL;
    }
    int length = snprintf(path, sizeof(path), "%s/i2c%u-0x%02x.bin", directory, bus, (unsigned int)address);
    if (length < 0 || (size_t)length >= sizeof(path))
    {
        return -ENAMETOOLONG;
    }
    int fd = open(path, O_RDWR | O_CLOEXEC);
    if (fd < 0)
    {
        return -errno;
    }
    int32 status = CFE_SUCCESS;
    if (flock(fd, tx_len > 1 ? LOCK_EX : LOCK_SH) < 0)
    {
        status = -errno;
    }
    if (status == CFE_SUCCESS && tx_len > 1)
    {
        ssize_t n = pwrite(fd, tx + 1, tx_len - 1, offset);
        status = n < 0 ? -errno : n == tx_len - 1 ? CFE_SUCCESS : -EIO;
        offset += tx_len - 1;
    }
    if (status == CFE_SUCCESS && rx_len > 0)
    {
        ssize_t n = pread(fd, rx, rx_len, offset);
        status = n < 0 ? -errno : n == rx_len ? CFE_SUCCESS : -EIO;
    }
    close(fd);
    return status;
}
#endif

int32 LINUX_I2C_Transfer(const char *Device, uint16 Address, const uint8 *WriteData, uint16 WriteLength, uint8 *ReadData, uint16 ReadLength)
{
#ifndef FLIGHT_STUDIO_NATIVE_I2C
    int Bus;
    int Result;
    int32 Status;
    struct i2c_msg Messages[LINUX_I2C_MAX_MESSAGES];
    struct i2c_rdwr_ioctl_data Transfer = {.msgs = Messages, .nmsgs = 0};

#endif

    /* Validate each buffer before handing its pointer to the kernel. */
    bool EmptyTransfer = WriteLength == 0 && ReadLength == 0;
    bool MissingBuffer = (WriteLength != 0 && WriteData == NULL) || (ReadLength != 0 && ReadData == NULL);
    if (Device == NULL || Device[0] == '\0' || Address > LINUX_I2C_MAX_ADDRESS || EmptyTransfer || MissingBuffer)
    {
        return -EINVAL;
    }
#ifdef FLIGHT_STUDIO_NATIVE_I2C
    return RegisterTransfer(Device, Address, WriteData, WriteLength, ReadData, ReadLength);
#else
    if (WriteLength != 0)
    {
        Messages[Transfer.nmsgs++] = (struct i2c_msg){.addr = Address, .flags = 0, .len = WriteLength, .buf = (uint8 *)WriteData};
    }
    if (ReadLength != 0)
    {
        Messages[Transfer.nmsgs++] = (struct i2c_msg){.addr = Address, .flags = I2C_M_RD, .len = ReadLength, .buf = ReadData};
    }
    Bus = open(Device, O_RDWR | O_CLOEXEC);
    if (Bus < 0)
    {
        return -errno;
    }
    /* I2C_RDWR executes both messages as one bus transaction. */
    Result = ioctl(Bus, I2C_RDWR, &Transfer);
    Status = Result < 0 ? -errno : ((unsigned int)Result == Transfer.nmsgs ? CFE_SUCCESS : -EIO);
    close(Bus);
    return Status;
#endif
}

int32 LINUX_I2C_ReadRegister(const char *Device, uint16 Address, uint8 Register, uint8 *Data, uint16 Length)
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
