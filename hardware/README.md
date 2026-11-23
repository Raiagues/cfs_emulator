# Execution and hardware

Flight Studio runs cFS on local Linux, a QEMU Raspberry Pi 4B or a physical Pi with ARM64 Raspberry Pi OS. The interface and CLI share [HardwareManager](manager.py), which checks for this project's running cFS instances before starting another.

In **Hardware**, Native represents the local computer; Emulator and Board show the selected board and configured devices. **2D → Pinout** shows the 40 physical header numbers and their signals. On an empty board, begin with **Add bus**, then **Connect sensor**. **Link HAL** connects a device to an app reader. See the [installation guide](../README.md).

| Target | Build environment | Runtime |
| --- | --- | --- |
| Native | Local Linux compiler | Local `core-cpu1` process |
| Emulator | ARM64 cross-compiler in `cfs-builder:local` | `cfs.service` in the emulated Raspberry Pi OS |
| Board | The same ARM64 flight profile | `cfs-studio.service` on the SSH-connected Pi |

All targets use the independent NASA checkout in `cFS/` and definitions in `mission/`. Connection settings and execution records live locally in `hardware/.runtime/`; the board and OS choices are in `project/config.json`. OpenSSH manages identities.

## Studio and mission lifecycle

`./start` starts or reuses this workspace's web server. `./stop.sh` stops only that server and is safe to repeat. Use matching `--port N` arguments for a nondefault Studio port. These web-server actions do not require SSH.

Stop the mission with `./start --no-ui stop --target native`, `qemu` or `physical`. Shut down QEMU with `./start --no-ui emulator stop`. Shutting down a physical board requires the explicit `./start --no-ui shutdown --target physical` action.

## Native

```sh
./start --no-ui profile --native
./start --no-ui build
./start --no-ui run --no-follow
./start --no-ui logs
./start --no-ui stop
```

Build products are installed in `mission/build-native/exe/cpu1/`. Process output also goes to `hardware/.runtime/native.log`. Selecting Native preserves the configured board profile and sensors for other targets. Hardware readers use the devices available on this host.

`run` returns after startup by default. Add `--follow` to follow logs. Ctrl+C stops following the log; `stop` stops cFS. Builds default to one worker.

## Emulator

Choose the emulator image and local SSH port in setup. Once the environment is prepared, use the Raspberry Pi 4B profile:

```sh
./start --no-ui profile --board raspi4b --os raspios
./start --no-ui build --target qemu
./start --no-ui boot --target qemu
./start --no-ui run --target qemu --no-follow
./start --no-ui stop --target qemu
./start --no-ui shutdown --target qemu
```

**Start emulator** creates a container specific to this checkout. QEMU uses `raspi4b` and the persistent disk `board/raspios.qcow2`. The configured SSH port is published on host loopback, reaches container port 2222 and is forwarded to guest port 22.

Guest Linux sees four Pi cores. Studio applies systemd's temporary `AllowedCPUs` property to constrain the cFS service to virtual core 1, leaving other cores available for kernel and network activity. Custom images must retain four cores and cgroup v2's `cpuset` controller.

After SSH becomes available, Studio checks systemd and processes to identify the mission state. If the first query times out, a second allows up to 30 seconds. Ground Station performs the same check before connecting and requires the process to belong to the cFS service. An inconclusive response blocks the operation with a connection error.

Client keys live in `hardware/.runtime/ssh/`. To reuse an older disk associated with `~/.ssh/cfs-emulator/`, set `FLIGHT_STUDIO_EMULATOR_KEYS` to that directory and run `./start --no-ui emulator key` before starting Studio in the same environment. At boot or resume, Studio checks the Docker disk mount and published port, obtains the guest's public host key through the container's internal port and writes `board/known_hosts`. Subsequent SSH connections must present that key. A newly created guest disk has a new identity.

A new project has an empty `buses` list. QEMU boot generates `board/mission.dtb` from the kernel device tree and enables configured buses. Restart QEMU after changing devices, buses or addresses. Board, OS and emulator infrastructure changes require QEMU to be stopped. To retry an already booting guest's SSH connection, use `./start --no-ui boot --target qemu --retry`.

Boot logs are in `logs/latest.log`; follow them with `./start --no-ui logs --target qemu --kind boot`. A stopped container retains its output until the next boot. The `./boot.sh` and `./logs.sh` shortcuts start the guest and follow its console. `./stop.sh` is reserved for the Studio web server.

