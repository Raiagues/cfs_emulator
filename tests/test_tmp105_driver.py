"""TMP105 driver decoding, compiled from project/drivers with a scripted I2C bus.

Simulated bus answers only; this does not exercise a real sensor.
"""
import errno
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'project/drivers/tmp105_lib/fsw'

CFE_STUB = r'''
#ifndef CFE_H
#define CFE_H
#include <stddef.h>
#include <stdint.h>
typedef int32_t int32;
typedef uint16_t uint16;
typedef uint8_t uint8;
#define CFE_SUCCESS 0
#define OS_printf(...) ((void)0)
#endif
'''

I2C_STUB = r'''
#ifndef LINUX_I2C_LIB_H
#define LINUX_I2C_LIB_H
#include "cfe.h"
int32 LINUX_I2C_ReadRegister(const char *Device, uint16 Address, uint8 Register, uint8 *Data, uint16 Length);
#endif
'''

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include "tmp105_lib.h"

static long BusStatus;
static uint8 Bytes[2];

int32 LINUX_I2C_ReadRegister(const char *Device, uint16 Address, uint8 Register, uint8 *Data, uint16 Length)
{
    (void)Device; (void)Address; (void)Register;
    if (BusStatus != 0)
    {
        return (int32)BusStatus;
    }
    Data[0] = Bytes[0];
    if (Length > 1)
    {
        Data[1] = Bytes[1];
    }
    return 0;
}

int main(int argc, char **argv)
{
    int32 Temperature = 12345;
    int32 Status;
    (void)argc;
    BusStatus = strtol(argv[1], NULL, 0);
    Bytes[0] = (uint8)strtol(argv[2], NULL, 0);
    Bytes[1] = (uint8)strtol(argv[3], NULL, 0);
    Status = TMP105_LIB_ReadTemperature("/dev/i2c-1", 0x48, &Temperature);
    printf("{\"status\": %ld, \"temperature\": %ld}\n", (long)Status, (long)Temperature);
    return 0;
}
'''


@unittest.skipUnless(shutil.which('cc'), 'no host C compiler')
class Tmp105DriverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='tmp105-')
        build = Path(cls.directory.name)
        (build / 'cfe.h').write_text(CFE_STUB)
        (build / 'linux_i2c_lib.h').write_text(I2C_STUB)
        (build / 'main.c').write_text(HARNESS)
        cls.program = build / 'tmp105-test'
        command = ['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-I', str(build), '-I', str(DRIVER / 'public_inc'),
                   '-I', str(DRIVER / 'src'), '-o', str(cls.program), str(DRIVER / 'src/tmp105_lib.c'), str(build / 'main.c')]
        subprocess.run(command, check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def read(self, high, low, bus=0):
        completed = subprocess.run([str(self.program), str(bus), str(high), str(low)], check=True, capture_output=True, text=True, timeout=30)
        return json.loads(completed.stdout)

    def test_decodes_millidegrees_celsius(self):
        cases = {(0x17, 0x80): 23500, (0x00, 0x00): 0, (0xFF, 0x00): -1000, (0xE7, 0x00): -25000,
                 (0x7F, 0xF0): 127937, (0x80, 0x00): -128000, (0x00, 0x10): 62}
        for (high, low), millidegrees in cases.items():
            with self.subTest(register=f'{high:02X}{low:02X}'):
                self.assertEqual(self.read(high, low), {'status': 0, 'temperature': millidegrees})

    def test_impossible_register_data_is_an_error(self):
        # All ones is what an unanswered read returns on a bus that reports no NACK.
        for high, low in ((0xFF, 0xFF), (0x17, 0x81), (0x00, 0x0F)):
            with self.subTest(register=f'{high:02X}{low:02X}'):
                self.assertEqual(self.read(high, low), {'status': -errno.EIO, 'temperature': 12345})

    def test_bus_errors_keep_their_errno(self):
        for code in (errno.ENOENT, errno.EACCES, errno.EREMOTEIO, errno.ENXIO, errno.ETIMEDOUT):
            with self.subTest(errno=errno.errorcode[code]):
                self.assertEqual(self.read(0x17, 0x80, bus=-code), {'status': -code, 'temperature': 12345})


if __name__ == '__main__':
    unittest.main()
