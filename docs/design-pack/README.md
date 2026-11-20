# Flight Studio design pack

Put this folder in the repository at `docs/design-pack/` and tell the terminal AI:

> Read `docs/design-pack/00_START_HERE.md` and every file it lists, in order, before changing anything. Then follow it exactly.

## Contents

| Path | What it is |
| --- | --- |
| `00_START_HERE.md` | The brief: reading order, how to work, hard rules, definition of done |
| `01_PRODUCT_AND_UX_RULES.md` | The owner's design and UX rules |
| `02_ARCHITECTURE.md` | Infrastructure vs graphical layer, API, journey state machine, URL map |
| `03_FIRST_RUN_FLOW.md` | Every step of the first run, every highlighted action, every endpoint, the global controls map |
| `04_WELCOME_SPEC.md` | The Welcome onboarding, chapter by chapter |
| `05_ANIMATION_SPEC.md` | Tokens, components, every keyframe, where each animation is required |
| `06_DESIGN_FIX_PROMPT.md` | Fixes for the current screens (Event/Send redesign included) |
| `07_README_SPEC.md` | How to rewrite the repository README |
| `08_INFRA_SPEC.md` | CLI and infrastructure: native, emulator, board, ground link, sensors |
| `09_ACCEPTANCE_TESTS.md` | Tests that must pass |
| `10_AUDIT_FINDINGS.md` | What is wrong today, from reading and running the code |
| `design/source/` | Approved design files (`*.dc.html`) and the canvas layout |
| `design/preview/` | The same designs as standalone pages: open in a browser and click |
| `design/screens/` | Reference screenshots (Welcome states and the six first-steps screens) |
| `audit/code_report.md`, `audit/endpoints.md` | Code review (29 findings with file:line) and the full control → route → endpoint map |
| `audit/ux_report.md`, `audit/ux/shots/` | First-time-user click-through of the current build: 51 issues with screenshots, and every control tested |
| `audit/infra_report.md` | Terminal-only run of native, CLI, emulator and board paths, with root causes and patches |
| `design/tools/` | `mk.js` / `mklive.js` render a `.dc.html` to a static or live page; `follow-highlight-*.js` click through the designs the way the acceptance test does |

## Running the design tools

```sh
cd docs/design-pack/design/tools
npm i playwright && npx playwright install chromium
node mklive.js ../source/Welcome.dc.html ../preview/Welcome.html   # regenerate a preview
node follow-highlight-welcome.js 0,1,2,3,7,4,11,5,12,8,9,10           # every Welcome chapter
node follow-highlight-first-steps.js                                 # the six first-steps screens
```
