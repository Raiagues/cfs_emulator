# Design system and animation specification

Every item here is mandatory. The terminal AI that implements this pack tends to skip motion and replace it with static states; that counts as a failed requirement. Each animation below has a test in `09_ACCEPTANCE_TESTS.md` that checks it actually runs in the browser.

## Tokens

Dark theme values (the light theme maps each colour through the existing `tools/tokens.py` rule: lightness inverted, saturation kept; reuse that mapping, do not hand-pick light colours).

| Token | Value | Use |
| --- | --- | --- |
| page | `#13171c` | page background |
| card | `#161a20` | `wc-card` background |
| panel | `#1a1f25` | panels, tiles |
| deep | `#11161c` | logs, inner panels |
| line | `#262c34` | borders |
| line-2 | `#343c47` | stronger borders, ghost buttons |
| text | `#eef0f2` | primary text |
| chip-text | `#c9cfd6` | secondary text, chip text |
| muted | `#8e96a1` | labels |
| faint | `#5b636e` | disabled, timestamps |
| chip | `#20252b` | chip background |
| sand | `#d4b48a` / text `#f3dcb8` / bg `#2a241c` / ink `#1b150c` | the action colour: coach ring, primary buttons, user's own things (your app, your command) |
| green | `#5fc9a3` / text `#9fe3c9` / bg `#16261f` (border `#2f6e58`) | done, healthy, framework pieces |
| blue | `#7cb4f0` / text `#a9cdf5` / bg `#16212e` | telemetry, data coming down, OS layer |
| red | `#e5786d` / bg `#2a1a19` / border `#5a3330` | failure, lost, late |
| hot | `#ec8461` | heat |
| pink | `#e7c4dc` / bg `#241a22` | cFE core chips |

Fonts: Inter (UI text, 12 to 20 px; titles 20 px weight 400; never bold titles) and JetBrains Mono (code, values, labels in capitals 10 px with 0.12 em tracking). Both are already vendored in `interface/static/fonts/`.

Spacing: 4 px grid; cards 20 to 24 px inner padding; gaps 6, 8, 10, 14 px.

Radius: 4 px buttons and chips, 6 px cards and panels, 8 to 12 px overlays, 99 px pills and round buttons.

## Components (copy these styles; screens may not redefine them)

```css
.wc-card{position:relative;border-radius:6px;border:1px solid #262c34;background:#161a20;overflow:hidden;box-sizing:border-box}
.wc-panel{border-radius:6px;border:1px solid #262c34;background:#1a1f25;padding:12px 14px;display:flex;flex-direction:column;gap:9px;box-sizing:border-box}
.wc-lbl{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#8e96a1}
.wc-btn{position:relative;height:34px;padding:0 14px;box-sizing:border-box;border-radius:4px;border:1px solid #343c47;background:transparent;color:#c9cfd6;font:inherit;font-size:13px;display:inline-flex;align-items:center;justify-content:center;gap:8px;cursor:pointer;white-space:nowrap;transition:background .2s,color .2s,border-color .2s}
.wc-chip{height:22px;padding:0 7px;box-sizing:border-box;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:11px;display:inline-flex;align-items:center;background:#20252b;color:#c9cfd6;white-space:nowrap}
.w-nav{height:32px;padding:0 14px;box-sizing:border-box;border-radius:6px;border:1px solid #343c47;background:transparent;color:#c9cfd6;font:inherit;font-size:12px;display:inline-flex;align-items:center;gap:8px;cursor:pointer;text-decoration:none;transition:border-color .2s,color .2s}
.w-nav.ghost{border-color:transparent;color:#8e96a1}
.w-nav.ready{border-color:#d4b48a;color:#f3dcb8}
```

- Primary action button: sand background, ink text, 4 px radius, weight 600, no shadow, no gradient.
- Token button: 40 px high, 16 px horizontal padding, 6 px radius, 1 px border (sand variant `#8a7152` on `#1e1b16`, green variant `#2f6e58` on `#13201b`), 18 px icon, 13 px label; enters with `fs-pop` and always has `fs-coach`.
- Caption pill: 30 px high, 14 px padding, 99 px radius, 13 px weight 500; colours: info sand-bg/sand-text, good green-bg/green-text, bad red-bg/red, warn `#2a2214`/`#e8c08a`. Positioning wrapper rule: put `fs-pop` on an inner element, because `fs-pop` animates `transform` with `fill-mode: both` and would cancel a centring `translateX(-50%)` on the same element.
- Log line: 11 px mono time in faint, 12 px mono arrow in the meaning colour, 13 px message.

