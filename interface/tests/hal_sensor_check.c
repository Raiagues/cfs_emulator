/* Exercise the generated flight drivers against a register-level I²C endpoint. */
#include "tmp105_lib.h"
#include "lsm303dlhc_mag_lib.h"
#include "mpu6050_lib.h"
#include "lab_sensor_lib.h"
#include "lab_cal_lib.h"
#include "lab_byte_lib.h"
#include "linux_i2c_lib.h"

#include <assert.h>
#include <errno.h>
#include <string.h>

typedef struct
{
    uint8_t Registers[256];
    unsigned int Writes, Bursts;
    uint8_t LastBurst;
    uint16_t Address;
    bool FailWrite;
} Endpoint;

static int32_t Transfer(const void *context, uint16_t address, const uint8_t *tx, uint16_t ntx,
                        uint8_t *rx, uint16_t nrx)
{
    Endpoint *port = (Endpoint *)context;
    assert(port->Address == address && tx && (size_t)tx[0] + nrx <= 256);
    if (nrx)
    {
        assert(ntx == 1);
        if (nrx > 1)
        {
            ++port->Bursts;
            port->LastBurst = nrx;
        }
        memcpy(rx, &port->Registers[tx[0]], nrx);
        return 0;
    }
    assert(ntx == 2);
    if (port->FailWrite)
        return -EIO;
    port->Registers[tx[0]] = tx[1];
    ++port->Writes;
    return 0;
}

/* Exercise the original public ABI on the same endpoint. */
static Endpoint Legacy;
int32 LINUX_I2C_Transfer(const char *path, uint16 address, const uint8 *tx, uint16 ntx, uint8 *rx, uint16 nrx)
{
    assert(strcmp(path, "/dev/i2c-test") == 0);
    return Transfer(&Legacy, address, tx, ntx, rx, nrx);
}

static HAL_SENSOR_Bus_t Bus(Endpoint *port)
{
    return (HAL_SENSOR_Bus_t){.Transaction = Transfer, .Context = port, .Address = port->Address};
}

static void Word(Endpoint *port, uint8_t reg, int16_t value)
{
    port->Registers[reg] = (uint16_t)value >> 8;
    port->Registers[reg + 1] = (uint8_t)value;
}

static void Temperature(void)
{
    Endpoint port = {.Address = 0x48};
    HAL_SENSOR_Device_t device = TMP105_Bind(Bus(&port), NULL);
    int32 sample = 0;
    Word(&port, 0, -384);
    assert(TMP105_Acquire(&device, &sample) == 0 && sample == -1500);
    assert(port.Writes == 0 && port.Bursts == 1 && port.LastBurst == 2);
    Word(&port, 0, -1);
    assert(TMP105_Acquire(&device, &sample) == -EIO && sample == -1500);
    Legacy.Address = 0x49;
    Word(&Legacy, 0, 192);
    assert(TMP105_LIB_ReadTemperature("/dev/i2c-test", 0x49, &sample) == 0 && sample == 750);
}

static void Magnetometer(void)
{
    Endpoint port = {.Address = 0x1E};
    HAL_SENSOR_Device_t device = LSM303DLHC_MAG_Bind(Bus(&port), NULL);
    LSM303DLHC_MAG_Vector_t sample = {0};
    assert(LSM303DLHC_MAG_Acquire(&device, &sample) == -ENODEV && port.Writes == 0);
    memcpy(&port.Registers[10], "H43", 3);
    assert(LSM303DLHC_MAG_Acquire(&device, &sample) == -EAGAIN);
    assert(port.Writes == 3 && port.Registers[0] == 0x10 && port.Registers[1] == 0x20 && port.Registers[2] == 0);
    port.Registers[9] = 1;
    port.Registers[1] = 2 << 5;
    Word(&port, 3, 855);
    Word(&port, 5, -760);
    Word(&port, 7, -855);
    assert(LSM303DLHC_MAG_Acquire(&device, &sample) == 0);
    assert(sample.X == 100000 && sample.Y == -100000 && sample.Z == -100000 && port.LastBurst == 6);
    Word(&port, 3, 0);
    Word(&port, 5, -4096); /* overflow on the last decoded axis */
    assert(LSM303DLHC_MAG_Acquire(&device, &sample) == -ERANGE && sample.X == 100000);
    port.Registers[1] = 0;
    assert(LSM303DLHC_MAG_Acquire(&device, &sample) == -EINVAL && sample.X == 100000);
    assert(port.Writes == 3);
}

