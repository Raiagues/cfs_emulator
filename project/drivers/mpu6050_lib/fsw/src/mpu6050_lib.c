/************************************************************************
 * NASA Docket No. GSC-19,200-1, and identified as "cFS Draco"
 *
 * Copyright (c) 2023 United States Government as represented by the
 * Administrator of the National Aeronautics and Space Administration.
 * All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License. You may obtain
 * a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 ************************************************************************/

/**
 * @file
 *   Sample CFS library
 */

/*************************************************************************
** Includes
*************************************************************************/
#include "mpu6050_lib_version.h"
#include "mpu6050_lib_internal.h"

#include "cfe_config.h"

/* for "strncpy()" */
#include <string.h>

/*************************************************************************
** Private Data Structures
*************************************************************************/
char MPU6050_LIB_Buffer[MPU6050_LIB_BUFFER_SIZE];

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */
/*                                                                 */
/* Library Initialization Routine                                  */
/* cFE requires that a library have an initialization routine      */
/*                                                                 */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */
int32 MPU6050_LIB_Init(void)
{
    char VersionString[MPU6050_LIB_CFG_MAX_VERSION_STR_LEN];

    /*
     * Call a C library function, like strcpy(), and test its result.
     *
     * This is primary for a unit test example, to have more than
     * one code path to exercise.
     *
     * The specification for strncpy() indicates that it should return
     * the pointer to the destination buffer, so it should be impossible
     * for this to ever fail when linked with a compliant C library.
     */
    if (strncpy(MPU6050_LIB_Buffer, "SAMPLE DATA", sizeof(MPU6050_LIB_Buffer) - 1) != MPU6050_LIB_Buffer)
    {
        return CFE_STATUS_NOT_IMPLEMENTED;
    }

    /* ensure termination */
    MPU6050_LIB_Buffer[sizeof(MPU6050_LIB_Buffer) - 1] = 0;

    CFE_Config_GetVersionString(VersionString,
                                MPU6050_LIB_CFG_MAX_VERSION_STR_LEN,
                                "Mpu6050 Lib",
                                MPU6050_LIB_VERSION,
                                MPU6050_LIB_BUILD_CODENAME,
                                MPU6050_LIB_LAST_OFFICIAL);

    OS_printf("SAMPLE Lib Initialized.%s\n", VersionString);

    return CFE_SUCCESS;
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */
/*                                                                 */
/* Mpu6050 Lib function                                             */
/*                                                                 */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * */
int32 MPU6050_LIB_Function(void)
{
    OS_printf("MPU6050_LIB_Function called, buffer=\'%s\'\n", MPU6050_LIB_Buffer);

    return CFE_SUCCESS;
}

#include "linux_i2c_lib.h"
#include <errno.h>

/* Verify the device identity before applying its startup register writes. */
int32 MPU6050_Configure(const char *Device, uint16 Address)
{
    uint8 identity;
    int32 status = LINUX_I2C_ReadRegister(Device, Address, 0x75, &identity, 1);
    if (status != CFE_SUCCESS) { return status; }
    if (identity != 0x68) { return -ENODEV; }
    status = LINUX_I2C_WriteRegister(Device, Address, 0x6b, 0x01);
    if (status != CFE_SUCCESS) { return status; }
    status = LINUX_I2C_WriteRegister(Device, Address, 0x6c, 0x00);
    if (status != CFE_SUCCESS) { return status; }
    status = LINUX_I2C_WriteRegister(Device, Address, 0x1b, 0x00);
    if (status != CFE_SUCCESS) { return status; }
    status = LINUX_I2C_WriteRegister(Device, Address, 0x1c, 0x00);
    if (status != CFE_SUCCESS) { return status; }
    return CFE_SUCCESS;
}

/* Sign extend one big-endian register pair before converting to engineering units. */
static int32 DecodeWord(const uint8 *data)
{
    int32 word = ((int32)data[0] << 8) | data[1];
    return word >= 32768 ? word - 65536 : word;
}

int32 MPU6050_Read(const char *Device, uint16 Address, MPU6050_Sample_t *Sample)
{
    uint8 data[14];
    if (Sample == NULL) { return -EINVAL; }
    int32 status = LINUX_I2C_ReadRegister(Device, Address, 0x3b, data, sizeof(data));
    if (status != CFE_SUCCESS) { return status; }
    Sample->Value_accel_x = (int32)((int64)DecodeWord(&data[0]) * 1000 / 16384 + 0);
    Sample->Value_accel_y = (int32)((int64)DecodeWord(&data[2]) * 1000 / 16384 + 0);
    Sample->Value_accel_z = (int32)((int64)DecodeWord(&data[4]) * 1000 / 16384 + 0);
    Sample->Value_temperature = (int32)((int64)DecodeWord(&data[6]) * 1000 / 340 + 36530);
    Sample->Value_gyro_x = (int32)((int64)DecodeWord(&data[8]) * 1000 / 131 + 0);
    Sample->Value_gyro_y = (int32)((int64)DecodeWord(&data[10]) * 1000 / 131 + 0);
    Sample->Value_gyro_z = (int32)((int64)DecodeWord(&data[12]) * 1000 / 131 + 0);
    return CFE_SUCCESS;
}
