"""Generated sensor reader: every read reaches telemetry, each new failure is reported once.

The real project/appgen/templates/sensor.c.in is rendered with a scripted read
function and compiled with the host C compiler against minimal cFE stubs.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'project/appgen/templates'
NOT_IMPLEMENTED = -939524093  # (int32)0xc8000003, as in cFE

CFE_STUB = r'''
#ifndef CFE_H
#define CFE_H
#include <stdbool.h>
#include <stdint.h>
typedef int32_t int32;
typedef uint32_t uint32;
typedef uint16_t uint16;
typedef uint8_t uint8;
typedef int32 CFE_Status_t;
typedef uint32 CFE_SB_MsgId_t;
typedef struct { uint8 Bytes[16]; } CFE_MSG_TelemetryHeader_t;
#define CFE_SUCCESS ((CFE_Status_t)0)
#define CFE_STATUS_NOT_IMPLEMENTED ((CFE_Status_t)0xc8000003)
#define CFE_EVS_EventType_INFORMATION 2
#define CFE_EVS_EventType_ERROR 3
#define CFE_MSG_PTR(header) ((void *)&(header))
#define CFE_SB_ValueToMsgId(value) ((CFE_SB_MsgId_t)(value))
void CFE_MSG_Init(void *Msg, CFE_SB_MsgId_t MsgId, unsigned long Size);
void CFE_SB_TimeStampMsg(void *Msg);
CFE_Status_t CFE_SB_TransmitMsg(void *Msg, bool Increment);
CFE_Status_t CFE_EVS_SendEvent(uint16 EventID, uint16 EventType, const char *Spec, ...);
#endif
'''

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include "demo_probe_sensor.h"

static int Count, Next;
static long *Statuses;
static int Events[16], Transmitted;

void CFE_MSG_Init(void *Msg, CFE_SB_MsgId_t MsgId, unsigned long Size) { (void)Msg; (void)MsgId; (void)Size; }
void CFE_SB_TimeStampMsg(void *Msg) { (void)Msg; }
CFE_Status_t CFE_SB_TransmitMsg(void *Msg, bool Increment) { (void)Msg; (void)Increment; Transmitted++; return CFE_SUCCESS; }
CFE_Status_t CFE_EVS_SendEvent(uint16 EventID, uint16 EventType, const char *Spec, ...)
{
    (void)EventType; (void)Spec;
    Events[EventID]++;
    return CFE_SUCCESS;
}

int32 Test_Read(int32 *Value)
{
    int32 Status = (int32)Statuses[Next++];
    if (Status == CFE_SUCCESS)
    {
        *Value = 1000 * Next;
    }
    return Status;
}

int main(int argc, char **argv)
{
    Count = argc - 1;
    Statuses = calloc((size_t)Count, sizeof(*Statuses));
    for (int i = 0; i < Count; i++)
    {
        Statuses[i] = strtol(argv[i + 1], NULL, 0);
    }
    DEMO_Probe_Init();
    for (int i = 0; i < Count; i++)
    {
        const DEMO_Probe_Payload_t *Data;
        DEMO_Probe_Read();
        Data = DEMO_Probe_GetData();
        printf("{\"value\": %ld, \"status\": %ld, ", (long)Data->Value, (long)Data->Status);
        printf("\"reads\": %lu, \"errors\": %lu, \"valid\": %u, ", (unsigned long)Data->ReadCounter, (unsigned long)Data->ErrorCounter, Data->Valid);
        printf("\"error_events\": %d, \"value_events\": %d, \"packets\": %d}\n", Events[8], Events[9], Transmitted);
    }
    return 0;
}
'''


def render(name, tokens):
    text = (TEMPLATES / name).read_text()
    for token, value in tokens.items():
        text = text.replace(f'@{token}@', value)
    return text


@unittest.skipUnless(shutil.which('cc'), 'no host C compiler')
class SensorTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='sensor-template-')
        build = Path(cls.directory.name)
        tokens = {'PREFIX': 'DEMO', 'APP': 'demo', 'NAME': 'probe', 'ENTITY': 'Probe', 'ENTITY_UPPER': 'PROBE',
                  'DRIVER': 'custom', 'VALUE_TYPE': 'int32', 'VALUE_NOTE': 'Latest successful sample.',
                  'VALUE_INCLUDE': '', 'DRIVER_INCLUDE': '', 'DRIVER_STATE': '', 'DRIVER_INIT': '',
                  'READ_VALUE': '    return Test_Read(Value);',
                  'VALUE_EVENT': '        CFE_EVS_SendEvent(DEMO_SENSOR_VALUE_INF_EID, CFE_EVS_EventType_INFORMATION, "probe");',
                  'DEVICE': '/dev/i2c-1', 'ADDRESS': '0x48', 'SENSOR_TLM_MID': '0x0A01'}
        (build / 'cfe.h').write_text(CFE_STUB)
        eventids = '#define DEMO_SENSOR_READ_ERR_EID 8\n#define DEMO_SENSOR_VALUE_INF_EID 9\nint32 Test_Read(int32 *Value);\n'
        (build / 'demo_eventids.h').write_text(eventids)
        (build / 'demo_probe_sensor.h').write_text(render('sensor.h.in', tokens))
        (build / 'demo_probe_sensor_cfg.h').write_text(render('sensor_cfg.h.in', tokens))
        (build / 'demo_probe_sensor.c').write_text(render('sensor.c.in', tokens))
        (build / 'main.c').write_text(HARNESS)
        cls.program = build / 'sensor-test'
        command = ['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-I', str(build), '-o', str(cls.program),
                   str(build / 'demo_probe_sensor.c'), str(build / 'main.c')]
        subprocess.run(command, check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def reads(self, *statuses):
        completed = subprocess.run([str(self.program), *map(str, statuses)], check=True, capture_output=True, text=True, timeout=30)
        return [json.loads(line) for line in completed.stdout.splitlines()]

    def test_a_failure_is_reported_once_per_status_change(self):
        steps = self.reads(0, -2, -2, -2, -121, -121, 0, -2)
        self.assertEqual([step['error_events'] for step in steps], [0, 1, 1, 1, 2, 2, 2, 3])
        self.assertEqual([step['errors'] for step in steps], [0, 1, 2, 3, 4, 5, 5, 6])
        self.assertEqual([step['status'] for step in steps], [0, -2, -2, -2, -121, -121, 0, -2])
        self.assertEqual([step['valid'] for step in steps], [1, 0, 0, 0, 0, 0, 1, 0])
        # Every read is published, and the payload keeps only the latest successful sample.
        self.assertEqual([step['packets'] for step in steps], list(range(1, 9)))
        self.assertEqual([step['value'] for step in steps], [1000, 1000, 1000, 1000, 1000, 1000, 7000, 7000])
        self.assertEqual(steps[-1]['value_events'], 2)

    def test_first_read_failure_is_reported_even_with_the_initial_status(self):
        # A sensor without a driver returns CFE_STATUS_NOT_IMPLEMENTED, also its initial status.
        steps = self.reads(NOT_IMPLEMENTED, NOT_IMPLEMENTED, NOT_IMPLEMENTED)
        self.assertEqual([step['error_events'] for step in steps], [1, 1, 1])
        self.assertEqual([step['errors'] for step in steps], [1, 2, 3])
        self.assertEqual({step['valid'] for step in steps}, {0})
        self.assertEqual({step['value'] for step in steps}, {0})


if __name__ == '__main__':
    unittest.main()