static void Inertial(void)
{
    Endpoint port = {.Address = 0x69};
    MPU6050_Sample_t sample = {0};
    HAL_SENSOR_Device_t device = MPU6050_Bind(Bus(&port), NULL);
    port.Registers[0x75] = 0x68;
    port.FailWrite = true;
    assert(MPU6050_Acquire(&device, &sample) == -EIO && !device.Configured);
    port.FailWrite = false;
    Word(&port, 0x3b, 8192);
    Word(&port, 0x41, -340);
    Word(&port, 0x47, -131);
    assert(MPU6050_Acquire(&device, &sample) == 0 && port.Writes == 4 && port.Registers[0x6b] == 1);
    assert(sample.Value_accel_x == 500 && sample.Value_temperature == 35530 && sample.Value_gyro_z == -1000);
    port.Registers[0x1c] = 1 << 3;
    port.Registers[0x1b] = 2 << 3;
    assert(MPU6050_Acquire(&device, &sample) == 0 && sample.Value_accel_x == 1000 && sample.Value_gyro_z == -4000);
    assert(port.Writes == 4 && port.Bursts == 2 && port.LastBurst == 14);
}

static void FourthModel(void)
{
    Endpoint a = {.Address = 0x48}, b = {.Address = 0x49};
    HAL_SENSOR_Device_t first = LAB_SENSOR_Bind(Bus(&a), NULL), second = LAB_SENSOR_Bind(Bus(&b), NULL);
    LAB_SENSOR_Sample_t sample = {0};
    a.Registers[0] = b.Registers[0] = 66;
    Word(&a, 16, 256);
    Word(&b, 16, -512);
    assert(LAB_SENSOR_Acquire(&first, &sample) == 0 && sample.Value_temperature == 1000);
    assert(LAB_SENSOR_Acquire(&second, &sample) == 0 && sample.Value_temperature == -2000);
    assert(a.Writes == 1 && b.Writes == 1 && a.Registers[1] == 1 && b.Registers[1] == 1);
}

static void StatefulModel(void)
{
    Endpoint a = {.Address = 0x48}, b = {.Address = 0x49};
    LAB_CAL_State_t a_state, b_state;
    HAL_SENSOR_Device_t first = LAB_CAL_Bind(Bus(&a), &a_state), second = LAB_CAL_Bind(Bus(&b), &b_state);
    LAB_CAL_Sample_t sample = {0};
    a.Registers[0] = b.Registers[0] = 66;
    assert(LAB_CAL_Acquire(&first, &sample) == 0 && sample.Value_temperature == 1);
    assert(LAB_CAL_Acquire(&first, &sample) == 0 && sample.Value_temperature == 2);
    assert(LAB_CAL_Acquire(&second, &sample) == 0 && sample.Value_temperature == 1);
    assert(a_state.Count == 2 && b_state.Count == 1);
}

static void CustomProtocol(void)
{
    Endpoint port = {.Address = 0x48};
    HAL_SENSOR_Device_t device = LAB_BYTE_Bind(Bus(&port), NULL);
    LAB_BYTE_Sample_t sample = {0};
    port.Registers[0x10] = 231;
    assert(LAB_BYTE_Acquire(&device, &sample) == 0 && sample.Value_level == 231);
    assert(port.Writes == 0 && port.Bursts == 0);
}

int main(void)
{
    Temperature();
    Magnetometer();
    Inertial();
    FourthModel();
    StatefulModel();
    CustomProtocol();
    return 0;
}
