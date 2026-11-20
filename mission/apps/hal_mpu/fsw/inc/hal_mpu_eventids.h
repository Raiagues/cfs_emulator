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
 * Define Hal Mpu Events IDs
 */

#ifndef HAL_MPU_EVENTS_H
#define HAL_MPU_EVENTS_H

#define HAL_MPU_RESERVED_EID      0
#define HAL_MPU_INIT_INF_EID      1
#define HAL_MPU_CC_ERR_EID        2
#define HAL_MPU_NOOP_INF_EID      3
#define HAL_MPU_RESET_INF_EID     4
#define HAL_MPU_MID_ERR_EID       5
#define HAL_MPU_CMD_LEN_ERR_EID   6
#define HAL_MPU_PIPE_ERR_EID      7
#define HAL_MPU_VALUE_INF_EID     8
#define HAL_MPU_CR_PIPE_ERR_EID   9
#define HAL_MPU_SUB_HK_ERR_EID    10
#define HAL_MPU_SUB_CMD_ERR_EID   11
#define HAL_MPU_TABLE_REG_ERR_EID 12

/* @studio.begin sensor.events d8743d026315289f */
#define HAL_MPU_SENSOR_READ_ERR_EID 13
#define HAL_MPU_SENSOR_VALUE_INF_EID 14

/* @studio.end sensor.events */
#endif /* HAL_MPU_EVENTS_H */
