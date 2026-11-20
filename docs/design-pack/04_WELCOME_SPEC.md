# Welcome onboarding specification

Source: `design/source/Welcome.dc.html` (logic in its `<script data-dc-script>`; markup above it). Clickable: `design/preview/Welcome.html`. Screenshots: `design/screens/NN-*.png`. Reproduce the behaviour exactly; the numbers below are taken from the source. All timings assume one logic tick every 100 ms, as in the source (`setInterval(tick, 100)`); keep the same tick model, driven by `requestAnimationFrame` or a 100 ms interval, and pause it when the tab is hidden.

## Frame

- Canvas 1440×720 (design viewport); content card 1180×460 centred under the title row. Must fit 1440×900 with no page scroll.
- Top: product bar, then the progress rail: four groups (Satellite · Why space is hard · Software · Your lab) of round icon buttons joined by lines. The current chapter's icon has a conic progress ring filled by the chapter's task progress; the line after a done chapter fills sand. Done chapters show a check. Clicking any icon opens that chapter.
- Title row: eyebrow `GROUP · i / n` in the mono label style, the title (20 px, weight 400), Back (ghost) and Next (flat). Next gets the `ready` style when the chapter's task is complete. On the last chapter Next becomes Start.
- Revisiting a chapter resets that chapter's state to its initial values (the chosen mission is kept). Completed chapters keep their rail check.
- Chapter order: Satellite (0) · Radiation (1) · Power (2) · Ground (3) · Frameworks (7) · Separate apps (4) · cFS (11) · OS layer (5) · Boards (12) · On your desk (8) · Pick where it runs (9) · Your first steps (10). Numbers in brackets are the ids used in the source.

## Shared components (exact styles in `05_ANIMATION_SPEC.md`)

- **Token button**: flat, 40 px high, icon + label, sand or green variant, appears with `fsPop`, always carries the coach ring. Used for the one action that advances a chapter ("Solar flare", "Split into separate apps", "Add layers in between"…).
- **Caption pill**: rounded, one line, coloured by meaning (sand info, green good, red bad, amber warning), appears with `fsPop` near the thing it explains, lives for its `n` ticks.
- **Ground log**: panel with time, direction arrow (↑ sent, ↓ received, ✓ good, ! warning, × lost) and message; new lines enter with `fsIn`; at most 7 lines.

## Chapters

### 0 · What is a satellite?
Satellite drawing with six dashed hotspots (solar panels, battery, flight computer, radio, camera, attitude). The next unexplored hotspot carries the coach ring. Tapping one fills its card on the right (name, one-line role, icon) with `fsPop`. Task: 6 of 6. Screenshot `00-*`.

