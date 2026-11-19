# Flight Studio

Flight Studio is a local workspace for developing NASA cFS flight software. It edits
the mission's C sources and draws each app's command and telemetry routes from those
same sources. It builds cFS and runs it on this computer, in a Raspberry Pi 4B
emulated by QEMU, or on a physical Raspberry Pi 4B. Its Ground Station uses the NASA
cFS-GroundSystem modules to send commands to the running build and to decode its
telemetry. In QEMU, Python functions can also set the readings of emulated I²C
sensors, which the flight software reads through its Linux drivers.

![Flight Studio with cFS running in QEMU. The editor shows the CPU1 startup script, the mission architecture lists the cFS apps next to a Raspberry Pi 4B with a TMP105 sensor, and the terminal shows cFS events, including the event of a SAMPLE_APP NOOP command.](docs/images/studio-qemu-overview.png)

## Requirements

Every target needs Linux, Git, Python 3.10 or later and the packages listed in
[`ground_station/requirements.txt`](ground_station/requirements.txt), which the NASA
Ground Station modules import. Native builds also need CMake, Make and a C compiler.
The emulator and builds for the board need Docker 23 or later with Buildx and an
OpenSSH client. [`scripts/setup.sh`](scripts/setup.sh) checks these and installs what
is missing on Ubuntu 24.04 or later and Debian 13 or later, on AMD64. The emulated
Raspberry Pi keeps its disk in `board/raspios.qcow2`, which takes about 3 GB.

## Install

```sh
git clone https://github.com/Raiagues/cfs_emulator.git
cd cfs_emulator
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r ground_station/requirements.txt
```

