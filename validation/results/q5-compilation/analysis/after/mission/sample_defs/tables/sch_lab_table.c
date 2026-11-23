/************************************************************************
 * NASA Docket No. GSC-18,719-1, and identified as “core Flight System: Bootes”
 *
 * Copyright (c) 2020 United States Government as represented by the
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

#include "cfe_tbl_filedef.h" /* Required to obtain the CFE_TBL_FILEDEF macro definition */
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SCH_LAB))
#include "sch_lab_tbl.h"
#endif
#include "cfe_sb.h" /* Required to use the CFE_SB_MSGID_WRAP_VALUE macro */

/*
** Include headers for message IDs here
*/
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CI_LAB))
#include "ci_lab_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_TO_LAB))
#include "to_lab_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SAMPLE_APP))
#include "sample_app_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
#include "cf_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_HS))
#include "hs_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_MD))
#include "md_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
#include "fm_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_LC))
#include "lc_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CS))
#include "cs_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SC))
#include "sc_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_DS))
#include "ds_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_HK))
#include "hk_msgids.h"
#endif

#ifdef CFS_SBN_ENABLED
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
#include "sbn_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
#include "sbn_msgdefs.h"
#endif
#endif

/*
** SCH Lab schedule table
** When populating this table:
**  1. The entire table is processed (SCH_LAB_MAX_SCHEDULE_ENTRIES) but entries with a
**     packet rate of 0 are skipped
**  2. You can have commented out entries or entries with a packet rate of 0
**  3. If the table grows too big, increase SCH_LAB_MAX_SCHEDULE_ENTRIES
*/

#ifdef APPGEN_ENABLED
#include "appgen_includes.h"
#endif

/* clang-format: off */
SCH_LAB_ScheduleTable_t SCH_TBL_Structure =
{
    .TickRate = 10,
    .Config   = {
#ifdef APPGEN_ENABLED
#include "appgen_schedule.inc"
#endif
        {CFE_SB_MSGID_WRAP_VALUE(CFE_ES_SEND_HK_MID),     40, 0}, /* every 4.0 seconds */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_EVS_SEND_HK_MID),    42, 0}, /* every 4.2 seconds */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_TIME_SEND_HK_MID),   44, 0}, /* every 4.4 seconds */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_SB_SEND_HK_MID),     46, 0}, /* every 4.6 seconds */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_TBL_SEND_HK_MID),    48, 0}, /* every 4.8 seconds */
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CI_LAB))
        {CFE_SB_MSGID_WRAP_VALUE(CI_LAB_SEND_HK_MID),     50, 0}, /* every 5.0 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_TO_LAB))
        {CFE_SB_MSGID_WRAP_VALUE(TO_LAB_SEND_HK_MID),     52, 0}, /* every 5.2 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SAMPLE_APP))
        {CFE_SB_MSGID_WRAP_VALUE(SAMPLE_APP_SEND_HK_MID), 54, 0}, /* every 5.4 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
        {CFE_SB_MSGID_WRAP_VALUE(CF_SEND_HK_MID),         56, 0}, /* every 5.6 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
        {CFE_SB_MSGID_WRAP_VALUE(CF_WAKE_UP_MID),         1,  0}, /* every 0.1 seconds (example of 10 Hz packet) */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_MD))
        {CFE_SB_MSGID_WRAP_VALUE(MD_SEND_HK_MID),         58, 0}, /* every 5.8 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_HS))
        {CFE_SB_MSGID_WRAP_VALUE(HS_SEND_HK_MID),         60, 0}, /* every 6.0 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SC))
        {CFE_SB_MSGID_WRAP_VALUE(SC_SEND_HK_MID),          62, 0}, /* every 6.2 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SC))
        {CFE_SB_MSGID_WRAP_VALUE(SC_WAKEUP_MID),           10, 0}, /* every 1.0 seconds (example of 1 Hz packet) */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
        {CFE_SB_MSGID_WRAP_VALUE(FM_SEND_HK_MID),          66, 0}, /* every 6.6 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_DS))
        {CFE_SB_MSGID_WRAP_VALUE(DS_SEND_HK_MID),          68, 0}, /* every 6.8 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_LC))
        {CFE_SB_MSGID_WRAP_VALUE(LC_SEND_HK_MID),          70, 0}, /* every 7.0 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CS))
        {CFE_SB_MSGID_WRAP_VALUE(CS_SEND_HK_MID),          72, 0}, /* every 7.1 seconds */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CS))
        {CFE_SB_MSGID_WRAP_VALUE(CS_BACKGROUND_CYCLE_MID), 5,  0}, /* every 0.5 seconds (example of 2 Hz packet) */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_HK))
        {CFE_SB_MSGID_WRAP_VALUE(HK_SEND_HK_MID),          76, 0}, /* every 7.6 seconds */
#endif
#ifdef CFS_SBN_ENABLED
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_CMD_MID),             46, SBN_HK_CC}, /* every 4.6 seconds (matching the SB) */
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_CMD_MID),             2, SBN_SCH_WAKEUP_CC}, /* every 0.2 seconds */
#endif
#endif
    }
};

/*
** The macro below identifies:
**    1) the data structure type to use as the table image format
**    2) the name of the table to be placed into the cFE Table File Header
**    3) a brief description of the contents of the file image
**    4) the desired name of the table image binary file that is cFE compatible
*/
CFE_TBL_FILEDEF(SCH_TBL_Structure, SCH_LAB.Schedule, Schedule Lab MsgID Table, sch_lab_table.tbl)