### 1 · Radiation flips bits
Ground log on the left, satellite with battery gauge on the right. Sequence (each step's button is the only highlight):
1. "Request battery level" → packet up, answer "Battery 80%" down.
2. "Solar flare" token on the sun → rays (`w-ray`) cross the scene; the next answer has a flipped bit.
3. "Request battery level" → the answer shows 80% while the real value is 16% (bits row shows the flipped bit in red).
4. "Start imaging: 50 photos" → the battery empties, the satellite goes dark ("No telemetry from the satellite").
5. "Add a checksum" token → the message now carries the sum of its digits; the ground checker block shows `8 + 0 = 8`, `check sent 7`, `✗ 8 ≠ 7`, the message is discarded and re-requested, then `1 + 6 = 7`, `✓ 7 = 7`.
6. "Postpone imaging until battery > 50%" → safe outcome.
Task: 5 of 5.

### 2 · Power runs out in the shadow
Sun, Earth with shadow, satellite on orbit, segmented battery with bolt, photo cone. Play starts the orbit. Tokens in order: "Turn on the camera" (photos drain the battery), then "Safe mode below 30%". The cycle never stops: empty battery → off → wakes in sun in SAFE MODE (badge) with photos blocked → back to normal at 60%. With the 30% rule the battery never empties. Task: 3 of 3.

### 3 · Talking to the ground
Earth with two ground stations, orbit, satellite with a MEMORY box of 6 tiles, right panel with "Cost per orbit" bar (budget line at $200) and a numbered "Photos on the ground" grid (24 slots).
- Start: the satellite itself carries the coach ring; tap starts time (clock at the top left).
- A photo every 10 minutes: camera cone flashes to the point under the satellite, a single-colour sand tile pops into memory.
- Over station A while it is not booked: time drops to slow motion (chip "slow motion"), station A has the ring and a tip "tap to book this station" under it. Booked passes cost $10/min ($160 per pass); photos fly from memory to the station and land in the numbered grid.
- Memory full: the next photo drops (red tile falls, `w-drop`) and its number appears in the grid as a red × gap.
- After the first loss: the unbooked station gets the ring and the tip "book a second station" with slow motion over it.
- Both booked: cost per orbit $320 turns red; both stations get the ring with "over budget · tap one to cancel".
- Cancel one: caption "some photos lost, inside the budget". Task: 4 (paid, lost, both, cancel).

### 7 · Why use a framework (first chapter of Software)
1. **Sorting game.** Nine cards, one at a time, centred: Hear commands from Earth · Photograph clouds · Do something every 10 seconds · Change the battery rule from Earth · Drive the wheels · Send status and photos down · Write down what went wrong · Point the mirror at a star · Know the exact time. Two drop zones, both with the coach ring: "every mission needs it" (green, three mission icons) and "only one mission needs it" (sand, three mission columns). Correct: the card disappears and its chip pops into the zone (specific ones under their mission). Wrong: the card shakes (`w-shake`/`w-shake2` alternate so it replays) and a red hint pill appears ("the rover and the telescope need it too", "only the rover does this"…). Progress dots on top.
2. **Columns.** After the ninth card: "what every mission needs becomes the framework", then the three mission columns of seven blocks each (shared green, specific sand), which slide (0.8 s, cubic-bezier(.4,0,.2,1)) into one dashed shelf "framework · reused in every mission" while the specific blocks stay as each mission's app (Photo app, Drive app, Star app). Caption "build them once, reuse them: that is a framework".
3. **Pick your mission.** The three mission headers get dashed outlines with the ring. Picking one sets the mission used by later chapters.
4. **Message flow.** Ground station log on the left with START and STOP; framework blocks Commands, Telemetry, Scheduler (green) and the app card with its two rules (START → every 10 s, take a photo · STOP → stop). START (ring) → pill "START" travels Ground → Commands → app; the app runs; every 10 s a "10 s" pill from Scheduler wakes it, the camera icon flashes, a blue pill "Photo n saved" travels app → Telemetry → Ground and a log line appears with the mission time. After two photos STOP gets the ring; a photo already on its way can still arrive after STOP, then "Photo app stopped". Caption "the framework carried every message".
5. **Other frameworks.** Five cards: cFS (we use it, NASA Goddard), F Prime (NASA JPL), KubOS (Kubos), RODOS (DLR · Univ. Würzburg), NanoSat MO (ESA · TU Graz). Each shows its style diagram with labelled message pills moving along the wires (one shared bus; pieces wired to each other; apps ask services). No "flew on" or "written in" rows. Task: 4 (sorted, picked, flow done, two styles seen).

### 4 · Why separate apps
The satellite alone in orbit; no ground commands. Earth with day and night halves, sun on the right with a soft glow, the shadow band behind Earth, the orbit ring coloured by temperature (blue −150 °C in shadow to red +120 °C in sun, with lag after leaving the shadow), labels "−150 °C" and "+120 °C", a temperature tag following the satellite, a ground station on the night side, the satellite computer panel (Radio, Camera, Power, Heaters) with a dashed "one program" outline, and a ground station log. 2.5° per tick.
- Pass 1 in the shadow: green beam, pill "all OK" travels down, log "pass 1 · battery 76% · all OK".
- In full sun after pass 1: the camera tile glows (`saHot`), then a part burns at about 340°: sparks (`saSpark`), smoke (`saSmoke`), camera tile red, caption "a camera part burned in the heat".
- One program: Heaters, Power, then Radio die in sequence (3, 6, 9 ticks), satellite turns grey, beacon stops; caption "one program: the crash took the radio down too". Pass 2: the station pings (`saPing`), "no answer", log "pass 2 · no answer", caption "the ground can't reach it anymore". The orbit stops; token "Run each app on its own".
- Separate apps: replay from the start; the same burn stops only the camera; pass 2 has contact: pill and log "camera stopped · rest OK", caption "the radio kept working: the ground knows what broke". Task: 3.

### 11 · We use NASA's cFS
Header "core Flight System · NASA Goddard · open source" with chips LRO 2009, GPM 2014, MMS 2015. Mission tabs (three round icons) at top right switch the app. The six shared needs from the sorting game fly from a pile on the left into CI, TO, SCH, TIME, EVS, TBL boxes on the software bus (staggered 7 ticks, 12-tick smoothstep each), and the mission's specific need flies into the app box ("you write"). SB is the bus itself (a button on the bus). Tapping a box zooms into a panel (`fsPop`) with the name, the plain name chip, one sentence, and a looping animation:
- CI: dish → "START" pill → CI → bus → app.
- TO: app → bus → TO → dish, pill "Photo 3 saved".
- SCH: clock with a sweeping hand (2.4 s) sending "wake up" pills to two apps.
- TIME: a ticking clock and a photo stamped with the time.
- EVS: log lines appear one by one (started, Photo 1 saved, heater on, camera too hot).
- TBL: a settings row "safe mode below 30% → 40%" changed by a pill from the ground while the app's code box keeps a lock.
- SB: one app publishes, two subscribers receive.
Inside the zoom, the "next piece →" button carries the ring; on the last one the close button does. Task: 7 pieces seen.

### 5 · Which operating system?
Left mini-stack (App, cFS, OSAL highlighted, PSP, Board).
1. Two lanes, Linux (general purpose) and RTEMS (real-time), each with a timeline scrolling left, dashed grid lines every 100 ms, and a task dot that must land on each line. A small satellite points its camera beam at a target. Token "Start a heavy job": a grey job bar appears in both lanes; on Linux dots start landing late (red, with a red bar back to the grid line, satellite wobbles 10°, beam red); RTEMS stays on the grid (the job bar is cut where the task runs). Late counters per lane. After 6 late: caption "Linux was late: the camera missed its target", token "Which OS for each mission?".
2. Three mission cards: weather satellite (photo every 10 s → "Linux is fine"), Mars rover (steer every 100 ms → "RTEMS · real-time"), telescope (hold the mirror on a star → "RTEMS · real-time"). Each reveals its OS with `fsPop` when tapped; the next unrevealed card has the ring.
3. OSAL: your app, cFS, "OSAL · translates to <OS>" above an OS block; three OS buttons (Linux · laptop, Pi; RTEMS · flight boards; VxWorks · flight boards). Switching swaps the OS block (`osSwapA/B`) and shows "no change" on the app and cFS. Task: 3.

### 12 · Which computer runs it?
Left mini-stack with PSP highlighted. Five board cards: Laptop · native ($0 · you have it), Raspberry Pi 4B (under $100), CubeSat computer (~$5k–8k), Rad-hard computer (~$200k), Emulator · QEMU ($0). The selected board's drawing, four property rows with ✓ / ✗ / ~ (Real pins and parts, Survives radiation, Easy to get, Fast to try code), the layer column (your app, cFS, OSAL marked "same", then PSP: "pc-linux" for laptop, Pi and emulator, "needs its own" for the flight boards) and the processor (x86, ARM, ARM9, PowerPC, virtual ARM). "Radiation test" sends particles (`bdRay`) into the board: laptop and Pi crash (reboot badge, shake), the flight boards show a shield. The emulator drawing materialises a virtual Pi inside the laptop (`bdMat`). Price bars on one scale grow over 1.2 s. Task: 5 boards seen.

### 8 · The satellite's computer, on your desk
Build the lab stack from the bottom (Linux, cFS core, NASA apps, Your app), one highlighted row at a time.

### 9 · Pick where it runs
Native, Emulator (start here), Board. Picking stores the target for the Setup screen.

### 10 · Your first steps
The nine steps of the first flight (Target, Boot, Event, App, Command, Send, Sensor, Test, Board) as a timeline with the stack diagram underneath. One step at a time: the next step's node carries the ring; tapping it highlights the layers that step touches. Play runs through all steps once and stops at Board. Task: 9 visited. Then Start.

## Copy

All visible strings are in the source; do not reword them. Prices and temperatures are sourced: Raspberry Pi under $100 (2026 list prices), CubeSat computer about $5k–8k (ISISPACE iOBC catalog average), rad-hard about $200k (RAD750, 2002 figure), ISS outside surfaces about −157 °C to +121 °C (shown rounded).
