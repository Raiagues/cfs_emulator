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

/**
 * \file
 *  Define TO Lab CPU specific subscription table
 */

#include "cfe_tbl_filedef.h" /* Required to obtain the CFE_TBL_FILEDEF macro definition */
#include "cfe_sb_api_typedefs.h"
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_TO_LAB))
#include "to_lab_tbl.h"
#endif

/*
** Add the proper include file for the message IDs below
*/

/*
** Common CFS app includes below are commented out
*/
#include "cfe_msgids.h"
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_TO_LAB))
#include "to_lab_msgids.h"
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CI_LAB))
#include "ci_lab_msgids.h"
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
#endif

#ifdef APPGEN_ENABLED
#include "appgen_includes.h"
#endif

/* clang-format: off */
TO_LAB_Subs_t TO_LAB_Subs =
{
    .Subs = {
#ifdef APPGEN_ENABLED
#include "appgen_telemetry.inc"
#endif
        /* CFS App Subscriptions */
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_TO_LAB))
        {CFE_SB_MSGID_WRAP_VALUE(TO_LAB_HK_TLM_MID),          {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_TO_LAB))
        {CFE_SB_MSGID_WRAP_VALUE(TO_LAB_DATA_TYPES_MID),      {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CI_LAB))
        {CFE_SB_MSGID_WRAP_VALUE(CI_LAB_HK_TLM_MID),          {0, 0}, 1},
#endif

        /* cFE Core subscriptions */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_ES_HK_TLM_MID),          {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_EVS_HK_TLM_MID),         {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_SB_HK_TLM_MID),          {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_TBL_HK_TLM_MID),         {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_TIME_HK_TLM_MID),        {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_TIME_DIAG_TLM_MID),      {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_SB_STATS_TLM_MID),       {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_TBL_REG_TLM_MID),        {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_EVS_LONG_EVENT_MSG_MID), {0, 0}, 16},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_ES_APP_TLM_MID),         {0, 0}, 1},
        {CFE_SB_MSGID_WRAP_VALUE(CFE_ES_MEMSTATS_TLM_MID),    {0, 0}, 1},

        /* Other CFS apps */
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SAMPLE_APP))
        {CFE_SB_MSGID_WRAP_VALUE(SAMPLE_APP_HK_TLM_MID), {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
        {CFE_SB_MSGID_WRAP_VALUE(CF_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
        {CFE_SB_MSGID_WRAP_VALUE(CF_EOT_TLM_MID),        {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
        {CFE_SB_MSGID_WRAP_VALUE(CF_CH0_TX_MID),        {0, 0}, 5},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CF))
        {CFE_SB_MSGID_WRAP_VALUE(CF_CH1_TX_MID),        {0, 0}, 5},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_MD))
        {CFE_SB_MSGID_WRAP_VALUE(MD_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_HS))
        {CFE_SB_MSGID_WRAP_VALUE(HS_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_HK))
        {CFE_SB_MSGID_WRAP_VALUE(HK_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SC))
        {CFE_SB_MSGID_WRAP_VALUE(SC_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
        {CFE_SB_MSGID_WRAP_VALUE(FM_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
        {CFE_SB_MSGID_WRAP_VALUE(FM_FILE_INFO_TLM_MID),  {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
        {CFE_SB_MSGID_WRAP_VALUE(FM_DIR_LIST_TLM_MID),   {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
        {CFE_SB_MSGID_WRAP_VALUE(FM_OPEN_FILES_TLM_MID), {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_FM))
        {CFE_SB_MSGID_WRAP_VALUE(FM_MONITOR_TLM_MID),    {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_DS))
        {CFE_SB_MSGID_WRAP_VALUE(DS_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_LC))
        {CFE_SB_MSGID_WRAP_VALUE(LC_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_CS))
        {CFE_SB_MSGID_WRAP_VALUE(CS_HK_TLM_MID),         {0, 0}, 1},
#endif
#ifdef CFS_SBN_ENABLED
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_HK_TLM_MID),         {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_HKNET_TLM_MID),      {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_HKPEER_TLM_MID),     {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_HKMYSUBS_TLM_MID),   {0, 0}, 1},
#endif
#if !defined(CFS_CPU1_MODULE_SELECTION) || (defined(CFS_MODULE_SBN))
        {CFE_SB_MSGID_WRAP_VALUE(SBN_HKPEERSUBS_TLM_MID), {0, 0}, 1},
#endif
#endif
        /* TO_UNUSED entry to mark the end of valid MsgIds */
        {CFE_SB_MSGID_RESERVED, {0, 0}, 0}
    }
};

CFE_TBL_FILEDEF(TO_LAB_Subs, TO_LAB.Subscriptions, TO Lab Sub Tbl, to_lab_sub.tbl)
