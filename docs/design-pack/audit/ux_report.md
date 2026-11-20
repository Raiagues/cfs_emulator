# Flight Studio: UX audit of the first-flight flow

Branch `first-flight-flow` (commit `071396c`), working copy `<repo>`, audited 2026-11-19/20.
Screenshots are in `audit/ux/shots/` (all names below are relative to that folder). Logs are in `audit/ux/logs/`.

---

## 1. How I ran it

### Environment
Ubuntu 24.04 container, root, 2 CPUs, 7 GB. The default `python3` is a custom build, `/usr/local/bin/python3` 3.13. Chrome 153 runs headless. There is no Docker daemon and no KVM. Another agent was working in `<repo>` at the same time. Its `apt-get update` held the apt lock during my first install attempt, and it later ran its own cFS in a separate network and IPC namespace.

### Commands, in order

| Time (local) | Command / action | Result |
|---|---|---|
| 21:08 | `cd <repo> && ./start` | UI on http://127.0.0.1:8765. |
| 21:08 | `google-chrome --headless=new --no-sandbox --remote-debugging-port=9222 --user-data-dir=audit/ux/chrome-profile` | One persistent browser. Small Playwright scripts attach over CDP (`audit/ux/lib.cjs`, `do.cjs`), so the page keeps its state between steps. Viewport 1440×900; 1280×720 checked as well. |
| 21:09 | Opened `/`, chose **Native**, clicked **Install requirements** | Failed after 3 s: **"Native tools · exit 1"**. The log shows an apt lock held by the other agent's `apt-get update`. |
| 21:12 | Clicked the **+** on **Source** | NASA cFS shallow clone with submodules, about 20 s. Source turned green. |
| 21:16 | **Install requirements** again, after the apt lock was released | **Endless loop.** The installer prints "Native build tools and Ground Station packages ready." but the UI check still fails ("Check Ground Station Python packages"). apt's PyQt5 is built for Ubuntu's Python 3.12, while the Studio runs on Python 3.13 (see issue 3). |
| 21:17 | Workaround from the README: `python3 -m venv audit/ux/venv`, then restart the server with `VIRTUAL_ENV=… PATH=venv/bin:$PATH venv/bin/python3 ./start`. I killed only my own server PID. | **Install requirements** ran `pip install -r ground_station/requirements.txt` inside the venv (about 30 s). All three groups turned green and **Continue to boot** appeared. |
| 21:18 | **Continue to boot** | Native build of cFS with 2 jobs: Build cFS done in about **66 s**. cFS then **died** during CORE_STARTUP (`OS_QueueCreate … errno 22 … msg_max`, then `CFE_EVS … Application Init Failed`, `PROCESSOR RESET`, `CFE_PSP: Exiting cFE`). The UI kept spinning on **Starting core** for more than 5 minutes (see issue 1). |
| 21:24 | Restarted my server inside a private IPC namespace: `unshare --ipc sh -c 'echo 256 > /proc/sys/fs/mqueue/msg_max && VIRTUAL_ENV=… exec venv/bin/python3 ./start'`. The default namespace kept `msg_max=10`. | Reloading `#boot` **started a new build and boot by itself**. It reached OPERATIONAL in **19 s** (incremental build) and showed **cFS is running**. |
| 21:26–21:27 | Event step: Connect, ENABLE_OUTPUT, NOOP | Worked. First event and CommandCounter 0 → 1. Guide showed 3/9. |
| 21:28 | App step: wizard, `hello_app` | Created. Guide showed 4/9. |
| 21:30–21:34 | Command step: `greet`, then the 7-step editor; handler written and saved with Ctrl+S | Guide showed 5/9 *before* any code was written (issue 7). |
| 21:34–21:36 | Send step: **Stop previous build** → **Build cFS** (about 35 s) → **Start cFS** → GREET 42 | Event "HELLO: greet 42" arrived, but the step did not complete. |
| 21:38 | **New test**, then **Run test** | Passed 1/1. Guide showed 5/9, because Event had been unchecked by the restart. |
| 21:40 | Sensor, Test, Board | Sensor and Test are dead ends on Native. Opening Board switched the workspace target to `physical`. |
| 21:46 → | Wrote the crawler `audit/ux/explore.mjs` and ran it | It covered the three setup screens, then the session was interrupted. It now saves partial results after each screen. |

The root cause of the boot failure in this environment is probably this. cFS runs as **root** in a container that drops `CAP_SYS_RESOURCE`, and `/proc/sys/fs/mqueue/msg_max` is 10. OSAL permissive mode *is* enabled for cpu1, but it does not shorten queue depths for euid 0, so `CFE_SB_CreatePipe` fails with EINVAL. A normal (non-root) user would probably not hit this. The README does say "run as your normal user". **Still, the UI must handle any boot failure, and it handles none** (issue 1).

