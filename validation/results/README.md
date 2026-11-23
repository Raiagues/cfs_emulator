# Reading the validation results

The quantitative results come from backend procedures without a browser. Later interface illustrations are packaged separately. There are three execution targets: **Native**, **QEMU**, and the **physical Raspberry Pi**. In raw records they are named `native`, `qemu`, and `physical`. ARM64 describes the shared architecture of the last two; it is not a fourth target.

## Start here

| Package | What it contains |
| --- | --- |
| [Command sequence captures](illustrations/q1-sequence/README.md) | Four real HK panels (0 → 1 → 0 → 1), the corresponding literal cFS log, and capture metadata; a later illustration outside the quantitative sample. |
| [Sensor encoding guide](SENSOR-ENCODING.md) | Fixed inputs, sensor addresses and registers, scaled units, the full received packet, and a read-only decoding example. |
| [Final campaign](final/README.md) | The primary Q1–Q5 evidence: commands, sensor readings, interruptions, installed-file comparisons, and timings. `raw/` holds observations and logs; `tables/` holds summaries derived from them. |
| [Compilation supplement](q5-compilation/README.md) | Ten additional incremental build cycles for the profile shared by QEMU and the physical board. `cycles/` contains the operations and logs; `analysis/` contains the source audit and derived tables. It supplements the final campaign without replacing its records. |
| [Interface illustrations](final/illustrations/ground-qemu/) | Captures taken after the measured campaign. They illustrate the interface and do not add observations to the quantitative results. |
| [Native NOOP illustration](illustrations/q1-native/README.md) | A later real interface capture of one NOOP, its application event, and the counter change from 1 to 2. It is separate from the 108 measured Q1 transmissions. |

## Five questions

| Question | What was checked | Where to look |
| --- | --- | --- |
| **Q1 — Did each application answer?** | A command must produce the application's event and a later housekeeping packet with the expected counters. Sending a UDP packet alone is insufficient. | [Individual commands and counters](final/tables/q1_attempts.csv); full packets in `final/raw/{native,qemu,physical}/commands.json`. |
| **Q2 — Did the reading match the known input?** | Controlled inputs were compared with decoded readings in memory-backed registers, Native, and QEMU, using each model's resolution. The physical MPU6050 was observed without a calibrated reference or controlled orientation. | [Inputs and readings](final/tables/q2_samples.csv), [errors and limits](final/tables/q2_errors.csv), [physical readings](final/tables/physical_readings.csv). |
| **Q3 — Was an absent sensor reported as invalid?** | The C HAL and Native mission were checked during interruption and recovery. On the board, the connected MPU6050 was valid and the two absent sensors were invalid. | [Interruptions](final/tables/q3_interruptions.csv), [C acquisitions](final/tables/q3_hal_samples.csv), [Native recovery](final/tables/q3_recovery.csv). |
| **Q4 — Were the same files used on QEMU and the board?** | The installed executable, modules, tables, and startup file were compared by SHA-256. | [File-by-file comparison](final/tables/q4_artifacts.csv). |
| **Q5 — How long did the operations take?** | Source editing, compilation, starting cFS, and starting the QEMU guest were timed separately. | [Campaign timings](final/tables/q5_timings.csv), [shared-profile build timings](q5-compilation/analysis/q5_timings.csv). |

The sensor table contains one row per channel, not one row per packet. The physical readings demonstrate acquisition; they do not establish sensor accuracy or equivalence to emulator inputs.

## What the timing names mean

- **Create/delete an app:** scripts edit sources on the host computer. These operations are common to all targets and are not repeated measurements on each board.
- **Full/incremental build:** the host compiler prepares the program. Native has its own build; QEMU and the physical board share one build profile. A full build starts without an existing build; an incremental build recompiles after an app is added.
- **Start cFS until first HK:** the target's operating system is already available. The interval includes the run/deployment steps and ends when Ground receives the first housekeeping (HK) status packet. Each of the three targets has its own series.
- **QEMU boot until first HK:** starts with the guest shut down and an already prepared disk. It includes guest boot, deployment, starting cFS, and reception of the first HK packet.
- **Image preparation/first provisioning:** one-time setup recorded separately; it is not part of the repeated prepared-disk boots.

The tables retain every measured duration. `n` means repetitions; `median` is the central value after sorting the times (the mean of the two central values for an even count); `min` and `max` give the observed range. `iqr` describes the spread of the middle half of the observations. Full builds have one observation each. The repeated measurements are descriptive; they do not establish a performance improvement. Builds used one worker.

## One sensor reading, from input to packet

