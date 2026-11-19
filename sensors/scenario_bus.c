/* Local signal test adapter. The flight HAL sees a register bus or an I/O error. */
#include "hal_sensor.h"
#include "profile.h"
#include <errno.h>
#include <string.h>

static uint8_t *bank;
static bool disconnected;

static int32_t transfer(const void *ctx, uint16_t address, const uint8_t *tx, uint16_t n,
                        uint8_t *rx, uint16_t count)
{
    (void)ctx;
    (void)address;
    if (disconnected)
        return -ENODEV;
    if (n == 2 && !count)
    {
        bank[tx[0]] = tx[1];
        return 0;
    }
    if (n != 1 || !rx || tx[0] + count > 256)
        return -EINVAL;
    memcpy(rx, bank + tx[0], count);
    return 0;
}

int32_t read_sample(uint8_t registers[256], bool dropout, int32_t *out, size_t count)
{
    static HAL_SENSOR_Device_t device = {.Bus = {.Transaction = transfer}, .Profile = &Profile};
    bank = registers;
    disconnected = dropout;
    return HAL_SENSOR_Acquire(&device, out, count);
}