### Reusable tools I left behind
- `audit/ux/explore.mjs` is the crawler. For each screen (3 setup routes and 12 studio routes) it takes a screenshot, lists every visible button, link, tab, input, select or summary, then reloads and clicks each element. For each one it records the URL change, the guide pill change, any dialog opened, network calls, console errors and whether the screen visibly changed. **Every mutating `POST /api/*` is intercepted** and logged as "would POST", so Build, Stop and Delete can be pressed safely. Usage: `node explore.mjs --themes dark,light --max 45 [--screens event,app] [--viewport 1280x720]`. Results go to `crawl-results.json` and `crawl-table.md`.
- `audit/ux/lib.cjs`, `do.cjs` and `monitor-boot.cjs` are the CDP helpers I used for manual, human-style exploration.
- Logged errors (`logs/events.jsonl`): `404 /favicon.ico`, plus a `400 /api/mission/draft` when the app name is reserved (expected). There were no JavaScript page errors. The crawl recorded two side effects of plain navigation: opening **Sensor**/**Test** POSTs `/api/simulation/orbit`, and opening **Board** POSTs `/api/hardware/target {"target":"physical"}`.

Everything I started is stopped: no Studio server, Chrome, `core-cpu1` or crawler from `ux_work` is running.

---

## 2. The first-run journey, narrated as a newcomer

**Choose target** (`01-setup-initial-dark.png`, `01-setup-initial-light.png`). The page is clean: three drawings (Native, Emulator, Board) joined by dotted arrows, a "Jobs − 4 +" stepper, three round icons (Compiler, Python, Source), and **Install requirements** plus **Details**. The 9-step **First flight** bar sits on top. **Native is already highlighted** even though I never chose it; the README tells me to "choose Native". I don't know what "Jobs" means. All nine steps in the bar are links I can already click.

**Details before installing** (`02-setup-details-before-install-dark.png`, `02b…`, `02c…`). There are tabs Compiler / Python / Source with git, cmake, make, cc rows marked ○. Clicking **Check again** checks only the open tab. The page now says "Click + to fix" on Source, while Compiler and Python stay neutral (`02d…`, `02e…`).

**Click Native → checks** (`03-setup-native-clicked-checks.png`). Compiler turns green; Python and Source get an amber **+**. A small amber "Click + to fix" appears.

**Install requirements** (`04-setup-installing-3s.png`). After 3 s, small red text at the very bottom of the screen says **"Native tools · exit 1"**. Nothing on the icons tells me what failed. **Details** shows the Python row with a long, shell-quoted Python one-liner and `ModuleNotFoundError` (`04b…`, `04c…`). **Installer log** opens a terminal panel *over* the Details dialog and hides its buttons. The terminal says an apt lock is held by another process (`04d-setup-installer-log.png`).

**Click + on Source** (`05-setup-source-plus-clicked.png`). A ring animates around Source and the label reads "Installing NASA cFS". The old red "Native tools · exit 1" stays on screen. About 20 s later Source is green (`05d-setup-source-ready-main.png`).

**Peek at Emulator and Board** (`06-…`, `07-…`). On Emulator I get two dropdowns with one option each and a **Configure** sheet (SSH port, image `ghcr.io/raiagues/cfs_emulator:latest`). **Install requirements** fails with "Toolchain · exit 1"; Details shows a raw Docker socket error (`06d`–`06g`). On Board I get "Host: Not set", "SSH user: Not set" and **Configure**. Clicking the **+** on Network sensibly opens the settings sheet. After saving `raspberrypi.local`, **Install requirements** fails with **"Toolchain · exit 1"**, although Board has no Toolchain group. The real cause, "ssh: No such file or directory", is only inside Details (`07e`–`07g`).

**Jumping ahead out of curiosity: Event before setup** (`09-out-of-order-event-before-setup.png`). The studio opens with a **giant grey magnifying glass filling the screen**, the words "No commands" squeezed into a narrow column, and a tiny amber "Catalog details · 1". That link says "Build and run the flight software to prepare the catalog" (`09c…`). **Build cFS** in the header is highlighted, and so is coach step "1 Telemetry on".

**Back to Target → Install requirements again** (`10b…`, `10c…`). The installer log ends with "Native build tools and Ground Station packages ready." while the page says "Check Ground Station Python packages". I am stuck in a loop with no hint. With the README's venv advice and a server restart, all three groups go green and **Continue to boot** appears (`11d-setup-venv-after-install.png`, `11e-setup-ready-light.png`).

**First boot** (`12-boot-start-0s.png`). A good screen: six stage cards (Build cFS, Early init, Starting core, Core ready, Loading apps, Operational), a "CFS · LAYER BY LAYER" stack (Apps / cFE / OSAL / PSP / Linux / This computer), a side drawing and a console strip. The build reaches "Compiling 49%" at 30 s. After about 66 s **Starting core** starts spinning and **never stops** (`12-boot-progress-0060s/0120s/0180s.png`). The console strip shows `CFE_PSP: Exiting cFE with PROCESSOR Reset status.` and **Open console** shows why (`12b-boot-stuck-console-open.png`). There is no error state and no retry button; the timer keeps counting and the progress bar under "Starting core" keeps animating. Clicking a finished milestone replays that moment (`12c…`), and **Resume view** returns (`12e…`). Each layer row draws a small diagram (`12f-boot-layer-*.png`). **Replay boot** (↻) restarts the *recorded* log from 00:00 "Preparing build". It looks as if the build were starting again (`12g`, `12h`).

**After the environment fix, reload** (`14b…`). Reloading `#boot` silently starts a whole new build and boot, which reaches **cFS is running** (`13-boot-operational-dark.png`, `13b-…-light.png`, `13f-…-1280x720.png`). A small amber **Next** appears at the far right of the guide. sch_lab stays drawn as "not started" although the log says "SCH Lab Initialized". **Change** goes back to Target, and browser Back returns without a rebuild (`13d`, `13e`).

**Next → Event** (`15-event-initial-dark.png`). This is the owner's "Round trip" screen. A 3-card coach (Telemetry on / First command / Answer) sits over the ENABLE_OUTPUT form, with an empty `dest_IP` field and an amber **Connect**. Below is the round-trip diagram: a GROUND label, a dashed "cFS · Native" frame, boxes for ci_lab, sample_app, to_lab ("Output off" in red) and a dashed sch_lab, a Software Bus bar crossed by wires, and "UDP 1234/2234" labels overlapping the lines. Under that is an empty caption bar and an empty SENT strip. On the right are "No telemetry" and **Select ENABLE_OUTPUT**, and there is a second **Connect** at the bottom left. I count six highlighted or competing actions. Clicking **Connect** fills `dest_IP` with `127.0.0.1` for me (`15c…`). **Send** works: the coach ticks step 1 and **auto-selects NOOP**. The events panel fills with ten "L237 TO_LAB AddPkt 0x…" lines that I never caused (`15e…`). **Send** on NOOP works: the event "SAMPLE: NOOP command" arrives, CommandCounter shows +1, all three coach cards tick, the guide shows 3/9 and **Next** appears (`15g-event-noop-answer-dark.png`). At that moment the command list **jumps from 3 commands to the full catalog of 18 apps**.

**System overview** (`16-…telemetry-dark.png`, `16b-…commands-dark.png`, `16d…`, `30b-event-light-system-overview.png`). This is the owner's second screenshot: 13 app tiles and 6 cFE tiles, each with "N received" or "N sent". The Commands view says **"to_lab 11 sent"** although I sent one command. Clicking a tile opens a numbered list in 12-hour time. Before telemetry is on, every tile reads "0 received", which is the owner's screenshot.

**Exploring Event further** (`17…`). Expanding a SENT row shows **View observation**, which visibly does nothing (`17b`). **Packet inspector** works (`17c`). **Packet type ↗** opens the code editor, and the guide pill **jumps to "5 Command"** (`17d`).

**Next → App** (`18-app-initial-dark.png`). A 2D architecture opens. "Your apps 0" sits above ci_lab, to_lab, sch_lab and sample_app chips. **Create your first app** is amber, the header's **Build cFS** is amber, and the NASA apps row has active **Edit** and trash buttons. The 3D view is a pretty layered stack, but its labels are unreadable (`21-arch-3d-dark.png`). Selecting ci_lab shows **Open code / Commands / View in 2D** (`21b`). **Commands** jumps to the Ground station and the guide moves back to "Event" (`21c`).

**App wizard** (`19-app-wizard-step1-dark.png` … `19j…`). Clean step 1: a bus drawing with a dashed "Your app" slot, three facts and a Name field with placeholder `orbit_demo`. An empty name gives the browser bubble; "Bad Name!" gives "Please match the requested format."; `sample_app` gives "A module already uses this name". Step 2, **Its files**, lists 4 sections, **61 files** behind "25/10/1/25 more files", a raw `CFE_APP, hello_app, …` startup line and a CMake line, each file with a hollow circle that looks like a radio button. **Create hello_app** ticks all files and says **"hello_app on the bus"**, although nothing has been built or loaded. **Next → add a command** is offered.

**Next → Command** (`22-command-initial-dark.png`). A bare **New command** dialog: Mission app, and a Command name field with no example. After `greet`, the button greys out for about 4 s with no message (`22b`). Then the code editor opens with a 7-step trail (Code, Struct, Prototype, Dispatch, Events, Handler, Test) at **0/7**. Meanwhile the guide already shows **Command ✓, 5/9** and an amber **Next**. There are two amber "Next" buttons on screen (`22c`). I walked the trail with **Next step** (`23-cmd-editor-step1..7.png`). The payload field `Value uint32` was already made for me. **Events** asks me to "Edit event emission" without saying what to write. **Handler** is still `return CFE_STATUS_NOT_IMPLEMENTED;`, yet **Next step** lets me through to **Test**. The **CFE_EVS_SendEvent** example link is nice: it jumps to the NOOP handler in `hello_app_cmds.c`, which still says "SAMPLE: NOOP command" (`23b`). I wrote the handler (I needed to add `#include "hello_app_eventids.h"` myself) and saved with Ctrl+S, which showed "File saved" and 6/7 (`23d`, `23e`).

**Test → Open Ground Station → Send** (`24-send-open-ground-station.png`). An almost empty screen with one small card: "HELLO_APP_GREET_CC · Back to code · **Stop previous build**". Pressing it stops cFS and **removes the Event check** (5/9 → 4/9, `24b`). Next comes **Build cFS** (about 35 s, `24c`–`24e`), then **Start cFS**. The header says "Run cFS" for the same thing. Then the GREET form appears, still showing the old run's telemetry while "Disconnected" (`24g`). **Connect & send** with 42 quietly re-enables to_lab output too. The event **"HELLO: greet 42"** arrives, buried under ten AddPkt lines, but the SENT row just says **"Sent"** and the step does not complete (`24h`). Only by guessing **··· → New test** (`25…`): Test name, Timeout, a Command dropdown of about 400 commands, Step "Flight event", EVS app name, Event ID, Message contains. Then **Run test** shows **"Passed · 1/1"** and the guide shows Send ✓ (`25e`). Event is still unchecked until I send a NOOP again (`30c`).

**Next → Sensor** (`26-sensor-initial-dark.png`). An orbit globe and map with sliders for perigee, apogee, inclination, RAAN, argument of perigee, mean anomaly and propagator. The status says **"Synthetic data is off · 0 sensors enabled · Emulator required"** and **Start** is disabled. The dashed **Hardware** link opens a drawing of a laptop and nothing else (`26b`, `26c`). The Python, QEMU and Test tabs have only disabled buttons (`27-*`). **Test** (step 8) is the same screen (`28-test-step-dark.png`). There is nowhere to go.

**Board** (`29-board-step-dark.png`). Clicking step 9 takes me to the setup page with **Board selected and saved**. The guide drops from **5/9 to 2/9**. **Event** now opens a Board workspace with the giant magnifier (`29b`). Only the **Native** button in the header brings my progress back (`29c`).

---

## 3. Issues

Severity: **blocker** stops the first flight; **major** misleads or breaks the guided promise; **minor** is polish.

### A. Broken flows and redirects

**1. Boot never reports a failed start. It spins forever.** *Blocker*
- Screen/element: First boot → **Starting core** card, timer, console strip.
- Steps: make cFS exit during startup (here: root without CAP_SYS_RESOURCE and `msg_max=10`). Any crash, missing library or bad startup script would do the same.
- What happened: the log ends with `CFE_ES_ResetCFE: PROCESSOR RESET … CFE_PSP: Exiting cFE`, and `core-cpu1` is gone. The backend job stays "running" (it keeps `tail -F native.log`). The card spins, its progress bar keeps animating, the timer counts past 5 minutes, and the status says "Working · Native". There is no error, no retry and no hint.
- Owner's rules: no dead ends; realistic ops wording; one obvious next action.
- Shots: `12-boot-progress-0060s.png`, `…0120s`, `…0180s`, `12b-boot-stuck-console-open.png`.
- Fix: watch the process exit code and the log lines `Exiting cFE`, `Application Init Failed`, `CFE_ES_ResetCFE`. Turn the current card red with ✕, stop the timer and the bar, and show one line quoted from the log ("CFE_EVS could not create its message queue"). Offer one primary **Try again** and a secondary **Open console**. For the known mqueue case, add the exact fix with a copy button (`sudo sysctl fs.mqueue.msg_max=256`, or "start the Studio as your normal user"). Also add an mqueue check to the setup checks so this is caught before Boot.

**2. Opening step 9 "Board" switches the whole workspace to the physical board.** *Blocker*
- Screen/element: First flight bar → **Board** (`/?target=physical`).
- Steps: complete steps 1–6 on Native, then click **Board** just to look.
- What happened: `POST /api/hardware/target {"target":"physical"}` (or `/api/infrastructure`) is sent, and `hardware/.runtime/target.json` becomes `physical`. The counter drops **5/9 → 2/9**. Every step link is rewritten to `?target=physical`. Event then shows "cFS · Physical board", "No commands" and the giant magnifier. Only the header's **Native** button restores things.
- Owner's rules: steps can't jump to broken states; no wrong redirects.
- Shots: `29-board-step-dark.png`, `29b-event-after-board-visit.png`, `29c-event-switch-back-native.png`.
- Fix: viewing a step must never change state. Step 9 should open a Board page that changes nothing: what you need (Pi 4B, SD card with Raspberry Pi OS 64-bit, SSH on), a drawing, and one explicit **Use the Board** button that asks for confirmation. Keep the Native progress visible.

**3. The setup installer can loop: "ready" in the log, failure in the UI.** *Major (blocker on systems like this one)*
- Screen/element: Choose target → **Install requirements** / Python group.
- Steps: system Python differs from the Studio interpreter (pyenv, a self-built `/usr/local` Python, conda). Click Install requirements.
- What happened: `setup-native.sh` uses `find_spec('PyQt5')`, which finds apt's Python 3.12 package directory, and prints "PyQt5: available … Native build tools and Ground Station packages ready." The UI check imports `PyQt5.QtCore` with `/usr/local/bin/python3` (3.13) and fails. Feedback says only "Check Ground Station Python packages". Pressing again does the same thing.
- Owner's rules: no dead ends; text only when it truly helps, but here it is needed.
- Shots: `10b-setup-native-install-retry.png`, `10c-setup-python-loop-log.png`, `04c-setup-python-check-expanded.png`.
- Fix: the installer must run exactly the UI's import check. When system packages exist but do not import, show in the Python group: "PyQt5 is installed for another Python (3.12). Run the Studio from a virtual environment." Add one button, **Create environment**, which creates `.venv`, installs `ground_station/requirements.txt` and restarts the Studio, or else the three commands with a copy button.

**4. Progress goes backwards when cFS restarts.** *Major*
- Screen/element: First flight bar (Event pill and counter).
- Steps: finish Event; later press **Stop previous build** (Send step) or **Stop cFS**.
- What happened: Event loses its check (5/9 → 4/9). After restarting, the Event coach is not shown, the Studio re-enables to_lab output by itself, and the step stays unchecked until the user happens to send NOOP again. Send can then be ✓ while Event is not (`25e`).
- Owner's rules: autonomy grows step by step; consistent step state.
- Shots: `24b-send-after-stop.png`, `25e-send-test-result.png`, `30c-event-light-noop-after-restart.png`.
- Fix: a proven step stays proven (store the proof with its build and target). If a later build makes it worth re-checking, show it inside the current step ("Your new build still answers NOOP ✓") and never untick earlier pills.

**5. The guide pill follows whichever screen is open, not the person's progress.** *Major*
- Screen/element: First flight bar's current-step highlight.
- Steps: on Event, click **Packet type ↗** or the pencil (open source); in Architecture, click **Open code** or **Commands**; in Synthetic data, click the **Test** tab; click the **Hardware** rail icon.
- What happened: the current pill jumps to "5 Command" (code), "3 Event" (ground), "8 Test" (synthetic Test tab) or "7 Sensor" (hardware), although the person is on step 3 or 4.
- Owner's rules: Back/Next/step buttons consistent; no wrong redirects.
- Shots: `17d-event-packet-type-source.png`, `21c-arch-ci_lab-commands-dest.png`, `21d-arch-ci_lab-open-code-dest.png`, `27-synthetic-tab-test.png`.
- Fix: the current step is the progress step. When the person browses another view, keep that pill highlighted and show a small "Back to Event" chip in the bar. Rename the Synthetic "Test" tab (for example "Scenarios") so it is not confused with step 8.

**6. Every future step can be opened before its prerequisites, which leads to broken screens.** *Major*
- Screen/element: First flight bar links 2–9 on the first visit.
- Steps: on a fresh install, click **Event** (or App, Command…).
- What happened: Event shows a giant magnifier, "No commands" in a narrow column, a tiny amber "Catalog details · 1", and both the header **Build cFS** and coach step 1 highlighted.
- Owner's rules: exactly one obvious next action; steps can't jump to broken states.
- Shots: `09-out-of-order-event-before-setup.png`, `09c-event-catalog-details-open.png`.
- Fix: steps that are not reached yet are shown but not clickable (tooltip "Finish Boot first"). If someone arrives by URL, show one centered empty state: drawing, "cFS is not running yet", and **Go to Boot**.

**7. The Command step is ticked before any code is written.** *Major*
- Screen/element: First flight → Command pill and **Next**; editor trail `0/7`.
- Steps: New command → `greet` → Create command.
- What happened: the guide immediately shows Command ✓ and 5/9 with an amber **Next** (to Send). The in-editor activity shows 0/7 with its own amber **Next step**. Two competing "Next" buttons.
- Owner's rules: one obvious next action; the person does the work themselves.
- Shot: `22c-command-after-create-wait.png`.
- Fix: complete Command only when the handler is implemented and the build succeeds (end of the 7 steps). Hide the guide's Next while an activity is open, so the activity's button is the only next action.

**8. The 7-step command editor never blocks, and its steps don't say what to do.** *Major*
- Screen/element: Code → "New command" trail, right panel **Next step**.
- Steps: press **Next step** seven times without editing.
- What happened: all steps can be skipped. **Handler** still returns `CFE_STATUS_NOT_IMPLEMENTED` and you pass anyway. **Events** stays at "5" (Pending) with no reason. "Edit event emission" only puts the cursor in the file. The handler file does not include `hello_app_eventids.h`, so a newcomer copying the NOOP example gets a compile error.
- Owner's rules: guided, step by step; the person does it, with help.
- Shots: `23-cmd-editor-step5.png`, `23-cmd-editor-step6.png`, `23-cmd-editor-step7.png`, `23b-cmd-events-example-clicked.png`, `23d-cmd-handler-edited-unsaved.png`.
- Fix: each step gets one sentence of task ("Send an event that shows the Value you received") and an **Insert example** button. The example is a 2-line `CFE_EVS_SendEvent(HELLO_APP_VALUE_INF_EID, …, Msg->Payload.Value)` with the include added to the user file. Tick the step automatically when the code is present, and keep Next disabled until then, with a small "Skip" link if needed. Mark the Handler step done only when `NOT_IMPLEMENTED` is gone and the build passes.

**9. A successful send of your own command isn't recognised; you have to discover "New test".** *Major*
- Screen/element: Send step → SENT row "HELLO_APP_GREET_CC · Sent"; Tests "···" menu.
- Steps: rebuild, start, send GREET 42.
- What happened: the flight answered ("HELLO: greet 42" event, hello_app CommandCounter 1), but the row only says **Sent** and the diagram shows only the uplink. The guide does not advance and nothing says a test is required. The test editor is a dense form (a Command dropdown of about 400 items, Event ID, "Message contains").
- Owner's rules: guided; visual; one next action.
- Shots: `24h-send-greet-sent.png`, `25-send-new-test-editor.png`, `25e-send-test-result.png`.
- Fix: match the reply automatically, as for NOOP: the next event from the commanded app and the rise of its CommandCounter. Show "hello_app answered: HELLO: greet 42 · CommandCounter 0 → 1" on the row and animate the downlink. Complete Send on that. Then offer **Save as test** with the observation pre-selected.

**10. Sensor and Test (steps 7–8) are dead ends on Native.** *Major*
- Screen/element: Synthetic data → **Start** (disabled), **Hardware** link, Python **Dry run** / **Send to QEMU** (disabled), Test **Run** (disabled).
- Steps: Next from Send.
- What happened: "Synthetic data is off · 0 sensors enabled · Emulator required". Hardware shows only a laptop drawing with zoom buttons. Nothing explains how to continue. The guide offers no way forward and no way to skip.
- Owner's rules: no dead ends.
- Shots: `26-sensor-initial-dark.png`, `26b-sensor-hardware-link.png`, `26c-hardware-native-2d.png`, `27-synthetic-tab-python.png`, `27-synthetic-tab-qemu.png`, `28-test-step-dark.png`.
- Fix: on Native, mark steps 7–8 with a small "Emulator" badge. When opened, show one card: "Sensors need the emulated Raspberry Pi (QEMU)", what it installs, and one button **Set up Emulator** that opens Target with Emulator focused. Alternatively, give Native a simulated sensor (UDP- or file-backed HAL) so the flow continues on this computer.

**11. Reloading Boot rebuilds and restarts by itself; "Replay boot" looks like a rebuild.** *Major*
- Screen/element: First boot page reload; **Replay boot** (↻) top right.
- Steps: with cFS not running, press F5 on `#boot`. Separately, click ↻.
- What happened: the reload started a real build and run (`POST /api/job first-boot`). ↻ resets the timer to 00:00 and replays "Preparing build → Compiling 8%…" from the recorded log, which looks like a rebuild, even replaying a failed boot.
- Owner's rules: no wrong redirects; realistic wording.
- Shots: `14b-boot-after-server-restart-reload.png`, `12g-boot-replay-clicked.png`, `12h-boot-replay-8s.png`.
- Fix: a reload restores the last state. Starting a build is always an explicit **Build and start** button. Rename ↻ to "Replay log", give it a different icon from the guide's "Start over", and show a "Replay" badge while replaying.

**12. The Studio sends commands on the person's behalf, and they show up in counters and logs.** *Major*
- Screen/element: Event → after ENABLE_OUTPUT; Send → **Connect & send**.
- What happened: 10 `TO_LAB_ADD_PKT_CC` commands are sent automatically (hidden from SENT). System overview reports "to_lab 11 sent", and the events panel fills with "L237 TO_LAB AddPkt 0x8ba, QoS 0.0, limit 1". After a restart, **Connect & send** silently re-sends ENABLE_OUTPUT too.
- Owner's rules: the person does the first commands; nothing pre-done; realistic, honest display.
- Shots: `15e-event-enable-sent-6s.png`, `16b-event-system-overview-commands-dark.png`, `24h-send-greet-sent.png`.
- Fix: subscribe through the to_lab subscription table (as real missions do), or show one grouped, explained row: "Studio subscribed to_lab to 10 packets (ADD_PKT)". Never count these as the user's commands, and collapse their events. After a restart, make "Turn telemetry on again" a visible coach step.

### B. Dead buttons / no visible effect

**13. "View observation" in a SENT row does nothing visible.** *Minor*. Event → SENT row → expand → **View observation**. The screen text and diagram are identical before and after (`17b-event-view-observation.png`). Fix: open that send's observation (event text and packet fields) in the right panel, and highlight the matching hop in the diagram.

**14. "Select ENABLE_OUTPUT" when ENABLE_OUTPUT is already selected.** *Minor*. Telemetry panel empty state (`15-event-initial-dark.png`, `15c-event-connected-dark.png`). It is redundant and competes with the form button. Fix: remove it. The empty state says "Waiting for to_lab output" with a subtle arrow to the form.

**15. Disabled controls never say why.** *Minor*. **Run cFS** while running; Synthetic **Start**, **Dry run**, **Send to QEMU**, **Save settings**, Test **Run**; Libraries **Edit**/**Remove**; cFS apps **New** (`27-*`, `18-app-initial-dark.png`). Fix: a tooltip or inline reason, plus the one action that enables the control ("Needs Emulator · Set up").

