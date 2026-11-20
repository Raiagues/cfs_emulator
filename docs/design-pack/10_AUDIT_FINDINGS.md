# Audit findings (branch first-flight-flow, commit 071396c)

Three passes: a code reading of the navigation, journey and server; a full click-through of the running UI as a first-time user (Native target built and booted for real); and a run of the infrastructure from the terminal (native build, run, ground link, app and library generation, sensor preview, emulator image). Severity: **must fix** (breaks a rule or a flow), **should fix** (quality), **keep** (works, don't break it).

The detailed reports are in `audit/` (click-through report with screenshots in `audit/ux/`, infrastructure report with logs).

## A. Keep (works today)

- Native path end to end: clone nasa/cFS, build, run to OPERATIONAL, stop.
- Ground station: commands and telemetry decoded from the build's own catalog; NOOP round trips pass for sample_app, to_lab, ds, fm, hk, hs, lc, md, sc and the cFE services.
- App and library generation from the CLI, and their builds.
- Security basics in `interface/server.py`: per-session token on POST, Host and Origin checks, static path traversal check, CSP header, request size limit.
- The job runner (`Studio.job`) with exclusive operations, cancellation and bounded logs.
- Unit tests: 79 tests, all passing; with the NASA `cFS/` checkout present 1 is skipped, without it 3 are skipped, including the two end-to-end HTTP tests of the mission workflow (so on a fresh clone the most important integration tests never run; make them fetch or require the checkout in CI). JavaScript tests: 33 of 33 pass. No CI runs either suite.
- The Target and First boot screens are close to their designs.

## B. Navigation and journey (must fix)

1. **The current step is decided by the URL, not by progress.** `interface/static/journey.js` maps rail views to steps (`railSteps = {architecture:'app', bench:'sensor', code:'command', ground:'event', simulation:'sensor'}`). Opening the Ground station view during the Send step marks Event as current; opening Synthetic data during Test marks Sensor as current. Fix: the step bar renders from the server's `current` (see `02_ARCHITECTURE.md`); rail views never change it. Fixed in `e8379b8`.
2. **Steps are credited out of order.** Fixed in `7c45166`. `interface/backend/journey.py` `derive()` marks each step done from its own evidence only. An app created before the first event marks App done while Event is not. Fix: `done[step] = evidence and done[previous]`.
3. **Reset lives in one browser.** "Start over" stores a cutoff in `localStorage` (`fs-journey-reset`); the server and other tabs keep the old progress. Fix: `POST /api/journey/reset` stored server-side. Fixed in `e8379b8`.
4. **Next can point past an incomplete step.** `journeyNavigation()` returns `stages[index+1]` when the current step is done, without checking earlier steps. Fix: `next_route` from the server. Fixed in `e8379b8`.
5. **A button keeps its label but changes its destination.** `app.js:356` switches the toolbar "Start emulator" button's `data-job` to `setup` when setup is missing; `app.js:748` then redirects to `/infrastructure?target=qemu`. The user presses "Start emulator" and lands on another page. Fix: show "Set up emulator" (or a disabled button with the reason) when setup is missing.
6. **Navigation is written from many places.** `location.href`/`history.*`/`href` are set in `app.js` (lines 509, 744, 748, 928, 930, 946, 968, 1204, 1302, 1477), `infrastructure.js:487`, `first-boot.js:210,234`, `sensor-designer.js:11`, `emulator-guide.html`, `journey.js` (step links). Fix: one router module. Fixed in `e8379b8`.
7. **Unreachable steps are clickable links** in the step bar (every stop gets an `href`). Fix: only reachable stops are links. Fixed in `e8379b8`.

## C. Code review (full report: `audit/code_report.md`; control-to-endpoint map: `audit/endpoints.md`)

Must fix:

1. **F1 · Opening a route has side effects.** Fixed in `311b8fc`. Mounting Boot POSTs `/api/job {action:'first-boot'}` (`first-boot.js:258`), which builds and deploys; any setup URL with `?target=` auto-verifies and saves the target (`infrastructure.js:506`, `:243` → `hardware/infrastructure.py:137`), which can regenerate mission sources; the Board pill is `/?target=physical`, so clicking it switches the saved target; Back onto `#command` reopens dialogs (`app.js:940-974`); `GET /api/first-boot` starts a `logs` job. Routes must be pure views: mutations only from labelled buttons, idempotent GETs, Back/Forward only re-render. Test: load every route and assert no POST was issued and no job exists.
2. **F2 · Four unsynchronised sources of navigation truth**: `location.hash`, `state.view` (`app.js:23`), body classes (`code-only`, `no-editor`, `no-tree`, `simulation-mode`) and the journey's `railSteps` alias table. "Code" is a CSS trick over the Architecture view (`app.js:991-992`, `workspace.css:265`). "Expand editor", "Show source" and `data-arch-source` change classes without the hash. One `router.js` with `{id, path, view, step, guard}`; everything else derived.
3. **F3 · Journey evidence is fragile, not durable and not per target** (server storage and event producers in `7c45166`): Target, App and Command from file mtimes (`journey.py:19,30,103`); Event only from the live ground session (resets on reconnect, `:38-41`); Sensor and Test global (`:49-62`); reset is a browser `localStorage` cutoff. Append evidence records `{step, target, at, ref}` at the moment of observation; reset is a server event; `derive()` is a fold.
4. **F4 · One global lock** (fixed in `89b7dec`) (`Studio.exclusive`, `server.py:53-59`) held for whole builds blocks file save, mission edits, `ground/send` and even GETs: "Operation in progress" during any build. Separate workspace, per-target runtime and catalog locks.
5. **F5 · Heavy blocking work in HTTP threads, polled aggressively**: `GET /api/hardware` runs `docker inspect` (30 s timeout), SSH probes, `pgrep` and a full-tree fingerprint on every call; `/api/jobs` serialises up to 30 × 3,000 lines every 1.5 s. Background monitor with TTL, SSE events, cursor logs, cached fingerprints.
6. **F6 · Inverted dependencies** (mission, jobs and boot moved to core in `89b7dec`): `hardware/infrastructure.py:94` takes the HTTP `Studio` object; the CLI imports `interface.backend.workspace`; the first-flight pipeline lives in `interface/backend/first_boot.py`; deployment policy lives in browser code (`command-launch.js`, `setup-plan.js`, `app.js:355`). Core package + CLI, thin adapter (see `02`).
7. **F7 · Ad-hoc runtime JSON** (fixed in `a3bf49e`) (about 15 files, no schema) read through private members across modules; real bug: `hardware/infrastructure.py:134` clears `_physical_observation`, which doesn't exist (the cache is `_flight_observations`). Typed state store with public methods.
8. **F8 · The default target disagrees** (fixed in `d04b712`): `manager.py:67-72` defaults to QEMU when the config has a board (it does), the setup page defaults to Native, `scripts/build-cfs.sh:127` re-implements the rule. A fresh `./start --no-ui build` does a flight build that needs Docker. One `default_target()`; ship native or require an explicit first choice.
9. **F9 · The ground station imports the PyQt5 desktop app** (`ground_station/official.py:18-33`) to send UDP, and closes a third-party class socket at import. Use a small UDP sender/decoder; drop PyQt5/zmq as runtime requirements of the Studio (this also removes the installer loop in D3). Fixed in `c553a14`.
10. **F10/F11 · QEMU ground link only on a Linux Docker bridge, live-patched networking; hard-coded container name and ports** prevent two checkouts or emulators.
11. **F16/F17 · Security**: any local user can obtain a shell through the terminal endpoints, and the editor can rewrite the server's own files; remote commands are built as shell strings. Restrict the editable tree to the mission; pass argument lists to SSH.

Should fix (details in the report): F12 sleeps and retries hiding races; F13 duplicated logic across layers; F14 `app.js` god module that drives itself through synthetic clicks; F15 CSS patch layers, alias variables and dead classes; F18 Python → bash → Python chains; F19 interpreter-global state; F20 legacy shims in hot paths; F21 the sensorless build copies the whole tree; F22 two deploy procedures and two service units; F23 tests that assert implementation details, default skips, no CI, no end-to-end; F24 non-reproducible image; F25 coarse error mapping; F26 hand-rolled routing; F27 author-environment leftovers and doc drift; F28 heuristic terminal input detection; F29 wiring state split between server and browser.

Dead code to delete (evidence in `audit/code_report.md`): `emulator-guide.html` (nothing links to it), `project/qemu/catalog.py`, `hardware/run.py`, the duplicate entry point `run.sh`; unused server paths (job actions `clone-cfs`, `setup`, `connect`; the streaming and batch setup-check modes; `?verify_source=1`; mission app `delete` over HTTP; mutate actions `add-app`, `remove-app`, `remove-command`); the removed "Communication" view in `app.js` (lines 549, 571, 608, 988) and unreachable branches (714-717, 1446-1447); about 90 dead CSS classes, 92 selectors defined in more than one file, `:root` redefined seven times (including a `--green` that is grey, `workspace.css:193`), 44 `!important`. Front-end tests that encode the inconsistent step mapping (`journey-navigation.mjs:33-44`) must be rewritten against the new journey.

Label and route mismatches to fix (from `audit/endpoints.md` §8): "Set up QEMU", "Set up emulator", "Emulator setup" and "Board setup" all navigate to `/infrastructure` (`app.js:509,748`), the emulator ones hard-coded to `?target=qemu`; "+ sensor" without a board goes to `/infrastructure?target=qemu` even on Board (`app.js:1302`); "Prepare board service" only opens an information dialog (`app.js:742-746`); the "Select board" placeholder sets the native profile (`app.js:313`); "View active flight" jumps back to Boot (`app.js:512`); duplicate concepts: `/` = `/infrastructure`, two target-selection endpoints (`/api/infrastructure`, `/api/hardware/target`), two profile endpoints, two clone paths, two batch-check APIs.

## D. UX click-through

Full report: `audit/ux_report.md` (51 issues, each with screenshot in `audit/ux/shots/`, repro and fix; plus a table of every control). The person ran the whole first flight on Native: Event worked, created `hello_app`, added a `greet` command, implemented it, and a send test passed. Must fix:

1. **Boot spins forever when cFS exits** (issue 1, blocker): the log shows `CFE_PSP: Exiting cFE` but the job stays running, the timer keeps counting, no error, no retry.
2. **Opening step 9 "Board" switches and saves the whole workspace to the physical target** (issue 2, blocker): progress drops from 5/9 to 2/9, step links point at the board, Event then shows a broken screen.
3. **Setup installer loops** (issue 3): its log says packages are ready while the UI's Python check keeps failing (PyQt5 checked differently; apt built it for Python 3.12, the Studio runs 3.13).
4. **Progress goes backwards** when cFS stops or restarts (issue 4): Event unticks while Send stays ticked.
5. **The step highlight follows the open screen, not progress** (issue 5); **every future step can be opened early** and shows broken screens (issue 6), including a 746 px magnifying-glass icon that pushes the Round trip / System overview buttons out of reach (issue 38).
6. **The Command step is ticked when the command is named**, while the editor shows 0/7, with two competing Next buttons (issue 7); the seven-step editor never blocks (a handler returning `CFE_STATUS_NOT_IMPLEMENTED` passes) and the Events step doesn't say what to write; the handler file lacks the include for event IDs (issue 8).
7. **A successful send of your own command isn't recognised**; the person has to discover "··· → New test" (issue 9).
8. **Sensor and Test are dead ends on Native** (issue 10). Native transport and scenario evidence implemented in `004f73e`.
9. **Reloading Boot rebuilds and restarts**; "Replay boot" looks like a rebuild (issue 11).
10. **Commands sent on the person's behalf** (ten `TO_LAB_ADD_PKT_CC`, silent re-enable) flood counters and logs (issues 12, 39).
11. **Too many highlights at once** (six on the first Event visit; "Build cFS" always amber) and **pre-filled choices** (dest_IP, NOOP auto-selected, payload, Native preselected) (issues 25, 26, 28).
12. **Install errors** are stale small red text naming the wrong group ("Toolchain · exit 1" on Board, which has no Toolchain group); the real causes are only in the log (issues 19 to 22).
13. **Round trip diagram and System overview** are polluted as the owner said (issues 36, 37); the catalog jumps from 3 to about 400 commands after the first success (issue 27).

Good, keep: no page scroll at 1440×900 or 1280×720 on any measured screen (issue 50); visible focus outlines and accessible names on icon buttons (issue 51).

## E. Infrastructure run

Full report with commands, timings, logs and exact patches: `audit/infra_report.md` (sections 1.2, 2.4, 3.2, 4 and 5). Must fix:

1. **`run` reports success when cFS has already died.** Fixed in `fbe7abc`. `hardware/manager.py` `_run_native` only checks that the process is alive after 1 second. Seen twice: cFS exited with `OS_QueueCreate errno 22` (running as root without `CAP_SYS_RESOURCE`, cFS asks for queues deeper than `msg_max=10`; happens in Docker and CI), and CI_LAB failed to bind UDP 1234 because another process held it; in both cases `run` exited 0 and `status` said running. Fix: wait for `CFE_ES_Main entering OPERATIONAL state` with a timeout, fail on early exit, queue-create errors or the CI_LAB bind error with a one-line hint, and check the UDP ports before starting. Same for `_run_qemu`.
2. **`setup-native.sh` says PyQt5 and zmq are ready when they cannot be imported.** Fixed in `c553a14`. It locates packages instead of importing them; apt installed them for Python 3.12 while `python3` is 3.13. Fix in `hardware/host_tools.py`: test real imports with the interpreter that will run the ground station; recommend a venv when the distro Python differs; also check `pgrep` and `stdbuf`.
3. **Emulator image tag does not match the branch.** `:latest` carries main's sensor-model fingerprint (`97259d0f…`) but this branch needs `4ecbafff…`, so a newcomer downloads several GB and then rebuilds locally. Fix: tag by fingerprint, publish from any branch that changes emulator inputs, multi-arch, pass `--platform`.
4. **Board binaries need glibc 2.38** (built on Debian trixie; confirmed `__isoc23_strtol@GLIBC_2.38`) and will not start on Raspberry Pi OS Bookworm (glibc 2.36). Fix: build in `debian:bookworm-slim` and check the glibc requirement before upload.
5. **`cfs-studio.service` runs a binary from the user's home as root, startable without a password.** Fix: run as the user with only the needed capabilities.
6. **No ground station command in the CLI.** Fixed in `06021be`. Add `./start --no-ui ground …` (the `GroundStation` class already does everything; the live tests prove it).
7. **NASA cFS is cloned at HEAD with no pinned revision.** Installation and repeated clean-clone verification in `cc3023e`. Pin a tag or commit in one place and show it in the README.

Should fix:

8. Docker Desktop (macOS, Windows/WSL2): QMP is a Unix socket inside a bind mount and the ground link needs the container's bridge IP; both break. Move QMP to loopback TCP, publish the UDP ports, or state clearly in the README that the emulator needs Linux with Docker Engine until then. The container name `pi4-cfs` and SSH port 2222 are fixed, so only one emulator per machine.
9. `simulate-preview --model mpu6050` prints nothing and exits 0: the model and the template for new models lack a `__main__` block.
10. CLI output: app, library and status commands dump 100 to 570 lines of JSON; make human output the default and add `--json`. `project` and `simulate` help shows `manage.py` and a `--root` option that `./start` rejects. Errors name UI buttons or low-level scripts instead of `./start` commands. Piping output gives a BrokenPipe traceback.
11. `scripts/setup.sh` refuses root (fine for a desktop user) but must say why and what to do, and the README must say it.
12. Not documented: disk use, image build and boot times, and software emulation (TCG) slowness without KVM.
13. Add a CI smoke test: build → run → ground check → stop on native.
