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
 *   sample sensor data and public interface for HAL_TEMP.
 */
#ifndef HAL_TEMP_SAMPLE_SENSOR_H
#define HAL_TEMP_SAMPLE_SENSOR_H

#include "cfe.h"
#include "tmp105_lib.h"

/************************************************************************
** Sensor telemetry payload. This is also the sensor's only stored state.
*************************************************************************/
typedef struct
{
    /* @studio.edit sensor.sample.payload */
    int32 Value;  /**< @unit millidegrees Celsius @range -128000..127937 */
    int32  Status;       /**< Status of the latest read. */
    uint32 ReadCounter;  /**< Number of attempted reads. */
    uint32 ErrorCounter; /**< Number of failed reads. */
    uint8  Valid;        /**< Nonzero only when the latest read succeeded. */
    uint8  Reserved[3];
} HAL_TEMP_Sample_Payload_t;

typedef struct
{
    CFE_MSG_TelemetryHeader_t   TelemetryHeader;
    HAL_TEMP_Sample_Payload_t Payload;
} HAL_TEMP_Sample_Tlm_t;

void HAL_TEMP_Sample_Init(void);
int32 HAL_TEMP_Sample_Read(void);
const HAL_TEMP_Sample_Payload_t *HAL_TEMP_Sample_GetData(void);

#endif /* HAL_TEMP_SAMPLE_SENSOR_H */
