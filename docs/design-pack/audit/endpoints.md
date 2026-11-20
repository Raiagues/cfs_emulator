# Flight Studio: UI control to endpoint map

Repo: `Raiagues/cfs_emulator`, branch `first-flight-flow`, commit `071396c`. Read-only audit. All paths are relative to the repo root. `file:line` refers to that commit.

Legend:
- **Handler**: the function that receives the DOM event.
- **Route/state**: the client-side navigation (`location.hash`, `history.pushState`, full page load) or state change.
- **Endpoint**: the HTTP call the handler makes (method, path, payload).
- **Server handler**: the Python function that serves it.
- **Runs**: the process, script or file write it ultimately triggers.
- ⚠ marks a mismatch or defect. Section 8 lists them all together.

How the client calls the server:
- `interface/static/app.js:43-55` `api(path, body)`: a GET when `body === undefined`, otherwise a POST with JSON and the `X-Studio-Token` header. On a 403 it fetches `GET /api/session` again and retries once.
- `interface/static/infrastructure.js:24-45` `request()`/`api()`: a second copy of the same client, with the same retry.
- `interface/static/journey.js:94` calls raw `fetch('/api/journey?...')`: a third client, with no token handling.
- Server dispatch: `interface/server.py:539-602` (`do_GET`, a dict of routes at 546-563 plus static files at 566-595) and `interface/server.py:607-706` (`do_POST`, an `if/elif` chain at 625-698).

---

## 1. Pages and top-level routing

| URL | Server code | Serves | Notes |
|---|---|---|---|
| `GET /` and `GET /infrastructure` | `server.py:566-567` | `interface/static/infrastructure.html` (setup, "Choose target") | ⚠ Two URLs for one page. The brand link uses `/infrastructure` (`index.html:23`), the journey uses `/` (`journey.js:33-34`), and the redirects use `/infrastructure?target=` (`app.js:509,748,1302`, `sensor-designer.js:11`). |
| `GET /studio`, `GET /studio/` | `server.py:568-577` | `index.html` (workspace) | Returns a 302 to `/?target=T#target` when `infrastructure.sources_ready()` is false (that check runs `git` via `project.nasa_source.source_status`). |
| `GET /emulator-guide.html` | `server.py:578-579` | `emulator-guide.html` | ⚠ **No page links to it** (grep finds only server.py). The content is stale: it mentions "Install dependencies", "Verify setup" and "open the workspace", which do not match the current labels. |
| `GET /<name>.(js,css,woff2,svg,png)` | `server.py:580-595` | static assets | Sent with `Cache-Control: no-store`, so every asset is downloaded again on each navigation. |

Workspace hash routes (`workspace-route.js:2-13`). An unknown hash falls back to `architecture`.

| hash id | view rendered | rendered by |
|---|---|---|
| `#boot` | `boot` | `app.js:555` → `showFirstBoot()` `app.js:531` → `first-boot.js:170` |
| `#event`, `#send`, `#ground` | `ground` | `app.js:491` `ground()` → `panels.js:renderGround` |
| `#app`, `#architecture` | `architecture` | `app.js:388` → `architecture.js:39` |
| `#command`, `#code` | **architecture with `body.code-only`** | `app.js:991-995`. ⚠ "Code" is not a view of its own: `state.view` is set to `'architecture'` and CSS hides the panel (`workspace.css:265` `.code-only .visual{display:none}`), so the whole architecture/3D diagram is still rendered in the background. |
| `#sensor`, `#test`, `#simulation` | `simulation` | `simulation.js:renderSimulationBoard` |
| `#bench` | `bench` | `app.js:389` |

There are four sources of truth for "where am I", and they are not kept in sync:
1. `location.hash`
2. `state.view` (`app.js:23`)
3. the body classes `code-only`, `no-editor`, `no-tree` and `simulation-mode`, toggled in at least 9 places (`app.js:130,992-995,1215,1237-1238,1247,1266-1267,1270,1392,1208`)
4. the step the journey bar derives from the hash (`journey.js:16,23`)

---

## 2. Setup page (`infrastructure.html` + `infrastructure.js`)

What happens when the page loads (`infrastructure.js:489-508`):
1. `GET /api/session`, then `GET /api/infrastructure` (→ `hardware/infrastructure.py:62 snapshot`), then `GET /api/jobs`.
2. If an installer is still running, the page follows it (`followInstaller`).
3. Otherwise, if the URL contains `?target=`, it calls `verify()` **automatically** (`:506`). ⚠ That can POST a save (see 2.1).

### 2.1 Controls

| # | Control (file:line) | Label | Handler | Route/state | Endpoint(s) | Server handler | Runs |
|---|---|---|---|---|---|---|---|
| S1 | `.target-option[data-target]` `infrastructure.html:23,28,33` | Native / Emulator / Board | `#targets` click `infrastructure.js:418-428` | `target=mode`, `dirty=true` if it differs from the saved target, URL **not** updated | `verify()` → `runChecks()` `:234-264` → if `dirty \|\| !target_saved \|\| mode!==settings.target`: `POST /api/infrastructure` `{target,build_jobs,board,os,connection,emulator}` (`saveForm` `:214-229`); then `POST /api/infrastructure/check {target,label}` once per check | `server.py:627-628` → `infrastructure.save` (`hardware/infrastructure.py:94-138`), `server.py:629-631` → `infrastructure.check_one` (`:298-306`) | `save`: writes `hardware/.runtime/target.json` (`select_target`, `:137`), and **may call `workspace.select_profile`, which regenerates mission files** (`:123-124`). `check_one`: runs `git/cmake/make/cc --version`, `docker version`, `docker buildx version`, `ssh -V`, `python -m hardware.infrastructure check-*`, the PyQt5/pyzmq import, and `python -m project.nasa_source --status` (`:217-249`) synchronously in the HTTP thread (30 s timeout each). ⚠ Clicking a card **persists** the selection. There is no "save" step. |
| S2 | `#build-jobs` stepper `[data-step]` (`infrastructure.js:77-80`) | − / + | `form` click `:463-472` → `input` + `change` | `dirty=true` | `form` `change` `:480-484` → `verify()` → `POST /api/infrastructure` + checks | as S1 | writes `native-build-settings.json` |
| S3 | `select[name=board]`, `select[name=os]` (qemu, `:62-67`) | Board / Operating system | `form` `change` `:480-484` | `dirty=true` | `verify()` → `POST /api/infrastructure` | `infrastructure.save` → `workspace.select_profile` | **Rewrites `project/config.json` and the generated mission files** if the sources are installed. ⚠ A change in a dropdown triggers a mission regeneration with no confirmation. |
| S4 | `.connection-value[data-setting=host\|user]` `:69-71,85-86` | Host / SSH user | `form` click `:466` → `openSettings(field)` `:315-336` | opens `#settings-sheet` | none | none | none |
| S5 | `#advanced-toggle` `:74` | Configure | `openSettings()` | opens `#settings-sheet` | none | none | none |
| S6 | `#settings-sheet` submit `infrastructure.html:56` | Save settings | `settingsForm` submit `:345-378` | `busy`, then the dialog closes | `POST /api/infrastructure` with `connection{host,user,port,identity_file,directory}` or `emulator{ssh_port,image}`, then `verify()` | `infrastructure.save` | writes `connection.json` / `emulator.json`. For physical it may SSH to the *previous* board to confirm cFS is stopped (`:112-118`). |
| S7 | `#settings-cancel` / `.close-dialog` | Cancel / × | `:341`, `:447-448` | closes the dialog | none | none | none |
| S8 | `#requirements .requirement[data-group]` (built at `:175`) | Compiler/Python/Source, Docker/Image/Toolchain, Network/SSH key/Service | `:434-440` | failed group: `installRequirements(name)`; other states: `inspect(name)` | `POST /api/terminal/create {target,setup_action}` → poll `GET /api/jobs` every 400 ms (`:281-293`) → `GET /api/infrastructure` → `verify()` | `server.py:674-676` → `Shells.create` (`interface/backend/terminal.py`) | PTY that runs `terminal.py:21-28 SETUP_COMMANDS`: `clone-cfs` → `scripts/install-cfs.sh` → `python -m project.nasa_source` (`git clone --depth 1 --recurse-submodules`). `native-tools` → `scripts/setup-native.sh` → `python -m hardware.host_tools` (apt/dnf/pacman/zypper + pip). `dependencies` → `scripts/setup.sh --build-only`. `emulator-image` → `scripts/setup.sh` (sudo docker install, `usermod -aG docker`, `docker pull ghcr.io/raiagues/cfs_emulator:latest` or `scripts/build.sh`). `board-key` → `python -m hardware.infrastructure authorize-key` (ssh-keygen + ssh-copy-id). `board-service` → `... prepare-service` (uploads `hardware/setup_board.py`, runs it with sudo). |
| S9 | `#install` `infrastructure.html:45` | Install requirements | `:429` `installRequirements()` `:380-415` | loops over `nextRepair()` (`setup-plan.js:27-35`) | as S8, repeated | as S8 | as S8. For a `settings` repair it opens S5 instead. |
| S10 | `#enter` (submit) `infrastructure.html:46` | Continue to boot | `form` submit `:485-488` | `location.href='/studio?target=T#boot'` (full load) | `GET /studio` | `server.py:568-577` | Opening `#boot` **auto-starts a first-boot job** (see J2). |
| S11 | `#inspect` `infrastructure.html:47` | Details / Input required | `:430-433` | an installer is running: `showTerminal()`; otherwise `inspect(first missing group)` | none (the terminal polls `POST /api/terminal/read` every 120 ms, `shell.js:55-71`) | `server.py:677-678` | none |
| S12 | `#check-groups button[data-group]` (built at `:132-136`) | group names | `:441-444` → `inspect(name)` | switches the tab in the dialog | none | none | none |
| S13 | `#check` `infrastructure.html:63` | Check again | `:446` `verify(activeGroup)` | | `POST /api/infrastructure` (if dirty) + `POST /api/infrastructure/check` × group | as S1 | probes |
| S14 | `#fix-group` | Install / Target settings | `:445` `installRequirements(activeGroup)` | | as S8 | as S8 | as S8 |
| S15 | `#show-terminal` | Installer log | `:461` `showTerminal()` | opens `#setup-terminal` | `POST /api/terminal/read` polling | `Shell.read` | none |
| S16 | `#shell-terminal` keystrokes | (xterm) | `shell.js:48-49` | | `POST /api/terminal/input {id,data}`, `POST /api/terminal/resize` | `server.py:679-682` | writes to the installer PTY (needed for sudo passwords) |
| S17 | `[data-theme-toggle]` `infrastructure.html:17` | (icon) | `theme.js:23-28` | `localStorage['fs-theme']` | none | none | none |
| S18 | `#flight-guide` | First flight bar | `journey.js` | see section 3 | `GET /api/journey?target=` every 3.5 s | `server.py:547` | none |