The ARM64 payload is in `mission/build-flight/exe/cpu1/`. **Run cFS** uploads it over SSH to a temporary guest directory, activates it, starts the service and checks status. Confirm `OPERATIONAL` in flight logs and inspect [Ground Station responses](../ground_station/README.md#sending-a-command-and-confirming-its-response).

## Physical board

In **Physical board** setup, supply the SSH host or alias, user, port and mission directory relative to the remote user's home. An identity file is optional. **Test SSH** queries model, architecture, OS, device nodes and service state. **Prepare cFS service** installs authorization for the Studio service.

```sh
./start --no-ui profile --board raspi4b --os raspios
./start --no-ui connect --target physical --host raspberrypi.local --user pi
./start --no-ui build --target physical
./start --no-ui run --target physical --no-follow
./start --no-ui stop --target physical
```

Host and user values are examples. The CLI also accepts `--ssh-port`, `--identity-file` and `--directory`. With passwordless sudo, Studio prepares the service and verifies readiness; otherwise setup provides a command to run interactively. The service runs `core-cpu1` as the SSH user in `studio/current/cpu1` under the mission directory. Deployment checks executable and library glibc requirements before uploading. The sudo rule covers service administration, its journal, `i2c-dev` loading and Linux shutdown. See [setup_board.py](setup_board.py).

Each upload gets a new `releases/` directory. Activation switches `studio/current`, starts the service and verifies it. Failure restores the previous link and preserves the upload for inspection. After successful startup, Studio retains the current and previous versions; cleanup only touches older releases with valid names and activation markers. See [activate_release.py](activate_release.py).

Sensor readers use the board's physical devices. Failed acquisition publishes `Valid = 0` and an error in `Status`; for example, `-2` (`ENOENT`) means that the requested device node is absent. Check I²C configuration, bus and address.

An isolated sensorless profile can exercise the remaining mission on a board without the configured sensors:

```sh
./start --no-ui build --target physical --sensorless
./start --no-ui run --target physical --sensorless --no-follow
```

Studio copies upstream sources and local definitions into `hardware/.runtime/sensorless/`, removes reader apps and devices from that copy, builds it and selects a matching packet catalog. The main project's links remain intact.

## Bus and Python integration

A board defines its buses; a chip model defines registers and channels. Linking a device to an app selects the required libraries. See [HAL and models](../project/drivers/README.md), [Linux I²C](../project/drivers/buses/linux_i2c/README.md) and [Linux UART](../project/drivers/buses/linux_uart/README.md).

```python
from pathlib import Path
from hardware.manager import HardwareManager

manager = HardwareManager(Path.cwd())
manager.execute("build", target="native", emit=print)
manager.execute("run", target="native", emit=print)
manager.execute("stop", target="native", emit=print)
```

The CLI and interface share `hardware/.runtime/execution.lock` to serialize build, boot, run, stop and shutdown operations for one checkout. A competing operation reports that the workspace is busy and can be retried after the active operation ends.

## Local or forked emulator images

From the repository root, `./start --no-ui emulator` displays the selected image and SSH port. With Docker and Buildx available:

```sh
./start --no-ui emulator --image flight-studio:local
./scripts/build.sh
./scripts/setup.sh
```

The build records the compiled QEMU models' fingerprint in the image. Allow disk space for decompressed Raspberry Pi OS, the converted disk and QEMU build tree, plus the persistent `board/` disk created at first boot. Select a different port with, for example, `--port 2223` while the emulator is stopped.

To publish through a fork's GHCR, run **Publish emulator image**. It builds Linux amd64 and arm64 variants and tags them with their model fingerprint. In the matching checkout, replace the repository name below. Private packages require Docker read access.

```sh
digest=$(python3 project/qemu/generate.py --fingerprint)
./start --no-ui emulator --image "ghcr.io/my-account/my-project:models-$digest"
./scripts/setup.sh
```

## Clean Debian host check

This recipe installs dependencies and downloads cFS in a fresh filesystem. It includes mission sources while excluding build outputs, guest disks, runtime state and SSH keys. The container builds Native; ARM64 execution is evaluated separately on QEMU and the board.

```sh
docker build -f scripts/portability.Dockerfile -t flight-studio-host:local .
docker run --rm --network none flight-studio-host:local
```
