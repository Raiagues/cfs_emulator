"""Command-to-MID evidence shared by the communication catalog and the architecture view.

The C fixtures follow the dispatch shapes of the NASA apps (sample_app, hs, sbn,
cfe evs, cf, cfe tbl) and of an application with unrelated names. They are not
compiled; catalog.py later asks the compiler for every value named here.
"""
from pathlib import Path
import tempfile
import unittest

from ground_station.c_source import arguments, blank_lexemes, calls, entry_routes, mid_regions
from ground_station.catalog import clean, structures
from ground_station.discovery import command_mappings
from interface.backend.architecture_details import describe_application
from interface.backend.source_index import SourceIndex


ROOT = Path(__file__).resolve().parents[1]

SAMPLE_APP = '''
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } SAMPLE_APP_NoopCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } SAMPLE_APP_ResetCountersCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } SAMPLE_APP_SendHkCmd_t;

CFE_Status_t SAMPLE_APP_NoopCmd(const SAMPLE_APP_NoopCmd_t *Msg) { return CFE_SUCCESS; }
CFE_Status_t SAMPLE_APP_ResetCountersCmd(const SAMPLE_APP_ResetCountersCmd_t *Msg) { return CFE_SUCCESS; }
CFE_Status_t SAMPLE_APP_SendHkCmd(const SAMPLE_APP_SendHkCmd_t *Msg) { return CFE_SUCCESS; }

bool SAMPLE_APP_VerifyCmdLength(const CFE_MSG_Message_t *MsgPtr, size_t ExpectedLength)
{
    bool result = true;
    size_t ActualLength = 0;
    CFE_MSG_GetSize(MsgPtr, &ActualLength);
    if (ExpectedLength != ActualLength)
    {
        result = false;
    }
    return result;
}

void SAMPLE_APP_ProcessGroundCommand(const CFE_SB_Buffer_t *SBBufPtr)
{
    CFE_MSG_FcnCode_t CommandCode = 0;
    CFE_MSG_GetFcnCode(&SBBufPtr->Msg, &CommandCode);
    switch (CommandCode)
    {
        case SAMPLE_APP_NOOP_CC:
            if (SAMPLE_APP_VerifyCmdLength(&SBBufPtr->Msg, sizeof(SAMPLE_APP_NoopCmd_t)))
            {
                SAMPLE_APP_NoopCmd((const SAMPLE_APP_NoopCmd_t *)SBBufPtr);
            }
            break;
        case SAMPLE_APP_RESET_COUNTERS_CC:
            if (SAMPLE_APP_VerifyCmdLength(&SBBufPtr->Msg, sizeof(SAMPLE_APP_ResetCountersCmd_t)))
            {
                SAMPLE_APP_ResetCountersCmd((const SAMPLE_APP_ResetCountersCmd_t *)SBBufPtr);
            }
            break;
        default:
            CFE_EVS_SendEvent(SAMPLE_APP_CC_ERR_EID, CFE_EVS_EventType_ERROR, "Invalid ground command code: CC = %d", CommandCode);
            break;
    }
}

void SAMPLE_APP_TaskPipe(const CFE_SB_Buffer_t *SBBufPtr)
{
    static CFE_SB_MsgId_t CMD_MID     = CFE_SB_MSGID_RESERVED;
    static CFE_SB_MsgId_t SEND_HK_MID = CFE_SB_MSGID_RESERVED;
    CFE_SB_MsgId_t MsgId = CFE_SB_INVALID_MSG_ID;
    if (!CFE_SB_IsValidMsgId(CMD_MID))
    {
        CMD_MID     = CFE_SB_ValueToMsgId(SAMPLE_APP_CMD_MID);
        SEND_HK_MID = CFE_SB_ValueToMsgId(SAMPLE_APP_SEND_HK_MID);
    }
    CFE_MSG_GetMsgId(&SBBufPtr->Msg, &MsgId);
    if (CFE_SB_MsgId_Equal(MsgId, SEND_HK_MID))
    {
        SAMPLE_APP_SendHkCmd((const SAMPLE_APP_SendHkCmd_t *)SBBufPtr);
    }
    else if (CFE_SB_MsgId_Equal(MsgId, CMD_MID))
    {
        SAMPLE_APP_ProcessGroundCommand(SBBufPtr);
    }
    else
    {
        CFE_EVS_SendEvent(SAMPLE_APP_MID_ERR_EID, CFE_EVS_EventType_ERROR, "SAMPLE: invalid command packet,MID = 0x%x", (unsigned int)CFE_SB_MsgIdToValue(MsgId));
    }
}
'''