**16. Some cards look clickable but are not.** *Minor*. Coach card "3 Answer" is a span while 1–2 are buttons (`15g`). After clicking an earlier boot milestone, later finished milestones become "Waiting" and can't be clicked until **Resume view** (`12c-boot-milestone-build-clicked.png`). Fix: same affordance for all cards; past milestones stay clickable during replay.

**17. "Check again" in Setup details checks only the open tab.** *Minor* (`02d-setup-details-check-again.png`, `02e…`). Compiler and Python stay "pending" while the summary says "Click + to fix". Fix: re-check all groups, or label it "Check Source".

**18. "Start over" (↻ in the guide) only hides the ticks.** *Minor*. It sets a localStorage cutoff, stays on the same screen, and resets nothing in the project. It uses the same icon as "Replay boot". Fix: rename it "Reset progress" with a confirm dialog that returns to step 1, or remove it.

### C. Errors and error messages

**19. Install failures are reported as "‹group› · exit 1" in small red text at the bottom edge, and the text goes stale.** *Major*
- Shots: `04-setup-installing-3s.png` (apt lock), `05-setup-source-plus-clicked.png` (the old error still shown during a new install), `06d-setup-emulator-install-attempt.png`, `07f-setup-board-install-attempt.png`.
- Fix: put the error on the failing group icon (red ring) with a one-line cause from the log: "Another install is using apt. Wait for it to finish, then retry". Add a **Retry** button next to it. Clear it when a new run starts.

