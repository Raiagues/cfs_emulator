#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif

#include "linux_uart_lib_internal.h"
#include "linux_uart_lib_version.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <termios.h>
#include <unistd.h>

int32 LINUX_UART_LIB_Init(void)
{
    OS_printf("Linux UART library " LINUX_UART_LIB_VERSION " initialized.\n");
    return CFE_SUCCESS;
}

static speed_t LINUX_UART_Baud(uint32 BaudRate)
{
    switch (BaudRate)
    {
        case 1200: return B1200;
        case 2400: return B2400;
        case 4800: return B4800;
        case 9600: return B9600;
        case 19200: return B19200;
        case 38400: return B38400;
        case 57600: return B57600;
        case 115200: return B115200;
        default: return 0;
    }
}

int32 LINUX_UART_Open(const char *Device, const LINUX_UART_Config_t *Config, int32 *Descriptor)
{
    int Port;
    int32 Status;
    speed_t Speed;
    struct termios Settings;

    if (Device == NULL || Device[0] == '\0' || Config == NULL || Descriptor == NULL ||
        (Config->DataBits != 7 && Config->DataBits != 8) ||
        (Config->StopBits != 1 && Config->StopBits != 2) ||
        (Config->Parity != 'N' && Config->Parity != 'E' && Config->Parity != 'O'))
    {
        return -EINVAL;
    }
    Speed = LINUX_UART_Baud(Config->BaudRate);
    if (Speed == 0)
    {
        return -EINVAL;
    }
    Port = open(Device, O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (Port < 0)
    {
        return -errno;
    }
    if (tcgetattr(Port, &Settings) != 0)
    {
        Status = -errno;
        close(Port);
        return Status;
    }
    cfmakeraw(&Settings);
    Settings.c_iflag &= ~(IXON | IXOFF | IXANY | INPCK | IGNPAR);
    Settings.c_cflag &= ~(CSIZE | CSTOPB | PARENB | PARODD | CRTSCTS);
    Settings.c_cflag |= CLOCAL | CREAD | (Config->DataBits == 7 ? CS7 : CS8);
    if (Config->StopBits == 2)
    {
        Settings.c_cflag |= CSTOPB;
    }
    if (Config->Parity != 'N')
    {
        Settings.c_cflag |= PARENB;
        Settings.c_iflag |= INPCK;
        if (Config->Parity == 'O')
        {
            Settings.c_cflag |= PARODD;
        }
    }
    Settings.c_cc[VMIN] = 0;
    Settings.c_cc[VTIME] = 0;
    if (cfsetispeed(&Settings, Speed) != 0 || cfsetospeed(&Settings, Speed) != 0 ||
        tcsetattr(Port, TCSANOW, &Settings) != 0)
    {
        Status = -errno;
        close(Port);
        return Status;
    }
    *Descriptor = Port;
    return CFE_SUCCESS;
}

int32 LINUX_UART_Close(int32 Descriptor)
{
    return close(Descriptor) == 0 ? CFE_SUCCESS : -errno;
}

static int32 LINUX_UART_Ready(int32 Descriptor, short Event, uint32 TimeoutMs)
{
    struct pollfd Port = {.fd = Descriptor, .events = Event};
    int Result;
    if (Descriptor < 0 || TimeoutMs > INT_MAX)
    {
        return -EINVAL;
    }
    Result = poll(&Port, 1, (int)TimeoutMs);
    if (Result < 0)
    {
        return -errno;
    }
    if (Result == 0)
    {
        return -ETIMEDOUT;
    }
    if ((Port.revents & POLLNVAL) != 0)
    {
        return -EBADF;
    }
    return (Port.revents & Event) != 0 ? CFE_SUCCESS : -EIO;
}

int32 LINUX_UART_Read(int32 Descriptor, uint8 *Data, uint32 Capacity, uint32 *Bytes, uint32 TimeoutMs)
{
    int32 Status;
    ssize_t Count;
    if (Bytes == NULL)
    {
        return -EINVAL;
    }
    *Bytes = 0;
    if (Data == NULL || Capacity == 0 || Capacity > INT_MAX)
    {
        return -EINVAL;
    }
    Status = LINUX_UART_Ready(Descriptor, POLLIN, TimeoutMs);
    if (Status != CFE_SUCCESS)
    {
        return Status;
    }
    Count = read(Descriptor, Data, Capacity);
    if (Count <= 0)
    {
        return Count < 0 ? -errno : -EIO;
    }
    *Bytes = (uint32)Count;
    return CFE_SUCCESS;
}

int32 LINUX_UART_Write(int32 Descriptor, const uint8 *Data, uint32 Length, uint32 *Bytes, uint32 TimeoutMs)
{
    int32 Status;
    ssize_t Count;
    if (Bytes == NULL)
    {
        return -EINVAL;
    }
    *Bytes = 0;
    if (Data == NULL || Length == 0 || Length > INT_MAX)
    {
        return -EINVAL;
    }
    Status = LINUX_UART_Ready(Descriptor, POLLOUT, TimeoutMs);
    if (Status != CFE_SUCCESS)
    {
        return Status;
    }
    Count = write(Descriptor, Data, Length);
    if (Count < 0)
    {
        return -errno;
    }
    *Bytes = (uint32)Count;
    return CFE_SUCCESS;
}
