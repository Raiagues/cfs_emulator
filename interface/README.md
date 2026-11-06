# Flight Studio interface

```sh
./start
./start --ui --port 8766
```

`./start` serves the interface at http://127.0.0.1:8765 through
[`server.py`](server.py). The server listens only on 127.0.0.1 and accepts only that
host name. Every request that changes something must carry the session token that
the page receives from `/api/session`. The frontend is plain JavaScript in `static/`
with no build step, and the xterm.js files it uses are kept in `static/vendor/`.

## Views

| Page / area | Contents |
| --- | --- |
| Code | File explorer and editor for the flight sources |
| Architecture | Mission blocks and app diagrams, next to the editor |
| Infrastructure (`/`) | Execution target, SSH, emulator image/port, requirements and preparation terminal |
| Hardware | Local computer in Native; board, sensors, buses and addresses in Emulator/Board |
| Synthetic data | Sensor signals and live values, described in [Synthetic sensor data](../sensors/README.md) |
| Ground station | Commands, decoded telemetry and activity, described in [Ground Station](../ground_station/README.md) |
| Terminal | Operation output and local shells |

## Architecture

**Open workspace** on the Infrastructure page opens `/studio`, with the CPU1 startup
script next to the mission architecture. The
mission view lists the cFS apps and libraries, the board and its sensors. Colors on
files and blocks mark changes since the last Git commit.

Selecting an app opens its diagram, grouped into initialization, message handling,
commands and telemetry, and support routines. Under each message ID the app receives,
the diagram lists the command codes that reach it, the handler function of each code
and the tables and libraries that handler uses. Clicking a function, route, payload
field, table or library opens its C source at the matching line. In full screen, the
app diagram is on the left and the mission on the right.

![The SAMPLE_APP diagram with Commands and telemetry expanded. SAMPLE_APP_CMD_MID leads to four command codes and their handlers, SAMPLE_APP_SEND_HK_MID leads to SendHkCmd, and SAMPLE_APP_HK_TLM_MID is the published telemetry. The editor shows SAMPLE_APP_NoopCmd in sample_app_cmds.c, opened from the NoopCmd card.](../docs/images/sample-app-command-routes.png)

Communication, next to Structure, shows the traffic the Ground Station observed for
each app. Selecting a counter lists the recent packets with their decoded fields and
bytes.

## Editing the mission

Edit, at the top of the architecture panel, shows the editing controls and opens the
startup script.

- New app opens a draft with priority, stack size, wakeup frequency and housekeeping
  frequency. The draft previews the startup entry, the generated functions and the
  native build and startup lines, and Save writes them.
- New library previews a library with the layout of `sample_lib` before saving it.
- Add app and Add library include an app or library that already exists in the
  checkout, and Add library also lists the drivers that can be added.
- The power button enables or disables an app's startup entry, and a disabled app
  stays in the diagram.
- The minus button offers Remove from mission, which excludes the module from the
  build and the startup script while keeping its files. For modules created by the
  project, it also offers Delete source files.

A library that included apps or devices still need cannot be removed until those
dependencies are removed. Every change takes effect after Build cFS and Run cFS. The
same operations from a terminal are listed in [Project and mission](../project/README.md).

## Terminal

The terminal panel keeps one terminal per operation, such as a build, the Linux boot,
cFS output or a synthetic data session. Switching between the flight software and
Synthetic data selects the matching terminal, and the list on the right selects any
other. Closing a terminal that follows logs leaves the service it follows running.
Terminal → + → New terminal opens a shell in the repository root.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+S | Save the file |
| Ctrl+F | Find in the editor |
| Ctrl+P | Find a file |
| Ctrl+B | Show or hide the explorer |
| Ctrl+` | Show or hide the terminal |

Dragging a divider resizes the panels, and double-clicking it restores the default
size. The browser keeps the panel sizes between sessions.

## Modules

- `server.py` serves the API and the static files.
- `backend/` holds the source workspace, mission operations, app diagrams and terminal
  sessions.
- `static/app.js` keeps the workspace state and calls the API.
- `static/mission-diagram.js` and `static/app-diagram.js` draw the architecture.
- `static/communication.js` shows the traffic observed by the Ground Station.
- `static/simulation.js` controls synthetic data sessions.
- `static/board.js` and `static/terminal.js` draw the workbench and the terminals.

## Design note

### Diagrams are read from the C sources

A diagram kept by hand drifts away from the code it describes. The backend
([`architecture_details.py`](backend/architecture_details.py), with
[`c_source.py`](../ground_station/c_source.py)) therefore reads each app's C sources
to find its subscriptions, the comparisons that route each message ID, the handler of
each command code, its packets and the tables it uses. A command code appears under a
message ID only when the dispatch code compares against that ID. The analysis reads
text rather than a syntax tree, so dispatch written in other forms is not drawn. The
API lists those cases as unresolved instead of guessing a route.