HS = '''
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } HS_NoopCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } HS_ResetCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } HS_SendHkCmd_t;

void HS_NoopCmd(const HS_NoopCmd_t *BufPtr) { }
void HS_ResetCmd(const HS_ResetCmd_t *BufPtr) { }
void HS_SendHkCmd(const HS_SendHkCmd_t *BufPtr) { }

bool HS_VerifyMsgLength(const CFE_MSG_Message_t *MsgPtr, size_t ExpectedLength)
{
    bool result = true;
    size_t ActualLength = 0;
    CFE_SB_MsgId_t MessageID = CFE_SB_INVALID_MSG_ID;
    CFE_MSG_GetSize(MsgPtr, &ActualLength);
    if (ExpectedLength != ActualLength)
    {
        CFE_MSG_GetMsgId(MsgPtr, &MessageID);
        if (CFE_SB_MsgIdToValue(MessageID) == HS_SEND_HK_MID)
        {
            CFE_EVS_SendEvent(HS_HKREQ_LEN_ERR_EID, CFE_EVS_EventType_ERROR, "Invalid HK request msg length: ID = 0x%08lX", (unsigned long)CFE_SB_MsgIdToValue(MessageID));
        }
        result = false;
    }
    return result;
}

void HS_NoopVerifyDispatch(const CFE_SB_Buffer_t *BufPtr)
{
    if (HS_VerifyMsgLength(&BufPtr->Msg, sizeof(HS_NoopCmd_t)))
    {
        HS_NoopCmd((const HS_NoopCmd_t *)BufPtr);
    }
}

void HS_ResetVerifyDispatch(const CFE_SB_Buffer_t *BufPtr)
{
    if (HS_VerifyMsgLength(&BufPtr->Msg, sizeof(HS_ResetCmd_t)))
    {
        HS_ResetCmd((const HS_ResetCmd_t *)BufPtr);
    }
}

void HS_SendHkVerifyDispatch(const CFE_SB_Buffer_t *BufPtr)
{
    if (HS_VerifyMsgLength(&BufPtr->Msg, sizeof(HS_SendHkCmd_t)))
    {
        HS_SendHkCmd((const HS_SendHkCmd_t *)BufPtr);
    }
}

void HS_AppProcessGroundCmd(const CFE_SB_Buffer_t *BufPtr)
{
    CFE_MSG_FcnCode_t CommandCode = 0;
    CFE_MSG_GetFcnCode(&BufPtr->Msg, &CommandCode);
    switch (CommandCode)
    {
        case HS_NOOP_CC:
            HS_NoopVerifyDispatch(BufPtr);
            break;
        case HS_RESET_CC:
            HS_ResetVerifyDispatch(BufPtr);
            break;
        default:
            break;
    }
}

void HS_AppPipe(const CFE_SB_Buffer_t *BufPtr)
{
    static CFE_SB_MsgId_t CMD_MID = CFE_SB_MSGID_RESERVED;
    static CFE_SB_MsgId_t SEND_HK_MID = CFE_SB_MSGID_RESERVED;
    CFE_SB_MsgId_t MessageID = CFE_SB_INVALID_MSG_ID;
    if (!CFE_SB_IsValidMsgId(CMD_MID))
    {
        CMD_MID = CFE_SB_ValueToMsgId(HS_CMD_MID);
        SEND_HK_MID = CFE_SB_ValueToMsgId(HS_SEND_HK_MID);
    }
    CFE_MSG_GetMsgId(&BufPtr->Msg, &MessageID);
    if (CFE_SB_MsgId_Equal(MessageID, SEND_HK_MID))
    {
        HS_SendHkVerifyDispatch(BufPtr);
    }
    else if (CFE_SB_MsgId_Equal(MessageID, CMD_MID))
    {
        HS_AppProcessGroundCmd(BufPtr);
    }
}
'''

EVS = '''
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } CFE_EVS_NoopCmd_t;
typedef struct { uint8 BitMask; uint8 Spare; } CFE_EVS_BitMaskCmd_Payload_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; CFE_EVS_BitMaskCmd_Payload_t Payload; } CFE_EVS_EnablePortsCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } CFE_EVS_SendHkCmd_t;

void CFE_EVS_ProcessGroundCommand(const CFE_SB_Buffer_t *SBBufPtr, CFE_SB_MsgId_t MsgId);
bool CFE_EVS_VerifyCmdLength(const CFE_MSG_Message_t *MsgPtr, size_t ExpectedLength);

int32 CFE_EVS_NoopCmd(const CFE_EVS_NoopCmd_t *data) { return CFE_SUCCESS; }
int32 CFE_EVS_EnablePortsCmd(const CFE_EVS_EnablePortsCmd_t *data) { return CFE_SUCCESS; }
int32 CFE_EVS_SendHkCmd(const CFE_EVS_SendHkCmd_t *data) { return CFE_SUCCESS; }

void CFE_EVS_ProcessCommandPacket(const CFE_SB_Buffer_t *SBBufPtr)
{
    static CFE_SB_MsgId_t CMD_MID     = CFE_SB_MSGID_RESERVED;
    static CFE_SB_MsgId_t SEND_HK_MID = CFE_SB_MSGID_RESERVED;
    CFE_SB_MsgId_t MessageID = CFE_SB_INVALID_MSG_ID;
    if (!CFE_SB_IsValidMsgId(CMD_MID))
    {
        CMD_MID     = CFE_SB_ValueToMsgId(CFE_EVS_CMD_MID);
        SEND_HK_MID = CFE_SB_ValueToMsgId(CFE_EVS_SEND_HK_MID);
    }
    CFE_MSG_GetMsgId(&SBBufPtr->Msg, &MessageID);
    if (CFE_SB_MsgId_Equal(MessageID, SEND_HK_MID))
    {
        CFE_EVS_SendHkCmd((const CFE_EVS_SendHkCmd_t *)SBBufPtr);
    }
    else if (CFE_SB_MsgId_Equal(MessageID, CMD_MID))
    {
        CFE_EVS_ProcessGroundCommand(SBBufPtr, MessageID);
    }
}

void CFE_EVS_ProcessGroundCommand(const CFE_SB_Buffer_t *SBBufPtr, CFE_SB_MsgId_t MsgId)
{
    int32 Status = CFE_STATUS_WRONG_MSG_LENGTH;
    CFE_MSG_FcnCode_t FcnCode = 0;
    CFE_MSG_GetFcnCode(&SBBufPtr->Msg, &FcnCode);
    switch (FcnCode)
    {
        case CFE_EVS_NOOP_CC:
            if (CFE_EVS_VerifyCmdLength(&SBBufPtr->Msg, sizeof(CFE_EVS_NoopCmd_t)))
            {
                Status = CFE_EVS_NoopCmd((const CFE_EVS_NoopCmd_t *)SBBufPtr);
            }
            break;
        case CFE_EVS_ENABLE_PORTS_CC:
            if (CFE_EVS_VerifyCmdLength(&SBBufPtr->Msg, sizeof(CFE_EVS_EnablePortsCmd_t)))
            {
                Status = CFE_EVS_EnablePortsCmd((const CFE_EVS_EnablePortsCmd_t *)SBBufPtr);
            }
            break;
        default:
            break;
    }
}

bool CFE_EVS_VerifyCmdLength(const CFE_MSG_Message_t *MsgPtr, size_t ExpectedLength)
{
    bool result = true;
    CFE_MSG_Size_t ActualLength = 0;
    CFE_MSG_GetSize(MsgPtr, &ActualLength);
    if (ExpectedLength != ActualLength)
    {
        result = false;
    }
    return result;
}
'''

