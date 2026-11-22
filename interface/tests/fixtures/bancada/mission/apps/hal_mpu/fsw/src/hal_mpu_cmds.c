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
 *   This file contains the source code for the Hal Mpu Ground Command-handling functions
 */

/*
** Include Files:
*/
#include "hal_mpu.h"
#include "hal_mpu_cmds.h"
#include "hal_mpu_msgids.h"
#include "hal_mpu_eventids.h"
#include "hal_mpu_version.h"
#include "hal_mpu_tbl.h"
#include "hal_mpu_utils.h"
#include "hal_mpu_msg.h"

/* The sample_lib module provides the SAMPLE_Function() prototype */
#include "sample_lib.h"

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/*  Purpose:                                                                  */
/*         This function is triggered in response to a task telemetry request */
/*         from the housekeeping task. This function will gather the Apps     */
/*         telemetry, packetize it and send it to the housekeeping task via   */
/*         the software bus                                                   */
/* * * * * * * * * * * * * * * * * * * * * * * *  * * * * * * *  * *  * * * * */
CFE_Status_t HAL_MPU_SendHkCmd(const HAL_MPU_SendHkCmd_t *Msg)
{
    int i;

    /*
    ** Get command execution counters...
    */
    HAL_MPU_Data.HkTlm.Payload.CommandErrorCounter = HAL_MPU_Data.CommandErrorCounter;
    HAL_MPU_Data.HkTlm.Payload.CommandCounter      = HAL_MPU_Data.CommandCounter;

    /*
    ** Send housekeeping telemetry packet...
    */
    CFE_SB_TimeStampMsg(CFE_MSG_PTR(HAL_MPU_Data.HkTlm.TelemetryHeader));
    CFE_SB_TransmitMsg(CFE_MSG_PTR(HAL_MPU_Data.HkTlm.TelemetryHeader), true);

    /*
    ** Manage any pending table loads, validations, etc.
    */
    for (i = 0; i < HAL_MPU_PLATFORM_NUMBER_OF_TABLES; i++)
    {
        CFE_TBL_Manage(HAL_MPU_Data.TblHandles[i]);
    }

    return CFE_SUCCESS;
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/* SAMPLE NOOP commands                                                       */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
CFE_Status_t HAL_MPU_NoopCmd(const HAL_MPU_NoopCmd_t *Msg)
{
    HAL_MPU_Data.CommandCounter++;

    CFE_EVS_SendEvent(HAL_MPU_NOOP_INF_EID,
                      CFE_EVS_EventType_INFORMATION,
                      "SAMPLE: NOOP command %s",
                      HAL_MPU_VERSION);

    return CFE_SUCCESS;
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/*  Purpose:                                                                  */
/*         This function resets all the global counter variables that are     */
/*         part of the task telemetry.                                        */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * *  * * * * * * *  * *  * * * * */
CFE_Status_t HAL_MPU_ResetCountersCmd(const HAL_MPU_ResetCountersCmd_t *Msg)
{
    HAL_MPU_Data.CommandCounter      = 0;
    HAL_MPU_Data.CommandErrorCounter = 0;

    CFE_EVS_SendEvent(HAL_MPU_RESET_INF_EID, CFE_EVS_EventType_INFORMATION, "SAMPLE: RESET command");

    return CFE_SUCCESS;
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/*  Purpose:                                                                  */
/*         This function Process Ground Station Command                       */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * *  * * * * * * *  * *  * * * * */
CFE_Status_t HAL_MPU_ProcessCmd(const HAL_MPU_ProcessCmd_t *Msg)
{
    CFE_Status_t               Status;
    void                      *TblAddr;
    HAL_MPU_ExampleTable_t *TblPtr;
    const char                *TableName = "HAL_MPU.ExampleTable";

    /* Sample Use of Example Table */
    HAL_MPU_Data.CommandCounter++;
    Status = CFE_TBL_GetAddress(&TblAddr, HAL_MPU_Data.TblHandles[0]);
    if (Status < CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("Hal Mpu: Fail to get table address: 0x%08lx", (unsigned long)Status);
    }
    else
    {
        TblPtr = TblAddr;
        CFE_ES_WriteToSysLog("Hal Mpu: Example Table Value 1: %d  Value 2: %d", TblPtr->Int1, TblPtr->Int2);

        HAL_MPU_GetCrc(TableName);

        Status = CFE_TBL_ReleaseAddress(HAL_MPU_Data.TblHandles[0]);
        if (Status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("Hal Mpu: Fail to release table address: 0x%08lx", (unsigned long)Status);
        }
        else
        {
            /* Invoke a function provided by HAL_MPU_LIB */
            SAMPLE_LIB_Function();
        }
    }

    return Status;
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/* A simple example command that displays a passed-in value                   */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
CFE_Status_t HAL_MPU_DisplayParamCmd(const HAL_MPU_DisplayParamCmd_t *Msg)
{
    HAL_MPU_Data.CommandCounter++;
    CFE_EVS_SendEvent(HAL_MPU_VALUE_INF_EID,
                      CFE_EVS_EventType_INFORMATION,
                      "HAL_MPU: ValU32=%lu, ValI16=%d, ValStr=%s",
                      (unsigned long)Msg->Payload.ValU32,
                      (int)Msg->Payload.ValI16,
                      Msg->Payload.ValStr);

    return CFE_SUCCESS;
}
