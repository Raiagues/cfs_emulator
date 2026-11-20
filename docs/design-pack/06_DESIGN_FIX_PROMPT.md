# Design fix brief

The current UI was built quickly by a tool that executes well but makes poor design and navigation decisions. This brief lists what to fix and how. Read `01_PRODUCT_AND_UX_RULES.md` and `05_ANIMATION_SPEC.md` first. Detailed, screenshot-backed issues from a full click-through of the current build are in `10_AUDIT_FINDINGS.md` (section "UX click-through"); fix all of them.

Do not restyle working screens for taste. Change what breaks a rule. Keep what already matches the designs (the Target screen and the First boot screen are close to the design; keep their structure and fix only the items below).

## Method

1. For each screen, put the current screenshot (1440×900, dark) next to the reference in `design/screens/`. List every element that is not in the reference. Each one must justify its place against `01`; otherwise remove it.
2. Count highlighted elements at each moment of the guided flow. Exactly one (or the two options of an open choice).
3. Count words on screen outside logs and code. If a sentence repeats what a label or the picture already says, delete it.
4. Check every button against the generated `NAVIGATION_MAP.md`.
5. Check both themes and 1280×720.

## Global fixes

- **One component set.** Replace every local button, chip, card and pill style with the components in `05_ANIMATION_SPEC.md`. The current build has 11 stylesheets; screen stylesheets may only do layout.
- **Empty states.** An empty state is a small icon (at most 32 px) and one line, centred in its panel. The current Event screen before setup shows a magnifying-glass icon that fills the whole workspace (an unsized SVG); every icon must have an explicit width and height.
- **No placeholders for things that don't exist yet.** Remove empty grey strips, empty "SENT" tables with dashed bars, and panels that only say "Off". Show the panel when it has its first content, with `fsIn`.
- **Labels match destinations.** A toolbar button labelled "Start emulator" must start the emulator. If setup is missing, the button is replaced by "Set up emulator" (or disabled with the reason as its tooltip), never a silent redirect to another page under the old label. Same rule for every control.
- **The step bar** follows `03_FIRST_RUN_FLOW.md`: current stop from the server, Next only when reachable and with the coach ring, unreachable stops not clickable.
- **Captions instead of notices.** Replace any inline red or grey status sentence ("Native tools · exit 1", "Catalog details · 1") with: the failing item turning red in place, plus one caption that says what failed in operator words, plus the one action that fixes it highlighted.
- **Wording.** Apply the wording rules in `01` to every string. Remove counts and jargon that the step doesn't need ("FC 6", "24 B", "UDP 1234/2234" are useful only inside the packet detail view, not in the first view).

## Event and Send screen (Ground station) · the main redesign

The owner sent two screenshots of the current Event step and called them ugly and polluted: the "Round trip" diagram and the "System overview" grid. Rebuild this screen from `design/source/Lesson.dc.html` with these changes, which the design already follows or which tighten it:

- **Layout.** Left: command list (only the apps the current step uses: to_lab and sample_app in Event; your app added in Send). Centre top: the three step cards (Telemetry on · First command · Answer; in Send: Build and run · Your command · Answer). Centre: the command form for the selected command and a large Send button. Centre bottom: the path diagram. Right: telemetry, which appears only after the first packet.
- **The path diagram shows only the current path.** Nodes: Ground, ci_lab, the target app, to_lab, back to Ground. Nodes that are not on the current path are hidden (not greyed). No port numbers, no dashed "cFS · Emulator" frame with empty space, no Software Bus bar crossing nodes that are not involved, no sch_lab box during this step. The packet pill travels the path with its command name on it; the node it reaches lights up; the answer pill comes back blue.
- **System overview** is not part of the first run. Move it to the free Ground station rail view, and even there show only apps that are running in the current build, each with its real received count, sorted by activity, never a grid where everything says "0 received". Collapse cFE services into one row.
- **Telemetry panel.** Before ENABLE_OUTPUT: hidden. After: one card per telemetry packet that has arrived, with the fields that changed animated (+1 pop), and the latest event line. No "No telemetry · Select ENABLE_OUTPUT" box: the highlight on the ENABLE_OUTPUT row already says what to do.
- **The form.** dest_IP is empty with the placeholder 127.0.0.1 and carries the coach ring after ENABLE_OUTPUT is selected; payload fields are empty with placeholders; the packet length and checksum are inside "See the bytes", not on the main form.
- **Connect.** Disconnected state is a single highlighted Connect button where Send will be, not a footer "Disconnected · Connect" in the sidebar.