Open Flight Studio and select **Clone NASA cFS** on the setup screen. It downloads the default branch and the submodule revisions specified by the [official NASA repository](https://github.com/nasa/cFS). The screen shows the installed commit. To perform the same step from a terminal, run `./scripts/install-cfs.sh`.

The platform Git repository ignores the independent checkout in `cFS/`. Studio reads the NASA sources and builds with its own `mission/sample_defs/`, custom modules in `mission/apps/` and `mission/libs/`, and output under `mission/build-*/`. See [Project and mission](project/README.md).

## First run

The checked-in project selects a Raspberry Pi 4B with Raspberry Pi OS. Add devices from the hardware workbench to populate I²C bus 1. The four steps below start the
interface, the emulator, cFS and the Ground Station separately. Each step ends with
the sign to look for before going on. Native execution, which needs no Docker, is
described after them.

### 1. Interface

```sh
./start
```

Open http://127.0.0.1:8765. The server only accepts connections from this computer,
and `./start --ui --port 8766` selects another port. **Infrastructure** opens first. Choose Native, Emulator or Physical board, configure access and press **Run all checks**.
Preparation commands run in the page's terminal. **Open workspace** opens the 3D hardware workbench. The initial mission includes the NASA cFS apps, with no project-created apps or attached sensors. Select the Flight Studio name to return to Infrastructure.

```mermaid
flowchart LR
    Infrastructure --> Target[Native / Emulator / Board]
    Target --> Access[Tools and connection]
    Access --> Workspace[Code and architecture]
    Workspace --> Build --> Run
```

### 2. QEMU

Run the setup script once. It checks Docker, Buildx and OpenSSH, creates the emulator's SSH key in `~/.ssh/cfs-emulator/` and downloads the
emulator image. When the download fails, it builds the image locally. It asks for
sudo when it has to install packages, start Docker or add your user to the `docker`
group, and a group change takes effect after you sign in again.

```sh
./scripts/setup.sh
```

Until setup has run, the toolbar shows Set up QEMU in place of Start emulator.
In the toolbar, choose Emulator and press Start emulator. The first boot copies
the Raspberry Pi OS disk to `board/` and adds this computer's SSH key to it. Linux is
ready when the terminal prints `Sensor values applied.` and then
`Raspberry Pi ready.`. Stop emulator powers Linux off and waits for the emulator to exit.
From a terminal, the same steps are `./start --no-ui boot` and
`./start --no-ui shutdown`.

### 3. cFS

Press Build cFS and then Run cFS. Builds for the emulator use the `cfs-builder:local`
Docker image with the ARM64 cross compiler, which the first build creates. Run uploads
the build to the guest, starts `cfs.service` and shows its output in the terminal. A
running service only means that the process started. cFE has finished its startup
sequence when the output shows `CFE_ES_Main entering OPERATIONAL state`, and apps that
fail to start report their errors in the same output.

```sh
./start --no-ui build
./start --no-ui run     # follows the output; Ctrl+C stops following, not cFS
./start --no-ui stop
```

### 4. Ground Station

Open Ground station in the left rail and press Connect. Flight Studio reads the
command and telemetry definitions of the running build, starts a UDP receiver and
asks TO_LAB to send telemetry to this computer. The status reads `QEMU · Connected`
once the receiver is listening, and telemetry is arriving when the packet counters
grow.

To check the command path, select `SAMPLE_APP_NOOP_CC` under **Send commands** and
press **Send command**. Look for `SAMPLE: NOOP command` under **Telemetry events**.
Then open `SAMPLE_APP_HkTlm_t` under **Received telemetry** and check that its
`CommandCounter` has increased by one. The [Ground Station guide](ground_station/README.md)
follows the command from the browser to the flight app and back.

### Native execution

Select **Native** to build with the host compiler and run `core-cpu1` on this
computer. Board/OS selectors are hidden and the workbench shows the local computer.
The board and sensor configuration stays saved for Emulator and Board mode.
Build cFS, Run cFS and Ground Station use the native build; Ground Station connects
to 127.0.0.1.

```sh
./start --no-ui profile --native
./start --no-ui build
./start --no-ui run --no-follow
./start --no-ui logs
./start --no-ui stop
```

For a physical Raspberry Pi 4B, select **Board** and press **Check connection**.
[Execution targets](hardware/README.md) describes the one-time SSH authorization.

## How the parts connect

The browser and `./start --no-ui` call the same Python code, so both work on the same
project, builds and running targets. Only one build or runtime operation runs at a
time in a checkout.

```mermaid
flowchart TB
    subgraph studio["Flight Studio"]
        ui["Browser UI<br/>interface/static/"] -->|"HTTP on 127.0.0.1"| server["interface/server.py"]
        cli["./start --no-ui"]
        server --> edit["Mission editing<br/>interface/backend/<br/>project/"]
        server --> manager["Build and execution<br/>hardware/manager.py"]
        server --> gs["Ground Station<br/>ground_station/"]
        cli --> edit
        cli --> manager
        cli -->|"simulate"| synthetic["Synthetic data<br/>sensors/"]
        manager -->|"starts"| synthetic
    end
    edit -->|"writes"| mission[("mission/")]
    manager -->|"reads"| cfs[("cFS/ · NASA checkout")]
    manager -->|"builds"| mission
    subgraph targets["Execution targets"]
        native["Native process"]
        qemu["QEMU Raspberry Pi 4B<br/>in Docker"]
        board["Raspberry Pi 4B<br/>over SSH"]
    end
    manager -->|"runs cFS"| targets
    synthetic -->|"QMP"| qemu
    gs <-->|"UDP commands<br/>and telemetry"| targets
```

## Documentation

- [Interface](interface/README.md) covers the views, mission editing, terminals and
  keyboard shortcuts.
- [Project and mission](project/README.md) covers apps, libraries, devices, drivers and
  their mission configuration.
- [App generator](project/appgen/README.md) covers generated code and which files are
  yours to edit.
- [Execution targets](hardware/README.md) covers builds, QEMU, the physical board and
  deployment.
- [Synthetic sensor data](sensors/README.md) covers the Python functions and the path
  of a value from QMP to the flight software.
- [Ground Station](ground_station/README.md) covers definitions, UDP transport and what
  each status confirms.

`./start --help` lists the commands, and `./start --no-ui COMMAND --help` shows the
options of one command.


## Comparing an I²C sensor

In Hardware, choose **Add sensor** and select MPU6050. AD0 selects address 0x68 or 0x69. **Validate model** exercises the compiled QEMU device on a separate Pi 4 instance. It checks the identity, register defaults, burst data, range selection and software reset. The model implements the register interface for accelerometer, temperature and gyroscope sampling. FIFO, interrupts and DMP are outside its implementation.

Add a flight reader to the mission app, build and run it to initialize the sensor, then select **Test sensor**. Repeat on the physical board with the same wiring and address. The inspector shows the two most recent measurements side by side, in g, °C and °/s. Stationary measurements depend on the board orientation and sensor bias.

For a new device, choose **New I²C register model** in the same dialog. Enter its identity, startup writes, output registers, units and sensitivity from the device register map. This generator supports a contiguous burst of up to 32 bytes containing signed, big-endian, 16-bit measurements on the Pi 4 I²C bus. Install the updated emulator image in workspace setup and run **Validate model** before connecting a flight reader.
