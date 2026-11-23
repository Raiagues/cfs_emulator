# Final technical evaluation

This protocol exercises the backend without a browser. Each result must come from a new run with a frozen platform commit, an identified official NASA checkout, and an independent mission. Unit tests verify the harness; their temporary data are not study results.

The harness only modifies missions with an `.evaluation.json` marker created by `prepare`. Do not copy a mission or artifacts from a previous run. All builds use one job. Each output directory must be new; a failure preserves partial evidence and returns an error without artificially completing the counts.

## Questions and criteria

| Question | Final procedure | Criterion |
| --- | --- | --- |
| Q1 | Three repetitions of NOOP → RESET_COUNTERS → NOOP for `sample_app`, `eval_temp`, `eval_mag`, and `eval_mpu` on each target. | Each command receives an application EVS event and subsequent housekeeping with a distinct sequence number. NOOP increments CommandCounter; RESET clears the counters; the following NOOP produces 1. UDP transmission alone does not confirm execution. There are 36 commands per target. |
| Q2 | Three constant input levels per sensor, with five distinct packets per level on Native/QEMU. The C HAL uses constants and steps in memory-backed registers, with three repetitions of 15 readings per scenario and sensor. | Differences remain within model quantization and output rounding limits; inputs, raw registers, telemetry, and units are preserved. |
| Q3 | C HAL: five valid readings, five readings during interruption, and five recovered readings; three repetitions per sensor. Native cFS: make only the isolated mission's sensor register file unavailable, collect five invalid readings, and restore it. | Nonzero status and an invalid reading during absence; the first HAL reading after restoration is valid. On Native, record every packet received after restoration until the first valid sample, subject to the explicit timeout. On the board, the connected sensor reports valid readings and absent sensors report invalid readings. |
| Q4 | One ARM build used on QEMU and the board; hashes for each local and installed file. | Identical files and the same fingerprint, with any difference declared. The Native executable is not claimed to be binary-identical to ARM. |
| Q5 | Ten Native create app/incremental build/delete cycles; ten cFS starts per target; five complete QEMU guest boots. Full Native and ARM builds: N=1 each. | Descriptive measurements: N, median, inclusive IQR, minimum, and maximum. No inference of statistical improvement or generalization. |

Physical acquisition uses the MPU6050, which the operator reported as stationary on the floor. Its orientation is uncontrolled. Measurements are descriptive, without calibration or an accuracy comparison with QEMU. The absent TMP105 and magnetometer must continue responding to commands while reporting invalid readings.

There is no orbit, eclipse, or spacecraft dynamics interpretation. `protocol.py` fixes the levels before collection: TMP105 temperatures approximately −3 to 32 °C, magnetic fields in tens of µT, acceleration near 1 g with different vectors, and small angular velocities. These synthetic levels do not attempt to reproduce the physical setup's orientation.

## Preparation and registers

Run from the final committed revision. `prepare` uses `git archive HEAD` and the public NASA installer, followed by the public profile, bus, sensor, app, and HAL commands. The copy's `cFS/` and `mission/` directories are not published.

```sh
python3 -B -m validation prepare --directory /tmp/flight-evaluation-final
python3 -B -m validation registers \
  --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/registers
```

Optionally, `prepare --source-copy /path/to/cFS` creates an independent copy of an existing clean official checkout. In that case, the report states that there was no new network download. Do not use this option to claim validation of installation over the network.

The register experiment compiles the platform's C HAL and memory-backed bus adapter. It comprises 27 runs and 405 readings, including 45 readings during nine scheduled interruptions. Each sample's 256 raw bytes, status, and effective reading are recorded; errors are not presented as valid values. Compiler, source, and model versions or hashes are recorded. The sample index is not a measured time.

## Coordinated target execution

Before starting, configure authorized SSH access and the available QEMU image in the copy's private runtime. Never publish keys, tokens, or the connection dictionary. Stop the normal-use mission before evaluation. An operator must coordinate these commands sequentially; the harness does not remove unrelated containers or processes.

```sh
python3 -B -m validation build --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/build-native --target native
python3 -B -m validation cycles --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/cycles-native
python3 -B -m validation starts --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/starts-native --target native --leave-running
python3 -B -m validation target --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/native --target native
```

The `target` command collects from an already running mission; it does not build or start cFS. On completion, it closes only its own Ground Station connection. Stop the mission with `start --no-ui stop --target native` from the **copy** before proceeding to the next target.