**20. Board target: "Toolchain · exit 1" names a group that isn't on screen.** *Major*. Board shows Network, SSH key and Service. The real causes are `ssh` not installed (`[Errno 2] No such file or directory: 'ssh'` in the Network check) and `setup.sh` refusing root ("Run ./scripts/setup.sh as your normal user") (`07e-setup-board-details.png`, `07g-setup-board-installer-log.png`). Fix: map failures to the visible group, e.g. "Network: OpenSSH client missing → Install", and show "The Studio is running as root" as one clear banner.

**21. Emulator: raw Docker error, no next step.** *Minor*. "failed to connect to the docker API at unix:///var/run/docker.sock …" (`06e-setup-emulator-details-after-fail.png`). Fix: "Docker is installed but not running. Start Docker Desktop, or run `sudo systemctl start docker`, then Check again."

**22. The installer log mixes sessions.** *Minor*. The Emulator "Toolchain" job shows the earlier Native apt output first (`06f-setup-emulator-installer-log.png`). Fix: one log per job, titled with the target and time.

**23. Validation relies on browser bubbles.** *Minor*. Wizard: "Please match the requested format." (`19c-app-wizard-bad-name.png`). New command: no placeholder or rule (pattern `[a-z][a-z0-9_]*`) (`22-command-initial-dark.png`). Jobs accepts 0 and 999, showing only "Unsaved" (`03c-setup-jobs-zero.png`). Emulator SSH port 99999 shows only the bubble (`06c…`). Fix: one inline hint under each field ("lowercase letters, digits and _ · e.g. `set_mode`"; "Jobs 1–64").

**24. Missing favicon.** *Minor*. `GET /favicon.ico` 404 produces a console error on first load. Fix: ship a small favicon.

### D. Guidance gaps

**25. Native is pre-selected before the person chooses.** *Major*. `aria-pressed=true` on the first visit (`01-setup-initial-dark.png`). The README says "choose Native". Fix: nothing selected; the three cards are the only action. After a choice, the checks run and **Install requirements** appears.

**26. Too many highlighted actions on one screen.** *Major*
- Event first visit: coach step 1, the selected ENABLE_OUTPUT row, the form's amber **Connect**, a second **Connect** bottom-left, **Select ENABLE_OUTPUT**, the header's amber **Build cFS**, a red **Stop cFS**, and the amber "Round trip" toggle (`15-event-initial-dark.png`).
- App: **Create your first app**, the header's amber **Build cFS** or **Rebuild cFS**, and the guide's **Next** (`18`, `20`).
- Owner's rules: exactly one obvious next action.
- Fix: one accent color per screen, used only for the next action. Header Build/Run/Stop are neutral unless they are the next action. Remove duplicate Connect buttons. "Round trip"/"System overview" become a quiet segmented control.

