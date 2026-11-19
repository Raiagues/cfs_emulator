#ifndef LINUX_I2C_SENSOR_H
#define LINUX_I2C_SENSOR_H

#include "hal_sensor.h"
#include "linux_i2c_lib.h"

/* Bind a HAL endpoint to a Linux device path. The path must outlive the binding. */
static inline int32_t LINUX_I2C_SensorTransfer(const void *path, uint16_t address,
    const uint8_t *tx, uint16_t tx_size, uint8_t *rx, uint16_t rx_size)
{
    return LINUX_I2C_Transfer(path, address, tx, tx_size, rx, rx_size);
}

static inline HAL_SENSOR_Bus_t LINUX_I2C_SensorBus(const char *path, uint16_t address)
{
    return (HAL_SENSOR_Bus_t){.Transaction = LINUX_I2C_SensorTransfer, .Context = path, .Address = address};
}

#endif
