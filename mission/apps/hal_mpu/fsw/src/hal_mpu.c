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
 * \file
 *   This file contains the source code for the Hal Mpu.
 */

/*
** Include Files:
*/
/* @studio.begin app.includes 94cb3fdde70d9808 */
#include "hal_mpu_components.h"
/* @studio.end app.includes */
#include "hal_mpu.h"
#include "hal_mpu_cmds.h"
#include "hal_mpu_utils.h"
#include "hal_mpu_eventids.h"
#include "hal_mpu_dispatch.h"
#include "hal_mpu_tbl.h"
#include "hal_mpu_version.h"

/*
** global data
*/
HAL_MPU_Data_t HAL_MPU_Data;

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  * *  * * * * **/
/*                                                                            */
/* Application entry point and main process loop                              */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  * *  * * * * **/
void HAL_MPU_Main(void)
{
    CFE_Status_t     status;
    CFE_SB_Buffer_t *SBBufPtr;

    /*
    ** Create the first Performance Log entry
    */
    CFE_ES_PerfLogEntry(HAL_MPU_PERF_ID);

    /*
    ** Perform application-specific initialization
    ** If the Initialization fails, set the RunStatus to
    ** CFE_ES_RunStatus_APP_ERROR and the App will not enter the RunLoop
    */
    status = HAL_MPU_Init();
    if (status != CFE_SUCCESS)
    {
        HAL_MPU_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    }

    /*
    ** Hal Mpu Runloop
    */
    while (CFE_ES_RunLoop(&HAL_MPU_Data.RunStatus) == true)
    {
        /*
        ** Performance Log Exit Stamp
        */
        CFE_ES_PerfLogExit(HAL_MPU_PERF_ID);

        /* Pend on receipt of command packet */
        status = CFE_SB_ReceiveBuffer(&SBBufPtr, HAL_MPU_Data.CommandPipe, CFE_SB_PEND_FOREVER);

        /*
        ** Performance Log Entry Stamp
        */
        CFE_ES_PerfLogEntry(HAL_MPU_PERF_ID);

        if (status == CFE_SUCCESS)
        {
            HAL_MPU_TaskPipe(SBBufPtr);
        }
        else
        {
            CFE_EVS_SendEvent(HAL_MPU_PIPE_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "SAMPLE APP: SB Pipe Read Error, App Will Exit");

            HAL_MPU_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /*
    ** Performance Log Exit Stamp
    */
    CFE_ES_PerfLogExit(HAL_MPU_PERF_ID);

    CFE_ES_ExitApp(HAL_MPU_Data.RunStatus);
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  */
/*                                                                            */
/* Initialization                                                             */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
CFE_Status_t HAL_MPU_Init(void)
{
    CFE_Status_t status;
    char         VersionString[HAL_MPU_CFG_MAX_VERSION_STR_LEN];

    /* Zero out the global data structure */
    memset(&HAL_MPU_Data, 0, sizeof(HAL_MPU_Data));

    HAL_MPU_Data.RunStatus = CFE_ES_RunStatus_APP_RUN;

    /*
    ** Register the events
    */
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("Hal Mpu: Error Registering Events, RC = 0x%08lX\n", (unsigned long)status);
    }
    else
    {
        /*
         ** Initialize housekeeping packet (clear user data area).
         */
        CFE_MSG_Init(CFE_MSG_PTR(HAL_MPU_Data.HkTlm.TelemetryHeader),
                     CFE_SB_ValueToMsgId(HAL_MPU_HK_TLM_MID),
                     sizeof(HAL_MPU_Data.HkTlm));

        /*
         ** Create Software Bus message pipe.
         */
        status = CFE_SB_CreatePipe(&HAL_MPU_Data.CommandPipe,
                                   HAL_MPU_PLATFORM_PIPE_DEPTH,
                                   HAL_MPU_PLATFORM_PIPE_NAME);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MPU_CR_PIPE_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mpu: Error creating SB Command Pipe, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Subscribe to Housekeeping request commands
        */
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_MPU_SEND_HK_MID), HAL_MPU_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MPU_SUB_HK_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mpu: Error Subscribing to HK request, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Subscribe to ground command packets
        */
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_MPU_CMD_MID), HAL_MPU_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MPU_SUB_CMD_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mpu: Error Subscribing to Commands, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Register Example Table(s)
        */
        status = CFE_TBL_Register(&HAL_MPU_Data.TblHandles[0],
                                  "ExampleTable",
                                  sizeof(HAL_MPU_ExampleTable_t),
                                  CFE_TBL_OPT_DEFAULT,
                                  HAL_MPU_TblValidationFunc);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MPU_TABLE_REG_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mpu: Error Registering Example Table, RC = 0x%08lX",
                              (unsigned long)status);
        }
        else
        {
            status = CFE_TBL_Load(HAL_MPU_Data.TblHandles[0], CFE_TBL_SRC_FILE, HAL_MPU_PLATFORM_TABLE_FILE);
        }

        CFE_Config_GetVersionString(VersionString,
                                    HAL_MPU_CFG_MAX_VERSION_STR_LEN,
                                    "Hal Mpu",
                                    HAL_MPU_VERSION,
                                    HAL_MPU_BUILD_CODENAME,
                                    HAL_MPU_LAST_OFFICIAL);

        CFE_EVS_SendEvent(HAL_MPU_INIT_INF_EID,
                          CFE_EVS_EventType_INFORMATION,
                          "Hal Mpu Initialized.%s",
                          VersionString);
    }

/* @studio.begin app.subscribe 2ba2e87db4fa0afd */

    /* Attach the mission readers after the sample has initialized its tables. */
    if (status == CFE_SUCCESS)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_MPU_WAKEUP_MID), HAL_MPU_Data.CommandPipe);
    }
    if (status == CFE_SUCCESS)
    {
        status = HAL_MPU_ComponentsInit();
    }
/* @studio.end app.subscribe */
    return status;
}
