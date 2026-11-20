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
 *   Specification for the HAL_TEMP command function codes
 *
 * @note
 *   This file should be strictly limited to the command/function code (CC)
 *   macro definitions.  Other definitions such as enums, typedefs, or other
 *   macros should be placed in the msgdefs.h or msg.h files.
 */
#ifndef HAL_TEMP_FCNCODES_H
#define HAL_TEMP_FCNCODES_H

#include "hal_temp_fcncode_values.h"

/************************************************************************
 * Macro Definitions
 ************************************************************************/

/*
** Hal Temp command codes
*/
#define HAL_TEMP_NOOP_CC           HAL_TEMP_CCVAL(NOOP)
#define HAL_TEMP_RESET_COUNTERS_CC HAL_TEMP_CCVAL(RESET_COUNTERS)
#define HAL_TEMP_PROCESS_CC        HAL_TEMP_CCVAL(PROCESS)
#define HAL_TEMP_DISPLAY_PARAM_CC  HAL_TEMP_CCVAL(DISPLAY_PARAM)

/* @studio.begin command.codes 01ba4719c80b6fe9 */

/* @studio.end command.codes */
#endif
