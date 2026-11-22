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


/* Generated mission integration; edit native configuration or project app settings. */

/**
 * @file
 *   Registered sensor and telemetry calls for HAL_MAG.
 */

#include "hal_mag_components.h"
/* @studio.begin component.includes 39887ee18581bfcb */
#include "hal_mag_user.h"
#include "sensors/hal_mag_sample_sensor.h"
/* @studio.end component.includes */

/************************************************************************
** Initialize registered components, then invoke user initialization.
*************************************************************************/
CFE_Status_t HAL_MAG_ComponentsInit(void)
{
/* @studio.begin component.init bfd1bf26bc005376 */
    HAL_MAG_Sample_Init();
/* @studio.end component.init */
    return HAL_MAG_UserInit();
}

/************************************************************************
** Read sensors, invoke application logic and publish custom telemetry.
*************************************************************************/
void HAL_MAG_ComponentsWakeup(void)
{
/* @studio.begin component.wakeup 23fff65001896038 */
    HAL_MAG_Sample_Read();
    HAL_MAG_UserWakeup();
/* @studio.end component.wakeup */
}
