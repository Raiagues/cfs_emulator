# Flight Studio interface

The local page at `/` prepares the target and official cFS checkout. Continue to the first boot to build and start the mission, then use `/studio` for the workbench. Follow the [installation guide](../README.md) on a new computer.

`./start` starts or reuses the server for this workspace. `./stop.sh` stops only that web server and does not contact the emulator or board. Both accept `--port` to select a nondefault Studio port. Use `./start --no-ui stop --target native`, `qemu` or `physical` to stop a cFS mission.

## Navigation

| Area | Purpose |
| --- | --- |
| **Ground station** | Build commands from the compiled catalog, send them and inspect telemetry and events. See the [Ground Station guide](../ground_station/README.md). |
| **Architecture** | Browse the default 2D mission map or switch to the 3D stack. Inspect apps, libraries, cFE services, OSAL and PSP. |
| **Hardware** | Inspect the Native computer or selected board. **2D → Pinout** shows physical connector numbers and GPIO names. |
| **Code** | Browse source files and edit user modules. Git marks added and modified files. |
| **Synthetic data** | Configure device signals, preview them locally and follow an injection session. See the [signal guide](../sensors/README.md). |
| **Terminal** | Follow builds, jobs and local shells in the lower panel. |

## Editing the mission

Select a module to inspect its dependencies, sources or commands. In 3D, drag to rotate and use the wheel to zoom; layer labels lead to their corresponding 2D groups. Group controls create, edit or remove modules. **Build cFS** is in the top toolbar, with a rebuild notice when a previous build is out of date.

- **Your apps → New** shows the name, entry point, priority, stack size and wakeup/housekeeping rates before creating an app from NASA's `sample_app`.
- **Libraries → New** creates a mission library from NASA's `sample_lib`.
- **New** in the NASA apps group includes an available checkout module. Scheduling and communication dependencies constrain removal.
- **Edit** offers the operations allowed for the selected module. Renaming a user module updates build, startup and source references.
- **Remove** excludes a module from the build and CPU1 startup while preserving its sources. Remaining library consumers are checked before removal.

Open an app to inspect initialization, MID and function-code dispatch, handlers, tables and telemetry. A library exposes its consumers and public API. Selecting a source location opens the corresponding line in the editor.

## Reading and editing code

The official checkout is available under `cFS/`. User apps and libraries are created in its `apps/` and `libs/` directories; new missions expose these through aliases under `mission/`. NASA framework files remain available for reference. The [template guide](../project/appgen/README.md) identifies editable handlers and integration points.

Activity completion marks belong to the platform's progress state. They are separate from the cFS source files. The code pipeline distinguishes completed steps from the currently selected step.

After implementing a command, the final activity step follows the selected target’s deployment state: stop an outdated running mission, build the sources, and run the installed build. **Open Ground Station** then opens the same Ground Station used for the first event, selecting the app and command from the compiled catalog. Enable telemetry if needed, enter the command fields, and send. Finishing a build or receiving a reply does not navigate to another page. The route replay starts only after the expected event and housekeeping counter confirm that send.

| Shortcut | Action |
| --- | --- |
| Ctrl+S | Save the active file |
| Ctrl+F | Search in the editor |
| Ctrl+P | Find a file |
| Ctrl+B | Toggle the explorer |
| Ctrl+` | Toggle the terminal |

Drag dividers to resize panels. The terminal keeps an operation's history. Closing a log-following view does not stop the service producing those logs.

## Implementation

The server binds to loopback and serves JavaScript and fonts from this repository. Browser writes use the token from `/api/session`. File, mission and draft hashes detect concurrent edits. See [server.py](server.py) and the shared [laboratory service](../jobs/service.py).

The source index analyzes function signatures, Software Bus subscriptions and comparisons connecting MIDs to handlers. It exposes resolved routes and records unresolved cases. See [source_index.py](../project/source_index.py) and [architecture_details.py](../project/architecture_details.py). The source-derived navigation inventory is available through `./scripts/nav-map` from the repository root.