---

## 3. "First flight" journey bar (`interface/static/journey.js`)

The bar is mounted on both pages (`infrastructure.html:19,71`, `index.html:49,102`).
- `update()` (`journey.js:52-84`) sets each `<a>` href with `stepUrl()` (`:32-39`).
- The highlighted step comes from `journeyNavigation()` (`:19-30`).
- In the workspace, clicks on `/studio#...` links are intercepted by `app.js:975-984` and routed to `openFlightStep()` (`app.js:934-960`). Every other link triggers a full page load.
- Completion comes from `GET /api/journey?target=T` → `server.py:547` → `interface/backend/journey.py:106-120 snapshot` → `derive()` (`:34-64`).
- The client hides any step whose `observed_at <= since` (`journey.js:24`).

How the current step is chosen (`journey.js:16,23`):
- `railSteps = {architecture:'app', bench:'sensor', code:'command', ground:'event', simulation:'sensor'}`.
- On the setup page the current step is always `target`, or `board` when the URL has `?target=physical` without `#target`.
- `next` is shown only in the workspace. It requires `done[current]`, and for `boot` it requires `body.dataset.bootReadyTarget === target`.

| # | Step | Link on setup page | Link in workspace | Client handler and state | Endpoints and side effects | Completion evidence (`journey.py`) | Problems |
|---|---|---|---|---|---|---|---|
| J1 | Target | `/?target=T#target` (or `/` when no target) | same (full load, not intercepted, `app.js:979`) | setup-page boot `infrastructure.js:489-507`. Because `?target` is explicit, `verify()` runs. | `POST /api/infrastructure` when the target differs or `!target_saved`; N × `POST /api/infrastructure/check` (each may SSH to the board for physical) | `setup_observed_at` `:92-103`: the **mtime** of `checks-T.json` + `checks_verified` + `selected`. A fallback heuristic scans the boot trace for `phase=='build'` (`:98-102`). | ⚠ Navigating here **writes** state (target selection) and runs probes. ⚠ Evidence is a file mtime. |
| J2 | Boot | `/studio?target=T#boot` | `#boot` | `openFlightStep('boot')` → `selectView('boot')` (`app.js:959,985`) → `showFirstBoot()` → `mountFirstBoot()` (`first-boot.js:170-312`) | Polls `GET /api/first-boot?target=T` every 600 ms (`first-boot.js:251-271`). ⚠ It **auto-POSTs** `/api/job {action:'first-boot',options:{target}}` when `verified && !running && !job.id && !stopped` (`first-boot.js:258`). Server: `server.py:273-274` → `first_boot.execute` (`first_boot.py:234-268`): `manager.execute('build')` (`project/manage.py sync`, `scripts/build-cfs.sh` → cmake natively, or `docker build cfs-builder` + `docker run cmake`), then `freeze_catalog`, then (qemu) `bash boot.sh` (`docker run pi4-cfs` → `scripts/emulator.sh` → `qemu-system-aarch64`), then `run` (native `core-cpu1` / ssh tar + `systemctl start cfs.service` / ssh tar + `activate_release.py`), then follows the journal. ⚠ The GET also starts a `logs` job (SSH `journalctl`) through `Studio.follow_boot_journal` (`server.py:320-337`, `first_boot.py:214-216`). | `operational-T.json` contains `OPERATIONAL` (`first_boot.py:147-152`, `journey.py:115-116`) | ⚠ A navigation (link, Back/Forward, deep link, "Continue to boot") launches a multi-minute build and deploy. ⚠ A GET has side effects. ⚠ For physical, Boot already deploys to the board, so it overlaps J9. |
| J3 | Event | `/studio?target=T#event` | `#event` | `openFlightStep('event')` → `selectView('ground',…,'event')` (`app.js:959,985-1022`) | `GET /api/ground/catalog?target=T` (runs under the **global operation lock**, `wait=3`, `server.py:559`), `GET /api/ground`, `GET /api/ground/tests`, then `GET /api/ground` every 1.5 s (`app.js:1496`). Connect and send are covered in section 5.4. | `ground.first_flight.event`, **only while the station is connected and on the same target** (`journey.py:38-41`) | ⚠ Reachable with cFS not running; the user lands on "Catalog unavailable". ⚠ **Completion is not durable**: disconnecting, a server restart or a new connection un-checks Event (confirmed in `docs/validation.md:24`). ⚠ While any build or first-boot job holds `Studio.operation`, the catalog GET fails after 3 s with "Operation in progress". |
| J4 | App | `/studio?target=T#app` | `#app` | `openFlightStep('app')` sets `archApp='', archOverview=true, mapMode, mapSection='mission'` (`app.js:937-939`) → `selectView('architecture',…,'app')` | `GET /api/workspace` (heavy, see 6.1) | **mtime** of `mission/apps/<n>/CMakeLists.txt` (`journey.py:11-19`) | ⚠ Evidence is an mtime. After "Start over", existing apps never count again; touching or checking out a file counts as "done". |
| J5 | Command | `/studio?target=T#command` | `#command` | `openFlightStep('command')` `app.js:940-952`: if `authoredCommand()` → `resumeCommand()` → code view. Else if there is no managed app → `history.replaceState('#app')` + wizard. Else `selectView('code', app.entry,1,null,'command')` + `newCodeCommand()` dialog. | dialog submit → `POST /api/mutate {action:'add-command',payload:{app,name},expected_hash}` (`app.js:673`) → `server.py:635-636` → `Workspace.mutate` → `_mutate_components` (`workspace.py:539-599`) → `bash scripts/project.sh add-command …` → `python3 project/manage.py add-command` | `*_fcncodes.h` region `command.codes` contains a `#define` (header mtime) (`journey.py:20-30`) | ⚠ **Back/Forward re-runs the activity**: `popstate` → `followLocation` → `openFlightStep` (`app.js:966-974`) reopens the "New command" dialog or the wizard. ⚠ `authoredCommand()` falls back to `commands.at(-1)` (`app.js:964`), so it "resumes" an arbitrary manifest command. ⚠ The "Code" rail highlights *Command* (`railSteps.code`) but sets `commandTask=null` (`app.js:1258`). |
| J6 | Send | `/studio?target=T#send` | `#send` | `openFlightStep('send')` `app.js:953-956`: if `authoredCommand()` → `openGroundRoute(app,id,true)` (`app.js:1023-1029`) and a `state.commandLaunch` card; otherwise a plain ground view | Launch card buttons (`app.js:499-501`, `command-launch.js:2-33`), section 5.4 | a passed round-trip run or receipt of a mission command with observations (`journey.py:42-48`) | ⚠ Enterable with no authored command; it then shows a generic Ground Station with the bar on "Send". ⚠ The launch action `active` jumps *back* to Boot on another target (`app.js:510-513`). ⚠ The `setup` action leaves to `/infrastructure` (`app.js:509`). |
| J7 | Sensor | `/studio?target=T#sensor` | `#sensor` | `state.signalView='signals'` → `selectView('simulation',…,'sensor')` (`app.js:958-959`) | `GET /api/simulation`, `GET /api/hardware` | `signal-observations.json` device timestamps for devices linked to apps, plus `simulate`/`values` job receipts (`journey.py:49-60`) | ⚠ The "Hardware" rail maps to Sensor (`railSteps.bench`), but the Sensor link opens **Synthetic data**, not Hardware. ⚠ Requires QEMU (QMP writes); impossible on Native or Board. ⚠ The evidence file is **not per target**, so a QEMU run completes Sensor for Native and Board too. ⚠ The prerequisite work (bus, device, HAL link) is on the Hardware view, which the step does not open. |
| J8 | Test | `/studio?target=T#test` | `#test` | `state.signalView='test'` → simulation view | as J7; Run → `POST /api/job {action:'simulate-preview',options:{device,scenario}}` | `history.tested` or a successful `simulate-preview` with `scenario_result` (`journey.py:51,61-62`) | ⚠ Labelled "Check that everything works", but the evidence is a **local Python/C dry-run scenario**, not a flight test. ⚠ Shares a screen with Sensor. ⚠ The evidence is not per target. |
| J9 | Board | `/?target=physical` | `/?target=physical` (full load out of the workspace) | setup-page boot with explicit `physical` → `verify()` → `saveForm()` | ⚠ `POST /api/infrastructure {target:'physical',…}` → `hardware.select_target('physical')` (+ `select_profile` if board/os differ) (`infrastructure.py:119-124,137`) | `operational-physical.json` with `OPERATIONAL` and `same_board` (`journey.py:35-37`) | ⚠ **Clicking the pill changes the project's persisted default target to physical.** ⚠ The destination is the target setup form, not a board deploy screen. "Next" from Test does the same. |
| J10 | Next | (hidden on setup) | `stepUrl(next)` | `journey.js:75-83` | as the destination step | none | ⚠ From Test the next step is Board → `/?target=physical` (see J9). |
| J11 | Start over `[data-flight=reset]` | ⟲ | same | `journey.js:114-118`: `since=now` in `localStorage['fs-journey-reset']` | none; the server only learns about it through `journey_reset_at` in `POST /api/ground/start` (`app.js:868`) | none | ⚠ Per browser, client-side only. Server evidence (mtimes) is unchanged, so steps derived from file mtimes cannot be redone without touching files. |