Before measuring the ARM build, prepare the `cfs-builder` image defined by the Dockerfile and record its command, duration, and identifier in `setup-builder/`. The compiler must already be available, as with the Native build; the product's image cache check remains part of the build measurement. Compile ARM once with `validation build --target qemu`. Prepare the image, disk, and SSH access once, recording their actual identifiers. The QEMU image must contain the model fingerprint required by `project/qemu/generate.py --fingerprint`; its preparation is a prerequisite recorded separately in `setup-qemu-image/`, not one of the five boot measurements. `validation boots --target qemu --leave-running` measures five boots of a previously shut-down guest, using the same persistent disk and image. Record the initial disk-provisioning boot separately if it has not yet occurred; it is not interchangeable with the five boots using a prepared disk.

After stopping cFS without shutting down the guest, `validation starts --target qemu --leave-running` measures ten starts; `validation target --target qemu` collects commands and sensor data. Shut down QEMU before testing the board. The board reuses the ARM artifacts without recompilation: ten starts with `starts --target physical --leave-running`, followed by `target --target physical`. No phase powers off the physical board.

Each `run` includes the product's transfer and deployment. The report provides `payload_transfer` separately, the first observed OPERATIONAL line as a distinct metric, total `run` time including other steps, the interval from Ground connection/ENABLE_OUTPUT to the first HK, and total time to HK. QEMU boot ends after SSH verification and stopping any preexisting guest service. Log times are observations made on the host, not internal QEMU execution timestamps.

The ten incremental cycles require a prior Native build. After the tenth deletion, a restoration build of the baseline mission is marked separately and excluded from the ten measurements. If a run exceeds feasible resources or time, record the failure and explicitly revise the protocol before repeating; do not silently reduce N.

## Incremental builds for the shared QEMU/physical profile

The platform has three execution targets: Native, QEMU and the physical board. QEMU and the board use the same cross-compiled artifacts. ARM64 names their architecture, not an additional execution target. App creation and deletion operate on shared sources on the host; they do not execute on a guest or board.

The [compilation procedure](compilation.py) measures ten incremental cycles for the shared QEMU/physical build profile. It requires a newly prepared independent mission, with no existing ARM build, and a committed measurement procedure. It records a baseline build before the cycles and a restoration build afterward, outside the ten incremental measurements. Every cycle creates an app, builds with `--target qemu`, and deletes the app. The procedure records before/after source manifests, preserves all observed durations, and retains raw logs, per-cycle times, and exact procedure/platform revisions. After the baseline build and before any timed cycle, it copies the mission definitions and any module-selection file to `<measurements>/baseline-reference/`. Keep these bytes for the separate source audit; this copy is outside the measured operations. Builds use one worker; it does not boot QEMU or contact a physical board.

For the published mission revision, run from a checkout containing the compilation procedure:

```sh
git worktree add --detach /tmp/flight-platform-frozen 64add2472dbf6869563612cf6b2c427b181dba5d
python3 -B -m validation prepare --source /tmp/flight-platform-frozen --directory /tmp/flight-q5-fresh
python3 -B -m validation.compilation --workspace /tmp/flight-q5-fresh/flight --output /tmp/flight-q5-measurements --repetitions 10
```

Each directory must be new. `prepare --source-copy /path/to/clean/cFS` can use an independent copy of a verified local NASA checkout and records that source method.

The collection ends with a strict byte-identity check of the restored sources. Its result is separate from the success and timings of the 32 CLI operations. Creating and deleting modules can leave generated module-selection guards in the mission definitions. If all 32 commands succeeded and only this final byte check failed, retain the original `metrics.json` unchanged and run the committed [source audit and analysis](compilation_summary.py):

```sh
python3 -B -m validation.compilation_summary \
  --workspace /tmp/flight-q5-fresh/flight \
  --measurements /tmp/flight-q5-measurements \
  --reference /tmp/flight-q5-measurements/baseline-reference \
  --output /tmp/flight-q5-analysis
```

The analysis rejects missing, failed, reordered, or inconsistent command records. It verifies the recorded baseline hashes, unchanged app/configuration/startup definitions, empty module overrides, absence of cycle apps, and equality of the four preprocessed tables for both configured CPUs. Only the expected persistent integration scaffolding is accepted. A final analysis summary keeps `byte_identical=false`, the original collection status and hash, and separate measurement/analysis revisions. It exports the statistics from all ten successful cycles, preserving slow observations and excluding prerequisite/restoration builds. Other failures require investigation and do not become final results through this analysis.

