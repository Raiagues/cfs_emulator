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
 * Auto-Generated stub implementations for functions defined in hal_mpu_cmds header
 */

#include "hal_mpu_cmds.h"
#include "utgenstub.h"

/*
 * ----------------------------------------------------
 * Generated stub function for HAL_MPU_DisplayParamCmd()
 * ----------------------------------------------------
 */
CFE_Status_t HAL_MPU_DisplayParamCmd(const HAL_MPU_DisplayParamCmd_t *Msg)
{
    UT_GenStub_SetupReturnBuffer(HAL_MPU_DisplayParamCmd, CFE_Status_t);

    UT_GenStub_AddParam(HAL_MPU_DisplayParamCmd, const HAL_MPU_DisplayParamCmd_t *, Msg);

    UT_GenStub_Execute(HAL_MPU_DisplayParamCmd, Basic, NULL);

    return UT_GenStub_GetReturnValue(HAL_MPU_DisplayParamCmd, CFE_Status_t);
}

/*
 * ----------------------------------------------------
 * Generated stub function for HAL_MPU_NoopCmd()
 * ----------------------------------------------------
 */
CFE_Status_t HAL_MPU_NoopCmd(const HAL_MPU_NoopCmd_t *Msg)
{
    UT_GenStub_SetupReturnBuffer(HAL_MPU_NoopCmd, CFE_Status_t);

    UT_GenStub_AddParam(HAL_MPU_NoopCmd, const HAL_MPU_NoopCmd_t *, Msg);

    UT_GenStub_Execute(HAL_MPU_NoopCmd, Basic, NULL);

    return UT_GenStub_GetReturnValue(HAL_MPU_NoopCmd, CFE_Status_t);
}

/*
 * ----------------------------------------------------
 * Generated stub function for HAL_MPU_ProcessCmd()
 * ----------------------------------------------------
 */
CFE_Status_t HAL_MPU_ProcessCmd(const HAL_MPU_ProcessCmd_t *Msg)
{
    UT_GenStub_SetupReturnBuffer(HAL_MPU_ProcessCmd, CFE_Status_t);

    UT_GenStub_AddParam(HAL_MPU_ProcessCmd, const HAL_MPU_ProcessCmd_t *, Msg);

    UT_GenStub_Execute(HAL_MPU_ProcessCmd, Basic, NULL);

    return UT_GenStub_GetReturnValue(HAL_MPU_ProcessCmd, CFE_Status_t);
}

/*
 * ----------------------------------------------------
 * Generated stub function for HAL_MPU_ResetCountersCmd()
 * ----------------------------------------------------
 */
CFE_Status_t HAL_MPU_ResetCountersCmd(const HAL_MPU_ResetCountersCmd_t *Msg)
{
    UT_GenStub_SetupReturnBuffer(HAL_MPU_ResetCountersCmd, CFE_Status_t);

    UT_GenStub_AddParam(HAL_MPU_ResetCountersCmd, const HAL_MPU_ResetCountersCmd_t *, Msg);

    UT_GenStub_Execute(HAL_MPU_ResetCountersCmd, Basic, NULL);

    return UT_GenStub_GetReturnValue(HAL_MPU_ResetCountersCmd, CFE_Status_t);
}

/*
 * ----------------------------------------------------
 * Generated stub function for HAL_MPU_SendHkCmd()
 * ----------------------------------------------------
 */
CFE_Status_t HAL_MPU_SendHkCmd(const HAL_MPU_SendHkCmd_t *Msg)
{
    UT_GenStub_SetupReturnBuffer(HAL_MPU_SendHkCmd, CFE_Status_t);

    UT_GenStub_AddParam(HAL_MPU_SendHkCmd, const HAL_MPU_SendHkCmd_t *, Msg);

    UT_GenStub_Execute(HAL_MPU_SendHkCmd, Basic, NULL);

    return UT_GenStub_GetReturnValue(HAL_MPU_SendHkCmd, CFE_Status_t);
}
