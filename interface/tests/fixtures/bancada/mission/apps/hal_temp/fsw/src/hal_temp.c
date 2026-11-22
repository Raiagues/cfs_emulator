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
 *   This file contains the source code for the Hal Temp.
 */

/*
** Include Files:
*/
/* @studio.begin app.includes a7662aafd3269228 */
#include "hal_temp_components.h"
/* @studio.end app.includes */
#include "hal_temp.h"
#include "hal_temp_cmds.h"
#include "hal_temp_utils.h"
#include "hal_temp_eventids.h"
#include "hal_temp_dispatch.h"
#include "hal_temp_tbl.h"
#include "hal_temp_version.h"

/*
** global data
*/
HAL_TEMP_Data_t HAL_TEMP_Data;

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  * *  * * * * **/
/*                                                                            */
/* Application entry point and main process loop                              */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  * *  * * * * **/
void HAL_TEMP_Main(void)
{
    CFE_Status_t     status;
    CFE_SB_Buffer_t *SBBufPtr;

    /*
    ** Create the first Performance Log entry
    */
    CFE_ES_PerfLogEntry(HAL_TEMP_PERF_ID);

    /*
    ** Perform application-specific initialization
    ** If the Initialization fails, set the RunStatus to
    ** CFE_ES_RunStatus_APP_ERROR and the App will not enter the RunLoop
    */
    status = HAL_TEMP_Init();
    if (status != CFE_SUCCESS)
    {
        HAL_TEMP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    }

    /*
    ** Hal Temp Runloop
    */
    while (CFE_ES_RunLoop(&HAL_TEMP_Data.RunStatus) == true)
    {
        /*
        ** Performance Log Exit Stamp
        */
        CFE_ES_PerfLogExit(HAL_TEMP_PERF_ID);

        /* Pend on receipt of command packet */
        status = CFE_SB_ReceiveBuffer(&SBBufPtr, HAL_TEMP_Data.CommandPipe, CFE_SB_PEND_FOREVER);

        /*
        ** Performance Log Entry Stamp
        */
        CFE_ES_PerfLogEntry(HAL_TEMP_PERF_ID);

        if (status == CFE_SUCCESS)
        {
            HAL_TEMP_TaskPipe(SBBufPtr);
        }
        else
        {
            CFE_EVS_SendEvent(HAL_TEMP_PIPE_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "SAMPLE APP: SB Pipe Read Error, App Will Exit");

            HAL_TEMP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /*
    ** Performance Log Exit Stamp
    */
    CFE_ES_PerfLogExit(HAL_TEMP_PERF_ID);

    CFE_ES_ExitApp(HAL_TEMP_Data.RunStatus);
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  */
/*                                                                            */
/* Initialization                                                             */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
CFE_Status_t HAL_TEMP_Init(void)
{
    CFE_Status_t status;
    char         VersionString[HAL_TEMP_CFG_MAX_VERSION_STR_LEN];

    /* Zero out the global data structure */
    memset(&HAL_TEMP_Data, 0, sizeof(HAL_TEMP_Data));

    HAL_TEMP_Data.RunStatus = CFE_ES_RunStatus_APP_RUN;

    /*
    ** Register the events
    */
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("Hal Temp: Error Registering Events, RC = 0x%08lX\n", (unsigned long)status);
    }
    else
    {
        /*
         ** Initialize housekeeping packet (clear user data area).
         */
        CFE_MSG_Init(CFE_MSG_PTR(HAL_TEMP_Data.HkTlm.TelemetryHeader),
                     CFE_SB_ValueToMsgId(HAL_TEMP_HK_TLM_MID),
                     sizeof(HAL_TEMP_Data.HkTlm));

        /*
         ** Create Software Bus message pipe.
         */
        status = CFE_SB_CreatePipe(&HAL_TEMP_Data.CommandPipe,
                                   HAL_TEMP_PLATFORM_PIPE_DEPTH,
                                   HAL_TEMP_PLATFORM_PIPE_NAME);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_TEMP_CR_PIPE_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Temp: Error creating SB Command Pipe, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Subscribe to Housekeeping request commands
        */
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_TEMP_SEND_HK_MID), HAL_TEMP_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_TEMP_SUB_HK_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Temp: Error Subscribing to HK request, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Subscribe to ground command packets
        */
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_TEMP_CMD_MID), HAL_TEMP_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_TEMP_SUB_CMD_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Temp: Error Subscribing to Commands, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Register Example Table(s)
        */
        status = CFE_TBL_Register(&HAL_TEMP_Data.TblHandles[0],
                                  "ExampleTable",
                                  sizeof(HAL_TEMP_ExampleTable_t),
                                  CFE_TBL_OPT_DEFAULT,
                                  HAL_TEMP_TblValidationFunc);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_TEMP_TABLE_REG_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Temp: Error Registering Example Table, RC = 0x%08lX",
                              (unsigned long)status);
        }
        else
        {
            status = CFE_TBL_Load(HAL_TEMP_Data.TblHandles[0], CFE_TBL_SRC_FILE, HAL_TEMP_PLATFORM_TABLE_FILE);
        }

        CFE_Config_GetVersionString(VersionString,
                                    HAL_TEMP_CFG_MAX_VERSION_STR_LEN,
                                    "Hal Temp",
                                    HAL_TEMP_VERSION,
                                    HAL_TEMP_BUILD_CODENAME,
                                    HAL_TEMP_LAST_OFFICIAL);

        CFE_EVS_SendEvent(HAL_TEMP_INIT_INF_EID,
                          CFE_EVS_EventType_INFORMATION,
                          "Hal Temp Initialized.%s",
                          VersionString);
    }

/* @studio.begin app.subscribe 1465fb9ce17505f0 */

    /* Attach the mission readers after the sample has initialized its tables. */
    if (status == CFE_SUCCESS)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_TEMP_WAKEUP_MID), HAL_TEMP_Data.CommandPipe);
    }
    if (status == CFE_SUCCESS)
    {
        status = HAL_TEMP_ComponentsInit();
    }
/* @studio.end app.subscribe */
    return status;
}