# A mission app whose names share nothing with the NASA examples: the ground
# MID is not called *_CMD_MID, the comparison operands are swapped and a
# string holds unbalanced delimiters.
THERMAL = '''
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } THERMAL_NoopCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; uint8 Heater; uint8 Spare[3]; } THERMAL_SetHeaterCmd_t;
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } THERMAL_SendHkCmd_t;

void THERMAL_Noop(const THERMAL_NoopCmd_t *Cmd) { }
void THERMAL_SetHeater(const THERMAL_SetHeaterCmd_t *Cmd) { }
void THERMAL_SendHk(const THERMAL_SendHkCmd_t *Cmd) { }

bool THERMAL_LengthIs(const CFE_MSG_Message_t *MsgPtr, size_t ExpectedLength)
{
    size_t ActualLength = 0;
    CFE_MSG_GetSize(MsgPtr, &ActualLength);
    return ActualLength == ExpectedLength;
}

void THERMAL_ProcessGround(const CFE_SB_Buffer_t *BufPtr)
{
    CFE_MSG_FcnCode_t CommandCode = 0;
    CFE_MSG_GetFcnCode(&BufPtr->Msg, &CommandCode);
    switch (CommandCode)
    {
        case THERMAL_NOOP_CC:
            if (THERMAL_LengthIs(&BufPtr->Msg, sizeof(THERMAL_NoopCmd_t)))
            {
                THERMAL_Noop((const THERMAL_NoopCmd_t *)BufPtr);
            }
            break;
        case THERMAL_SET_HEATER_CC:
            if (THERMAL_LengthIs(&BufPtr->Msg, sizeof(THERMAL_SetHeaterCmd_t)))
            {
                THERMAL_SetHeater((const THERMAL_SetHeaterCmd_t *)BufPtr);
            }
            break;
        default:
            CFE_EVS_SendEvent(THERMAL_CC_ERR_EID, CFE_EVS_EventType_ERROR, "bad code (%u), see {docs", (unsigned int)CommandCode);
            break;
    }
}

void THERMAL_Pipe(const CFE_SB_Buffer_t *BufPtr)
{
    static CFE_SB_MsgId_t GROUND = CFE_SB_MSGID_RESERVED;
    static CFE_SB_MsgId_t HOUSEKEEPING = CFE_SB_MSGID_RESERVED;
    CFE_SB_MsgId_t MsgId = CFE_SB_INVALID_MSG_ID;
    if (!CFE_SB_IsValidMsgId(GROUND))
    {
        GROUND = CFE_SB_ValueToMsgId(THERMAL_GROUND_MID);
        HOUSEKEEPING = CFE_SB_ValueToMsgId(THERMAL_HK_REQUEST_MID);
    }
    CFE_MSG_GetMsgId(&BufPtr->Msg, &MsgId);
    /* if (CFE_SB_MsgId_Equal(MsgId, THERMAL_CMD_MID)) { is only a comment */
    if (CFE_SB_MsgId_Equal(MsgId, HOUSEKEEPING))
    {
        CFE_EVS_SendEvent(THERMAL_HK_EID, CFE_EVS_EventType_DEBUG, "hk request {");
        THERMAL_SendHk((const THERMAL_SendHkCmd_t *)BufPtr);
    }
    else if (CFE_SB_MsgId_Equal(GROUND, MsgId))
    {
        THERMAL_ProcessGround(BufPtr);
    }
}
'''

# The MID switch form is not read, and HEATER_CMD_MID exists only as a name.
UNROUTED = '''
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } HEATER_NoopCmd_t;

void HEATER_Noop(const HEATER_NoopCmd_t *Cmd) { }

void HEATER_ProcessCommandPacket(const CFE_SB_Buffer_t *BufPtr)
{
    CFE_MSG_FcnCode_t CommandCode = 0;
    CFE_MSG_GetFcnCode(&BufPtr->Msg, &CommandCode);
    switch (CommandCode)
    {
        case HEATER_NOOP_CC:
            HEATER_Noop((const HEATER_NoopCmd_t *)BufPtr);
            break;
    }
}

void HEATER_TaskPipe(const CFE_SB_Buffer_t *BufPtr)
{
    CFE_SB_MsgId_t MsgId = CFE_SB_INVALID_MSG_ID;
    CFE_MSG_GetMsgId(&BufPtr->Msg, &MsgId);
    switch (CFE_SB_MsgIdToValue(MsgId))
    {
        case HEATER_GROUND_MID:
            HEATER_ProcessCommandPacket(BufPtr);
            break;
    }
}
'''