## Motion rules

- Default durations: state changes 0.2 to 0.4 s; objects moving between places 0.6 to 0.8 s with `cubic-bezier(.4,0,.2,1)`; things that follow a simulation clock use `transition: left .1s linear, top .1s linear` so they glide between ticks.
- Loops that teach (packets, bus pills, clock hands, pings) run continuously while their scene is visible and stop when it is hidden.
- `prefers-reduced-motion: reduce`: stop decorative loops (coach ring, pulses, dashes, pills, rays, sparks, smoke) but keep every state change and every position update (instant instead of animated). The flows must remain fully usable.
- The simulation clock ticks every 100 ms. Pause it when the document is hidden.

## Keyframes and animation classes (exact, from the approved design)

Colours appear as CSS variables (`var(--cRRGGBB)` is the hex `#RRGGBB`; `rgba(var(--rR_G_B),a)` is `rgba(R,G,B,a)`).

```css
@keyframes fsPulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes fsSpin{to{transform:rotate(360deg)}}
@keyframes fsDraw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes fsPop{0%{transform:scale(.4);opacity:0}60%{transform:scale(1.14);opacity:1}100%{transform:scale(1);opacity:1}}
@keyframes fsRing{0%{box-shadow:0 0 0 0 rgba(var(--r95_201_163),.55)}100%{box-shadow:0 0 0 16px rgba(var(--r95_201_163),0)}}
@keyframes fsIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
@keyframes fsPing2{0%{box-shadow:0 0 0 0 rgba(var(--r212_180_138),.5)}100%{box-shadow:0 0 0 8px rgba(var(--r212_180_138),0)}}
@keyframes fsDash{to{stroke-dashoffset:-20}}
@keyframes fsPulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes fsMove{from{offset-distance:0%}to{offset-distance:100%}}
@keyframes fsBlink{0%,100%{opacity:1}50%{opacity:.15}}
@keyframes fsCoach{0%{box-shadow:0 0 0 0 rgba(212,180,138,.6)}70%{box-shadow:0 0 0 12px rgba(212,180,138,0)}100%{box-shadow:0 0 0 0 rgba(212,180,138,0)}}
@keyframes fsHand{0%,100%{transform:translate(0,0)}50%{transform:translate(-5px,-5px)}}
@keyframes fsRay{from{transform:translate(0,0) rotate(-35deg)}to{transform:translate(-460px,330px) rotate(-35deg)}}
@keyframes fsFly{0%{transform:translate(0,-120px);opacity:0}20%{opacity:1}100%{transform:translate(0,0);opacity:0}}
@keyframes fsDot{from{left:0}to{left:100%}}
@keyframes fsShake{0%,100%{transform:translateX(0)}20%{transform:translateX(-8px)}40%{transform:translateX(8px)}60%{transform:translateX(-5px)}80%{transform:translateX(5px)}}
@keyframes fsDrop{0%{transform:translateY(0);opacity:1}100%{transform:translateY(70px) rotate(40deg);opacity:0}}
@keyframes fsMoveP{0%{offset-distance:0%;opacity:0}4%{opacity:1}30%{offset-distance:100%;opacity:1}34%{offset-distance:100%;opacity:0}100%{offset-distance:100%;opacity:0}}
@keyframes saPing{0%{transform:scale(.5);opacity:.9}100%{transform:scale(2.4);opacity:0}}
@keyframes saBeacon{0%{transform:scale(.5);opacity:.7}100%{transform:scale(1.7);opacity:0}}
@keyframes saSpark{0%{transform:rotate(var(--r)) translateX(6px) scaleX(.2);opacity:1}100%{transform:rotate(var(--r)) translateX(26px) scaleX(1);opacity:0}}
@keyframes saSmoke{0%{transform:translateY(0) scale(.6);opacity:.8}100%{transform:translateY(-34px) scale(2);opacity:0}}
@keyframes saHot{0%,100%{box-shadow:0 0 0 0 rgba(236,132,97,0)}50%{box-shadow:0 0 18px 2px rgba(236,132,97,.45)}}
@keyframes fsShake2{0%,100%{transform:translateX(0)}20%{transform:translateX(-8px)}40%{transform:translateX(8px)}60%{transform:translateX(-5px)}80%{transform:translateX(5px)}}
@keyframes czMove{0%{offset-distance:0%;opacity:0}8%{opacity:1}82%{offset-distance:100%;opacity:1}100%{offset-distance:100%;opacity:0}}
@keyframes czHand{to{transform:rotate(360deg)}}
@keyframes czStamp{0%,15%{transform:translateY(16px);opacity:0}30%,85%{transform:translateY(0);opacity:1}100%{opacity:0}}
@keyframes bdRay{0%{transform:translate(0,0) rotate(35deg);opacity:0}10%{opacity:1}100%{transform:translate(110px,150px) rotate(35deg);opacity:0}}
@keyframes bdMat{0%{opacity:0;transform:scale(.5)}60%{opacity:1;transform:scale(1.06)}100%{opacity:1;transform:scale(1)}}
@keyframes osSwapA{0%{transform:translateY(24px);opacity:0}100%{transform:none;opacity:1}}
@keyframes osSwapB{0%{transform:translateY(24px);opacity:0}100%{transform:none;opacity:1}}
@keyframes fsCoach2{0%{box-shadow:0 0 0 0 rgba(212,180,138,.45)}100%{box-shadow:0 0 0 8px rgba(212,180,138,0)}}

.fs-dark{--c0d1115:#0d1115;--c11171c:#11171c;--c13171c:#13171c;--c14181d:#14181d;--c161a20:#161a20;--c163b30:#163b30;--c1a1f25:#1a1f25;--c1b150c:#1b150c;--c1c1f24:#1c1f24;--c1f7a5b:#1f7a5b;--c22272e:#22272e;--c262c34:#262c34;--c2b313a:#2b313a;--c2e9a74:#2e9a74;--c2f363f:#2f363f;--c3a414b:#3a414b;--c3a424c:#3a424c;--c3e8f72:#3e8f72;--c4b525c:#4b525c;--c5b636d:#5b636d;--c5b8fb0:#5b8fb0;--c5fc9a3:#5fc9a3;--c7cb4f0:#7cb4f0;--c7d8590:#7d8590;--c8e96a1:#8e96a1;--c9aa2ad:#9aa2ad;--c9fdcc4:#9fdcc4;--ca4acb6:#a4acb6;--cb7bfc4:#b7bfc4;--cb9c0c8:#b9c0c8;--cc3a6ff:#c3a6ff;--cc9cfd6:#c9cfd6;--cc9d0d4:#c9d0d4;--cd4b48a:#d4b48a;--cd7dbe0:#d7dbe0;--cd7dee0:#d7dee0;--cd9a35b:#d9a35b;--ce8c08a:#e8c08a;--ce8cda8:#e8cda8;--ceef0f2:#eef0f2;--cff7a59:#ff7a59;--r95_201_163:95,201,163;--r212_180_138:212,180,138;--r217_163_91:217,163,91;--c161a1f:#161a1f;--c16261f:#16261f;--c2a241c:#2a241c;--c2f6e58:#2f6e58;--c6b7380:#6b7380;--c9fe3c9:#9fe3c9;--cf3dcb8:#f3dcb8;--c343c47:#343c47;--c0a0d10:#0a0d10;--c0d1720:#0d1720;--c11161c:#11161c;--c13201b:#13201b;--c14202e:#14202e;--c142131:#142131;--c15271f:#15271f;--c16212e:#16212e;--c162a22:#162a22;--c1a1416:#1a1416;--c1c2128:#1c2128;--c1c2f55:#1c2f55;--c1d3a33:#1d3a33;--c1d3a5c:#1d3a5c;--c1e1b16:#1e1b16;--c1f3550:#1f3550;--c1f5c3a:#1f5c3a;--c20252b:#20252b;--c241a22:#241a22;--c2a1a19:#2a1a19;--c2a2f38:#2a2f38;--c2a3d55:#2a3d55;--c2e4d6b:#2e4d6b;--c34506e:#34506e;--c3a4250:#3a4250;--c5a3330:#5a3330;--c5b636e:#5b636e;--c5c4d38:#5c4d38;--c6aa8ff:#6aa8ff;--c7d9fe6:#7d9fe6;--c8a7152:#8a7152;--c8a94c8:#8a94c8;--c9aa3ad:#9aa3ad;--ca99aa8:#a99aa8;--ca9cdf5:#a9cdf5;--ca9cff5:#a9cff5;--cb39b6a:#b39b6a;--cc49f88:#c49f88;--cc9a09a:#c9a09a;--cd4a07a:#d4a07a;--ce5786d:#e5786d;--ce7c4dc:#e7c4dc;--cec8461:#ec8461;--cf0a35e:#f0a35e;--cf0d58a:#f0d58a;--cff6a4d:#ff6a4d;--cffb44d:#ffb44d;--cffd36b:#ffd36b;--r0_0_0:0,0,0;--r124_180_240:124,180,240;--r19_23_28:19,23,28;--r236_132_97:236,132,97}
.fs-pulse{animation:fsPulse 1.1s ease-in-out infinite}
.fs-spin{animation:fsSpin .9s linear infinite;transform-origin:50% 50%;transform-box:fill-box}
.fs-pop{animation:fsPop .5s cubic-bezier(.2,.9,.3,1.25) both}
.fs-ring{animation:fsRing 1s ease-out 2}
.fs-in{animation:fsIn .35s ease-out both}
.fs-ping2{animation:fsPing2 1.3s ease-out infinite}
.fs-dash{stroke-dasharray:4 6;animation:fsDash .7s linear infinite}
.fs-mv{position:absolute;left:0;top:0;width:9px;height:9px;margin:0;border-radius:99px;offset-rotate:0deg;animation:fsMove 1.6s linear infinite;pointer-events:none;transition:opacity .3s}
.fs-blink{animation:fsBlink .5s steps(1) infinite}
.fs-coach{animation:fsCoach 1.4s ease-out infinite;z-index:3}
.fs-coach::after{content:'';position:absolute;right:-16px;bottom:-20px;width:26px;height:26px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M10 9.5V4a2 2 0 0 1 4 0v6l3.6.6a2.5 2.5 0 0 1 2.1 2.8L19 19a3 3 0 0 1-3 2.6h-4.3a3 3 0 0 1-2.4-1.2L5.6 17a1.8 1.8 0 0 1 2.7-2.4L10 16z' fill='%2313171c' stroke='%23d4b48a' stroke-width='1.6' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat center/contain;animation:fsHand 1s ease-in-out infinite;pointer-events:none;z-index:6}
.wc-card{position:relative;border-radius:6px;border:1px solid var(--c262c34);background:var(--c161a20);overflow:hidden;box-sizing:border-box}
.wc-panel{border-radius:6px;border:1px solid var(--c262c34);background:var(--c1a1f25);padding:12px 14px;display:flex;flex-direction:column;gap:9px;box-sizing:border-box}
.wc-lbl{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--c8e96a1)}
.wc-btn{position:relative;height:34px;padding:0 14px;box-sizing:border-box;border-radius:4px;border:1px solid var(--c343c47);background:transparent;color:var(--cc9cfd6);font:inherit;font-size:13px;display:inline-flex;align-items:center;justify-content:center;gap:8px;cursor:pointer;white-space:nowrap;transition:background .2s,color .2s,border-color .2s}
.wc-seg{display:flex;padding:3px;border-radius:6px;background:var(--c13171c);border:1px solid var(--c262c34)}
.wc-row{display:flex;align-items:center;gap:10px;min-height:26px;font-size:12px;color:var(--cc9cfd6)}
.wc-sw{position:relative;width:34px;height:20px;flex:none;border-radius:99px;border:none;padding:0;background:var(--c343c47);cursor:pointer;transition:background .2s}
.wc-sw::before{content:'';position:absolute;left:3px;top:3px;width:14px;height:14px;border-radius:99px;background:var(--ceef0f2);transition:left .2s}
.wc-stat{flex:1;min-width:0;padding:8px 10px;border-radius:4px;background:var(--c13171c);display:flex;flex-direction:column;gap:2px}
.wc-chip{height:22px;padding:0 7px;box-sizing:border-box;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:11px;display:inline-flex;align-items:center;background:var(--c20252b);color:var(--cc9cfd6);white-space:nowrap}
.wc-cfs{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.w-ray{position:absolute;width:44px;height:2px;border-radius:99px;background:linear-gradient(90deg,rgba(229,120,109,0),var(--ce5786d));animation:fsRay 2.6s linear infinite;pointer-events:none;transition:opacity .6s}
.w-fly{position:absolute;left:24px;top:14px;width:22px;height:22px;border-radius:4px;background:var(--cd4b48a);animation:fsFly .9s ease-in infinite;pointer-events:none}
.w-drop{animation:fsDrop 1s ease-in forwards;pointer-events:none}
.w-shake{animation:fsShake .5s ease-in-out}
.fs-mvp{position:absolute;left:0;top:0;height:22px;padding:0 9px;border-radius:99px;font-family:'JetBrains Mono',monospace;font-size:11px;display:flex;align-items:center;white-space:nowrap;offset-rotate:0deg;offset-anchor:50% 50%;animation:fsMoveP 6s linear infinite;pointer-events:none;z-index:4}
.sa-ping{animation:saPing 1.4s ease-out infinite}
.sa-beacon{animation:saBeacon 1.6s ease-out infinite}
.sa-spark{animation:saSpark .6s ease-out 4}
.sa-smoke{animation:saSmoke 1.6s ease-out infinite}
.sa-hot{animation:saHot 1s ease-in-out infinite}
.w-shake2{animation:fsShake2 .5s ease-in-out}
.cz-mv{position:absolute;left:0;top:0;height:24px;padding:0 10px;border-radius:99px;font-family:'JetBrains Mono',monospace;font-size:11px;display:flex;align-items:center;white-space:nowrap;offset-rotate:0deg;offset-anchor:50% 50%;animation:czMove 3s linear infinite;pointer-events:none;z-index:4;box-shadow:0 0 0 3px var(--c161a20)}
.cz-hand{animation:czHand 2.4s linear infinite}
.cz-stamp{animation:czStamp 3s ease-out infinite}
.bd-ray{animation:bdRay 1.2s ease-in infinite}
.bd-mat{animation:bdMat 1.2s .3s both;transform-box:fill-box;transform-origin:50% 50%}
.os-a{animation:osSwapA .45s both}
.os-b{animation:osSwapB .45s both}
.fs-coach{animation:fsCoach2 1.8s ease-out infinite!important}
.fs-coach::after{display:none!important}
.w-nav{height:32px;padding:0 14px;box-sizing:border-box;border-radius:6px;border:1px solid var(--c343c47);background:transparent;color:var(--cc9cfd6);font:inherit;font-size:12px;display:inline-flex;align-items:center;gap:8px;cursor:pointer;text-decoration:none;transition:border-color .2s,color .2s}
.w-dot{position:absolute;top:-4px;width:10px;height:10px;margin-left:-5px;border-radius:99px;animation:fsDot 1.4s linear infinite}
.w-shake{animation:none}
```