## More fixes from the click-through (see `audit/ux_report.md` issues 1 to 51)

- **No hidden commands.** Remove the automatic `TO_LAB_ADD_PKT_CC` burst and the silent re-enable of output (issue 12); see `03`.
- **Command list and log stay small.** Only the current step's apps in the list (issue 27); the person's replies first, housekeeping collapsed (issue 39); old telemetry is cleared or marked stale after a restart (issue 30).
- **Disabled controls say why** in their tooltip and accessible name, in one short line (issue 15). Things that look clickable are clickable (issue 16).
- **One name per action** everywhere: Build cFS, Run cFS, Stop cFS, Connect, Send (issue 48). Rebuild is Build; "Start cFS" is Run cFS.
- **Beginner views don't offer destructive edits** of NASA apps (issue 33): Edit and Remove on ci_lab, to_lab, sch_lab and sample_app appear only in the free Architecture view, behind a confirm.
- **App wizard step 2** shows the four files the person will touch (CMakeLists.txt, the app's .c, its message definitions, its function codes), then "and 57 more" folded (issue 32). The startup line is shown as a readable row (name, entry point, priority, stack), not the raw CSV.
- **Sensor screen** opens on the sensor and its signal; orbit elements fold under "Orbit" (issue 34).
- **Boot screen** shows the apps that matter (ci_lab, to_lab, sch_lab, sample_app, and the person's apps once created); the rest fold into "+9 NASA apps" (issue 31). sch_lab must not stay dashed once its startup line is in the log.
- **Overlays** never cover each other's buttons; the terminal docks at the bottom and the diagram collapses to a one-line strip while it is open (issues 40, 41). Editor tabs: at most five, older ones close (issue 42).
- **Jargon on the beginner path** (issue 49): "INFO + CommandCounter ↑", "MID 0x0808", "EVS #8", "FC 6", "char [16]", "Jobs" move into detail views.
- **Validation** is inline under the field, in plain words, never a browser bubble (issue 23). Add a favicon (issue 24).
- **Reproduce outside the Studio** (issue 35): each step has a small "In the terminal" disclosure with the exact command that does the same thing (for example the `./start --no-ui` twin or the plain cFS/QEMU command).

## Target screen

- Keep the three cards and the three check rings.
- "Jobs − 4 +" is a build detail; move it into Details.
- The "Click + to fix" hint is redundant once the first missing ring carries the coach ring; remove it.
- When an installer fails, the ring turns red and the caption says which package failed and why in one line, with Details highlighted. Remove the free-floating red "Native tools · exit 1".
- Emulator settings and Board settings open as small sheets anchored to the card, as now; validate inline (the port field shows the error under itself).

## First boot screen

- Keep the phase cards and the layer column. Each layer lights only when its real log milestone is seen.
- The right-hand detail panel shows the selected layer; when nothing is selected it shows the layer that is currently starting, not an empty box.
- The console line at the bottom shows the latest real log line in mono; Open console opens the terminal.

## App, Command, Sensor and Test screens

- App: follow `Mission.dc.html`. "Create your first app" is the only highlight until the wizard opens. The mission map stays dim until the first app exists ("Shows the whole mission once you have an app" as a tooltip only).
- Command: follow `AddCommand.dc.html`: seven stops, Next highlighted on "written for you" stops, Accept highlighted on "your turn". The editor shows the highlighted lines for the current stop; other files stay closed.
- Sensor and Test: follow `Ground.dc.html`. "Synthetic data is off · Start" strip carries the ring until the first confirmed write; then the Test tab; then Run test.

## Acceptance

For every screen: the follow-the-highlight test in `09` reaches the step's evidence without any click that isn't highlighted; the screenshot comparison shows no element that isn't in the reference or justified in `RESULTS.md`; no page scroll at 1440×900.
