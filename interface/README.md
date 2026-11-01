# Flight Studio interface

```sh
./start
./start --ui --port 8766
```

Default address: **http://127.0.0.1:8765**. The frontend uses local assets and has
no npm build step. Ground Station dependencies are listed in
[`ground_station/requirements.txt`](../ground_station/requirements.txt).

## Workspace

| View | Function |
| --- | --- |
| Files | Flight-source explorer and editable files |
| Architecture | Mission blocks and expandable application diagrams beside the editor |
| Hardware | Board, sensors, bus/address details and physical connection |
| Synthetic data | Signal selection, Widgets/Code editor and live sensor values |
| Ground Station | Commands, decoded telemetry and activity |
| Terminal | Operation output and interactive local shells |

Studio opens the CPU1 startup script beside the mission architecture. **Edit**
reveals inline block controls and opens that startup source. In full screen,
selecting an app shows its diagram on the left and the mission on the right.

- **New app** opens a draft with priority, stack size and wakeup/housekeeping frequencies.
  **Save** generates C sources, build entries, startup and scheduler data.
- **New library** previews a library using the `sample_lib` layout before saving.
- App properties edit the same native startup and schedule settings.
- **Add app** includes an existing application from the local catalog.
- **Power** enables or disables startup. Disabled apps stay in the diagram.
- **− → Remove from mission** excludes an app or library from build and startup, preserving source files.
- **− → Delete source files** also deletes a project-created app or library.
- **Add library** selects an existing native library or available driver. Libraries
  required by included apps or hardware must be detached before removal.

The app view groups initialization, message handling, commands, telemetry and
support routines. Function cards, MID/CC routes, payload fields and table/library
chips open actual C source. Library blocks show the libraries they call and link
to implementations and build configuration. Git colors identify source changes on
files and module blocks. Opening a source link does not modify the file.

**Communication** shows each app's telemetry received and commands sent by Ground
Station. Select a counter to inspect recent packets, decoded fields and bytes.
Counters cover the current Ground Station connection.

## Synthetic data

Open **Configure synthetic data** or the waveform icon. The left panel selects
sensors and shows live values; the right panel provides two views:

- **Widgets:** choose sensors, initial values, update interval and each signal's
  function: Python waveform, constant, sine, ramp or custom Python.
- **Code:** edit `sensors/<model>.py`, including its `SIGNALS` configuration and
  custom functions. `sensors/signals.py` only selects sensors and the session interval.

**Save** updates the same Python settings used by both views. **Test code** runs
a finite sample preview in the terminal, including without a board. **Start** sends all
enabled signals and opens their terminal. Hardware bus/address configuration
remains in the Hardware view. See [Synthetic sensor data](../sensors/README.md).

## Execution

With no board selected, **Native** builds and runs cFS on the local computer.
Select a board and OS to generate its toolchain.

In Emulator mode, **Start QEMU + Linux** boots the emulator and **Stop QEMU**
stops it. In Board mode, **Connect board** opens the SSH connection settings for
the powered-on board. **Build cFS**, **Run cFS** and **Stop cFS** work with the selected
target. **Start/Stop synthetic data** controls the configured signal session.
Running actions show progress and retain their output in one terminal. Only one
cFS instance can run per workspace.

**Terminal → + → New terminal** opens the local shell in the repository root.
Other terminals follow the Linux boot, cFS, build or Python output. Switching
between flight software and Synthetic data selects the corresponding terminal;
the terminal list remains available for manual selection. Closing a log reader
leaves its service running.

Ground Station reads command and telemetry definitions from the built cFS.
Selecting a packet opens its C definition; sending a command does not edit source.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+S | Save file |
| Ctrl+P | Find file |
| Ctrl+B | Toggle explorer |
| Ctrl+` | Toggle terminal |

Drag panel dividers to resize; double-click a divider to reset. Browser storage
keeps panel sizes and workbench layout.

## Modules

- `server.py`: loopback HTTP API and sessions.
- `backend/`: source workspace, native mission operations and terminal sessions.
- `static/app.js`: workspace state and API calls.
- `static/mission-diagram.js`, `app-diagram.js`: architecture views.
- `static/communication.js`: observed Ground Station traffic.
- `static/simulation.js`: synthetic session controls and live readings.
- `static/board.js`, `terminal.js`: workbench and terminals.
