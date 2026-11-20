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
 *
 * Main header file for the Sample application
 */

#ifndef HAL_MPU_H
#define HAL_MPU_H

/*
** Required header files.
*/
#include "cfe.h"
#include "cfe_config.h"

#include "hal_mpu_mission_cfg.h"
#include "hal_mpu_platform_cfg.h"

#include "hal_mpu_perfids.h"
#include "hal_mpu_msgids.h"
#include "hal_mpu_msg.h"

/************************************************************************
** Type Definitions
*************************************************************************/

/*
** Global Data
*/
typedef struct
{
    /*
    ** Command interface counters...
    */
    uint8 CommandCounter;
    uint8 CommandErrorCounter;

    /*
    ** Housekeeping telemetry packet...
    */
    HAL_MPU_HkTlm_t HkTlm;

    /*
    ** Run Status variable used in the main processing loop
    */
    uint32 RunStatus;

    /*
    ** Operational data (not reported in housekeeping)...
    */
    CFE_SB_PipeId_t CommandPipe;

    CFE_TBL_Handle_t TblHandles[HAL_MPU_PLATFORM_NUMBER_OF_TABLES];
} HAL_MPU_Data_t;

/*
** Global data structure
*/
extern HAL_MPU_Data_t HAL_MPU_Data;

/****************************************************************************/
/*
** Local function prototypes.
**
** Note: Except for the entry point (HAL_MPU_Main), these
**       functions are not called from any other source module.
*/
void         HAL_MPU_Main(void);
CFE_Status_t HAL_MPU_Init(void);

#endif /* HAL_MPU_H */
