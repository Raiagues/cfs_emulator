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
 * Define Hal Mag Events IDs
 */

#ifndef HAL_MAG_EVENTS_H
#define HAL_MAG_EVENTS_H

#define HAL_MAG_RESERVED_EID      0
#define HAL_MAG_INIT_INF_EID      1
#define HAL_MAG_CC_ERR_EID        2
#define HAL_MAG_NOOP_INF_EID      3
#define HAL_MAG_RESET_INF_EID     4
#define HAL_MAG_MID_ERR_EID       5
#define HAL_MAG_CMD_LEN_ERR_EID   6
#define HAL_MAG_PIPE_ERR_EID      7
#define HAL_MAG_VALUE_INF_EID     8
#define HAL_MAG_CR_PIPE_ERR_EID   9
#define HAL_MAG_SUB_HK_ERR_EID    10
#define HAL_MAG_SUB_CMD_ERR_EID   11
#define HAL_MAG_TABLE_REG_ERR_EID 12

/* @studio.begin sensor.events fd36abd32e0c7914 */
#define HAL_MAG_SENSOR_READ_ERR_EID 13
#define HAL_MAG_SENSOR_VALUE_INF_EID 14

/* @studio.end sensor.events */
#endif /* HAL_MAG_EVENTS_H */
