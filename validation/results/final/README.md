# Technical evaluation — November 23, 2026

The final campaign exercised the backend without a browser during measurements. Captures in `illustrations/` were taken afterward using the real QEMU mission and are excluded from the quantitative counts.

- Executed code and protocol: [`64add2472dbf6869563612cf6b2c427b181dba5d`](https://github.com/Raiagues/cfs_emulator/tree/64add2472dbf6869563612cf6b2c427b181dba5d).
- Official NASA source: [`a4d305dc06fb7d468f5b45214d9f730b97d4bd77`](https://github.com/nasa/cFS/tree/a4d305dc06fb7d468f5b45214d9f730b97d4bd77), downloaded through the public installer. All 4,458 original tracked files remained unchanged through the end of the campaign.
- Original data-publication revision: [`3cb304040b4080cbf43807046308c954e06c70b1`](https://github.com/Raiagues/cfs_emulator/tree/3cb304040b4080cbf43807046308c954e06c70b1). It follows the executed revision and includes postprocessing and data without changing the measured flight code. This English documentation update preserves the historical measurements.
- [Protocol and reproduction commands](../../README.md), [templates and scripts](../../../project/README.md#templates-and-script-index), [verifiable summary](tables/summary.json), [copy manifest](procedure/package-manifest.json), and [file SHA-256 hashes](SHA256SUMS).

## Results and evidence locations

| Question | Observed result | Evidence |
| --- | --- | --- |
| Q1 — command responses | 36/36 transmissions confirmed on each target; 108/108 overall. Four applications, three repetitions of NOOP → RESET_COUNTERS → NOOP. | [Each attempt and its counters](tables/q1_attempts.csv), [counts by application/command](tables/q1_commands.csv); `raw/{native,qemu,physical}/commands.json`, catalog, and `downlink.jsonl`. |
| Q2 — known inputs | C HAL: 27 runs and 405 acquisitions, including the Q3 absence intervals. Native and QEMU: nine cases and 45 sensor packets per target; valid values within per-channel limits. | [Inputs and outputs](tables/q2_samples.csv), [errors and limits](tables/q2_errors.csv), `raw/registers/registers.json`, `raw/{native,qemu}/sensors.json`. |
| Q3 — absence reported as an invalid reading | Nine HAL interruptions: 45 invalid readings and recovery on the first C acquisition. Three Native interruptions: 15 invalid packets; a valid return observed between 1.879 and 1.895 s, within the 8 s limit. Board: five invalid packets from each of the two absent sensors. | [Interruptions](tables/q3_interruptions.csv), [HAL acquisitions](tables/q3_hal_samples.csv), [UDP recovery](tables/q3_recovery.csv), `raw/native/dropout.json`, `raw/physical/sensors.json`. |
| Q4 — identical ARM artifacts | 63 identical files on both targets: one executable, 24 modules, 37 tables, and one startup file. The same build fingerprint. | [Per-file hashes](tables/q4_artifacts.csv), `raw/{qemu,physical}/artifacts.json`. |
| Q5 — descriptive timing | Ten Native development cycles, ten cFS starts per target, five QEMU guest boots, and one full build per architecture. | [Individual durations](tables/q5_timings.csv), [N, minimum, median, IQR, and maximum](tables/q5_statistics.csv), `raw/*/metrics.json`, and corresponding logs. |

The 1,650 rows in `q2_samples.csv` are **per-channel** observations, not 1,650 packets. Only the MPU6050 is connected to the board: five valid packets with seven channels described in [physical_readings.csv](tables/physical_readings.csv). The operator reported that it was stationary on the floor; its orientation was uncontrolled. There is no metrological reference or accuracy comparison with the emulator.

The memory-backed TMP105 uses 12 bits and a 0.0625 °C step, with rounding. The QEMU model retained configuration `0x00`, 9 bits, and a 0.5 °C step, with truncation; the protocol limit is 0.501 °C. The [configuration register reading](raw/qemu/tmp105-configuration.json) records this condition. Each error is evaluated against its environment's limit without assuming equivalent quantization.

## Timing boundaries

| Operation | N | Median (s) | Minimum–maximum (s) |
| --- | ---: | ---: | ---: |
| Create a Native app | 10 | 1.568 | 1.268–1.720 |
| Incremental Native build | 10 | 32.164 | 31.691–76.395 |
| Delete a Native app | 10 | 2.622 | 2.620–2.673 |
| Start Native cFS until first HK | 10 | 8.610 | 8.445–8.867 |
| Start QEMU cFS until first HK | 10 | 29.806 | 29.297–30.346 |
| Start physical cFS until first HK | 10 | 14.923 | 14.837–15.365 |
| Prepared QEMU boot, deployment, and first HK | 5 | 101.900 | 101.203–114.895 |

On ARM targets, `run` includes transfer and deployment. The CSV separates `payload_transfer`, `operational_observed_s`, `run_total_s`, `ground_to_first_hk_s`, and `total_to_first_hk_s`. OPERATIONAL and SSH are observations made on the host. Across the five boots, the median boot job duration was 73.096 s; SSH was observed at 69.267 s. These phases are not instrumented internal guest times.

Full builds took 82.974 s (Native) and 122.082 s (ARM), N=1 each. Mission restoration after the ten cycles is excluded from their statistics. ARM compiler preparation, the QEMU image, and initial disk provisioning are recorded separately in `raw/setup-builder/`, `raw/setup-qemu-image-final/`, and `raw/first-boot-qemu/`; they are excluded from the five boot repetitions. Compiler preparation used cached Docker layers.

Measured operations ran sequentially with one build worker. The desktop and local platform service remained available; background load was not strictly controlled. Repetitions share files and caches. Measurements are descriptive, without inference of statistical improvement or generalization. This campaign contains no orbital or eclipse experiment.

## Reproduce the tables and verify integrity

From the checkout containing this publication:

```sh
python3 -B -m validation.summarize \
  --campaign validation/results/final/raw \
  --output /tmp/flight-tables-reproduced
cd validation/results/final
sha256sum -c SHA256SUMS
```

The output directory must be new. `summary.json` identifies each input by SHA-256, the executed revision, and the analyzer hash. Summary generation timestamps may change; the 11 CSVs must have identical content. To repeat the experiments, follow the [protocol](../../README.md) in an isolated mission. Coordinators in `procedure/` preserve this collection's procedure with explicit local paths that must be adapted to the new directory; configure SSH access privately.

Raw records preserve their bytes, values, durations, sequences, and messages. The manifest records the published selection and copy checks. The NASA checkout, builds, Docker images, disks, and runtime database remain outside Git. The postprocessing library is `validation/summarize.py`; its tests in `interface/tests/test_evaluation_summary.py` use synthetic data only to verify the analyzer.

The [TMP105 telemetry figure](illustrations/ground-qemu/ground-qemu-eval_temp-telemetry.png) shows actual fields received after collection. `Value=31500` is the telemetry integer in thousandths of a degree Celsius, equivalent to 31.5 °C. Counts from that illustration session do not replace the 108 measured commands. The [capture record](illustrations/ground-qemu/capture.json) contains packets, MIDs, hashes, and route provenance from the source code; the displayed tutorial is at an intermediate stage, and the interface remains under development.
