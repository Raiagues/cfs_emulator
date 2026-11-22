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
 *   This file contains the prototypes for the Hal Temp Ground Command-handling functions
 */

#ifndef HAL_TEMP_CMDS_H
#define HAL_TEMP_CMDS_H

/*
** Required header files.
*/
#include "cfe_error.h"
#include "hal_temp_msg.h"

CFE_Status_t HAL_TEMP_SendHkCmd(const HAL_TEMP_SendHkCmd_t *Msg);
CFE_Status_t HAL_TEMP_NoopCmd(const HAL_TEMP_NoopCmd_t *Msg);
CFE_Status_t HAL_TEMP_ResetCountersCmd(const HAL_TEMP_ResetCountersCmd_t *Msg);
CFE_Status_t HAL_TEMP_ProcessCmd(const HAL_TEMP_ProcessCmd_t *Msg);
CFE_Status_t HAL_TEMP_DisplayParamCmd(const HAL_TEMP_DisplayParamCmd_t *Msg);

#endif /* HAL_TEMP_CMDS_H */
