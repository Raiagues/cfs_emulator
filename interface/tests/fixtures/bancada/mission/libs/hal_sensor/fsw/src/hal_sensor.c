#include "hal_sensor.h"

#include <errno.h>
#include <limits.h>
#include <string.h>

int32_t HAL_SENSOR_LibInit(void)
{
    return 0;
}

int32_t HAL_SENSOR_ReadRegister(const HAL_SENSOR_Bus_t *bus, uint8_t reg, uint8_t *data, uint16_t size)
{
    if (!bus || !bus->Transaction || !data || !size)
        return -EINVAL;
    return bus->Transaction(bus->Context, bus->Address, &reg, 1, data, size);
}

int32_t HAL_SENSOR_WriteRegister(const HAL_SENSOR_Bus_t *bus, uint8_t reg, uint8_t value)
{
    const uint8_t command[] = {reg, value};
    if (!bus || !bus->Transaction)
        return -EINVAL;
    return bus->Transaction(bus->Context, bus->Address, command, sizeof(command), NULL, 0);
}

int32_t HAL_SENSOR_ConfigureRegisters(const HAL_SENSOR_Bus_t *bus, const HAL_SENSOR_Profile_t *profile)
{
    uint8_t identity[HAL_SENSOR_MAX_BURST];
    if (!bus || !bus->Transaction || !profile || profile->IdentitySize > sizeof(identity) ||
        (profile->IdentitySize && !profile->Identity) || (profile->SetupCount && !profile->Setup))
        return -EINVAL;
    if (profile->IdentitySize)
    {
        int32_t status = HAL_SENSOR_ReadRegister(bus, profile->IdentityRegister, identity, profile->IdentitySize);
        if (status != 0)
            return status;
        /** @check Verify the chip identity before writing its configuration. */
        if (memcmp(identity, profile->Identity, profile->IdentitySize) != 0)
            return -ENODEV;
    }
    for (size_t i = 0; i < profile->SetupCount; ++i)
    {
        int32_t status = HAL_SENSOR_WriteRegister(bus, profile->Setup[i].Register, profile->Setup[i].Value);
        if (status != 0)
            return status;
    }
    return 0;
}

static int32_t Decode(const HAL_SENSOR_Output_t *output, const uint8_t *bytes, const uint8_t *ranges, int32_t *value)
{
    uint16_t word = ((uint16_t)bytes[0] << 8) | bytes[1];
    int32_t raw = word >= 0x8000 ? (int32_t)word - 65536 : (int32_t)word;
    if (word & output->ReservedMask)
        return -EIO;
    if (output->HasInvalidRaw && raw == output->InvalidRaw)
        return -ERANGE;

    int64_t scaled = (int64_t)raw * output->Numerator;
    int32_t counts = output->Counts;
    if (output->RangeIndex >= 0)
    {
        uint8_t range = ranges[output->RangeIndex];
        if (output->GainCounts)
            counts = output->GainCounts[range];
        else
            scaled *= 1U << range;
    }
    if (counts <= 0)
        return -EINVAL;
    scaled = scaled / counts + output->Zero;
    if (scaled < INT32_MIN || scaled > INT32_MAX)
        return -ERANGE;
    *value = (int32_t)scaled;
    return 0;
}

int32_t HAL_SENSOR_ReadRegisters(const HAL_SENSOR_Bus_t *bus, const HAL_SENSOR_Profile_t *profile, int32_t *values)
{
    uint8_t data[HAL_SENSOR_MAX_BURST], ranges[HAL_SENSOR_MAX_OUTPUTS];
    int32_t status;
    if (!profile || !values || !profile->Outputs || profile->OutputCount > HAL_SENSOR_MAX_OUTPUTS ||
        profile->RangeCount > sizeof(ranges) || (profile->RangeCount && !profile->Ranges) ||
        profile->BurstSize < 2 || profile->BurstSize > sizeof(data))
        return -EINVAL;
    if (profile->ReadyMask)
    {
        uint8_t ready;
        status = HAL_SENSOR_ReadRegister(bus, profile->ReadyRegister, &ready, 1);
        if (status != 0)
            return status;
        if ((ready & profile->ReadyMask) != profile->ReadyMask)
            return -EAGAIN;
    }
    for (size_t i = 0; i < profile->RangeCount; ++i)
    {
        const HAL_SENSOR_Range_t *range = &profile->Ranges[i];
        if (range->Shift > 7 || range->Mask > 7)
            return -EINVAL;
        status = HAL_SENSOR_ReadRegister(bus, range->Register, &ranges[i], 1);
        if (status != 0)
            return status;
        ranges[i] = (ranges[i] >> range->Shift) & range->Mask;
    }
    status = HAL_SENSOR_ReadRegister(bus, profile->FirstRegister, data, profile->BurstSize);
    if (status != 0)
        return status;
    for (size_t i = 0; i < profile->OutputCount; ++i)
    {
        const HAL_SENSOR_Output_t *output = &profile->Outputs[i];
        if (output->ByteOffset + 1 >= profile->BurstSize ||
            (output->RangeIndex >= 0 && (size_t)output->RangeIndex >= profile->RangeCount))
            return -EINVAL;
        status = Decode(output, data + output->ByteOffset, ranges, &values[i]);
        if (status != 0)
            return status;
    }
    return 0;
}

int32_t HAL_SENSOR_Configure(HAL_SENSOR_Device_t *device)
{
    if (!device || !device->Profile || !device->Bus.Transaction)
        return -EINVAL;
    int32_t status = device->Ops && device->Ops->Configure
        ? device->Ops->Configure(device)
        : HAL_SENSOR_ConfigureRegisters(&device->Bus, device->Profile);
    device->Configured = status == 0;
    return status;
}

int32_t HAL_SENSOR_Read(const HAL_SENSOR_Device_t *device, int32_t *values, size_t capacity)
{
    int32_t sample[HAL_SENSOR_MAX_OUTPUTS];
    if (!device || !device->Profile || !device->Bus.Transaction || !values ||
        device->Profile->OutputCount > HAL_SENSOR_MAX_OUTPUTS || device->Profile->OutputCount > capacity)
        return -EINVAL;
    int32_t status = device->Ops && device->Ops->Read
        ? device->Ops->Read(device, sample)
        : HAL_SENSOR_ReadRegisters(&device->Bus, device->Profile, sample);
    if (status == 0)
        memcpy(values, sample, device->Profile->OutputCount * sizeof(sample[0]));
    return status;
}

int32_t HAL_SENSOR_Acquire(HAL_SENSOR_Device_t *device, int32_t *values, size_t capacity)
{
    if (!device || !device->Profile || !values || capacity < device->Profile->OutputCount)
        return -EINVAL;
    if (!device->Configured)
    {
        int32_t status = HAL_SENSOR_Configure(device);
        if (status != 0)
            return status;
    }
    return HAL_SENSOR_Read(device, values, capacity);
}