For a complete register and packet diagram, all byte offsets, and a reproducible decoder, read the [sensor encoding guide](SENSOR-ENCODING.md).

The first case in [QEMU sensor records](final/raw/qemu/sensors.json) follows this path:

```text
Set TMP105 input to 21.537 °C through QEMU's qom-set
  → I²C bus 1, sensor address 0x48, register 0x00
  → read two bytes: 15 80
  → C driver converts the value to 21.500 °C
  → eval_temp publishes telemetry; Ground receives it
```

Below are **selected fields from the recorded JSON**, not a literal terminal transcript. Other fields and packets are omitted.

```json
{
  "expected_scaled": {"temperature": 21537},
  "raw_registers": {
    "bus": 1,
    "address": 72,
    "blocks": [{"register": 0, "size": 2, "hex": "1580"}]
  },
  "packets": [{
    "mid": 2561,
    "sequence": 83,
    "values": {"Value": 21500, "Status": 0, "Valid": 1}
  }]
}
```

Temperatures use thousandths of a degree Celsius: `21500` means 21.500 °C. The difference from the requested input is 0.037 °C. Decimal `72` is I²C address `0x48`; decimal `2561` is telemetry MID `0x0A01`. These identify different things. `Valid=1` and `Status=0` indicate a valid, successful read. The same received packet is preserved in [downlink.jsonl](final/raw/qemu/downlink.jsonl), with `event_id=1007`.

The [collection procedure](../flight.py) sets the input and invokes [READ_REGISTERS](../../hardware/sensor_probe.py), which selects register `0x00` and reads two bytes using Linux `I2C_RDWR`. The [register command instructions](../README.md#register-read-command) use the same helper; for this example the arguments are bus `1`, address `72`, and blocks `[[0,2]]`. The [TMP105 model](../../project/drivers/models/tmp105/model.json) and [C decoder](../../project/drivers/hal/src/hal_sensor.c) give `0x1580 × 1000 / 256 = 21500`. A separate [configuration read](final/raw/qemu/tmp105-configuration.json), taken after quantitative collection without changing the configuration, records 9-bit operation. The memory-backed case uses a different resolution; compare each result with its own limit.

## One confirmed command

The first entry in [QEMU command records](final/raw/qemu/commands.json) sends `SAMPLE_APP_NOOP_CC` with bytes `1882c000000100a4`. Selected recorded values are:

```text
Application: sample_app
Command: NOOP
Event: SAMPLE: NOOP command v7.0.2-rc1-oss
CommandCounter: 0 → 1
CommandErrorCounter: 0 → 0
Housekeeping sequence: 2 → 3
```

This is a readable summary of the `sent`, `baseline`, `event`, and `housekeeping` objects, not terminal stdout. The newer event and changed counter establish that the application handled the command. The [procedure](../flight.py) rejects stale events and packets.

## Revisions and reproduction

The measured platform revision is [`64add2472dbf6869563612cf6b2c427b181dba5d`](https://github.com/Raiagues/cfs_emulator/tree/64add2472dbf6869563612cf6b2c427b181dba5d), recorded with the official NASA revision in [prepare.json](final/raw/prepare.json). The original data publication is [`3cb304040b4080cbf43807046308c954e06c70b1`](https://github.com/Raiagues/cfs_emulator/tree/3cb304040b4080cbf43807046308c954e06c70b1). A later documentation or publication commit does not mean that its application code was measured.

The compilation supplement uses the same measured platform with separate measurement (`f6beb5f…`) and analysis (`fbf5390…`) revisions, fully recorded in its [summary](q5-compilation/analysis/summary.json); it was published at [`46711b4`](https://github.com/Raiagues/cfs_emulator/commit/46711b4cc9bc9b7bfc115f1ddc3d5e04e5d369a7). Its source audit distinguishes equivalent generated tables from byte-identical sources.

To repeat the work, follow the [protocol and commands](../README.md) with a new isolated mission and output directories. The [template/script index](../../project/README.md#templates-and-script-index) identifies platform changes; the [fixed inputs](../protocol.py), [C register experiment](../registers.py), [target collection](../flight.py), and [timing procedure](../metrics.py) identify the experiments. Supplemental compilation has its own [procedure](../compilation.py) and [analysis](../compilation_summary.py).

To check existing evidence without rerunning hardware, use the checksum and table-reproduction commands in the [final package](final/README.md#reproduce-the-tables-and-verify-integrity) and the [supplement](q5-compilation/README.md#reproduce). `SHA256SUMS` verifies published files; summaries identify their source records. The original bytes, values, timestamps, and durations remain in the raw records.