The [shared-profile compilation results](results/q5-compilation/README.md) complement the [mission evaluation](results/final/README.md). Host source operations, build destinations, and runtime targets are reported separately; the shared build is counted once.

## Evidence and publication

Preserve `prepare.json`, `nasa-before.json`, `sources.json`, `commands.json`, build/start logs, `catalog.json`, `downlink.jsonl`, sensor/register records, `artifacts.json`, and `metrics.json`. Packets contain original bytes, MID, CCSDS sequence, reception time, decoded fields, and errors. Private connections are not serialized; review logs before publication without changing measured values, bytes, or durations.

Only the completed campaign belongs in `validation/results/final/`; diagnostic attempts remain outside that directory. Generate a SHA-256 manifest of published files and record the harness commit. NASA source, Docker images/disks, builds, and private runtime remain outside Git. A code change after freezing the revision requires identifying the new revision and repeating the affected final evidence.

Each build records an input manifest before measurement. At the end of the incremental cycles, another manifest records the restored mission; the initial preparation manifest does not replace these later records.

## Register read command

Remote dumps use the same public helper, `hardware/sensor_probe.py:READ_REGISTERS`: Linux `I2C_RDWR` transactions with a repeated START, register pointer, and block read. Each evidence record stores `bus`, `address`, register/length pairs, and received bytes. The equivalent terminal command, using a previously authorized SSH alias, is:

```sh
# Example MPU6050 arguments: a 0x3b/14-byte burst, control registers, and WHO_AM_I.
python3 - "$SSH_TARGET" "$BUS" "$ADDRESS" "$BLOCKS_JSON" <<'PYTHON'
import shlex, subprocess, sys
from hardware.sensor_probe import READ_REGISTERS
command = shlex.join(['python3', '-c', READ_REGISTERS, *sys.argv[2:]])
subprocess.run(['ssh', sys.argv[1], command], check=True)
PYTHON
```

`BUS=1`, `ADDRESS=104`, and `BLOCKS_JSON='[[59,14],[107,1],[108,1],[27,1],[28,1],[117,1]]'` identify the protocol's MPU6050. The harness uses the same arguments, quoted with `shlex.join`; it does not publish the host or key path. On Native, the dump reads `hardware/.runtime/devices/i2c1-0x68.bin` in the isolated copy, the register image consumed by the native C transport.

A missing dump on Native, QEMU, or the physical MPU6050 fails the case; disconnected physical sensors may record `unavailable` with an I/O error. Native recovery is bounded by `min(timeout, max(5 s, 3 × acquisition period + 2 s))`, with the period and table used preserved in JSON. The test records transient packets until a valid reading returns. Only the synchronous HAL experiment verifies the first C call after restoration.

## Generate tables from the complete campaign

After completing every phase, run postprocessing into a new directory:

```sh
python3 -B -m validation.summarize \
  --campaign /tmp/flight-evaluation-final \
  --output /tmp/flight-evaluation-tables
```

The command verifies case counts, command order, subsequent events and counters for each transmission, sensor tolerances, interruptions, and ARM artifact hashes. An incomplete or inconsistent campaign does not produce a final output. The 11 CSVs, `summary.json`, and `examples.json` retain links to input files through SHA-256. The summary does not change original packets, durations, or values.

| Question | Raw records | Generated tables |
| --- | --- | --- |
| Q1 | `<target>/commands.json`, `<target>/downlink.jsonl`, and catalog | `q1_commands.csv`, `q1_attempts.csv` |
| Q2 | `registers/registers.json`, `<target>/sensors.json`, register dumps | `q2_samples.csv`, `q2_errors.csv`, `physical_readings.csv` |
| Q3 | `registers/registers.json`, `native/dropout.json`, `physical/sensors.json` | `q3_interruptions.csv`, `q3_hal_samples.csv`, `q3_recovery.csv` |
| Q4 | `qemu/artifacts.json`, `physical/artifacts.json` | `q4_artifacts.csv` |
| Q5 | `build-*/metrics.json`, `cycles-native/metrics.json`, `starts-*/metrics.json`, `boots-qemu/metrics.json`, and logs | `q5_timings.csv`, `q5_statistics.csv` |

For publication, keep raw data in `validation/results/final/raw/` and tables in `validation/results/final/tables/`, with an index and SHA-256 manifest. Postprocessing can be repeated with `raw/` as `--campaign`. The executed code revision is recorded in `raw/prepare.json`; the later results-publication revision must be identified separately. Do not include the `flight/` workspace, images/disks, SSH keys, or runtime database.