## Where each animation is required

| Animation | Element | Screen |
| --- | --- | --- |
| `fsCoach2` via `.fs-coach` | the single next action | every guided screen |
| `fsPop` | appearing chips, cards, captions, tokens, check marks | everywhere |
| `fsIn` | entering views, log lines | everywhere |
| `fsDraw` | check marks in the step bar and success states | step bar, Boot, Event |
| `fsPing2` | current stop of the step bar | step bar |
| `fsDash` | live links (ground link, beams) | Event, Send, Welcome Ground, Separate apps |
| `fsPulse` | live status dots, running checks | Target, Boot, Welcome |
| `fsSpin` | restarting or installing indicators | Target, Welcome Separate apps |
| `fsShake` / `fsShake2` (alternate to replay) | wrong answer, crash | Welcome Frameworks quiz, Layers/Boards crash |
| `w-ray` / `fsRay` | solar flare rays | Welcome Radiation |
| `w-drop` / `fsDrop` | lost photo falling | Welcome Ground |
| `fs-mvp` (`fsMoveP`) and `cz-mv` (`czMove`) | labelled message pills along offset paths | Welcome Frameworks styles, Welcome cFS zooms |
| `sa-ping`, `sa-beacon`, `sa-spark`, `sa-smoke`, `sa-hot` | ground pings, radio beacon, burn sparks, smoke, hot camera | Welcome Separate apps |
| `cz-hand`, `cz-stamp` | scheduler clock hand, time stamp | Welcome cFS zooms |
| `bd-ray`, `bd-mat` | radiation test particles, emulator materialising | Welcome Boards |
| `os-a` / `os-b` | OS block swap | Welcome OS layer, Boards PSP block |
| packet pill travelling the path (left/top transitions at 0.1 s linear) | Ground → ci_lab → app → to_lab → Ground | Event, Send |
| counter change `+1` pop | CommandCounter and other changed telemetry fields | Event, Send |
| layer column lighting from bottom to top at each real log milestone | Boot |
| file tree items appearing one by one | App wizard, Command guide |
