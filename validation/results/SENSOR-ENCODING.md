# Reading sensor inputs, registers, and telemetry

This guide explains the existing [final campaign](final/README.md). It does not change the measurements, register configuration, packet format, or original checksums. The measured platform and NASA revisions are recorded in [prepare.json](final/raw/prepare.json).

## Why the packet contains 21500

The TMP105 application uses a signed 32-bit integer in **thousandths of a degree Celsius**. Therefore, `Value = 21500` means **21.500 °C**. It does not mean 21,500 degrees. This is the software's choice of representation; the C driver is a function that reads and interprets the sensor bytes, not an additional hardware converter.

For the first QEMU case, the test sets a temperature of 21.537 °C. The sensor returns `15 80`. The driver interprets those bytes as the signed word `0x1580`, or 5504, and calculates:

```text
Sensor word:          0x1580 = 5504
Temperature:          5504 / 256 = 21.500 °C
Integer in telemetry: 5504 × 1000 / 256 = 21500
Display in °C:        21500 / 1000 = 21.500 °C
```

The representation preserves fractional degrees without using a floating-point field. Changing `Value` to `21` would discard the fraction; simply replacing the integer with `21.5` would change the packet's data-type contract. A readable display can divide by 1000 and add `°C` while retaining the original packet.

The unit and coefficients come from the [TMP105 model](../../project/drivers/models/tmp105/model.json). The [driver generator](../../project/sensor_driver.py) emits the model's profile. The shared [C decoder](../../project/drivers/hal/src/hal_sensor.c) joins the two bytes, interprets the sign, and applies the profile's scale. The [application template](../../project/appgen/templates/hal_sensor/sensor.c.in) copies the acquired value into the payload only when the read succeeds, then timestamps and transmits it. The [TMP105 event template](../../project/drivers/models/tmp105/event.c.in) already formats the value as decimal degrees Celsius in the application event.

## Three different inputs and recorded results

The [fixed input protocol](../protocol.py) defines three TMP105 inputs before collection. These rows are taken from [QEMU sensors.json](final/raw/qemu/sensors.json), not generated illustrations:

| Input set by the test (°C) | Input integer | Two bytes read from TMP105 | Received `Value` | Interpreted reading (°C) | Absolute difference (°C) | Packets |
| ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 21.537 | 21537 | `15 80` | 21500 | 21.500 | 0.037 | 5 |
| −3.241 | −3241 | `FC 80` | −3500 | −3.500 | 0.259 | 5 |
| 31.719 | 31719 | `1F 80` | 31500 | 31.500 | 0.219 | 5 |

For a negative temperature, `FC 80` is interpreted as a signed 16-bit word: `0xFC80 − 65536 = −896`, giving `−896 × 1000 / 256 = −3500`. The decoder performs this signed conversion explicitly.

The [complementary configuration read](final/raw/qemu/tmp105-configuration.json) returned `00` from configuration register `0x01`, documenting 9-bit operation. It was performed **after quantitative collection without changing the configuration**. The QEMU case has a 0.5 °C step and a 0.501 °C acceptance limit. The memory-backed and Native cases use 12-bit representation with a 0.0625 °C step; they have their own limits. See [errors and limits](final/tables/q2_errors.csv) and the [collection procedure](../flight.py). A requested input need not be exactly representable at the sensor's resolution.

These different positive and negative outputs, and the code path above, are evidence that the measured temperature was read and decoded rather than replaced with a constant expected result. The protocol's fixed inputs are test stimuli, not constants assigned to the received payload.

The later Ground screenshot displays `31500`, which means **31.500 °C** and agrees with the third input. Its [capture metadata](final/illustrations/ground-qemu/capture.json) records counter 6110, whereas the first quantitative example below has sequence and read counter 83. The screenshot illustrates a later state; it is not a capture of the first quantitative packet.

## Address, register, and MID identify different things