---

## 4. Workspace chrome (`index.html`, static elements)

All `<button>` clicks bubble to **one document-level dispatcher**, `app.js:1232-1450`. It is a 218-line `if/else if` chain keyed on `data-*` attributes; the first match wins. Line numbers below point at the matching branch.

| # | Control (file:line) | Label | Handler | Route/state | Endpoint | Server handler | Runs |
|---|---|---|---|---|---|---|---|
| W1 | `a.brand` `index.html:23` | Flight studio | native link | full load to `/infrastructure` (`beforeunload` warns about dirty buffers, `app.js:1210`) | `GET /infrastructure` | `server.py:566` | see section 2 (auto-verify only when `?target` is present; here it is absent) |
| W2 | `.target-switch button[data-target]` `index.html:28-30` | Native / Emulator / Board | dispatcher `app.js:1435` → `selectTarget()` `app.js:1201-1207` | `adoptTarget()`, `?target=` replaced in the URL | `POST /api/hardware/target {target}`, `GET /api/simulation` (qemu), `GET /api/hardware`, `GET /api/ground/catalog` (if on ground) | `server.py:663-664` → `HardwareManager.select_target` (`manager.py:74-78`) | writes `target.json`. ⚠ This is a second, different endpoint for the same concept as S1, and it skips the checks, settings and receipts that S1 does. |
| W3 | `#board-select` (custom listbox, `selectors.js:5-42`) | Board | `mountSelector` onChange `app.js:313` | `state.board=v, state.os=null`; **if v is empty** → `configureProfile()` | `POST /api/mission/profile {board:null,os:null,expected_hash}` then `POST /api/hardware/target` (`app.js:1184-1194`) | `server.py:653-655` → `Workspace.select_profile` (`workspace.py:493-522`) | rewrites `project/config.json` and the generated sources. ⚠ Choosing the placeholder option **"Select board"** switches the mission to the **native** profile while the toolbar target stays Emulator or Board. |
| W4 | `#os-select` | OS | onChange `app.js:314` → `configureProfile()` when a value is chosen | as W3 | `POST /api/mission/profile {board,os}` + `POST /api/hardware/target` | `select_profile` (requires QEMU stopped, `manager.py:462-464`) | mission regeneration. ⚠ Duplicate of S3 through a different endpoint. |
| W5 | `.boot-action[data-job]` `index.html:38` | dynamic: "Start emulator", "Retry QEMU connection", "Set up QEMU", "Check connection", "Prepare board service" (`app.js:356-360`, `terminal.js:5-10`) | dispatcher `app.js:1436` | `data-job` is rewritten on each render (`app.js:356`): physical → `probe` when a connection is saved, else `connect`; qemu → `setup` when docker/ssh/image are missing, else `boot` | `boot`/`probe` → `POST /api/job {action,options:{target,board,os,retry?}}`. `setup` → **`location.href='/infrastructure?target=qemu'`** (`app.js:748`). `connect` → `connect()` dialog (`app.js:742-746`), no request. | `server.py:670-671` → `Studio.job` → `_execute_job` (`server.py:271-304`) → `manager.execute` | `boot` qemu: `bash boot.sh` (docker run) + `systemctl stop cfs.service` over SSH (`manager.py:1036-1062`). `probe`: `ssh … python3 - < hardware/board_probe.py` (`manager.py:665-691`). ⚠ "Set up QEMU" navigates away instead of running anything. ⚠ "Prepare board service" (`connect`) opens a dialog whose Apply button is absent because no host is saved (`app.js:744`). It only offers a link to `/infrastructure?target=physical`, so the label promises an action that never happens. |
| W6 | `.shutdown-action[data-job=shutdown]` `index.html:39` | Stop emulator | `app.js:1436` | | `POST /api/job {action:'shutdown'}` | `_execute_job` → `manager._shutdown` (`manager.py:1097-1114`) | qemu: `bash stop.sh` → `python -m hardware.emulator_ssh ssh systemctl poweroff`, then polls `docker inspect` every 0.5 s for up to 180 s (`manager.py:485-530`) |
| W7 | `.synthetic-action[data-toggle-signals]` `index.html:40` | Synthetic data (switch) | `app.js:1272` → `stopSimulation()` / `startSimulation()` (`app.js:253-272`) | | start: `GET /api/simulation`, `POST /api/simulation` (if dirty), `POST /api/file` (dirty sensor files), `POST /api/job {action:'simulate'}`. stop: `POST /api/job/cancel {id}` per job | `server.py:659-662,625-626,670-673` | `python -u -m sensors.session --events`, which writes QMP properties into QEMU over `board/qmp.sock` (`manager.py:956-982`) |
| W8 | `.build-action[data-job=build]` `index.html:41` | Build cFS / Rebuild cFS | `app.js:1436` → `startJob('build')` `app.js:747-757` | saves all buffers first (`POST /api/file` × n) | `POST /api/job {action:'build',options:{target,board,os,sensorless?}}` | `manager._build` (`manager.py:1012-1034`) | `python3 project/manage.py sync`; `bash scripts/build-cfs.sh --target T` (native cmake, or `docker build --target cfs-builder` + `docker run … cmake`); then `freeze_catalog` (`server.py:298-303`) |
| W9 | `.run-action[data-job=run]` | Run cFS | as W8 | | `POST /api/job {action:'run'}` | `manager._run` (`manager.py:1064-1081`) | native `core-cpu1` + `time.sleep(1)`; qemu `boot.sh` if needed, `check-build`, `sensors/runtime.py prepare`, tar over ssh, `systemctl start cfs.service && sleep 2`; physical upload + `activate_release.py` |
| W10 | `.stop-action[data-job=stop]` | Stop cFS | as W8; the target is `hardware.execution.target` (`app.js:751`) | | `POST /api/job {action:'stop'}` | `manager._stop` (`manager.py:1086-1095`) | native SIGTERM/SIGKILL; qemu `ssh systemctl stop cfs.service`; physical `sudo -n systemctl stop cfs-studio.service` |
| W11 | `[data-theme-toggle]` `index.html:46` | theme | `theme.js` | localStorage | none | none | none |
| W12 | `#operation-output` `index.html:47` | Show output | `app.js:1230` | `terminal.open(job.id)` | none (log lines arrive through `GET /api/jobs`) | none | none |
| W13 | `#workspace-opening button` `index.html:51` | Retry | `app.js:1494` → `openWorkspace()` | | `GET /api/session`, `GET /api/hardware`, `GET /api/workspace` | | none |
| W14 | `.rail-button[data-view=architecture]` `index.html:55` | Architecture | `app.js:1258` → `selectView('architecture')` | `pushState('#architecture')`, so the journey highlights **App** | `GET /api/workspace` (indirect) | | none |
| W15 | `[data-view=bench]` `:56` | Hardware | `selectView('bench')` | `#bench`, journey highlights **Sensor** ⚠ | `GET /api/hardware` | `manager.status` (`manager.py:597-663`) | `docker inspect`, `docker image inspect`, SSH probe(s), `pgrep`, full source fingerprint walk |
| W16 | `[data-view=code]` `:57` | Code | `selectView('code')`, `commandTask=null` | `#code`, journey highlights **Command** ⚠; `state.view='architecture'` + `code-only` | `GET /api/tree?path=flight`, `GET /api/file?path=` | `Workspace.tree` (`workspace.py:91-116`, runs `git` through `library_index._changes`), `read_file` | `git status`-like subprocess per tree expansion |
| W17 | `[data-view=ground]` `:58` | Ground station | `selectView('ground')` | `#ground`, journey highlights **Event** | as J3 | | |
| W18 | `[data-view=simulation]` `:59` | Synthetic data | `selectView('simulation')` | `#simulation`, journey highlights **Sensor** | `GET /api/simulation` | `Workspace.simulation_snapshot` → `sensors.session.load_session` | |
| W19 | `#toggle-terminal` `:60` | Terminal (Ctrl+`) | `terminal.js:112-115` | toggles `body.no-terminal` | none | | |
| W20 | `#search-files` `:64` | Find a file (Ctrl+P) | `app.js:1524-1525` | shows `#file-search` | `GET /api/files/search?root=flight&q=` on input (debounced 160 ms) | `Workspace.search_files` (`workspace.py:143-164`) | `os.walk` over cFS and mission |
| W21 | `#file-results .file-result[data-file]` | file names | dispatcher `app.js:1257` → `openFile()` | | `GET /api/file?path=` | `read_file` | |
| W22 | `#hide-explorer` / `#show-explorer` `:64,70` | Hide or show sidebar (Ctrl+B) | `app.js:1511` | toggles `no-tree` | `GET /api/tree` | | |
| W23 | `#tree .file[data-file]`, `details.tree-group` | file and folder names | `app.js:1257` / `app.js:100` | | `GET /api/file`, `GET /api/tree?path=` | | |
| W24 | splitters `#explorer-splitter`, `#editor-splitter`, `#terminal-splitter` `:68,86,92` | drag, double-click, arrow keys | `layout.js:33-51` | `localStorage['flight-studio-layout']` | none | | |
| W25 | `#simulation-toolbar [data-simulation-save]` `:73` | Save | `app.js:1305` → `saveSimulation()` | | `POST /api/simulation {settings,expected_hash}` (rejected if a simulate job runs, `server.py:660`), then `GET /api/file` | `Workspace.save_simulation` → `project.manage.commit` | writes `sensors/*` and `project/config.json` |
| W26 | `[data-simulation-test]` | Start test / Stop test | `app.js:1307` → `testSimulation()` | | `POST /api/job {action:'simulate-preview',options:{device}}` or `POST /api/job/cancel` | `manager._simulate` | `python -m sensors.session --dry-run --events --steps 24` |
| W27 | `[data-simulation-start]` / `[data-simulation-stop]` | Start / Stop simulation | `app.js:1306,1308` | | as W7 | | |
| W28 | `#tabs [data-file]` / `[data-close-file]` | file tab / × | `app.js:1257,1259` | close saves first | `POST /api/file` (save on close) | `Workspace.write_file` under `Studio.exclusive` | ⚠ Closing a tab during a build fails ("Operation in progress", `server.py:53-59,626`) |
| W29 | `#find-toggle`, `#find-next`, `#find-close`, `#find-query` `:76-77` | Find | `app.js:1212-1214` | client only | none | | |
| W30 | `#editor-expand` `:76` | Expand editor | `app.js:1215` | toggles `code-only` **without changing the hash** | none | | ⚠ The rail then shows "Code" active (`syncNavigation`, `app.js:1499-1503`) while the hash and journey still say e.g. `#bench`/Sensor |
| W31 | `#toggle-editor` `:88` | (expand icon), title "Expand panel" | `app.js:1208` | toggles `no-editor` | none | | ⚠ Duplicate of the `[data-expand-panel]` branch (`app.js:1392`) |
| W32 | `#minimize-terminal` `:94` | Minimize terminal | `terminal.js:114` | | none | | |
| W33 | `details.terminal-open > summary` (`terminal.js:26-29`) | + (Open terminal) | menu | | none | | |
| W34 | `[data-new-shell]` (`terminal.js:79`) | New terminal | `terminal.js:106` | | `POST /api/terminal/create {}` | `Shells.create` | **interactive `$SHELL -i` in a PTY** (`terminal.py:52-57`) |
| W35 | `[data-terminal-stream=flight\|boot]` | Run cFS output / Linux output | `terminal.js:108` → `openLiveLogs()` (`app.js:759-766`) | | `POST /api/job {action:'logs',options:{kind}}` | `manager._logs` (`manager.py:918-954`) | `tail -F native.log`; `bash logs.sh` (`docker logs -f pi4-cfs`); `ssh … journalctl -f` |
| W36 | `[data-terminal-job]` | session | `terminal.js:107` → `open()` | | none | | |
| W37 | `[data-close-terminal]` | × | `terminal.js:98-105` | | shell: `POST /api/terminal/close`; running stream: `POST /api/job/cancel` | `Shell.close` / `Studio.cancel` | kills the PTY or process group |
| W38 | `#shell-terminal` keys | xterm | `shell.js:48-49` (file lines) | | `POST /api/terminal/input`, `/resize`; poll `/read` every 120 ms | `terminal.py` | |
| W39 | `#dialog` submit / `#cancel-dialog` / `#close-dialog` `:99` | Apply (relabelled) / Cancel / × | `dialog()` `app.js:645-650`, `app.js:1209` | depends on the dialog | depends on the dialog | | |
| W40 | `[data-close-inspector]` `:104` | × | `app.js:1354` | closes `#source-inspector-dialog` | none | | |
| W41 | keyboard: Ctrl+S | save | `app.js:1211` → `save()` | | `POST /api/file`, `GET /api/workspace` | `write_file` (exclusive) | |

---

## 5. Workspace dynamic controls, grouped by view

Every row is handled by the dispatcher `app.js:1232-1450` unless another handler is named.

### 5.1 Architecture (`mission-diagram.js`, `mission-stack.js`, `architecture.js`, `app-diagram.js`, `module-actions.js`, `app-wizard.js`)

| Control (file:line) | Label | Dispatcher branch | Effect | Endpoint → server → runs |
|---|---|---|---|---|
| `[data-map-mode]` `mission-diagram.js:159` | 3D / 2D | `app.js:1377` | `state.mapMode` | none |
| `[data-toggle-libraries]` `:160` | Show/Hide libraries | `app.js:1378-1383` | `localStorage['mission.showLibraries']` | none |
| `[data-mission-error-close]` `:161` | × | `app.js:1391` | clears the error | none |
| `select[data-flat-section-picker]` `:162` | Layer | `mission-diagram.js:239-240` (own listener) | `state.mapSection` | none |
| `[data-page-step]` `:92` | ‹ › | `mission-diagram.js:241-245` | paging | none |
| `[data-module-group][data-module-action]` `:71` | New / Edit / Remove | `app.js:1385-1388` → `openModuleAction()` (`module-actions.js:3-68`); for "mission/new" with nothing excluded → `newMissionApp()` | dialog | **New (create)**: `POST /api/mission/draft {kind,name,mode:'create'}` → `Workspace.mission_draft`. The app kind opens the wizard instead (`app.js:1092`). **Add existing**: `POST /api/mission/app\|library {action:'add',name,expected_hash}` → `MissionConfig.change_app/change_library`. **Remove**: `{action:'remove'}`. **Enable/Disable**: `{action:'enable'\|'disable'}`. **Rename**: `POST /api/mission/rename {kind,name,new_name}` → `module_rename.rename_module`. **Configure**: `POST /api/mission/draft {mode:'edit'}`. All of these write mission files through `project.manage.commit`. |
| `[data-arch-app]`, `[data-arch-library]` (`mission-diagram.js:82,87`; `app-diagram.js:75-76`; `architecture.js:12`) | module name | `app.js:1260-1269` | opens the detail pane | none |
| `[data-arch-tab]` `architecture.js:56` | Mission architecture / <name> | `app.js:1260-1269` | `archOverview` | none |
| `[data-arch-clear]` `architecture.js:52` | × | `app.js:1270` | closes the detail | none |
| `[data-arch-follow]` `architecture.js:52` | Show/Hide source | `app.js:1235-1245` | toggles `no-editor`/`no-tree`, **hash unchanged** | `GET /api/file` |
| `[data-arch-source]` (`app-diagram.js:13`, `architecture.js:6`, `mission-diagram.js:148,169-170`) | Code / function names / SB, ES, OSAL, PSP tiles | `app.js:1246-1254` | opens the source read-only | `GET /api/file` |
| `[data-mission-configure]` `architecture.js:52` | Configure app | `app.js:1389` → `prepareMissionDraft(..,'edit')` | | `POST /api/mission/draft {mode:'edit'}` |
| `#mission-draft-form` submit `architecture.js:18,24` | Save app/library | `app.js:1083-1085` → `saveMissionDraft()` `app.js:1123-1140` | | `POST /api/mission/draft` then `POST /api/mission/save {…,plan_hash}` → `Workspace.save_mission_draft` (`workspace.py:481-491`) → `commit` |
| `[data-mission-draft-cancel]` `architecture.js:24` | Cancel | `app.js:1390` | drops the draft | none |
| `[data-first-app]` `mission-diagram.js:101` | Create your first app | `app.js:1384` → `newMissionApp()` → `openAppWizard()` | wizard | `POST /api/mission/draft` ×1-2, `POST /api/mission/save` (`app-wizard.js:95-106`) |
| wizard `[data-close]`, `[data-back]`, submit (`app-wizard.js:72-76,80-113`) | ×, Back, "See its files →" / "Create <name>" / "Next → add a command" | `modal.onclick/onsubmit` | the last step calls `onCommand` → `selectView('code',…,'command')` + `newCodeCommand()` (`app.js:663`) | `POST /api/mutate {action:'add-command'}` on dialog submit |
| `[data-map-code]` (inspector, `mission-diagram.js:190`) | Open code | `app.js:1370` → `selectView('code',path)` | `#code` | `GET /api/tree`, `GET /api/file` |
| `[data-map-ground]` `:191` | Commands | `app.js:1371` → `openGroundRoute(app)` | `#ground` | as J3 |
| `[data-map-section]` `:194` | View in 2D | `app.js:1372-1376` | 2D map | none |
| `[data-cad-node]` svg, `[data-camera]`, `[data-clear-selection]`, `select[data-cad-neighbor]` (`mission-stack.js:170`, `mission-diagram.js:199-200,271-282`) | 3D node, fit/zoom/orbit/pan, ×, Connections | own listeners in `mountMissionMap` (`mission-diagram.js:228-332`) | camera and selection | none. ⚠ The listeners are re-attached on every render. A `ResizeObserver` is created per render (`:247-248`). |
| `.stack-pick[role=button]` (svg, `mission-stack.js:112,163`) | layer captions / boxes | `app.js:1233` (included in the selector) and `app.js:1217-1221` (Enter → synthetic click) | whatever data-attribute is on the node | ⚠ The UI synthesizes `MouseEvent('click')` to drive itself |
| `[data-choose-board]` `mission-diagram.js:127`, `app.js:392` | Select board | `app.js:1255` → `$('#board-select').click()` | opens the toolbar menu by a synthetic click ⚠ | none |
| `[data-view=bench][data-inspect=board]` `mission-diagram.js:125`; OS tile `[data-view=bench]` `:171` | board drawing / OS | `app.js:1258` | `#bench` | `GET /api/hardware` |
| `[data-view=bench][data-device][data-inspect]` `:132` | device id | `app.js:1258` | `#bench`, device selected | `GET /api/hardware` |
| `[data-create=device]` `:128`, `[data-add-bus]` `:128`, `[data-link-hal]` `:132,192` | Add sensor / Add bus / Add HAL | `app.js:1443` / `1419-1424` | the bus and HAL branches first `selectView('bench')`, **pushing `#bench`** | see 5.2 |
| `[data-create=sensor\|telemetry]`, `[data-remove=sensor\|telemetry]` `architecture.js:33-36` | Add sensor / Add telemetry / Detach / packet × | `app.js:1443-1444` → `create()`/`remove()` | dialog | `POST /api/mutate {action:'add-sensor'\|'add-telemetry'\|'remove-sensor'\|'remove-telemetry',payload,expected_hash}`. Add actions go through `scripts/project.sh` → `manage.py`; remove actions go through `Workspace._remove` → `commit`. |

### 5.2 Hardware / bench (`app.js:389-418`, `hardware-links.js`, `board.js`)

| Control | Label | Branch | Endpoint → runs |
|---|---|---|---|
| `[data-inspect=board]` `app.js:400,402` | Connections / board name | `app.js:1433` | none |
| `[data-connect]` `app.js:402` | host ▾ (physical) | `app.js:1445` → `connect()` | none, or `POST /api/job {action:'probe'}` if a host is saved |
| `.assembly-primary` (`hardware-links.js:51`) | Add bus / Connect sensor / Link HAL / Inspect sensor / Build cFS / Start emulator / Set up emulator / Retry emulator connection / Connect board / Run cFS / Test in Ground Station | `data-add-bus` → `app.js:1419-1424` → `busDialog`. `data-create=device` → `create('device')`. `data-link-hal` → `halDialog`. `data-inspect`. `data-workbench-job` → `app.js:1440-1442` **clicks the toolbar button**. `data-workbench-ground` → `openGroundRoute`. | add-bus: `POST /api/mutate {action:'add-bus',payload:{bus}}` → `project.sh add-bus` → `manage.py`. link-hal: `{action:'link-hal',payload:{app,name,device,new_app}}`. Workbench jobs as W5/W8/W9. ⚠ "Set up emulator" → `data-workbench-job="boot"` → toolbar `.boot-action`, whose `data-job` is `setup` → **navigates to `/infrastructure`**. The workbench label differs from the toolbar label ("Set up QEMU"). ⚠ The duplicated `needsSetup` logic is at `hardware-links.js:42` and `app.js:355`. |
| `.assembly-source[data-hardware-source]` `hardware-links.js:36,75` | Open reader | `app.js:1429-1431` → `selectView('code',…)` | `GET /api/file` |
| `[data-remove-bus]` `:62` | trash | `app.js:1425-1428` | `POST /api/mutate {action:'remove-bus'}` → `project.sh` |
| `.port-add[data-create=device][data-preferred-bus]` `:63` | + | `app.js:1443` → `create('device',undefined,bus)` | `POST /api/mutate {action:'add-device',payload:{model,id,bus,address}}` → `project.sh add-device … --value` |
| `[data-design-sensor]` (`app.js:708,711`) | New I²C model | `app.js:1437` → `designSensor()` (`sensor-designer.js:2-45`) | `POST /api/hardware/model {name,address,id_register,id_value,outputs,controls}` → `project.sensor_models.register` (exclusive). The dialog text sends the user to `/infrastructure?target=qemu` to rebuild the image (`sensor-designer.js:11`). |
| `[data-hardware-settings]` `app.js:417` | pencil | `app.js:1432` → `hardwareSettings()` `app.js:470-485` | `GET /api/hardware/device?id=`; submit `POST /api/hardware/device {id,bus,address,pins,expected_hash}` → `hardware_settings.update_device` → `commit`. The 2D bend offset is kept only in `localStorage` (`app.js:478`). ⚠ Pins are stored both in the server config and in browser storage (`app.js:462-469`). |
| `[data-sensor-menu]` `app.js:417` | ⋯ | `app.js:1418` → `sensorMenu()` `app.js:486-490` | dialog with `[data-file=project/config.json]` "Open settings", `[data-job=values]` "Reset all signals" → `POST /api/job {action:'values'}` → `bash scripts/project.sh values` → `python3 sensors/runtime.py values` (QMP), and `[data-remove=device\|sensor\|telemetry]` → `POST /api/mutate` |
| `[data-close-inspection]` | × | `app.js:1434` | none |
| `[data-model-definition]` `app.js:417` | Model definition | `app.js:1256` → `selectView('code', path)` | `GET /api/file` |
| `[data-test-device]` | Test sensor | `app.js:1439` | `POST /api/job {action:'sensor-test',options:{device}}` → `hardware.sensor_probe.probe` (SSH/i2c) |
| `[data-test-model]` | Validate model | `app.js:1438` | `POST /api/job {action:'model-test'}` → `sensor_probe.validate_model` → `python -m project.qemu.check_device` |
| `[data-copy-setup]` (no template emits it; see 7.3) | n/a | `app.js:1446` | clipboard |
| `[data-hardware-refresh]` (no template emits it) | n/a | `app.js:1447` | `POST /api/job {action:'probe'}` or `GET /api/hardware` |
| board 3D/2D, pin and zoom buttons (`board.js:495-501,562-583`) | 3D / 2D / pins / zoom / reset | own listeners | localStorage only |
| `[data-device]` (bare) | device | `app.js:1416` | none |

### 5.3 Code (`source-guide.js`, `app.js:1313-1369`)

| Control | Label | Branch | Endpoint |
|---|---|---|---|
| `.guide-new[data-code-command]` `source-guide.js:171`; `panels.js:131` | New command / New command in code | `app.js:1321` → `newCodeCommand()` | `POST /api/mutate {action:'add-command'}` |
| `.guide-new[data-create=app]` `source-guide.js:172` | New app | `app.js:1443` → `create('app')` → `newMissionApp()` | wizard (5.1) |
| `[data-guide-step]`, `[data-step-move]` `:224,242` | Code / Struct / Prototype / Dispatch / Events / Handler / Test, ‹ › | `app.js:1335-1353` | `GET /api/file`. Step 6 also does `GET /api/ground`. |
| `[data-edit-handler]` `:206,216` | Edit handler | `app.js:1322-1333` | `GET /api/file` |
| `[data-command-test]` `:221` | Test → Open Ground Station | `app.js:1316-1320` | `POST /api/file` × dirty, `GET /api/workspace`, then `openGroundRoute(...,true)` → `#send` |
| `[data-source-jump]` `:227` | jump | `app.js:1366-1369` | `GET /api/file` |
| `[data-dismiss-command]` `:239` | Close activity | `app.js:1315` | `recordRoute('code')`; the journey moves to Command |
| `[data-source-tab]` `:248` | Source / Packet / Dispatch / Tags | `app.js:1355-1365` | Packet also calls `GET /api/ground/catalog` (exclusive) |
| `[data-select-source-command]`, `select[data-guide-command]` | command picker | `app.js:1334`, `app.js:1075` | `GET /api/file` |
| `.source-index-row` `:123` | index row | dispatcher on its own `data-*` | `GET /api/file` |
| tag picker (`source-guide.js:355-389`) | `@` autocompletion | own listeners | none |
| `[data-command-back]` `app.js:500` | Back to code | `app.js:1313` → `resumeCommand` | `GET /api/file` |

### 5.4 Ground Station (`panels.js`, `round-trip-view.js`, `communication.js`, `trip-editor.js`, `command-launch.js`)

| Control | Label | Branch | Endpoint → server → runs |
|---|---|---|---|
| `[data-ground=start\|stop]` `panels.js:89,132` | Connect / Disconnect | `app.js:1448` → `groundConnection()` `app.js:864-872` | `POST /api/ground/start {target,journey_reset_at}` → `Studio.ground_start` (`server.py:404-442`): `manager.status()` (docker + SSH), `ssh systemctl show --property=InvocationID` (`:432-437`), `hardware.ground_link.resolve_ground_link`. For QEMU that runs `docker inspect pi4-cfs` + QMP `hostfwd_add` (`ground_link.py:66-101`). Then `GroundStation.start`: UDP sockets, the PyQt5/zmq `official.Receiver`, and a retry loop that sends `TO_LAB_OUTPUT_ENABLE_CC` 5 × 2 s (`station.py:149-157`). `POST /api/ground/stop` → `GroundStation.stop`. |
| `[data-ground=catalog]` `panels.js:112,126` | Retry / From build | `app.js:1448` → `groundRefresh()` | `GET /api/ground/catalog` (exclusive, may compile), `GET /api/ground`, `GET /api/ground/tests` |
| `#gs-command-form` submit `panels.js:87,90` | Send / Connect & send / Run test / Waiting for HK | `app.js:916-920` → `sendGroundCommand()` `app.js:885-911` | may call `ground/start` first; `POST /api/ground/send {command_id,values,target,test_id}` → `Studio.ground_send` → `GroundStation.send` → `official.Command.send` (UDP) |
| `[data-gs-select]` `panels.js:62` | command | `app.js:1414` | none |
| `[data-gs-source]` `panels.js:87,88,167` | edit icon / dispatch / identifier / Packet type | `app.js:1411` → `inspectGroundSource()` `app.js:1532-1537` | `GET /api/ground/source?kind&id&section&target` (exclusive) → `Studio.ground_source` |
| `#gs-search` input, `#ground-app` select `panels.js:127-128` | Search / Applications | `app.js:1072,1081` | none |
| `[data-all-ground-apps]` `panels.js:130` | All apps | `app.js:1398` | none |
| `[data-ground-pane]` `panels.js:125` | commands / route / telemetry (mobile) | `app.js:1400` | none |
| `[data-open-trip-command]` (coach `panels.js` contactCoach; `communication.js`) | Telemetry on / First command | `app.js:1402` | none |
| `[data-ground-mode]` `round-trip-view.js:132` | Round trip / System overview | `app.js:1397` | none |
| `[data-system-traffic]`, `[data-comm-app]`, `[data-system-packet]` (`communication.js`) | Commands/Telemetry, app blocks, packets | `app.js:1401,1406-1410,1403` | none |
| `select#trip-test` `round-trip-view.js:13` | test | `app.js:1076-1079` | none |
| `[data-edit-trip]` `round-trip-view.js:15-16` | edit / New test | `app.js:1404` → `editTrip()` (`trip-editor.js`) | `GET /api/ground/tests` if missing; save `POST /api/ground/tests {…,id,revision,target}` (`trip-editor.js:24`) → `Studio.ground_plan` → `round_trip` plans (writes JSON); delete `POST /api/ground/tests {delete:true}` (`:76-77`) |
| `[data-inspect-send]` `round-trip-view.js:108` | past send | `app.js:1393-1396` | none |
| `[data-stop-trip]` `round-trip-view.js:139` | stop | `app.js:1405` | `POST /api/ground/tests/cancel {id,session,target}` → `GroundStation.cancel_test` |
| `[data-ground-summary]`, `#ground-packet` `panels.js:217` | summary / packet select | `app.js:1399,1080` | none |
| Launch card `[data-command-launch]` `app.js:500` | Build cFS / Start emulator / Emulator setup / Board setup / Stop previous build / Start cFS / View active flight / Load command / Inspect command / Check target | `app.js:1314` → `advanceCommandLaunch()` `app.js:503-519` | `build/run/stop/boot` → `POST /api/job`. `setup` → **`location.href='/infrastructure?target=T'`** ⚠. `active` → `POST /api/hardware/target` + `openFlightStep('boot')` (**the journey goes backwards**) ⚠. `catalog` → `GET /api/ground/catalog`. `check` → `GET /api/hardware`. `source` → code view. |

### 5.5 Synthetic data (`simulation.js`, `signal-experiments.js`, `orbit-preview.js`)

| Control | Label | Branch | Endpoint → runs |
|---|---|---|---|
| `[data-signal-view]` `simulation.js:56` | Signals / Python / QEMU / Test | `app.js:1276-1280` | `recordRoute('test'\|'sensor')`, so the journey step changes on a tab click. Python tab → `GET /api/file`; QEMU tab → `GET /api/ground` |
| `[data-signal-device]`, `[data-simulation-device]` `simulation.js:40` | device | `app.js:1298,1310` | `GET /api/file` (Python tab) |
| `input[data-simulation-enable]` `simulation.js:40,104` | include | `change` `app.js:303-308` | client state; saved later through `POST /api/simulation` |
| `[data-signal-orbit]` `:56` | Orbit | `app.js:1293` | `recordRoute('sensor')` |
| `[data-signal-hardware]` `simulation.js:56`, `signal-experiments.js:61` | + sensor | `app.js:1299-1303` → `selectView('bench')` then `create('device')` or a **synthetic click on `[data-add-bus]`** (`app.js:1301`). If there is no board: `location.href='/infrastructure?target=qemu'` (`app.js:1302`). | ⚠ Hard-codes `qemu` even when the user is on Board. ⚠ The synthetic click on an element that is not rendered yet does nothing. |
| `[data-signal-begin]`, `[data-board-stop=simulate]` (`simulation.js:45`, `signal-experiments.js:17`) | Send to QEMU / Stop | `app.js:1273,1309` | as W7 |
| `[data-signal-preview-device]` `simulation.js:31` | Run model locally | `app.js:1271` | `POST /api/job {action:'simulate-preview',options:{device}}` |
| `[data-run-signal-test]` `signal-experiments.js:16` | Dry run | `app.js:1295` → `testSimulation()` | as W26 |
| `[data-signal-scenario]`, `[data-run-signal-scenario]` `signal-experiments.js:92` | orbit/eclipse/dropout, Run | `app.js:1281,1282-1292` | `POST /api/job {action:'simulate-preview',options:{device,scenario}}` → `python -m sensors.scenarios device scenario` (compiles the HAL with `cc`, `sensors/scenarios.py:46`) |
| `select[data-signal-script]`, `[data-signal-source]` `signal-experiments.js:14-15` | Python source / open | `app.js:300`, `app.js:1294` | `GET /api/file` / code view |
| `select[data-test-output]` `:93` | Output | `app.js:301` | none |
| `[data-signal-page]`, `[data-series-channel]`, `[data-signal-tab]`, `[data-signal-sidebar]`, `[data-back-sensors]`, `[data-simulation-add]`, `[data-simulation-remove]` | paging / channel / tabs / settings / back / add / remove | `app.js:1274,1275,1296,1297,1304,1311,1312` | none (client state) |
| `#simulation-form` inputs, submit `simulation.js:80,98` | signal settings / Save | `app.js:273-297,311` | `POST /api/simulation` |
| orbit `[data-orbit-play\|rate\|source\|model\|preset\|import]`, `input[data-orbit-number\|element]`, globe drag (`orbit-preview.js:61-74,219-284`) | play / 1× 60× 600× / elements / TLE / presets / Import | own **document-level** listeners (`orbit-preview.js:219,236,244,262,270-284`) | `POST /api/simulation/orbit {elements\|tle,cycle,materials}` → `sensors.orbit.preview` (runs in the HTTP thread, **not** exclusive). Debounced 90 ms (`:217`). |

### 5.6 Boot view (`first-boot.js`)

| Control | Label | Handler | Endpoint |
|---|---|---|---|
| `a` `first-boot.js:210` | Change | link → `stepUrl('target')` → `/?target=T#target` | full load to setup (auto-verify, J1) |
| `.boot-stage[data-stage]` `:76` | stage cards | `first-boot.js:275-287` | none (replay) |
| `.boot-layer[data-layer]` `:221` | Apps / cFE / OSAL / PSP / OS / HW | `:288` | none |
| `[data-replay]`, `[data-pause]` `:212-213` | Replay boot / Pause view | `:289-296` | none |
| `[data-console]` `:229` | Open/Close console | `:297` | none |
| `[data-retry]` `:234` | Retry first boot | `:298` → `start()` | `POST /api/job {action:'first-boot'}` (J2) |
| `a` `:234` | Check target | `stepUrl('target')` | J1 |
| ⚠ The same clicks also bubble to the global dispatcher `app.js:1232`. None of their `data-*` keys match a branch today, but nothing enforces that. | | | |

---

## 6. Reverse map: every server route

### 6.1 GET (`server.py:546-579`)

| Route | Server handler | What it runs | Callers |
|---|---|---|---|
| `/api/journey?target` | `journey.snapshot` (`journey.py:106-120`) | reads the config, `stat()`s CMakeLists and fcncodes, loads ~5 runtime JSON files, `ground_snapshot()` | `journey.js:94` (every 3.5 s on both pages) |
| `/api/session` | inline `{token}` | none | `app.js:52,1470`, `infrastructure.js:33,490` |
| `/api/workspace` | `Workspace.snapshot` (`workspace.py:224-271`) + `hardware.builds_status` (`manager.py:146-158`) | parses every app, runs `summarize_application` per app, `inspect_libraries`, `git` subprocesses (`library_index.py:13`), and **stat()s every file under `cFS/`, `mission/`, `project/`** for the fingerprint (`manager.py:160-204`) | `app.js:61` (each mutation, plus every 15 s, `app.js:1497`) |
| `/api/tree?path` | `Workspace.tree` | `git` via `library_index._changes` | `app.js:94` |
| `/api/files/search?root&q` | `Workspace.search_files` | `os.walk` | `app.js:1518` |
| `/api/file?path` | `Workspace.read_file` | read and annotate | `app.js:113,228,236,1117` |
| `/api/hardware` | `HardwareManager.status` (`manager.py:597-663`) | `docker inspect` (30 s timeout), SSH flight probe (8 s), physical SSH probe, `pgrep`, `docker image inspect`, fingerprint | `app.js:819` (on job completion, every 15 s on workbench views, on view change) |
| `/api/first-boot?target` | `first_boot.snapshot` with `journal=Studio.follow_boot_journal` | copies **all job lines**, SSH `observed_flight`, **may start a `logs` job** (side effect) | `first-boot.js:253` (every 600 ms) |
| `/api/infrastructure[?verify_source=1]` | `infrastructure.snapshot` | `~/.ssh` scan, check plans, `source_status` (git) when `verify_source=1` | `infrastructure.js:298,491`. ⚠ `verify_source=1` has **no UI caller** (tests call the function directly, `test_setup_checks.py:120`). |
| `/api/simulation` | `Workspace.simulation_snapshot` | `sensors.session.load_session` | `app.js:189` |
| `/api/hardware/device?id` | `hardware_settings.device_settings` | none | `app.js:471` |
| `/api/jobs` | `Studio.jobs_snapshot` | serializes up to 30 jobs × 3000 lines each, plus shells | `app.js:777` (every 1.5 s), `infrastructure.js:289` (every 400 ms during installs), `infrastructure.js:495` |
| `/api/ground/catalog?target` | `Studio.exclusive(ground_catalog, wait=3)` | `freeze_catalog` → compiler/cmake inspection on a cache miss | `app.js:848` |
| `/api/ground/tests` | `GroundStation.plans.read` | none | `app.js:848` |
| `/api/ground` | `Studio.ground_snapshot` | none | `app.js:848,882,1346` |
| `/api/ground/source?...` | `Studio.exclusive(ground_source, wait=3)` | `source_locations` | `app.js:1534` |

### 6.2 POST (`server.py:625-698`)

| Route | Server handler | Runs | Callers |
|---|---|---|---|
| `/api/file` | `exclusive(Workspace.write_file)` | atomic write, or `commit()` for model.json and startup | `app.js:182` |
| `/api/infrastructure` | `exclusive(infrastructure.save, app, body)` | target.json, connection.json, emulator.json, native-build-settings.json, **`workspace.select_profile`** | `infrastructure.js:220` |
| `/api/infrastructure/check` with `label` | `infrastructure.check_one` (**not exclusive**, blocking ≤30 s) | one probe subprocess | `infrastructure.js:252` |
| `/api/infrastructure/check` without `label`, `Accept: application/x-ndjson` | `Handler.stream_checks` (`server.py:512-537`) | all probes, streamed | ⚠ **UNUSED by the UI** (only `test_setup_checks.py:39-63`) |
| `/api/infrastructure/check` without `label`, JSON | `infrastructure.check` (`infrastructure.py:331-337`, "Compatibility response") | all probes | ⚠ **UNUSED** |
| `/api/mutate` | `exclusive(Workspace.mutate)` | `bash scripts/project.sh <action>` → `python3 project/manage.py` (add-*, link-hal, remove-bus, remove-device); `_remove` → `commit` (remove-sensor, remove-command, remove-telemetry); `remove-app` → `MissionConfig.change_app` | `app.js:449,673,712,740`. ⚠ Actions `add-app`, `remove-app` and `remove-command` have **no UI caller** (grep: no `data-remove="command"` or `"app"`; `create('app')` returns early to the wizard at `app.js:689`). |
| `/api/mission/app` (`action:'delete'`) | `exclusive(Workspace.delete_app)` | `module_delete.delete_app` | ⚠ **UNUSED by the UI** (`delete` is never sent; only the CLI calls `Workspace.delete_app` directly, `start:158-159`) |
| `/api/mission/app` (other actions) | `exclusive(Workspace.mission_app)` | `MissionConfig.change_app` | `app.js:1150` (add/remove/enable/disable) |
| `/api/mission/library` | `exclusive(Workspace.mission_library)` | `change_library` | `app.js:1150` |
| `/api/mission/rename` | `exclusive(Workspace.rename_module)` | `module_rename.rename_module` | `app.js:1173` |
| `/api/mission/draft` | `exclusive(Workspace.mission_draft)` | in-memory plan | `app.js:1097,1129`, `app-wizard.js:95,100` |
| `/api/mission/save` | `exclusive(Workspace.save_mission_draft)` | `commit` | `app.js:1130`, `app-wizard.js:104` |
| `/api/mission/profile` | `exclusive(Workspace.select_profile)` | `commit` of the regenerated mission | `app.js:1189` |
| `/api/simulation/orbit` | `sensors.orbit.preview` (not exclusive) | numerical propagation | `orbit-preview.js:171,255` |
| `/api/simulation` | `exclusive(Workspace.save_simulation)` | `commit` | `app.js:226` |
| `/api/hardware/target` | `exclusive(HardwareManager.select_target)` | target.json | `app.js:1191,1202` |
| `/api/hardware/model` | `exclusive(project.sensor_models.register)` | writes the model and driver | `sensor-designer.js:15` |
| `/api/hardware/device` | `exclusive(hardware_settings.update_device)` | `commit` | `app.js:477` |
| `/api/job` | `Studio.job` | see 6.3 | `app.js:755`, `first-boot.js:248` |
| `/api/job/cancel` | `Studio.cancel` | sets the cancel event | `app.js:270,1229` |
| `/api/terminal/create` | `Shells.create` | PTY: setup command or interactive shell | `infrastructure.js:408`, `terminal.js:106` |
| `/api/terminal/read` | `Shell.read` | none | `shell.js:59` |
| `/api/terminal/input` | `Shell.write` | none | `shell.js:48` |
| `/api/terminal/resize` | `Shell.resize` | none | `shell.js:49` |
| `/api/terminal/close` | `Shell.close` | kills the PTY session | `terminal.js:100` |
| `/api/ground/start` | `exclusive(Studio.ground_start)` | SSH, docker, QMP, UDP receiver | `app.js:868` |
| `/api/ground/stop` | `exclusive(GroundStation.stop)` | none | `app.js:868` |
| `/api/ground/send` | `exclusive(Studio.ground_send)` (`wait=0`) | UDP send | `app.js:908`. ⚠ Fails with "Operation in progress" whenever *any* exclusive job runs (e.g. `values`, `sensor-test`). |
| `/api/ground/tests` | `exclusive(Studio.ground_plan)` | writes plans | `trip-editor.js:24` |
| `/api/ground/tests/cancel` | `GroundStation.cancel_test` | none | `app.js:1405` |

### 6.3 `POST /api/job` actions (`server.py:37-39`, `_execute_job` `server.py:271-304`, `manager.execute` `manager.py:856-916`)

| action | Runs | UI caller |
|---|---|---|
| `first-boot` | `first_boot.execute`: build → catalog → (qemu boot) → run → follow logs | `first-boot.js:248` (auto on view open, and Retry) |
| `clone-cfs` | `scripts/install-cfs.sh` (`server.py:275-278`) | ⚠ **UNUSED**; the UI uses `terminal/create {setup_action:'clone-cfs'}` |
| `setup` | physical: `prepare_board`; qemu: `bash scripts/setup.sh` in a non-interactive job with `SUDO_ASKPASS=/bin/false` (it would fail at sudo) | ⚠ **UNUSED**: the UI turns `setup` into a navigation (`app.js:509,748`) |
| `build`, `run`, `stop`, `shutdown`, `boot` | see W5-W10 | toolbar, workbench, launch card |
| `connect`, `probe` | `probe` (+ `prepare_board` for connect) | `probe`: toolbar/connect dialog. `connect`: ⚠ never sent; the toolbar's `connect` opens a dialog instead (`app.js:1436`) |
| `logs` | `_logs` | `app.js:765`; internally from `follow_boot_journal` |
| `values` | `bash scripts/project.sh values` → `sensors/runtime.py values` | sensor menu "Reset all signals" |
| `simulate`, `simulate-preview` | `sensors.session`, `sensors.scenarios`, `sensors.<model>` | Synthetic data |
| `model-test`, `sensor-test` | `hardware.sensor_probe` | bench inspector |

### 6.4 Terminal `setup_action`s (`terminal.py:21-28`)

All six (`clone-cfs`, `board-key`, `board-service`, `native-tools`, `dependencies`, `emulator-image`) are reachable from `setup-plan.js:15-22` `repairFor()` → `infrastructure.js:408`. `dependencies` and `emulator-image` both run `scripts/setup.sh` (one with `--build-only`).

---

## 7. Front-end handlers with no emitter, and emitters with no handler

### 7.1 Dispatcher branches whose `data-*` is never emitted (dead branches)
- `copySetup` (`app.js:1446`) and `hardwareRefresh` (`app.js:1447`): `grep -rn "data-copy-setup\|data-hardware-refresh" interface/static` returns nothing.
- `selectView('communication')` remap (`app.js:988`), the `communication` key in the title map (`app.js:571`), and the `.communication-browser>nav,.communication-message` scroll restore (`app.js:549,608`): no template emits `data-view="communication"` or those classes (grep shows only these app.js lines). These are leftovers of a removed "Communication" view. The matching CSS is listed in `code_report.md` §6.
- `create()` branch `if(kind==='app' && …code-only)` (`app.js:714-717`): unreachable, because `kind==='app'` returns at `app.js:689`.

### 7.2 Attributes emitted but never read by JS or CSS
- `data-arch-expand` (`app-diagram.js:79`).
- `data-assembly-stage` (`hardware-links.js:50`).
- `data-mission-block` (`mission-diagram.js:81`).
- Evidence: `grep -rn "archExpand\|arch-expand\|assemblyStage\|assembly-stage\|missionBlock\|mission-block" interface/static` returns only the emitting line, plus `.arch-expand` in `workspace.css:278`, which is a class selector, not the attribute.

### 7.3 Server capabilities with no UI path
`/api/infrastructure/check` streaming and batch modes, `?verify_source=1`, job actions `clone-cfs`/`setup`/`connect`, `/api/mission/app action=delete`, and mutate actions `add-app`/`remove-app`/`remove-command`.

---

## 8. Mismatch list (navigation and labels)

1. **Navigation writes state.**
   - J1 and J9 POST `/api/infrastructure` simply by opening the step (`infrastructure.js:506` → `:243`). J9 switches the persisted target to physical (`infrastructure.py:137`).
   - J2 starts a full build and deploy by opening the step (`first-boot.js:258`).
   - J5 reopens dialogs on Back/Forward (`app.js:974` → `:940-952`).
   - `GET /api/first-boot` spawns a `logs` job (`server.py:332`).
2. **Rail ↔ journey contradictions** (`journey.js:16`):
   - Hardware → *Sensor*, but the Sensor step opens Synthetic data.
   - Code → *Command*, but the rail clears the command activity (`app.js:1258`).
   - Ground → *Event* even when the user is doing Send.
   - Architecture → *App*.
   - Unknown hash → *App* (`workspace-route.js:11`).
3. **Labels that redirect elsewhere:**
   - "Set up QEMU", "Set up emulator", "Emulator setup" and "Board setup" navigate to `/infrastructure` (`app.js:509,748`). The emulator ones are hard-coded to `?target=qemu`.
   - "+ sensor" with no board goes to `/infrastructure?target=qemu` even on the Board target (`app.js:1302`).
   - "Prepare board service" opens an informational dialog (`app.js:742-746`).
   - The "Select board" placeholder sets the native profile (`app.js:313`).
   - "View active flight" jumps back to Boot (`app.js:512`).
   - The "Board" journey pill opens a settings form, not a deploy.
4. **Duplicate routes and concepts:**
   - `/` = `/infrastructure`.
   - Two target-selection endpoints (`/api/infrastructure` vs `/api/hardware/target`).
   - Two profile-selection endpoints (`/api/infrastructure` vs `/api/mission/profile`).
   - Two clone paths (`job clone-cfs` vs `terminal clone-cfs`).
   - Two batch-check APIs (ndjson vs JSON) besides the per-label one.
5. **Steps enterable in an invalid state:**
   - Event with cFS stopped.
   - Send with no authored command.
   - Sensor and Test on Native or Board (impossible there).
   - Command and App while a build holds the global lock: the mission POSTs fail with "Operation in progress" (`server.py:53-59`).
6. **Steps credited from non-durable or cross-target evidence:**
   - Event resets on reconnect (`journey.py:38-41`).
   - Sensor and Test evidence is global, not per target (`journey.py:49-62`).
   - Target, App and Command come from file mtimes (`journey.py:19,30,103`).
7. **Hash not updated** by "Expand editor" (`app.js:1215`), "Show source" (`app.js:1235-1245`) and `data-arch-source` (`app.js:1246-1254`). The rail highlight, `state.view` and the journey step then disagree.
