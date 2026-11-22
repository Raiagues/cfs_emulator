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
 *   This file contains the source code for the Hal Mag.
 */

/*
** Include Files:
*/
/* @studio.begin app.includes 3fe07b6aea0f187f */
#include "hal_mag_components.h"
/* @studio.end app.includes */
#include "hal_mag.h"
#include "hal_mag_cmds.h"
#include "hal_mag_utils.h"
#include "hal_mag_eventids.h"
#include "hal_mag_dispatch.h"
#include "hal_mag_tbl.h"
#include "hal_mag_version.h"

/*
** global data
*/
HAL_MAG_Data_t HAL_MAG_Data;

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  * *  * * * * **/
/*                                                                            */
/* Application entry point and main process loop                              */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  * *  * * * * **/
void HAL_MAG_Main(void)
{
    CFE_Status_t     status;
    CFE_SB_Buffer_t *SBBufPtr;

    /*
    ** Create the first Performance Log entry
    */
    CFE_ES_PerfLogEntry(HAL_MAG_PERF_ID);

    /*
    ** Perform application-specific initialization
    ** If the Initialization fails, set the RunStatus to
    ** CFE_ES_RunStatus_APP_ERROR and the App will not enter the RunLoop
    */
    status = HAL_MAG_Init();
    if (status != CFE_SUCCESS)
    {
        HAL_MAG_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    }

    /*
    ** Hal Mag Runloop
    */
    while (CFE_ES_RunLoop(&HAL_MAG_Data.RunStatus) == true)
    {
        /*
        ** Performance Log Exit Stamp
        */
        CFE_ES_PerfLogExit(HAL_MAG_PERF_ID);

        /* Pend on receipt of command packet */
        status = CFE_SB_ReceiveBuffer(&SBBufPtr, HAL_MAG_Data.CommandPipe, CFE_SB_PEND_FOREVER);

        /*
        ** Performance Log Entry Stamp
        */
        CFE_ES_PerfLogEntry(HAL_MAG_PERF_ID);

        if (status == CFE_SUCCESS)
        {
            HAL_MAG_TaskPipe(SBBufPtr);
        }
        else
        {
            CFE_EVS_SendEvent(HAL_MAG_PIPE_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "SAMPLE APP: SB Pipe Read Error, App Will Exit");

            HAL_MAG_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /*
    ** Performance Log Exit Stamp
    */
    CFE_ES_PerfLogExit(HAL_MAG_PERF_ID);

    CFE_ES_ExitApp(HAL_MAG_Data.RunStatus);
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *  */
/*                                                                            */
/* Initialization                                                             */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
CFE_Status_t HAL_MAG_Init(void)
{
    CFE_Status_t status;
    char         VersionString[HAL_MAG_CFG_MAX_VERSION_STR_LEN];

    /* Zero out the global data structure */
    memset(&HAL_MAG_Data, 0, sizeof(HAL_MAG_Data));

    HAL_MAG_Data.RunStatus = CFE_ES_RunStatus_APP_RUN;

    /*
    ** Register the events
    */
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("Hal Mag: Error Registering Events, RC = 0x%08lX\n", (unsigned long)status);
    }
    else
    {
        /*
         ** Initialize housekeeping packet (clear user data area).
         */
        CFE_MSG_Init(CFE_MSG_PTR(HAL_MAG_Data.HkTlm.TelemetryHeader),
                     CFE_SB_ValueToMsgId(HAL_MAG_HK_TLM_MID),
                     sizeof(HAL_MAG_Data.HkTlm));

        /*
         ** Create Software Bus message pipe.
         */
        status = CFE_SB_CreatePipe(&HAL_MAG_Data.CommandPipe,
                                   HAL_MAG_PLATFORM_PIPE_DEPTH,
                                   HAL_MAG_PLATFORM_PIPE_NAME);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MAG_CR_PIPE_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mag: Error creating SB Command Pipe, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Subscribe to Housekeeping request commands
        */
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_MAG_SEND_HK_MID), HAL_MAG_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MAG_SUB_HK_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mag: Error Subscribing to HK request, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Subscribe to ground command packets
        */
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_MAG_CMD_MID), HAL_MAG_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MAG_SUB_CMD_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mag: Error Subscribing to Commands, RC = 0x%08lX",
                              (unsigned long)status);
        }
    }

    if (status == CFE_SUCCESS)
    {
        /*
        ** Register Example Table(s)
        */
        status = CFE_TBL_Register(&HAL_MAG_Data.TblHandles[0],
                                  "ExampleTable",
                                  sizeof(HAL_MAG_ExampleTable_t),
                                  CFE_TBL_OPT_DEFAULT,
                                  HAL_MAG_TblValidationFunc);
        if (status != CFE_SUCCESS)
        {
            CFE_EVS_SendEvent(HAL_MAG_TABLE_REG_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Hal Mag: Error Registering Example Table, RC = 0x%08lX",
                              (unsigned long)status);
        }
        else
        {
            status = CFE_TBL_Load(HAL_MAG_Data.TblHandles[0], CFE_TBL_SRC_FILE, HAL_MAG_PLATFORM_TABLE_FILE);
        }

        CFE_Config_GetVersionString(VersionString,
                                    HAL_MAG_CFG_MAX_VERSION_STR_LEN,
                                    "Hal Mag",
                                    HAL_MAG_VERSION,
                                    HAL_MAG_BUILD_CODENAME,
                                    HAL_MAG_LAST_OFFICIAL);

        CFE_EVS_SendEvent(HAL_MAG_INIT_INF_EID,
                          CFE_EVS_EventType_INFORMATION,
                          "Hal Mag Initialized.%s",
                          VersionString);
    }

/* @studio.begin app.subscribe 2d60fa83a6b73445 */

    /* Attach the mission readers after the sample has initialized its tables. */
    if (status == CFE_SUCCESS)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(HAL_MAG_WAKEUP_MID), HAL_MAG_Data.CommandPipe);
    }
    if (status == CFE_SUCCESS)
    {
        status = HAL_MAG_ComponentsInit();
    }
/* @studio.end app.subscribe */
    return status;
}