| Identifier | Example | What it selects |
| --- | --- | --- |
| Linux bus | `/dev/i2c-1` | The I²C controller used by the application. |
| Sensor address | `0x48` (decimal 72) | The TMP105 device on that bus; a 7-bit I²C address. |
| Register selector | `0x00` | The temperature register **inside** TMP105. Selecting it returns two bytes. |
| Telemetry MID | `0x0A01` (decimal 2561) | The cFS message published by `eval_temp`; not an I²C address. |
| Payload field | `Value` | The decoded temperature in the telemetry packet. |

The controlled campaign has three devices on bus 1. The [preparation record](final/raw/prepare.json), [raw QEMU reads](final/raw/qemu/sensors.json), and model definitions identify their addresses and measurement registers:

| Sensor | 7-bit address | Measurement register selection | Channels in its sensor packet |
| --- | --- | --- | ---: |
| [TMP105](../../project/drivers/models/tmp105/model.json) | `0x48` | `0x00`: two-byte temperature word | 1 |
| [LSM303DLHC magnetometer](../../project/drivers/models/lsm303dlhc_mag/model.json) | `0x1E` | Six-byte burst starting at `0x03`: X at `0x03–0x04`, Z at `0x05–0x06`, Y at `0x07–0x08` | 3 |
| [MPU6050](../../project/drivers/models/mpu6050/model.json) | `0x68` | Fourteen-byte burst starting at `0x3B`: acceleration X/Y/Z, temperature, angular velocity X/Y/Z | 7 |

For MPU6050, the pairs start at `0x3B`, `0x3D`, `0x3F`, `0x41`, `0x43`, `0x45`, and `0x47`, respectively. Its temperature channel is part of that same read.

For TMP105, the two returned bytes `15 80` both belong to the temperature register selected by `0x00`. **The second byte is not register `0x01`.** Register `0x01` separately selects the configuration byte.

## What the I²C read actually does

Both the [C Linux I²C driver](../../project/drivers/buses/linux_i2c/src/linux_i2c_lib.c) and the independent [register-read helper](../../hardware/sensor_probe.py) submit two messages in one Linux `I2C_RDWR` operation: write the register selector, then read the bytes with a repeated START.

```text
START
  → address 0x48 + WRITE
  → register selector 0x00
  → repeated START
  → address 0x48 + READ
  → first data byte 0x15
  → second data byte 0x80
  → STOP
```

This is a logical transaction diagram, not an electrical waveform captured during the test. It omits acknowledgement bits. Linux receives the 7-bit address `0x48`; the address bytes including the read/write bit would be `0x90` for writing and `0x91` for reading. QEMU emulates the controller and device; Native uses the platform's register-backed transport instead of an electrical bus.

