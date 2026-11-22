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
/* @studio.begin dispatch.includes 5c52d5ca36cdeb1e */
#include "hal_mpu_components.h"

/* @studio.end dispatch.includes */
#include "hal_mpu.h"
#include "hal_mpu_dispatch.h"
#include "hal_mpu_cmds.h"
#include "hal_mpu_eventids.h"
#include "hal_mpu_msgids.h"
#include "hal_mpu_msg.h"

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/* Verify command packet length                                               */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
bool HAL_MPU_VerifyCmdLength(const CFE_MSG_Message_t *MsgPtr, size_t ExpectedLength)
{
    bool              result       = true;
    size_t            ActualLength = 0;
    CFE_SB_MsgId_t    MsgId        = CFE_SB_INVALID_MSG_ID;
    CFE_MSG_FcnCode_t FcnCode      = 0;

    CFE_MSG_GetSize(MsgPtr, &ActualLength);

    /*
    ** Verify the command packet length.
    */
    if (ExpectedLength != ActualLength)
    {
        CFE_MSG_GetMsgId(MsgPtr, &MsgId);
        CFE_MSG_GetFcnCode(MsgPtr, &FcnCode);

        CFE_EVS_SendEvent(HAL_MPU_CMD_LEN_ERR_EID,
                          CFE_EVS_EventType_ERROR,
                          "Invalid Msg length: ID = 0x%X,  CC = %u, Len = %u, Expected = %u",
                          (unsigned int)CFE_SB_MsgIdToValue(MsgId),
                          (unsigned int)FcnCode,
                          (unsigned int)ActualLength,
                          (unsigned int)ExpectedLength);

        result = false;

        HAL_MPU_Data.CommandErrorCounter++;
    }

    return result;
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/* SAMPLE ground commands                                                     */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
void HAL_MPU_ProcessGroundCommand(const CFE_SB_Buffer_t *SBBufPtr)
{
    CFE_MSG_FcnCode_t CommandCode = 0;

    CFE_MSG_GetFcnCode(&SBBufPtr->Msg, &CommandCode);

    /*
    ** Process SAMPLE app ground commands
    */
    switch (CommandCode)
    {
        case HAL_MPU_NOOP_CC:
            if (HAL_MPU_VerifyCmdLength(&SBBufPtr->Msg, sizeof(HAL_MPU_NoopCmd_t)))
            {
                HAL_MPU_NoopCmd((const HAL_MPU_NoopCmd_t *)SBBufPtr);
            }
            break;

        case HAL_MPU_RESET_COUNTERS_CC:
            if (HAL_MPU_VerifyCmdLength(&SBBufPtr->Msg, sizeof(HAL_MPU_ResetCountersCmd_t)))
            {
                HAL_MPU_ResetCountersCmd((const HAL_MPU_ResetCountersCmd_t *)SBBufPtr);
            }
            break;

        case HAL_MPU_PROCESS_CC:
            if (HAL_MPU_VerifyCmdLength(&SBBufPtr->Msg, sizeof(HAL_MPU_ProcessCmd_t)))
            {
                HAL_MPU_ProcessCmd((const HAL_MPU_ProcessCmd_t *)SBBufPtr);
            }
            break;

        case HAL_MPU_DISPLAY_PARAM_CC:
            if (HAL_MPU_VerifyCmdLength(&SBBufPtr->Msg, sizeof(HAL_MPU_DisplayParamCmd_t)))
            {
                HAL_MPU_DisplayParamCmd((const HAL_MPU_DisplayParamCmd_t *)SBBufPtr);
            }
            break;

/* @studio.begin dispatch.commands 01ba4719c80b6fe9 */

/* @studio.end dispatch.commands */
        default:
            CFE_EVS_SendEvent(HAL_MPU_CC_ERR_EID,
                              CFE_EVS_EventType_ERROR,
                              "Invalid ground command code: CC = %d",
                              CommandCode);
            break;
    }
}

/* * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * **/
/*                                                                            */
/*  Purpose:                                                                  */
/*     This routine will process any packet that is received on the SAMPLE    */
/*     command pipe.                                                          */
/*                                                                            */
/* * * * * * * * * * * * * * * * * * * * * * * *  * * * * * * *  * *  * * * * */
void HAL_MPU_TaskPipe(const CFE_SB_Buffer_t *SBBufPtr)
{
    static CFE_SB_MsgId_t CMD_MID     = CFE_SB_MSGID_RESERVED;
    static CFE_SB_MsgId_t SEND_HK_MID = CFE_SB_MSGID_RESERVED;

    CFE_SB_MsgId_t MsgId = CFE_SB_INVALID_MSG_ID;

    /* cache the local MID Values here, this avoids repeat lookups */
    if (!CFE_SB_IsValidMsgId(CMD_MID))
    {
        CMD_MID     = CFE_SB_ValueToMsgId(HAL_MPU_CMD_MID);
        SEND_HK_MID = CFE_SB_ValueToMsgId(HAL_MPU_SEND_HK_MID);
    }

    CFE_MSG_GetMsgId(&SBBufPtr->Msg, &MsgId);

    /* Process all SB messages */
    if (CFE_SB_MsgId_Equal(MsgId, SEND_HK_MID))
    {
        /* Housekeeping request */
        HAL_MPU_SendHkCmd((const HAL_MPU_SendHkCmd_t *)SBBufPtr);
    }
/* @studio.begin dispatch.wakeup 5996dc6ee556ec5d */
    else if (CFE_SB_MsgId_Equal(MsgId, CFE_SB_ValueToMsgId(HAL_MPU_WAKEUP_MID)))
    {
        if (HAL_MPU_VerifyCmdLength(&SBBufPtr->Msg, sizeof(CFE_MSG_CommandHeader_t)))
        {
            HAL_MPU_ComponentsWakeup();
        }
    }
/* @studio.end dispatch.wakeup */
    else if (CFE_SB_MsgId_Equal(MsgId, CMD_MID))
    {
        /* Ground command */
        HAL_MPU_ProcessGroundCommand(SBBufPtr);
    }
    else
    {
        /* Unknown command */
        CFE_EVS_SendEvent(HAL_MPU_MID_ERR_EID,
                          CFE_EVS_EventType_ERROR,
                          "SAMPLE: invalid command packet,MID = 0x%x",
                          (unsigned int)CFE_SB_MsgIdToValue(MsgId));
    }
}
