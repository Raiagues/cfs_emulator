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


/* User file: preserved by appgen sync. */

/**
 * @file
 *   sample sensor adapter for HAL_TEMP.
 */

/* @studio.driver tmp105 */

/*
** Include Files:
*/
#include "hal_temp_sample_sensor.h"
#include "hal_temp_sample_sensor_cfg.h"
#include "hal_temp_eventids.h"
#include "linux_i2c_sensor.h"

#include <string.h>

/* The telemetry payload is the authoritative sensor state. */
static HAL_TEMP_Sample_Tlm_t HAL_TEMP_Sample_Tlm;
static HAL_SENSOR_Device_t HAL_TEMP_Sample_Device;
static TMP105_State_t HAL_TEMP_Sample_State;

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/* Device-specific read. Add driver calls or conversions here.                 */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
static int32 HAL_TEMP_Sample_ReadValue(int32 *Value)
{
    /* @studio.edit sensor.sample.read */
    return TMP105_Acquire(&HAL_TEMP_Sample_Device, Value);
}

/************************************************************************
** Initialize sensor state and telemetry header.
*************************************************************************/
void HAL_TEMP_Sample_Init(void)
{
    memset(&HAL_TEMP_Sample_Tlm, 0, sizeof(HAL_TEMP_Sample_Tlm));
    CFE_MSG_Init(CFE_MSG_PTR(HAL_TEMP_Sample_Tlm.TelemetryHeader),
                 CFE_SB_ValueToMsgId(HAL_TEMP_SAMPLE_TLM_MID), sizeof(HAL_TEMP_Sample_Tlm));
    HAL_TEMP_Sample_Tlm.Payload.Status = CFE_STATUS_NOT_IMPLEMENTED;
    HAL_TEMP_Sample_Device = TMP105_Bind(
        LINUX_I2C_SensorBus(HAL_TEMP_SAMPLE_DEVICE, HAL_TEMP_SAMPLE_ADDRESS),
        &HAL_TEMP_Sample_State);
    /* @studio.edit sensor.sample.init */
}

/** @brief Read sample and publish the timestamped sample and validity flag. */
int32 HAL_TEMP_Sample_Read(void)
{
    HAL_TEMP_Sample_Payload_t *Data = &HAL_TEMP_Sample_Tlm.Payload;
    int32 Value = {0};
    /* Before the first read, any failure is new. */
    int32 PreviousStatus = Data->ReadCounter == 0 ? CFE_SUCCESS : Data->Status;

    Data->ReadCounter++;
    Data->Status = HAL_TEMP_Sample_ReadValue(&Value);
    Data->Valid = Data->Status == CFE_SUCCESS;

    if (Data->Valid)
    {
        Data->Value = Value;
        int32 Magnitude = Value < 0 ? -Value : Value;

        CFE_EVS_SendEvent(HAL_TEMP_SENSOR_VALUE_INF_EID, CFE_EVS_EventType_INFORMATION,
                         "sample: %s%ld.%03ld C", Value < 0 ? "-" : "",
                         (long)(Magnitude / 1000), (long)(Magnitude % 1000));
    }
    else
    {
        Data->ErrorCounter++;
        /** @check Emit a new error event only when the device status changes. */
        if (Data->Status != PreviousStatus)
        {
            CFE_EVS_SendEvent(HAL_TEMP_SENSOR_READ_ERR_EID, CFE_EVS_EventType_ERROR,
                             "sample read failed: status=%ld", (long)Data->Status);
        }
    }

    CFE_SB_TimeStampMsg(CFE_MSG_PTR(HAL_TEMP_Sample_Tlm.TelemetryHeader));
    CFE_SB_TransmitMsg(CFE_MSG_PTR(HAL_TEMP_Sample_Tlm.TelemetryHeader), true);
    return Data->Status;
}

/************************************************************************
** Return the current sample without duplicating sensor state.
*************************************************************************/
const HAL_TEMP_Sample_Payload_t *HAL_TEMP_Sample_GetData(void)
{
    return &HAL_TEMP_Sample_Tlm.Payload;
}