GUARD = '''
static bool VerifyMsgLen(CFE_MSG_Message_t *MsgPtr, uint16 ExpectedLen, const char *MsgName)
{
    CFE_MSG_Size_t ActualLen = 0;
    if (CFE_MSG_GetSize(MsgPtr, &ActualLen) != CFE_SUCCESS)
    {
        return false;
    }
    if (ExpectedLen != ActualLen)
    {
        EVSSendErr(SBN_CMD_EID, "invalid length (Name=%s)", MsgName);
        return false;
    }
    return true;
}

static void NoopCmd(CFE_MSG_Message_t *MsgPtr)
{
    if (!VerifyMsgLen(MsgPtr, sizeof(CFE_MSG_CommandHeader_t), "noop"))
    {
        return;
    }
    SBN_AppData.CmdCnt++;
}

static void HKCmd(CFE_MSG_Message_t *MsgPtr)
{
    if (!VerifyMsgLen(MsgPtr, sizeof(CFE_MSG_CommandHeader_t), "hk"))
    {
        return;
    }
}

void SBN_HandleCommand(CFE_MSG_Message_t *MsgPtr)
{
    CFE_SB_MsgId_t MsgId;
    CFE_MSG_FcnCode_t FcnCode = 0;
    static CFE_SB_MsgId_t CMD_MID = CFE_SB_MSGID_RESERVED;
    if (!CFE_SB_IsValidMsgId(CMD_MID))
    {
        CMD_MID = CFE_SB_ValueToMsgId(SBN_CMD_MID);
    }
    if (CFE_MSG_GetMsgId(MsgPtr, &MsgId) != CFE_SUCCESS)
    {
        return;
    }
    if (!CFE_SB_MsgId_Equal(MsgId, CMD_MID))
    {
        SBN_AppData.CmdErrCnt++;
        EVSSendErr(SBN_CMD_EID, "invalid command pipe MsgId");
        return;
    }
    CFE_MSG_GetFcnCode(MsgPtr, &FcnCode);
    switch (FcnCode)
    {
        case SBN_NOOP_CC:
            NoopCmd(MsgPtr);
            break;
        case SBN_HK_CC:
            HKCmd(MsgPtr);
            break;
        case SBN_SCH_WAKEUP_CC:
            SBN_RecvNetMsgs();
            break;
    }
}
'''

TWO_ROUTES = '''
typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } RELAY_NoopCmd_t;

void RELAY_Noop(const RELAY_NoopCmd_t *Cmd) { }

void RELAY_Dispatch(const CFE_SB_Buffer_t *BufPtr)
{
    CFE_MSG_FcnCode_t CommandCode = 0;
    CFE_MSG_GetFcnCode(&BufPtr->Msg, &CommandCode);
    switch (CommandCode)
    {
        case RELAY_NOOP_CC:
            RELAY_Noop((const RELAY_NoopCmd_t *)BufPtr);
            break;
    }
}

void RELAY_Pipe(const CFE_SB_Buffer_t *BufPtr)
{
    CFE_SB_MsgId_t MsgId = CFE_SB_INVALID_MSG_ID;
    CFE_MSG_GetMsgId(&BufPtr->Msg, &MsgId);
    if (CFE_SB_MsgId_Equal(MsgId, CFE_SB_ValueToMsgId(RELAY_GROUND_MID)))
    {
        RELAY_Dispatch(BufPtr);
    }
    else if (CFE_SB_MsgId_Equal(MsgId, CFE_SB_ValueToMsgId(RELAY_BACKUP_MID)))
    {
        RELAY_Dispatch(BufPtr);
    }
}
'''


def catalog_view(source, defined, prefix):
    text = clean(source)
    return command_mappings(text, structures(text), set(defined), prefix)


def architecture_view(source, app):
    """Return ({code or MID: received MID}, {unresolved code: reason})."""
    with tempfile.TemporaryDirectory(prefix='command-routes-') as directory:
        root = Path(directory).resolve()
        path = root / 'cFS/apps' / app / 'fsw/src' / (app + '_dispatch.c')
        path.parent.mkdir(parents=True)
        path.write_text(source)
        record = {'name': app, **SourceIndex(root).application(path.parents[2])}
        details = describe_application(record, root=root)
    routes = {}
    for group in details['commands']:
        for handler in group['handlers']:
            routes[handler['cc']['symbol'] if handler['cc'] else group['mid']['symbol']] = group['mid']['symbol']
    unresolved = {item['expression']: item['reason'] for item in details['unresolved'] if item['kind'] == 'command_route'}
    return routes, unresolved


def received(mappings, explicit=None):
    return {code: mid for code, (mid, _, _) in {**mappings, **(explicit or {})}.items()}


