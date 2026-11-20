# Infrastructure and CLI specification

Everything here must work with no browser. The UI is a client of this layer. Findings from a real run of the current code on a clean Linux machine are in `10_AUDIT_FINDINGS.md` (section "Infrastructure run"); fix every item marked "must fix".

## What works today (keep it working)

Verified on a clean Linux x86_64 machine (2 CPUs, 7 GB RAM):
- `./scripts/install-cfs.sh` clones nasa/cFS with submodules and prepares the mission sources.
- `./scripts/setup-native.sh --check` reports missing tools; `./start --no-ui profile --native`, `build`, `run`, `status`, `stop` build and run cFS natively until `CFE_ES_Main entering OPERATIONAL state` (as a normal user; see the `run` false-success bug in `10_AUDIT_FINDINGS.md` E1).
- The ground station sends commands and decodes telemetry and events from the build's own catalog: NOOP round trips pass for sample_app, to_lab, ds, fm, hk, hs, lc, md, sc and the cFE services (sch_lab has no NOOP; that is correct, not an error). sample_app answers with the event "SAMPLE: NOOP command v7.0.2-rc1-oss" and its CommandCounter increases.
- `./start --no-ui app new <name>`, building it, `app delete`, `library new|list|remove`.
- `./start --no-ui simulate-preview --model tmp105` prints a preview with no device attached.
- The unit test suite (79 tests) passes.

## Command line (single entry point)

Keep `./start` as the only entry. Every subcommand prints human progress lines on stderr and, with `--json`, a final machine-readable result on stdout. Exit code 0 on success, non-zero with one clear error line otherwise.

| Command | Exists today | Purpose |
| --- | --- | --- |
| `./start` / `./start --ui [--port N]` | yes | Start the web UI |
| `./start --no-ui source install` | no (today `scripts/install-cfs.sh`) | Clone nasa/cFS and prepare mission sources; idempotent |
| `./start --no-ui setup --target native|qemu|physical [--check]` | partly (scripts) | Install or check prerequisites for a target |
| `./start --no-ui profile --native` / `--board raspi4b --os raspios` | yes | Select the build profile |
| `./start --no-ui build [--target T]` | yes | Build cFS for a target |
| `./start --no-ui run [--target T] [--host H]` | yes | Deploy and start |
| `./start --no-ui stop` / `status` | yes | Stop, show status |
| `./start --no-ui boot --target qemu` | yes | Start the emulator guest |
| `./start --no-ui emulator image|stop|logs` | no | Build or pull the image, stop the guest, follow its console |
| `./start --no-ui ground connect|send|listen|test` | no (tests use `ground_station/round_trip.py`) | Ground link from the terminal: `send sample_app NOOP`, `send to_lab ENABLE_OUTPUT --arg dest_IP=127.0.0.1`, `listen --events`, `test --all-noop` |
| `./start --no-ui app new|delete <name>` / `library …` | yes | Mission modules |
| `./start --no-ui simulate …` / `simulate-preview --model M` | yes | Sensor data |
| `./start --no-ui journey [--reset]` | no | Print the nine steps with done/reachable from evidence |

`scripts/*.sh` become thin wrappers that call `./start --no-ui …`, so there is one implementation of each action.

## Native target

- `run` succeeds only after the OPERATIONAL line is observed (with a timeout); it fails with one clear line on early exit, `OS_QueueCreate` errors (explain `msg_max` and running as a normal user) or the CI_LAB UDP bind error. Ports are checked before starting.
- Pin the NASA cFS revision in one place; `source install` checks out exactly that revision.

- Build in `mission/build-native`; run `core-cpu1` as the normal user; logs to the runtime folder; `status` reports pid and the last OPERATIONAL time.
- Detect a cFS already running on the UDP ports and say so in one line with the command to stop it.
- **Add a sensor transport for Native** (today the Sensor and Test steps say "Emulator required" on Native and every control is disabled). Design: the simulate job writes each device's register values to a file per device in the runtime folder (for example `hardware/.runtime/devices/i2c1-0x48.bin`), and the native build of each driver reads that file where the emulator build reads the I2C bus. Same models, same scenarios, same evidence (`confirmed write` = the file was written and the driver's next telemetry reflects it). Document it in the README.

## Emulator target (QEMU Raspberry Pi 4B)

What the current `Dockerfile` does: builds a patched QEMU 11.1.2 (with the project's I2C sensor devices generated from `project/qemu`), downloads and prepares a Raspberry Pi OS image, converts it to qcow2, and installs the guest provisioning. `scripts/emulator.sh` boots `qemu-system-aarch64 -M raspi4b` with kernel, device tree, initramfs, the qcow2 disk on SD, a serial console, a QMP socket for sensor writes, and `usb-net` with SSH forwarded to port 2222 (published by Docker on 127.0.0.1 only).

Requirements:
- `./start --no-ui emulator image` first tries `docker pull ghcr.io/raiagues/cfs_emulator:<fingerprint>`; only if that fails does it build locally, printing an honest time estimate (QEMU compile takes tens of minutes on 2 cores) and the build log path.
- The image tag includes the sensor-model fingerprint (`project/qemu/generate.py --fingerprint`), as the CI workflow already does; the CLI and the UI use the same function to compute it.
- Without KVM the guest is slow; boot time is measured and shown, never hidden behind a spinner with no time.
- Works on Linux with Docker Engine, on macOS with Docker Desktop (pass `--platform linux/amd64` only where needed) and on WSL2; document each in the README.
- No root assumptions on the host: the user must be in the `docker` group; say so if not.
- SSH: one key per checkout in the runtime folder; host key pinned per disk; recreating the disk updates the pin with an explicit message, never a silent `StrictHostKeyChecking=no`.

## Physical target

- 64-bit Raspberry Pi OS on a Pi 4B with SSH enabled. `setup --target physical --check` verifies reachability, user, key and permissions to install the service (`cfs.service`).
- Build ARM64 against the board's glibc: build inside `debian:bookworm-slim` (Raspberry Pi OS Bookworm has glibc 2.36) or check the binary's required glibc before upload and refuse with a clear message. Copy with `scp`, install the service to run as the user (not root), start it, and wait for OPERATIONAL in its log.

## Ground link

- Commands to ci_lab over UDP, telemetry from to_lab over UDP. Ports and addresses come from the build configuration and one defaults module, overridable by environment variables.
- The command catalog is generated from the build (message IDs, function codes, structures), never from a hand-written list.

## Sensors and scenarios (no UI)

- Models live in `sensors/` (tmp105, mpu6050, lsm303dlhc magnetometer) with `schema.py` and `signals.py`; scenarios can be described in a file and run with `simulate`.
- On the emulator, values are written through QMP to the generated QEMU devices; on native, through the new file transport above; on the board, real devices are read.

## Logs and errors

- Every job writes a log file and streams lines. A failure ends with one line that names the failing step and the fix ("Docker is not running. Start it with: sudo systemctl start docker").
- No `time.sleep` polling loops to wait for a process; wait on the process, the socket or the log line.