**27. The command catalog jumps from 3 to about 400 commands right after the first success.** *Major* (`15g-event-noop-answer-dark.png`; the test editor's Command dropdown in `25-send-new-test-editor.png`). Fix: keep showing to_lab, sample_app and the person's own apps. Add a quiet "Show all NASA apps (18)" toggle. Filter the test editor's Command dropdown to the selected command's app.

**28. Things are pre-filled that the person should do or choose.** *Major*. `dest_IP` is auto-filled with 127.0.0.1 on Connect (`15c`). NOOP is auto-selected after step 1 (`15e`). The payload `Value uint32` is pre-generated (`23-cmd-editor-step2.png`). The Studio re-enables telemetry by itself (issue 12). Fix: offer a suggestion chip ("Use this computer · 127.0.0.1") that the person clicks, with a one-line "to_lab needs to know where Ground is". Highlight NOOP in the list instead of selecting it. Ask for the payload field name and type in the New command dialog (default suggestion `Value · uint32`).

**29. "Send" after a code change takes three separate clicks with odd wording.** *Major*. The card shows "Stop previous build" → "Build cFS" → "Start cFS", while the header shows "Rebuild cFS"/"Build cFS" and "Run cFS" for the same things (`24-send-open-ground-station.png`, `24b`, `24e`). Fix: one primary button, **Rebuild and restart cFS**, showing the same 6-card progress as First boot. Then open the GREET form with Value focused.

**30. Old telemetry is shown as if live after a restart.** *Minor*. "Disconnected", yet ci_lab IngestPackets 12, "TO_LAB · UDP 2234" and the old event list are still there (`24g-send-form-ready.png`). Fix: clear or dim previous-run data with a "Previous run" label.

**31. The Boot screen overwhelms with 13 apps and shows sch_lab as "not started".** *Minor*. Apps row: sch_lab ci_lab to_lab sample_app lc cf ds fm hk hs sc md cs. sch_lab stays dashed although the log has "SCH Lab Initialized" (it emits no EVS event) (`13-boot-operational-dark.png`). Fix: on the first flight show the 4 lab and sample apps, with the rest as "+9 NASA apps". Detect sch_lab from the ES "Loading file" line or the startup completion.

**32. App wizard step 2 is a wall of files.** *Minor*. 61 files, a raw startup line `CFE_APP, hello_app, HELLO_APP_Main, HELLO_APP, 55, 32768, 0x0, 0;` and a CMake line; 15 rows labelled "Task interface"; hollow radio-like circles; `eds_*` files although EDS is off (`19f`, `19h`). Fix: show the 4 files the person will touch (main loop, command handler, message IDs, startup entry), each with a 3-word purpose. Put the rest behind "All 61 files".

**33. NASA apps can be edited or removed from the beginner's architecture view.** *Major*. cFS apps row: **Edit** and trash are active (`18-app-initial-dark.png`, `20-app-after-wizard-closed.png`). The README says NASA names belong to the checkout. Fix: lock NASA modules (the lock icon exists only on ci_lab, sch_lab and to_lab today). Hide Edit and Remove for them during the first flight.

**34. The Sensor screen opens with orbital-mechanics controls.** *Minor*. Perigee, apogee, inclination, RAAN, argument of perigee, mean anomaly, Elements/TLE, Two-body/J2 (`26-sensor-initial-dark.png`). Fix: show one line, "Orbit: Sun-synchronous, 550 km · Change", and put the sliders behind it.

**35. Nothing tells the person how to reproduce this outside the Studio.** *Major*. The Emulator uses `ghcr.io/raiagues/cfs_emulator:latest` (`06b-setup-emulator-configure-sheet.png`), not a stock QEMU Raspberry Pi image. No screen shows the real commands. Fix: on Emulator and Board (and at the end of the first flight), show a "Do it on your computer" card with copyable commands: `git clone --recursive https://github.com/nasa/cFS`, `make SIMULATION=native prep && make install`, the `qemu-system-aarch64 -M raspi4b …` line with the official Raspberry Pi OS image, and `ssh pi@…`. Also show the Studio's equivalent `./start --no-ui …` commands.

### E. Visual pollution and inconsistency

**36. The "Round trip" diagram (owner's screenshot 1) is polluted.** *Major*
- Shots: `15-event-initial-dark.png`, `15c-event-connected-dark.png`, `15e-event-enable-sent-6s.png`, `15g-event-noop-answer-dark.png`, `30-event-light-roundtrip.png`.
- Why it confuses a newcomer:
  1. **Four nested frames**: card, canvas, dashed "cFS · Native" box, node boxes. Plus a separate empty caption bar and an empty SENT strip with a dashed placeholder line. Lots of chrome around little meaning.
  2. **Every wire is always drawn**, whether or not traffic flows. Wires cross the Software Bus bar and each other, and a vertical wire cuts the "Software B|us" label.
  3. **"UDP 1234" / "UDP 2234" are drawn over the wires** next to the Ground box. Port numbers are noise for step 1.
  4. **Irrelevant nodes**: a dashed sch_lab (and later a dashed sample_app) that play no part in the step.
  5. **Alarm styling for a normal state**: to_lab "Output off" in red/orange on first visit, before the person has done anything wrong.
  6. **The same fact is said five times**: coach card, diagram caption ("to_lab output off"), SENT row ("Telemetry · MID 0x0808"), telemetry panel, events log.
  7. A legend ("— Command — Telemetry") and a "···" menu add more small text.
- Clean, guided version: one horizontal strip that shows only the hop of the current coach step.
  - Step 1: `Ground ─▶ ci_lab ─▶ to_lab`. The packet dot animates once on Send. to_lab turns from grey to green "sending to 127.0.0.1", and a return arrow `to_lab ─▶ Ground` lights with the first packet.
  - Step 2: `Ground ─▶ ci_lab ─▶ (Software Bus) ─▶ sample_app`. On reply, `sample_app ─▶ to_lab ─▶ Ground` animates and one line appears under the strip: "sample_app replied: NOOP command · CommandCounter 0 → 1".
  - No outer dashed frame, no ports (shown on hover), no idle apps, no caption bar, no legend. The coach cards become the strip's step labels.

**37. "System overview" (owner's screenshot 2) is a wall of identical counters.** *Major*
- Shots: `16-event-system-overview-telemetry-dark.png`, `16b-event-system-overview-commands-dark.png`, `16d-event-system-overview-telemetry-sample_app.png`, `30b-event-light-system-overview.png`.
- Why it confuses: 19 equal tiles (cf, ci_lab, cs, ds, fm, hk, hs, lc, md, sample_app, sc, sch_lab, to_lab; SB, ES, EVS, FS, TBL, TIME). Before telemetry is on, **every tile says "0 received"**; afterwards they are **session totals** that a beginner can't interpret. sch_lab and FS are **always 0**. "to_lab 11 sent" includes the hidden automatic commands. Tile text wraps badly ("ES / Executive / Services · 13 / received"). The detail list uses a default numbered list in **12-hour time** ("9:27:10 PM") while everything else is 24-hour. It sits as an equal tab next to the guided view.
- Clean version: keep it out of the first flight. Later, as a "Bus traffic" view: a list ranked by packets per second (last 30 s) with a tiny sparkline, only for apps with traffic; zero-traffic apps collapsed into "11 quiet apps"; cFE services in a separate muted row; clicking an app opens its packets in the existing Packet inspector.

**38. A giant magnifying-glass icon fills the Event screen, and it makes controls unreachable.** *Major*
- What happened: `.gs-empty-list` in the center column renders an unsized SVG (746×746 px) whenever there is no catalog. It pushes **Round trip** and **System overview** to y≈1085 inside an `overflow:hidden` column, so they can't be reached.
- Shots: `09-out-of-order-event-before-setup.png`, `29b-event-after-board-visit.png`.
- Fix: size the icon (e.g. `.gs-empty-list svg{width:16px;height:16px}`), and replace it with the single empty state from issue 6.

**39. The events log is flooded by housekeeping noise; the person's own reply scrolls away.** *Major*. Ten "L237 TO_LAB AddPkt … QoS 0.0, limit 1" lines, then "CFE_TIME Start FLYWHEEL / Stop FLYWHEEL" every few seconds. "HELLO: greet 42" sits below them (`15e`, `15g`, `24h-send-greet-sent.png`). Fix: by default show events from the app being commanded and errors only; collapse repeats ("FLYWHEEL ×6"); pin and highlight the reply to the last send. "All events" is one click away.

**40. Overlays stack or float badly.** *Minor*. The Installer log terminal covers the Details dialog's buttons (`04d-setup-installer-log.png`). The Tests "···" popover floats over the diagram frame and stays open (`25e-send-test-result.png`). The Details dialog re-centers and jumps vertically when its content changes (`02` → `02d`). Fix: one overlay at a time (the terminal replaces the dialog content, or docks); popovers close on outside click and anchor below their button; fixed dialog top.

**41. Opening the terminal squeezes the round-trip drawing to unreadable size.** *Minor* (`31-terminal-open-event.png`). Fix: when the terminal is open, collapse the diagram to the one-line strip, or give the terminal an overlay mode.

**42. Editor tabs pile up and overflow.** *Minor*. Eight tabs from earlier detours (sample_app header, ci_lab_app.c…) are truncated to "defa…", "ci_la…", and the fifth is cut under the @Tags toolbar (`22c`, `23-cmd-editor-step2.png`). Fix: the command activity opens its own tab set (closing detour tabs); the tab strip scrolls with an overflow menu and never sits under the toolbar.

**43. Synthetic Python buttons wrap and a checkbox has no label.** *Minor*. "Dry / run", "Send / to / QEMU" on two or three lines next to an unlabeled checkbox (`27-synthetic-tab-python.png`). Fix: one-line buttons (icon plus short label); label the checkbox (or remove it).

**44. 3D and 2D drawings: unreadable labels, one mislabel, one toy-like drawing.** *Minor*. In the 3D architecture, app names on the top layer are tiny and rotated; three labels (CFS APPS, LIBRARIES, YOUR APPS) point at the same layer; the hardware board layer is printed "Linux" (`21-arch-3d-dark.png`). The 2D Native hardware drawing is a cartoon laptop with a toy keyboard (`26c-hardware-native-2d.png`), against the "nothing childish" rule. Fix: name labels outside the stack (as already done for layers) with hover highlight; label the board "This computer · x86_64"; use the same flat line-art style as the setup illustrations.

**45. Boot side panel: a tiny diagram in a big empty panel.** *Minor*. The Apps diagram (Ground → ci_lab/to_lab → Software Bus → sch_lab/sample_app/+ App) is about 400×100 px inside a 470×520 panel, and the "Ground" label overlaps its arrow (`12f-boot-layer-apps.png`, `13-boot-operational-dark.png`). Fix: scale the drawing to the panel and fix the label offset.

**46. Small inconsistencies.** *Minor*
- Dropdowns with a single option (Board "Raspberry Pi 4B", OS "Raspberry Pi OS") on Emulator setup and in the header (`06`, `29b`).
- Native `<select>` styling in the test editor ("Flight event") next to custom controls (`25`).
- Brand "Flight studio" in the header but "Flight Studio" in titles; "Ground station" in the rail but "Ground Station" in the activity.
- Hex `0xA00` next to `0x1A00` (`19j`).
- 12-hour and 24-hour times mixed (`16d`).
- In the light theme, the disabled **Run cFS** looks enabled (`30b`).
- Fix: one select component; consistent naming; `0x0A00`; 24-hour everywhere; disabled at 40% opacity in both themes.

### F. Wording

**47. Labels that are wrong or overstate.** *Major*
- "Stop previous build" stops the running cFS, not a build.
- "hello_app on the bus" is shown before the app was built or loaded.
- "Catalog details · 1" really means "cFS is not running".
- "Toolchain · exit 1" appears on Board.
- The generated `hello_app` NOOP still prints "SAMPLE: NOOP command" (`23b`).
- Fix: "Stop cFS"; "hello_app is ready to build"; "cFS isn't running · Go to Boot"; plain causes; rename template strings with the app's prefix ("HELLO_APP: NOOP command").

**48. One action, several names.** *Minor*. "Build cFS" / "Rebuild cFS" / "Building cFS"; "Run cFS" (header) / "Start cFS" (card) / "Start" (synthetic); "Connect" / "Connect & send" / "Run test" on the same send button. Fix: "Build", "Start cFS", "Stop cFS", "Send"; when a test is selected, show "Send · runs test".

**49. Unexplained protocol jargon on the beginner path.** *Minor*. "INFO + CommandCounter ↑", "Telemetry · MID 0x0808", "EVS #8", "FC 6", "Indexed", "Pending", "char [16]", "uint8", "Jobs", "Click + to fix", "Emulator required". The real cFS names (ci_lab, to_lab, EVS, CommandCounter) are good and should stay, but say what they mean once. Fix: plain first, real name second ("sample_app replied (EVS event) · CommandCounter 0 → 1"). Show MID/FC on hover or in the Packet view. Rename "Jobs" to "Build jobs".

### G. Scrolling and overflow

**50. No page scrolling at 1440×900 or 1280×720 on any screen measured** (setup, boot, event, app, code, sensor; `13f-boot-operational-1280x720.png`). This meets the rule. Internal overflow problems remain:
- The Event center column is `overflow:hidden`, so content pushed down is unreachable (issue 38).
- The Sensor right panel needs an inner scroll to reach "Sensor sampling" and **Save settings** (y≈929) (`26`).
- After the first event, the command list scrolls internally and the selected command sits at the very bottom (`15g`).
- Opening the terminal crushes the Event layout (issue 41).
- Fix: scroll the selected command into view; keep primary buttons (Save settings) pinned in panel footers; give the Event column `overflow:auto` as a safety net.

### H. Accessibility basics

**51. Mostly good basics.** Focus outlines (2 px) are visible on every tabbable control (`32-setup-keyboard-focus.png`), icon buttons have accessible names ("Switch to light theme", "Start over", "Replay boot", "Pause view", "Open command source"), the 3D canvas has an aria-label with keyboard hints, and Escape closes dialogs and the console. The remaining gaps follow. *Minor*
- On the setup page, keyboard focus reaches the header and guide only *after* the main content and footer.
- An unlabeled checkbox on the Synthetic Python tab.
- State shown by color alone in places: tiles with or without traffic, diagram node states, the red "Output off".
- Much of the meaningful text is 10–11 px mono in the muted color (UDP labels, node sub-labels, "Telemetry · MID…"), which risks failing contrast on dark.
- The disabled state is weak in the light theme.
- Fix: put the header first in DOM order; label all inputs; add an icon or word to every color state; 12 px minimum for information-bearing text, with contrast ≥ 4.5:1 for muted text.

---

## 4. Every clickable element found

Status: **OK** works as expected · **BROKEN** wrong destination or state · **CONFUSING** works but misleads or competes · **DEAD** no visible effect · **DISABLED** · **NOT EXERCISED** seen but not clicked (destructive or not reached; the crawler would answer it with a blocked POST).

### Setup: Choose target (`/`, `/?target=…`)
| Element (exact label) | Expected | Actual | Status |
|---|---|---|---|
| "Flight studio / ux_work" (brand) | — | Plain text on setup | OK |
| "Switch to light theme" / "Switch to dark theme" | Toggle theme | Toggles; saved to localStorage `fs-theme`; carried into the studio | OK |
| Guide "1 Target" | Stay on setup | Stays | OK |
| Guide "2 Boot" … "8 Test" (before setup) | Locked or explained | Open studio routes; Event shows giant magnifier and "No commands" | BROKEN (#6) |
| Guide "9 Board" | Preview the board step | Selects Board, saves target=physical, progress 5/9 → 2/9 | BROKEN (#2) |
| Guide "Start over" ↻ | Restart the guide | Hides ticks only (localStorage cutoff) | CONFUSING (#18) |
| Card "Native · This computer" | Select Native, run checks | Selects and runs Compiler/Python/Source checks; pre-selected on first visit | OK / CONFUSING (#25) |
| Card "Emulator · QEMU" | Select, run checks | Shows Board/OS selects, Configure, Docker/Image/Toolchain | OK |
| Card "Board · SSH" | Select, run checks | Shows Host/SSH user chips, Configure, Network/SSH key/Service | OK |
| "Fewer build jobs" − / "Parallel build jobs" / "More build jobs" + | Change jobs | Works; 0 or 999 accepted with only "Unsaved" | OK / minor (#23) |
| "Inspect Compiler" (green) | Open details | Opens Setup details on Compiler | OK |
| "Install Python" (+) | Install Python group | Ran apt; failed (apt lock), later the loop (#3) | BROKEN here |
| "Install Source" (+) | Clone cFS | Shallow clone about 20 s, then green | OK |
| "Install requirements" | Install all missing | Native: failed / looped (#3, #19); Emulator and Board: "Toolchain · exit 1" (#20) | BROKEN here |
| "Continue to boot" | Go to First boot | `/studio?target=native#boot` and starts the build | OK |
| "Details" | Show checks or terminal | Opens Setup details (failing tab) or the running install terminal | OK |
| Details: tabs "Compiler" / "Python" / "Source" (or Docker/Image/Toolchain, Network/SSH key/Service) | Switch group | Switch | OK |
| Details: check rows (e.g. "git", "Ground Station Python packages", "Docker engine ≥ 23", "Board network") | Expand | Expand with command, output, exit code | OK (raw output) |
| Details: "Check again" | Re-check | Re-checks only the open tab | CONFUSING (#17) |
| Details: "Install" (fix-group) | Fix that group | Starts that group's install | OK |
| Details: "Target settings" (Board) | Open settings | Opens Board settings | OK |
| Details: "Installer log" | Show log | Opens the terminal over the dialog, hiding its buttons | CONFUSING (#40) |
| Details: "Close details" × / Escape | Close | Close | OK |
| Installer terminal: "Close terminal" × | Close | Close | OK |
| Emulator: "Board" select | Choose board | Single option "Raspberry Pi 4B" | CONFUSING (#46) |
| Emulator: "Operating system" select | Choose OS | Single option "Raspberry Pi OS" | CONFUSING (#46) |
| Emulator: "Configure" | Open settings | "Emulator settings" sheet | OK |
| Emulator settings: "Local SSH port" | Edit | 99999 blocked by browser bubble only | OK / minor |
| Emulator settings: "Emulator image" | Edit | Custom image `ghcr.io/raiagues/cfs_emulator:latest` | CONFUSING (#35) |
| Emulator settings: "Cancel" / "Close settings" × / "Save settings" | Close / save | Close; Save validates | OK |
| Emulator: "Install Docker" / "Install Image" / "Install Toolchain" (+) | Install group | Not clicked one by one; "Install requirements" failed (no Docker daemon; setup.sh refuses root) | NOT EXERCISED (group) |
| Board: "Edit Host: Not set" | Open settings at Host | Sheet opens, focus on Host | OK |
| Board: "Edit SSH user: Not set" | Open settings at user | Same sheet | OK |
| Board: "Configure" | Open settings | Board settings sheet | OK |
| Board: "Configure Network" (+) | Fix network | Opens settings (host required) | OK |
| Board: "Install SSH key" / "Install Service" (+) | Fix group | Covered by Install requirements → "Toolchain · exit 1" | NOT EXERCISED (group) |
| Board settings: "Board", "Operating system", "Host or SSH alias", "SSH user", "SSH port", "SSH private key", "Cancel", "Save settings", × | Edit / save | Save stores and re-checks | OK |

### First boot (`/studio#boot`)
| Element | Expected | Actual | Status |
|---|---|---|---|
| "Change" | Back to Target | `/?target=native#target`; Back returns without a rebuild | OK |
| "Pause view" / "Resume view" | Pause or resume the replay | Works; Pause disabled after OPERATIONAL | OK |
| "Replay boot" ↻ | Replay the log | Replays from 00:00, looks like a rebuild | CONFUSING (#11) |
| Milestone "Build cFS, Ready" … "Operational, Complete" | Show that moment | Jumps there; later cards become "Waiting" until Resume | OK / minor (#16) |
| Layer rows "Apps", "cFE", "OSAL", "PSP", "Linux", "This computer" | Show layer drawing | Side panel changes | OK |
| Side drawing "+ App" | Maybe start the app wizard | Not clicked | NOT EXERCISED |
| "Open console" / "Close console" / Escape | Toggle console | Works | OK |
| (On failure) any error or retry control | Retry | None exist; spinner forever | BROKEN (#1) |
| Page reload (F5) | Restore state | Starts a real build and run | BROKEN (#11) |
| Guide "Next" | Go to Event | `#event`, only after OPERATIONAL | OK |

### Studio header and rail (all workspace screens)
| Element | Expected | Actual | Status |
|---|---|---|---|
| "Workspace setup" (brand link) | Setup | `/infrastructure` (setup page) | OK |
| Target switch "Native" / "Emulator" / "Board" | Change target | Switches and saves the target; progress shown per target | OK (but see #2) |
| Board target: "Raspberry Pi 4B" / "Raspberry Pi OS" selects, "Check connection" | Board profile | Seen with single options; Check connection not clicked | NOT EXERCISED |
| "Build cFS" / "Rebuild cFS" | Build | Builds; always amber, competes with the step action | CONFUSING (#26, #48) |
| "Run cFS" | Start | Disabled while running (looks enabled in light theme) | DISABLED / minor |
| "Stop cFS" (red) | Stop | Stops cFS and removes the Event tick | CONFUSING (#4) |
| "Start emulator" / "Stop emulator" / "Synthetic data" switch | Emulator only | Hidden on Native | N/A |
| Theme toggle | Toggle | Works | OK |
| Rail "Architecture" | Architecture | Opens; guide pill → App | CONFUSING (#5) |
| Rail "Hardware" | Hardware | Opens (`#bench`); guide pill → Sensor | CONFUSING (#5) |
| Rail "Code" | Code | Opens; guide pill → Command | CONFUSING (#5) |
| Rail "Ground station" | Ground | Opens; guide pill → Event | CONFUSING (#5) |
| Rail "Synthetic data" | Synthetic data | Opens; guide pill → Sensor | CONFUSING (#5) |
| Rail "Terminal" | Toggle terminal | Opens a bottom panel with job list (Run cFS, Build cFS, Stop cFS, first-boot); squeezes layout | OK / minor (#41) |
| Terminal: "+", "−", job ×, job rows | Shell / minimize / close / select | Seen, not clicked | NOT EXERCISED |
| Guide pills (after setup) | Go to step | Go to step (Board breaks, see #2) | OK / BROKEN |
| Guide "Next" | Next step | Correct target; shown too early on Command (#7) | OK / CONFUSING |

### Event / Ground station (`#event`, `#ground`, `#send`)
| Element | Expected | Actual | Status |
|---|---|---|---|
| Coach "1 Telemetry on · to_lab · ENABLE_OUTPUT" | Select command | Selects ENABLE_OUTPUT | OK |
| Coach "2 First command · sample_app · NOOP" | Select command | Selects NOOP | OK |
| Coach "3 Answer · INFO + CommandCounter ↑" | — | Not clickable (span) | minor (#16) |
| "Catalog details · 1" (no cFS) | Explain | "Build and run the flight software to prepare the catalog." | CONFUSING (#6, #47) |
| Big magnifier empty state (no cFS) | Small icon | 746 px SVG hides Round trip and System overview | BROKEN (#38) |
| "From build" | Refresh catalog | Reloads catalog in place | OK |
| Group summaries "to_lab", "sample_app", "hello_app", "cf"… | Expand | Expand | OK |
| Command rows ("ENABLE_OUTPUT FC 6", "NOOP FC 0", "GREET FC 4"…) | Select | Select | OK |
| "All apps" | Show full catalog | Shows about 400 commands; also forced on after the first event | CONFUSING (#27) |
| "Search commands" / "Application" select | Filter | Filter (appear only after the first event) | OK |
| "New command in code" | New command dialog in Code | Not clicked | NOT EXERCISED |
| "Connect" (bottom-left) and "Connect" (form) | Connect ground | Connects; auto-fills `dest_IP` 127.0.0.1 | OK / CONFUSING (#28, duplicate) |
| "Disconnect" | Disconnect | Not clicked | NOT EXERCISED |
| `dest_IP` / "Value" inputs | Enter value | Work | OK |
| "Open command source" (pencil) | Open source | Opens code; guide pill jumps to Command | CONFUSING (#5) |
| "Packet layout" (dots "24 B") | Show bytes | Shows MID/FC/field offsets and buttons "packet", "identifier", "dispatch" (each opens code) | OK / CONFUSING (#5) |
| "Send" / "Connect & send" / "Run test" | Send | Sends; Connect & send also re-enables to_lab silently | OK / CONFUSING (#12) |
| "Round trip" / "System overview" | Switch view | Switch | OK (views polluted, #36/#37) |
| System overview: "Commands" / "Telemetry" | Switch | Switch | OK |
| System overview tiles ("sample_app 1 sent"…) | Show app traffic | Detail list (12-hour time) | OK / CONFUSING (#37) |
| System overview detail "Close application" × | Close | Close | OK |
| System overview detail command/packet buttons | Open command or packet | Not clicked | NOT EXERCISED |
| "Tests" (···) | Test tools | Popover with Test select, Edit, New test; floats over the diagram | CONFUSING (#40) |
| "Test" select ("Send only", saved tests) | Choose test | Works | OK |
| "New test" / "Edit" | Test editor | Opens "New round-trip test" | OK |
| Test editor: "Test name", "Timeout (s)", "Command" (≈400), step type ("Flight event"/"Telemetry packet"), "EVS app name", "Event ID", "Message contains", "Move step up/down", "Remove step", "+ Observation", "Cancel", "Save test", × | Build a test | Works; dense form | OK / CONFUSING (#9, #27) |
| SENT row summary | Expand | Expands | OK |
| "View observation" | Show observation | No visible change | DEAD (#13) |
| "Stop test" | Cancel waiting test | Not reached | NOT EXERCISED |
| Telemetry "Select ENABLE_OUTPUT" | Select command | Already selected; redundant | DEAD (#14) |
| Telemetry field cards ("IngestPackets", "CommandCounter"…) | Open packet | Opens Packet inspector at that packet | OK |
| "Packet inspector" / "Field overview" | Switch telemetry view | Works | OK |
| "Packet" select, "Fields", "Raw bytes" | Inspect | Works | OK |
| "Packet type ↗" / "Identifier ↗" | Open source | Opens code; guide pill jumps to Command | CONFUSING (#5) |
| Send step card: "Back to code" | Return to editor | Not clicked | NOT EXERCISED |
| Send step card: "Stop previous build" → "Build cFS" → "Start cFS" | Deploy new build | Works (35 s build); 3 clicks; removes the Event tick | CONFUSING (#29, #4) |

### App / Architecture (`#app`, `#architecture`)
| Element | Expected | Actual | Status |
|---|---|---|---|
| "3D" / "2D" | Switch view | Works | OK |
| Legend "Your apps / Libraries / cFS apps" | — | Not interactive | OK |
| "Hide libraries" | Toggle libraries | Not clicked | NOT EXERCISED |
| "Create your first app" | Wizard | Opens wizard | OK |
| Your apps: "+ New" / "Edit" / trash | Manage own apps | Visible; not clicked (destructive) | NOT EXERCISED |
| Libraries: "+ New" / "Edit" / trash | Manage libraries | Edit and Remove disabled for sample_lib; New not clicked | NOT EXERCISED |
| cFS apps: "New" (disabled) / "Edit" / trash (enabled) | Locked for NASA apps | Edit and Remove enabled for NASA apps | CONFUSING (#33) |
| 2D tiles (ci_lab, sample_app…) and "Hardware" card | Select | Not clicked in 2D | NOT EXERCISED |
| 3D tiles (ci_lab…) | Select | Selection bar appears | OK |
| 3D bar: "Connections (3)" select | List links | Shows ES/SB/EVS links | OK |
| 3D bar: "Open code" | Open module code | `#code`; guide pill → Command | CONFUSING (#5) |
| 3D bar: "Commands" | Module commands | `#ground` filtered to ci_lab; guide pill → Event | CONFUSING (#5) |
| 3D bar: "View in 2D", × | 2D / close | Seen | NOT EXERCISED |
| 3D layer labels "Open cFS apps in 2D"… | Open 2D section | Seen | NOT EXERCISED |
| 3D "Orbit", "Pan", "Zoom out", "Zoom in", "Reset view" | Camera | Seen | NOT EXERCISED |
| Wizard: "Close" × | Close | Close | OK |
| Wizard: "Name" | Enter name | Validation via browser bubble; reserved-name message is inline | OK / minor (#23) |
| Wizard: "See its files →" / "Back" | Navigate | Work; Back keeps the name | OK |
| Wizard: "N more files", "Settings" (Priority, Stack · bytes, Wakeup · Hz, Housekeeping · Hz) | Expand | Expand | OK / CONFUSING (#32) |
| Wizard: "Create hello_app" | Create | Writes the files; "hello_app on the bus" | OK / wording (#47) |
| Wizard: "Next → add a command" | Command step | Not clicked (I closed and used guide Next, which opened New command) | NOT EXERCISED |

### Command / Code (`#command`, `#code`)
| Element | Expected | Actual | Status |
|---|---|---|---|
| New command: "Mission app" select, "Command name", "Cancel", "Create command", × | Create command | Works; no example; about 4 s silent busy state | OK / minor (#23) |
| Trail circles "Code … Test", "0/7" counter, × close activity | Step navigation | Seen; navigated with Next step / Back | OK |
| "Next step" | Next sub-step | Never blocks (even with NOT_IMPLEMENTED) | BROKEN (#8) |
| "Back" | Previous sub-step | Works | OK |
| "See the packet", command entries (NOOP … GREET), "Value uint32" | Jump to code | Jump to lines | OK |
| "Edit event emission" / "Edit handler" | Edit with help | Focuses the editor only | CONFUSING (#8) |
| Example refs "HELLO_APP_NOOP_INF_EID", "CFE_EVS_SendEvent" | Show example | Jumps to the NOOP handler | OK |
| "Open Ground Station" (step 7) | Send step | `#send` card | OK |
| Code editor (textarea) + Ctrl+S | Save | "File saved"; trail 6/7 | OK |
| Editor tabs (×8, with close ×) | Switch tabs | Truncated and overlapped | CONFUSING (#42) |
| "@Tags", "Packet", "Dispatch", search, expand | Tools | Seen | NOT EXERCISED |
| Tree: "Find a file", "Hide sidebar", folders and files | Navigate | Files open (via guide jumps); tool buttons not clicked | OK / NOT EXERCISED |

### Sensor / Test / Synthetic data / Hardware (`#sensor`, `#test`, `#simulation`, `#bench`)
| Element | Expected | Actual | Status |
|---|---|---|---|
| Left "Orbit · SSO 550 · 97.6° · 96 min" | Orbit panel | Opens the panel (already open) | OK |
| Left "Hardware" (dashed) | Connect a sensor | `#bench`: laptop drawing only (Native) | BROKEN on Native (#10) |
| Tabs "Signals" / "Python" / "QEMU" / "Test" | Switch | Switch; "Test" moves the guide to step 8 | OK / CONFUSING (#5) |
| "1×" / "60×" / "600×", "Pause orbit preview", "Signal settings" | Preview speed / settings | Seen | NOT EXERCISED |
| "Start" | Start synthetic data | Disabled: "Emulator required" | DISABLED, no way forward (#10) |
| Orbit panel: "ISS-like" / "SSO 550" / "Molniya", "Elements" / "TLE", sliders and inputs, "Two-body" / "J2", "Interval (s)", "Save settings" (disabled), "Close settings" × | Orbit setup | Seen; opening the screen already POSTs `/api/simulation/orbit` | CONFUSING (#34) |
| Python: "sensors/signals.py" select, checkbox, "Dry run", "Send to QEMU" | Run locally / send | Buttons disabled, text wraps, checkbox unlabeled | DISABLED / CONFUSING (#43) |
| QEMU: "Open hardware" | Hardware | Seen ("No devices") | NOT EXERCISED |
| Test: "One orbit" / "Eclipse entry" / "Sensor drops out", "Run" | Run scenario | Scenario select works; Run disabled | DISABLED (#10) |
| Hardware (Native): "3D" / "2D", "Zoom out", "Zoom in", "Reset layout and view" | Inspect hardware | Work; nothing else to do on Native | OK / dead end (#10) |

### Board step
| Element | Expected | Actual | Status |
|---|---|---|---|
| Guide "9 Board" (from the studio) | Board preview | Setup page, Board selected and saved, progress 2/9, links rewritten | BROKEN (#2) |
| Header "Native" afterwards | Restore | Restores Native and 5/9 | OK |

---

### Top 15 issues (summary)
1. Boot hangs forever on a failed cFS start: no error, no retry (#1). Blocker.
2. Opening the "Board" step switches and saves the workspace target; progress drops 5/9 → 2/9 (#2). Blocker.
3. Setup installer loop: "ready" in the log, Python check failing in the UI (#3).
4. Progress goes backwards when cFS restarts (Event unticked), with no coach to redo it (#4).
5. The guide pill follows the open screen (code → "Command", ground → "Event", Synthetic Test tab → "Test") (#5).
6. Future steps can be opened early and land on broken screens (giant magnifier, "No commands") (#6, #38).
7. The Command step is ticked at creation (0/7 done); two amber "Next" buttons (#7).
8. The 7-step editor never blocks or teaches; NOT_IMPLEMENTED passes; Events step unexplained (#8).
9. Own-command success ("HELLO: greet 42") isn't recognised; you must find "New test" (#9).
10. Sensor and Test are dead ends on Native ("Emulator required", no path) (#10).
11. The Round trip diagram is polluted: frames, crossing wires, overlapping UDP labels, idle nodes, red "Output off", empty strips (#36).
12. System overview is a wall of 19 identical counters, all "0 received" at first, including hidden commands (#37).
13. Hidden automatic commands (10 × ADD_PKT, re-enable) and a flood of debug events bury the person's own reply (#12, #39).
14. Many competing highlighted actions per screen, and pre-filled inputs/selections the person should choose (#26, #28).
15. Install errors are terse, stale and point at the wrong group ("Native tools · exit 1", "Toolchain · exit 1" on Board) (#19, #20).