class LexicalHelpersTest(unittest.TestCase):
    def test_arguments_keep_literals_intact(self):
        self.assertEqual(arguments('ID, "a, (b", \',\', f(x, y)'), ['ID', '"a, (b"', "','", 'f(x, y)'])

    def test_calls_skip_comments_and_strings(self):
        text = 'f(1); /* f(2) */ g("f(3)", f(4)); // f(5)\n'
        self.assertEqual([args for _, _, _, args in calls(text, {'f'})], [['1'], ['4']])

    def test_blanking_keeps_offsets_lines_and_optionally_literals(self):
        text = 'a /* x\ny */ "s // t" // z\nb'
        self.assertEqual(blank_lexemes(text), 'a     \n' + ' ' * 18 + '\nb')
        self.assertEqual(blank_lexemes(text, literals=False), 'a     \n' + '     "s // t"     ' + '\nb')


class MidRegionTest(unittest.TestCase):
    def regions(self, body, aliases=None):
        return [(mid, body[begin:end].strip()) for mid, begin, end in mid_regions(blank_lexemes(body), aliases)]

    def test_positive_branch_and_converted_operand(self):
        body = 'if (CFE_SB_MsgId_Equal(CFE_SB_ValueToMsgId(A_HK_MID), MsgId)) { Hk(); } else { Other(); }'
        self.assertEqual(self.regions(body), [('A_HK_MID', 'Hk();')])

    def test_returning_guard_covers_the_rest_of_its_block(self):
        body = 'if (!CFE_SB_MsgId_Equal(MsgId, CFE_SB_ValueToMsgId(A_CMD_MID))) { Count++; return; } Run(); Done();'
        self.assertEqual(self.regions(body), [('A_CMD_MID', 'Run(); Done();')])

    def test_negations_without_a_returning_guard_give_no_route(self):
        for body in ('if (!CFE_SB_MsgId_Equal(MsgId, A_CMD_MID)) { Count++; } Run();',
                     'if (x) { Hk(); } else if (!CFE_SB_MsgId_Equal(MsgId, A_CMD_MID)) { return; } Run();',
                     'if (!CFE_SB_MsgId_Equal(MsgId, A_CMD_MID)) { if (y) { return; } } Run();'):
            self.assertEqual(self.regions(body), [], body)

    def test_compound_or_runtime_predicates_give_no_route(self):
        for body in ('if (CFE_SB_MsgId_Equal(MsgId, A_CMD_MID) || CFE_SB_MsgId_Equal(MsgId, A_HK_MID)) { Run(); }',
                     'if (CFE_SB_MsgId_Equal(MsgId, Table[i].MsgId)) { Run(); }',
                     'if (CFE_SB_MsgIdToValue(MsgId) == A_CMD_MID) { Run(); }',
                     'if (CFE_SB_MsgId_Equal(MsgId, A_CMD_MID)) Run();'):
            self.assertEqual(self.regions(body), [], body)

    def test_guard_stops_at_the_next_case_label(self):
        body = 'switch (x) { case A_ONE_CC: if (!CFE_SB_MsgId_Equal(MsgId, A_CMD_MID)) { return; } One(); break; case A_TWO_CC: Two(); }'
        self.assertEqual(self.regions(body), [('A_CMD_MID', 'One(); break;')])

    def test_aliases_are_local_first_and_ambiguous_globally(self):
        body = 'if (CFE_SB_MsgId_Equal(MsgId, CMD)) { Run(); }'
        self.assertEqual(self.regions(body, {'CMD': {'A_CMD_MID', 'B_CMD_MID'}}), [])
        self.assertEqual(self.regions(body, {'CMD': {'A_CMD_MID'}}), [('A_CMD_MID', 'Run();')])
        local = 'CMD = CFE_SB_ValueToMsgId(B_CMD_MID); ' + body
        self.assertEqual(self.regions(local, {'CMD': {'A_CMD_MID', 'B_CMD_MID'}}), [('B_CMD_MID', 'Run();')])

    def test_routes_follow_calls_and_keep_every_entry_mid(self):
        regions = {'pipe': [('A_GROUND_MID', 0, 10), ('A_BACKUP_MID', 10, 20)]}
        sites = {'pipe': [('dispatch', 5), ('dispatch', 15), ('log', 25)], 'dispatch': [('helper', 1)], 'helper': [], 'log': []}
        routes = entry_routes(regions, sites)
        self.assertEqual(routes['helper'], {'A_GROUND_MID', 'A_BACKUP_MID'})
        self.assertEqual(routes['log'], set())