The auxiliary read records the sensor bytes before the collected telemetry samples. It is a separate read, not instrumentation of the exact internal C acquisition that generated a particular packet. The fixed input permits their comparison. The [reproduction instructions](../README.md#register-read-command) explain how to invoke that helper.

## Every byte of one received telemetry packet

The first TMP105 case in [QEMU sensors.json](final/raw/qemu/sensors.json) contains a 36-byte packet with sequence 83 and event ID 1007. The same packet is retained in [downlink.jsonl](final/raw/qemu/downlink.jsonl). Its complete recorded hexadecimal string is:

```text
0a01c053001d000f46d9a6e700000000fc53000000000000530000000000000001000000
```

Byte positions below start at zero. The [compiled catalog](final/raw/qemu/catalog.json) gives the payload's field types, offsets, and total packet size. The measured NASA cFE headers define the [primary telemetry header and four spare bytes](https://github.com/nasa/cFE/blob/3673163b7fd34d7bb69546f1cd13ddb39ac7cde6/modules/msg/option_inc/default_cfe_msg_hdr_pri.h) and the [six-byte secondary time field](https://github.com/nasa/cFE/blob/3673163b7fd34d7bb69546f1cd13ddb39ac7cde6/modules/msg/option_inc/default_cfe_msg_sechdr.h).

| Byte positions | Recorded bytes | Field | Meaning in this packet |
| --- | --- | --- | --- |
| 0–1 | `0A 01` | Message ID/header bits | MID `0x0A01` identifies this telemetry. |
| 2–3 | `C0 53` | Sequence control | Unsegmented packet; sequence 83. |
| 4–5 | `00 1D` | CCSDS length | 29; this field stores total packet bytes minus 7, so 36 bytes here. |
| 6–9 | `00 0F 46 D9` | Time: seconds | Seconds component in the cFE message timestamp. |
| 10–11 | `A6 E7` | Time: subseconds | Fractional component of that timestamp. |
| 12–15 | `00 00 00 00` | Header `Spare[4]` | Explicit padding in the cFE telemetry header. |
| 16–19 | `FC 53 00 00` | `Value`, signed int32 | 21500 thousandths of °C = 21.500 °C. |
| 20–23 | `00 00 00 00` | `Status`, signed int32 | 0: the latest read succeeded. |
| 24–27 | `53 00 00 00` | `ReadCounter`, uint32 | 83 attempted reads. |
| 28–31 | `00 00 00 00` | `ErrorCounter`, uint32 | 0 failed reads. |
| 32 | `01` | `Valid`, uint8 | 1: the latest reading is valid. |
| 33–35 | `00 00 00` | Payload `Reserved[3]` | Reserved bytes, all zero. |

The primary header and timestamp use **big-endian** byte order. The compiled payload in this campaign uses **little-endian** byte order: `FC 53 00 00` represents `0x000053FC`, or 21500. Sensor-register byte order and telemetry-payload byte order are separate contracts.

The sensor address `0x48`, register selector `0x00`, and raw word `15 80` are **not fields in this telemetry packet**. They come from the separately recorded register read. The application sends the interpreted temperature, status, and counters. This distinction matters when drawing a packet diagram.

Run this from the repository root to decode the saved packet without running cFS, QEMU, or hardware:

```bash
python3 - <<'PYCODE'
import json
import struct
from pathlib import Path

records = json.loads(Path('validation/results/final/raw/qemu/sensors.json').read_text())
case = next(row for row in records if row['model'] == 'tmp105' and row['level'] == 0)
packet = case['packets'][0]
wire = bytes.fromhex(packet['hex'])
mid, sequence_control, length = struct.unpack('>HHH', wire[:6])
value, status, reads, errors, valid, r0, r1, r2 = struct.unpack('<iiIIB3B', wire[16:])
print(f'MID=0x{mid:04X}, sequence={sequence_control & 0x3FFF}, bytes={len(wire)}')
print(f'Value={value} -> {value / 1000:.3f} °C')
print(f'Status={status}, ReadCounter={reads}, ErrorCounter={errors}, Valid={valid}')
assert len(wire) == 36 == length + 7
assert (mid, sequence_control & 0x3FFF) == (0x0A01, 83)
assert (value, status, reads, errors, valid, r0, r1, r2) == (21500, 0, 83, 0, 1, 0, 0, 0)
PYCODE
```

The constants in these assertions verify a particular published record; they are not part of the flight driver or its measured output.

## Counting packets and channels

Each sensor packet carries all channels for that sensor. For both [Native](final/raw/native/sensors.json) and [QEMU](final/raw/qemu/sensors.json), the controlled collection contains:

```text
3 input levels × 5 packets per level × 3 sensors = 45 sensor packets per target
```

That is 15 TMP105 packets, 15 magnetometer packets, and 15 MPU6050 packets. One complete input level covers 11 channels: 1 + 3 + 7. Expanding every channel into a table row gives 165 channel observations per target, not 165 packets. Other housekeeping packets and interface captures do not add to this count. The [sample table](final/tables/q2_samples.csv) also includes the separate C HAL register experiment, so its total row count is not the number of received sensor packets.

The [collection procedure](../flight.py) sets the fixed input, reads the registers, locates the first matching sample after the change, then retains the following four distinct samples without filtering out wrong values. All five must satisfy the validity and per-channel limits. Physical MPU6050 acquisition is documented separately: it had no imposed calibrated input and is not included in the controlled 45-packet counts.
