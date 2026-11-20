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
 * Common definitions for all hal_mpu coverage tests
 */

#ifndef HAL_MPU_COVERAGETEST_COMMON_H
#define HAL_MPU_COVERAGETEST_COMMON_H

/*
 * Includes
 */

#include "utassert.h"
#include "uttest.h"
#include "utstubs.h"

#include "setup.h"
#include "eventcheck.h"

#include "cfe.h"
#include "hal_mpu_eventids.h"
#include "hal_mpu.h"
#include "hal_mpu_dispatch.h"
#include "hal_mpu_cmds.h"
#include "hal_mpu_utils.h"
#include "hal_mpu_msgids.h"
#include "hal_mpu_msg.h"
#include "hal_mpu_tbl.h"

/*
 * Macro to add a test case to the list of tests to execute
 */
#define ADD_TEST(test) UtTest_Add((Test_##test), Sample_UT_Setup, Sample_UT_TearDown, #test)

#endif /* HAL_MPU_COVERAGETEST_COMMON_H */