class CatalogCommandRoutesTest(unittest.TestCase):
    def test_sample_app(self):
        defined = {'SAMPLE_APP_CMD_MID', 'SAMPLE_APP_SEND_HK_MID', 'SAMPLE_APP_NOOP_CC', 'SAMPLE_APP_RESET_COUNTERS_CC'}
        mappings, unresolved, explicit = catalog_view(SAMPLE_APP, defined, 'SAMPLE_APP')
        expected = {
            'SAMPLE_APP_NOOP_CC': ('SAMPLE_APP_CMD_MID', 'SAMPLE_APP_NOOP_CC', 'SAMPLE_APP_NoopCmd_t'),
            'SAMPLE_APP_RESET_COUNTERS_CC': ('SAMPLE_APP_CMD_MID', 'SAMPLE_APP_RESET_COUNTERS_CC', 'SAMPLE_APP_ResetCountersCmd_t'),
            'SAMPLE_APP_SEND_HK_MID': ('SAMPLE_APP_SEND_HK_MID', '0', 'SAMPLE_APP_SendHkCmd_t')}
        self.assertEqual(mappings, expected)
        self.assertEqual((unresolved, explicit), ({}, {}))

    def test_hs_verify_dispatch_wrappers_and_direct_mid(self):
        defined = {'HS_CMD_MID', 'HS_SEND_HK_MID', 'HS_NOOP_CC', 'HS_RESET_CC'}
        mappings, unresolved, _ = catalog_view(HS, defined, 'HS')
        expected = {'HS_NOOP_CC': ('HS_CMD_MID', 'HS_NOOP_CC', 'HS_NoopCmd_t'),
                    'HS_RESET_CC': ('HS_CMD_MID', 'HS_RESET_CC', 'HS_ResetCmd_t'),
                    'HS_SEND_HK_MID': ('HS_SEND_HK_MID', '0', 'HS_SendHkCmd_t')}
        self.assertEqual(mappings, expected)
        self.assertEqual(unresolved, {})

    def test_evs_core_module(self):
        defined = {'CFE_EVS_CMD_MID', 'CFE_EVS_SEND_HK_MID', 'CFE_EVS_NOOP_CC', 'CFE_EVS_ENABLE_PORTS_CC'}
        mappings, unresolved, _ = catalog_view(EVS, defined, 'CFE_EVS')
        expected = {'CFE_EVS_NOOP_CC': 'CFE_EVS_CMD_MID', 'CFE_EVS_ENABLE_PORTS_CC': 'CFE_EVS_CMD_MID',
                    'CFE_EVS_SEND_HK_MID': 'CFE_EVS_SEND_HK_MID'}
        self.assertEqual(received(mappings), expected)
        self.assertEqual(mappings['CFE_EVS_ENABLE_PORTS_CC'][2], 'CFE_EVS_EnablePortsCmd_t')
        self.assertEqual(unresolved, {})

    def test_app_with_unrelated_names(self):
        defined = {'THERMAL_GROUND_MID', 'THERMAL_HK_REQUEST_MID', 'THERMAL_CMD_MID', 'THERMAL_NOOP_CC', 'THERMAL_SET_HEATER_CC'}
        mappings, unresolved, _ = catalog_view(THERMAL, defined, 'THERMAL')
        expected = {
            'THERMAL_NOOP_CC': ('THERMAL_GROUND_MID', 'THERMAL_NOOP_CC', 'THERMAL_NoopCmd_t'),
            'THERMAL_SET_HEATER_CC': ('THERMAL_GROUND_MID', 'THERMAL_SET_HEATER_CC', 'THERMAL_SetHeaterCmd_t'),
            'THERMAL_HK_REQUEST_MID': ('THERMAL_HK_REQUEST_MID', '0', 'THERMAL_SendHkCmd_t')}
        self.assertEqual(mappings, expected)
        self.assertEqual(unresolved, {})

    def test_missing_route_is_unresolved_even_when_app_cmd_mid_exists(self):
        defined = {'HEATER_CMD_MID', 'HEATER_GROUND_MID', 'HEATER_NOOP_CC'}
        mappings, unresolved, explicit = catalog_view(UNROUTED, defined, 'HEATER')
        self.assertEqual((mappings, explicit), ({}, {}))
        self.assertEqual(list(unresolved), ['HEATER_NOOP_CC'])
        self.assertIn('no MID comparison', unresolved['HEATER_NOOP_CC'])
        self.assertIn('HEATER_ProcessCommandPacket', unresolved['HEATER_NOOP_CC'])

    def test_returning_guard_routes_size_only_commands(self):
        defined = {'SBN_CMD_MID', 'SBN_NOOP_CC', 'SBN_HK_CC', 'SBN_SCH_WAKEUP_CC'}
        mappings, unresolved, explicit = catalog_view(GUARD, defined, 'SBN')
        self.assertEqual(mappings, {})
        expected = {'SBN_NOOP_CC': ('SBN_CMD_MID', 'SBN_NOOP_CC', 'sizeof(CFE_MSG_CommandHeader_t)'),
                    'SBN_HK_CC': ('SBN_CMD_MID', 'SBN_HK_CC', 'sizeof(CFE_MSG_CommandHeader_t)')}
        self.assertEqual(explicit, expected)
        # The wakeup case never reads the message, so it has no packet layout.
        self.assertEqual(unresolved, {})

    def test_guard_without_return_is_not_a_route(self):
        source = GUARD.replace('        EVSSendErr(SBN_CMD_EID, "invalid command pipe MsgId");\n        return;\n', '')
        defined = {'SBN_CMD_MID', 'SBN_NOOP_CC', 'SBN_HK_CC', 'SBN_SCH_WAKEUP_CC'}
        mappings, unresolved, explicit = catalog_view(source, defined, 'SBN')
        self.assertEqual((mappings, explicit), ({}, {}))
        self.assertEqual(sorted(unresolved), ['SBN_HK_CC', 'SBN_NOOP_CC'])
        self.assertIn('SBN_HandleCommand', unresolved['SBN_NOOP_CC'])

    def test_function_reached_from_several_mids_is_ambiguous(self):
        defined = {'RELAY_GROUND_MID', 'RELAY_BACKUP_MID', 'RELAY_NOOP_CC'}
        mappings, unresolved, _ = catalog_view(TWO_ROUTES, defined, 'RELAY')
        self.assertEqual(mappings, {})
        self.assertEqual(unresolved, {'RELAY_NOOP_CC': 'RELAY_Dispatch is reached from several MIDs (RELAY_BACKUP_MID, RELAY_GROUND_MID)'})

    def test_length_array_takes_the_mid_of_its_function(self):
        source = '''
        typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } CF_NoopCmd_t;
        typedef struct { CFE_MSG_CommandHeader_t CommandHeader; uint32 Value; } CF_ResetCmd_t;
        void CF_ProcessGroundCommand(const CFE_SB_Buffer_t *BufPtr)
        {
            static const uint16 expected_lengths[] = {
                [CF_NOOP_CC] = sizeof(CF_NoopCmd_t),
                [CF_RESET_CC] = sizeof(CF_ResetCmd_t),
            };
            CFE_MSG_FcnCode_t cmd = 0;
            CFE_MSG_GetFcnCode(&BufPtr->Msg, &cmd);
        }
        void CF_AppPipe(const CFE_SB_Buffer_t *BufPtr)
        {
            static CFE_SB_MsgId_t CMD_MID = CFE_SB_MSGID_RESERVED;
            CFE_SB_MsgId_t MsgId = CFE_SB_INVALID_MSG_ID;
            CMD_MID = CFE_SB_ValueToMsgId(CF_CMD_MID);
            CFE_MSG_GetMsgId(&BufPtr->Msg, &MsgId);
            if (CFE_SB_MsgId_Equal(MsgId, CMD_MID))
            {
                CF_ProcessGroundCommand(BufPtr);
            }
        }
        '''
        defined = {'CF_CMD_MID', 'CF_NOOP_CC', 'CF_RESET_CC'}
        mappings, unresolved, _ = catalog_view(source, defined, 'CF')
        expected = {'CF_NOOP_CC': ('CF_CMD_MID', 'CF_NOOP_CC', 'CF_NoopCmd_t'),
                    'CF_RESET_CC': ('CF_CMD_MID', 'CF_RESET_CC', 'CF_ResetCmd_t')}
        self.assertEqual(mappings, expected)
        self.assertEqual(unresolved, {})
        # The same array at file scope proves the layout, not the MID.
        array = source[source.index('        static const uint16'):source.index('        CFE_MSG_FcnCode_t cmd')]
        moved = array.replace('static const', 'const', 1) + source.replace(array, '')
        mappings, unresolved, _ = catalog_view(moved, defined, 'CF')
        self.assertEqual(mappings, {})
        self.assertEqual(set(unresolved), {'CF_NOOP_CC', 'CF_RESET_CC'})
        self.assertIn('length array', unresolved['CF_NOOP_CC'])

    def test_handler_table_is_explicit_mid_evidence(self):
        source = '''
        typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } CFE_TBL_NoopCmd_t;
        typedef struct { CFE_MSG_CommandHeader_t CommandHeader; } CFE_TBL_SendHkCmd_t;
        const CFE_TBL_CmdHandlerTblRec_t CFE_TBL_CmdHandlerTbl[] = {
            CFE_TBL_ENTRY(CFE_TBL_SEND_HK_MID, 0, CFE_TBL_SendHkCmd_t, CFE_TBL_SendHkCmd, CFE_TBL_MSG_MSGTYPE),
            CFE_TBL_ENTRY(CFE_TBL_CMD_MID, CFE_TBL_NOOP_CC, CFE_TBL_NoopCmd_t, CFE_TBL_NoopCmd, CFE_TBL_CMD_MSGTYPE),
            CFE_TBL_ENTRY(CFE_SB_INVALID_MSG_ID, 0, 0, NULL, CFE_TBL_TERM_MSGTYPE)};
        '''
        defined = {'CFE_TBL_CMD_MID', 'CFE_TBL_SEND_HK_MID', 'CFE_TBL_NOOP_CC'}
        mappings, unresolved, _ = catalog_view(source, defined, 'CFE_TBL')
        expected = {'CFE_TBL_NOOP_CC': ('CFE_TBL_CMD_MID', 'CFE_TBL_NOOP_CC', 'CFE_TBL_NoopCmd_t'),
                    'CFE_TBL_SEND_HK_MID': ('CFE_TBL_SEND_HK_MID', '0', 'CFE_TBL_SendHkCmd_t')}
        self.assertEqual(mappings, expected)
        self.assertEqual(unresolved, {})

    def test_conflicting_evidence_is_not_resolved(self):
        source = SAMPLE_APP + '''
        const Handler_t Handlers[] = { ENTRY(SAMPLE_APP_SEND_HK_MID, SAMPLE_APP_NOOP_CC, SAMPLE_APP_NoopCmd_t, Noop) };
        '''
        defined = {'SAMPLE_APP_CMD_MID', 'SAMPLE_APP_SEND_HK_MID', 'SAMPLE_APP_NOOP_CC', 'SAMPLE_APP_RESET_COUNTERS_CC'}
        mappings, unresolved, _ = catalog_view(source, defined, 'SAMPLE_APP')
        self.assertNotIn('SAMPLE_APP_NOOP_CC', mappings)
        self.assertIn('SAMPLE_APP_CMD_MID', unresolved['SAMPLE_APP_NOOP_CC'])
        self.assertIn('SAMPLE_APP_SEND_HK_MID', unresolved['SAMPLE_APP_NOOP_CC'])
        self.assertIn('SAMPLE_APP_RESET_COUNTERS_CC', mappings)

    def test_mid_missing_from_compiled_headers_is_reported(self):
        defined = {'SAMPLE_APP_SEND_HK_MID', 'SAMPLE_APP_NOOP_CC', 'SAMPLE_APP_RESET_COUNTERS_CC'}
        mappings, unresolved, _ = catalog_view(SAMPLE_APP, defined, 'SAMPLE_APP')
        self.assertEqual(set(mappings), {'SAMPLE_APP_SEND_HK_MID'})
        self.assertEqual(unresolved['SAMPLE_APP_NOOP_CC'], 'SAMPLE_APP_CMD_MID is not defined by the compiled headers')

    def test_functions_with_several_definitions_are_not_followed(self):
        duplicate = 'void SAMPLE_APP_ProcessGroundCommand(const CFE_SB_Buffer_t *SBBufPtr) { switch (x) { case SAMPLE_APP_NOOP_CC: break; } }\n'
        defined = {'SAMPLE_APP_CMD_MID', 'SAMPLE_APP_SEND_HK_MID', 'SAMPLE_APP_NOOP_CC', 'SAMPLE_APP_RESET_COUNTERS_CC'}
        mappings, unresolved, _ = catalog_view(SAMPLE_APP + duplicate, defined, 'SAMPLE_APP')
        self.assertEqual(set(mappings), {'SAMPLE_APP_SEND_HK_MID'})
        self.assertEqual(unresolved['SAMPLE_APP_NOOP_CC'], 'SAMPLE_APP_ProcessGroundCommand has several definitions')


