# Acceptance tests

All of these must pass before the work is done. Put the commands in `scripts/test` so they can run with one command, and paste the output into `docs/design-pack/RESULTS.md`. Browser tests use Playwright with Chromium at 1440×900 unless noted.

## 1. Existing suites stay green

- `python -m unittest` (or the repo's runner) for `interface/tests/*.py`: same or more tests, all passing (today: 79 pass, 1 skipped).
- The existing `.mjs` browser tests in `interface/tests/`.

## 2. Fresh clone

On a clean Linux user account: follow the README "Começar em 5 minutos" commands literally. Pass when the UI opens, the Native target's checks pass after their installers, and First boot reaches OPERATIONAL. Record the time taken.

## 3. Follow the highlight (the core UX test)

Write `interface/tests/follow-highlight.mjs`, modelled on `design/tools/follow-highlight-welcome.js` and `follow-highlight-first-steps.js` (they pass on the design previews; run them to see the expected behaviour). For each screen of the first run, starting from the journey state where the previous steps are done:

1. Find every visible element with the class `fs-coach` (visible: non-zero size, not hidden, opacity ≥ 0.15, not inside the step bar unless it is the Next button).
2. If none and the step is not complete, wait (up to 30 s, or the real job time for builds and boots); if still none, FAIL with a screenshot ("no next action").
3. If more than one, FAIL unless they are the declared options of an open choice (the sorting game's two zones).
4. Click it (or type into it when it is an input, using the value the test plan gives).
5. Repeat until the step's evidence is reported by `GET /api/journey`, then check that the step bar's Next carries `fs-coach` and leads to the next step's route.

The test also fails if any click lands on an element that is not highlighted, or if the step completes without the user doing the step's own action (anything pre-done).

## 4. Navigation map

`scripts/nav-map` extracts every interactive element and its destination from the code (static analysis plus a crawl in the browser). The test compares its output with the table in `03_FIRST_RUN_FLOW.md` and fails on any difference: missing control, extra control, or a control whose destination differs from its label. It also crawls every reachable screen, clicks every control once, and fails on any navigation to a 404, an uncaught exception in the console, or a failed network request.

## 5. Animations actually run

For each row of the table in `05_ANIMATION_SPEC.md`, a browser check:
- class-based animations: the element exists at the expected moment and `getComputedStyle(el).animationName` is the expected keyframe name and `animationPlayState` is `running`;
- moving elements (packet pills, flying chips, the satellite): sample `getBoundingClientRect()` three times 200 ms apart; the positions must differ;
- appearing elements: the element's `animationName` is `fsPop` or `fsIn` when it first appears;
- reduced motion: with `prefers-reduced-motion: reduce`, the same flows complete (test 3 passes) and decorative loops report `animationName: none`.

## 6. Layout

At 1440×900: `document.scrollingElement.scrollHeight <= innerHeight` on every screen. At 1280×720: no horizontal scroll. No text overflow (`scrollWidth > clientWidth` on labels and buttons) and no icon larger than its container. Run in dark and light themes.

## 7. Journey state machine

Unit tests for the journey package: out-of-order evidence is not credited; `current`, `reachable` and `next_route` for every combination of done steps; reset ignores older evidence; entering an unreachable step route redirects to the current step route.

## 8. Infrastructure without UI

A script runs, on the native target: `source install`, `setup --check`, `build`, `run`, `ground send to_lab ENABLE_OUTPUT --arg dest_IP=127.0.0.1`, `ground send sample_app NOOP` (expects the event and CommandCounter +1), `app new demo_app`, `build`, `run`, `app delete demo_app`, `simulate-preview --model tmp105`, `stop`. On machines with Docker and network access to the image registry: `emulator image`, `boot --target qemu`, `run --target qemu`, the same ground commands, `emulator stop`.

## 9. Design comparison

Screenshots of every screen and step at the moments listed in `design/screens/` are saved to `docs/design-pack/results/` and listed next to the references in `RESULTS.md`, with a sentence for any intended difference.
