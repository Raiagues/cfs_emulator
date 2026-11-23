# Project and mission

NASA supplies the framework, standard apps and examples in an independent official checkout, `cFS/`. A new workspace starts without user apps or linked sensors. Requested additions are created inside `cFS/apps/` and `cFS/libs/`. Platform scripts, templates and project choices remain outside that checkout, under `project/`. Follow the [getting-started guide](../README.md) to download the upstream sources.

Source installation is an explicit setup action. Creating a Docker image does not clone cFS; Native does not need Docker. The same local NASA checkout supports all three targets. The platform preserves the official framework sources and adds requested modules through generators.

New missions use aliases `mission/apps → ../cFS/apps` and `mission/libs → ../cFS/libs`. Separate definitions in `mission/sample_defs/` start from NASA's `cFS/sample_defs/`. Builds use `MISSION_DEFS` and `CFS_APP_PATH`, with outputs in `mission/build-native/` or `mission/build-flight/`. Existing missions keep their local sources and definitions.

Git ignores the local `cFS/` and `mission/` trees, app manifests in `project/apps/` and artifacts in `project/generated/`. These rules do not delete workspace files. The complete sources under `interface/tests/fixtures/bancada/` are isolated test fixtures, not modules installed in a new mission.

## Apps and libraries

In the 2D architecture, **New** creates or includes a module in the selected group. An app draft shows its entry point, priority, stack size and wakeup/housekeeping rates. Saving applies the build and startup definitions. The four original commands from `sample_app` remain available. See [workspace operations](../interface/README.md#editing-the-mission).

```sh
./start --no-ui app new attitude_app --priority 60 --stack-size 32768 --wakeup-hz 2 --hk-hz 0.25 --preview
./start --no-ui app new attitude_app --priority 60 --stack-size 32768 --wakeup-hz 2 --hk-hz 0.25
./start --no-ui app edit attitude_app --wakeup-hz 1
./start --no-ui library new payload_lib --preview
./start --no-ui library new payload_lib
```

| Operation | Effect |
| --- | --- |
| **Edit → Rename module** | Renames a user module and updates files, symbols, references, CMake and startup. NASA module identifiers retain their official names. |
| `app disable` / `app enable` | Controls startup of an app included in the build. |
| `app remove` / `library remove` | Excludes the module from the mission and preserves its sources. |
| `app add` / `library add` | Includes an existing module and its dependencies. |
| `app delete` / `library delete` | Deletes a user module's sources after backend checks. |
| `app list` / `library list` | Shows selected apps or available libraries. |

Prefix CLI operations with `./start --no-ui`. The CLI and browser share the implementation; a failed write restores the transaction's files. Apps retain editable handlers, payloads and periodic logic. Managed integration regions preserve manual code during later synchronization. Libraries copied from `sample_lib` provide `fsw/src/` and `fsw/public_inc/`. See [templates and edit points](appgen/README.md).

## Linking sensors and telemetry

The Raspberry Pi profile exposes I²C. This example uses the `attitude_app` created above and a TMP105 at `0x49`. For a physical board, use the actual device's seven-bit address.

```sh
./start --no-ui profile --board raspi4b --os raspios
./start --no-ui project add-bus i2c-bus.1
./start --no-ui project add-device "Payload temperature" --id payload_temp --model tmp105 --bus i2c-bus.1 --address 0x49 --value temperature=27000
./start --no-ui project add-sensor attitude_app board_temp --device payload_temp
./start --no-ui project add-command attitude_app set_mode
./start --no-ui project add-telemetry attitude_app temperature --sensor board_temp
./start --no-ui project locate attitude_app
```

In **Hardware**, select **Add bus**, then **Add sensor** to choose the model and address. **Link HAL** connects the device to an existing app or creates one from `sample_app`. The equivalent CLI action is `./start --no-ui project link-hal science temperature --device payload_temp --new-app`; omit `--new-app` to use an existing app.

`add-device` creates an instance with an ID, bus and address. `add-sensor` links an app reader to that instance. `add-command` creates a packet structure and editable handler. `add-telemetry --sensor` prepares the reader's data, status and validity packet. `locate` reports source paths and edit lines. Removing a reader and removing a hardware instance are separate operations.

Chip libraries use `hal_sensor`; the reader binds a device to its board transport. Reader links and CMake dependencies determine the libraries and cFE load order. Register a new chip through **Hardware** or `./start --no-ui project register-model <file>`. See [models, buses and HAL](drivers/README.md).

A reader can also expose a command-triggered sample:

```sh
./start --no-ui project link-hal hal_payload temp --device payload_temp --new-app --read-command read_now
```

The generated header-only command invokes the periodic reader and publishes its value, status and validity. Its function code is allocated from the app's free codes, and its command counters reflect the reader result. To remove this link while preserving the app, remove components in dependency order:

```sh
./start --no-ui project remove-command hal_payload read_now
./start --no-ui project remove-sensor hal_payload temp
```

Libraries created with `library new` include `@studio.edit library.init` and `@studio.edit library.function` locations where those functions exist in the copied `sample_lib`. Linking I²C materializes the shared `linux_i2c_lib` transport.

## Templates and script index

The following paths locate the implementation used by platform actions. Templates and scripts live outside the official NASA checkout; generated user sources are written into that local checkout only when requested.

| Action | Implementation and input |
| --- | --- |
| Download official cFS | [nasa_source.py](nasa_source.py) and [install-cfs.sh](../scripts/install-cfs.sh) |
| Prepare local source paths and mission definitions | [flight_sources.py](flight_sources.py) |
| Create an app | [appgen/sample.py](appgen/sample.py) copies the installed `cFS/apps/sample_app`; [appgen/render.py](appgen/render.py) applies integration templates |
| Create a library | [appgen/sample.py](appgen/sample.py) copies `cFS/libs/sample_lib` independently of app generation |
| Add commands, readers and telemetry | [manage.py](manage.py), [appgen/appgen.py](appgen/appgen.py) and [HAL templates](appgen/templates/hal_sensor/) |
| Materialize model and transport libraries | [driver guide](drivers/README.md), [model definitions](drivers/models/) and [transport sources](drivers/buses/) |
| Include or remove mission modules | [mission_config.py](mission_config.py), preserving sources when removing from a mission |
| Rename or delete user modules | [module_rename.py](module_rename.py), [module_delete.py](module_delete.py) and library operations in [mission_config.py](mission_config.py) |
| Build and run targets | [build-cfs.sh](../scripts/build-cfs.sh) and [hardware/manager.py](../hardware/manager.py); builds default to one worker |
| Derive command and telemetry definitions | [Ground Station catalog and C discovery](../ground_station/README.md#compiled-packet-catalog) |
| Run regression checks | [test commands](../README.md#tests) and [interface/tests/](../interface/tests/) |
| Reproduce measured technical validation | [validation/README.md](../validation/README.md), with procedures and raw observations |

App generation preserves references to the separate `sample_lib` dependency rather than treating it as another spelling of `sample_app`. Managed regions detect conflicting edits before writing; manual code outside them is preserved. Legacy schema-version-1 templates remain for compatibility with existing missions. Startup lists and mission-specific definitions stay outside the official framework sources.

## File map

| Path | Responsibility |
| --- | --- |
| `project/config.json` | Selected board/OS, devices and mission links |
| `project/apps/<app>.json` | App MIDs, performance ID, scheduling, commands, readers and telemetry |
| `project/boards/<board>.json` | Build profile, operating systems, buses and board catalog |
| `project/drivers/models/<id>/model.json` | Sensor identity, registers, conversions, channels and ABI |
| `project/drivers/catalog.json` | Shared HAL and transports |
| `project/generated/drivers.json` | Materialized-file signatures used to preserve local edits |
| `cFS/apps/`, `cFS/libs/` | Official sources and requested user modules in the local checkout |
| `mission/apps`, `mission/libs` | Aliases into the checkout for new missions |
| `mission/modules.cmake`, `mission/libraries.cmake` | CPU1 app and library selections |
| `mission/cpu1_cfe_es_startup.scr` | Active modules and retained startup recipes |
| `mission/sample_defs/targets.cmake` | Per-CPU module lists |
| `mission/sample_defs/toolchain-<architecture>.cmake` | Active profile's toolchain |
| `mission/sample_defs/default_osconfig.cmake`, `cfe_core_api_interface_cfg_values.h` | Loader limits, module names and cFE configuration |
| `mission/sample_defs/generate_startup.cmake`, `cpu1/install_custom.cmake` | Startup and mission-table installation |
| `mission/sample_defs/tables/`, `mission/sample_defs/generated/` | SCH_LAB/TO_LAB tables and integration fragments |
| `mission/build-native/`, `mission/build-flight/` | Local build artifacts |

## Checking and building

```sh
./start --no-ui project list
./start --no-ui project check
./start --no-ui project sync
./start --no-ui build --target qemu
```

`check` reports pending generated changes and returns exit code 1 when they exist. `sync` applies the plan. Rebuild and rerun after changing mission sources or membership. Restart QEMU after modifying emulated devices, addresses or buses so it loads the new topology. Synthetic signal settings can be applied through the data session. See [target execution](../hardware/README.md).