class ArchitectureAgreesWithCatalogTest(unittest.TestCase):
    """Both views must derive the same MID from the same code."""
    FIXTURES = [
        ('sample_app', SAMPLE_APP, 'SAMPLE_APP', {'SAMPLE_APP_CMD_MID', 'SAMPLE_APP_SEND_HK_MID', 'SAMPLE_APP_NOOP_CC', 'SAMPLE_APP_RESET_COUNTERS_CC'}),
        ('hs', HS, 'HS', {'HS_CMD_MID', 'HS_SEND_HK_MID', 'HS_NOOP_CC', 'HS_RESET_CC'}),
        ('evs', EVS, 'CFE_EVS', {'CFE_EVS_CMD_MID', 'CFE_EVS_SEND_HK_MID', 'CFE_EVS_NOOP_CC', 'CFE_EVS_ENABLE_PORTS_CC'}),
        ('thermal', THERMAL, 'THERMAL', {'THERMAL_GROUND_MID', 'THERMAL_HK_REQUEST_MID', 'THERMAL_CMD_MID', 'THERMAL_NOOP_CC', 'THERMAL_SET_HEATER_CC'}),
    ]

    def test_resolved_routes_match(self):
        for app, source, prefix, defined in self.FIXTURES:
            with self.subTest(app=app):
                mappings, unresolved, explicit = catalog_view(source, defined, prefix)
                routes, missing = architecture_view(source, app)
                self.assertEqual(routes, received(mappings, explicit))
                self.assertEqual((unresolved, missing), ({}, {}))

    def test_guard_routes_match(self):
        defined = {'SBN_CMD_MID', 'SBN_NOOP_CC', 'SBN_HK_CC', 'SBN_SCH_WAKEUP_CC'}
        mappings, _, explicit = catalog_view(GUARD, defined, 'SBN')
        routes, missing = architecture_view(GUARD, 'sbn')
        self.assertEqual(routes, received(mappings, explicit))
        self.assertEqual(missing, {'SBN_SCH_WAKEUP_CC': 'No local handler is called for this function code'})

    def test_both_views_leave_unproven_routes_unresolved(self):
        routes, missing = architecture_view(UNROUTED, 'heater')
        self.assertEqual(routes, {})
        self.assertIn('HEATER_ProcessCommandPacket', missing['HEATER_NOOP_CC'])
        routes, missing = architecture_view(TWO_ROUTES, 'relay')
        self.assertEqual(routes, {})
        self.assertEqual(missing['RELAY_NOOP_CC'], 'RELAY_Dispatch is reached from several MIDs: RELAY_BACKUP_MID, RELAY_GROUND_MID')


@unittest.skipUnless((ROOT / 'cFS/apps/sample_app/fsw/src').is_dir(), 'NASA cFS checkout not available')
class NasaSourcesTest(unittest.TestCase):
    """Source-only routes of the unmodified NASA checkout."""
    def routes(self, relative):
        directory = ROOT / relative
        record = {'name': directory.name, **SourceIndex(ROOT).application(directory)}
        details = describe_application(record, root=ROOT)
        routes = {}
        for group in details['commands']:
            for handler in group['handlers']:
                routes[handler['cc']['symbol'] if handler['cc'] else group['mid']['symbol']] = group['mid']['symbol']
        return routes

    def test_sample_app_hs_evs_and_sbn(self):
        sample = self.routes('cFS/apps/sample_app')
        self.assertEqual(sample['SAMPLE_APP_NOOP_CC'], 'SAMPLE_APP_CMD_MID')
        self.assertEqual(sample['SAMPLE_APP_SEND_HK_MID'], 'SAMPLE_APP_SEND_HK_MID')
        hs = self.routes('cFS/apps/hs')
        self.assertEqual({hs[code] for code in hs if code.endswith('_CC')}, {'HS_CMD_MID'})
        self.assertEqual(hs['HS_SEND_HK_MID'], 'HS_SEND_HK_MID')
        evs = self.routes('cFS/cfe/modules/evs')
        self.assertEqual(evs['CFE_EVS_NOOP_CC'], 'CFE_EVS_CMD_MID')
        sbn = self.routes('cFS/apps/sbn')
        # SBN reaches its codes only after a negated test that returns.
        self.assertEqual(sbn['SBN_NOOP_CC'], 'SBN_CMD_MID')


if __name__ == '__main__':
    unittest.main()
