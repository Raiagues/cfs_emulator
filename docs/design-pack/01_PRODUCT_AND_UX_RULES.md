# Product and UX rules

These rules come from the owner. Every screen, text and interaction is checked against them. When in doubt, choose the option that is simpler, more visual and closer to how real cFS work is done.

## What Flight Studio is

A local lab to learn and develop NASA cFS flight software. It is for development and testing only, never for flight. The person who opens it for the first time usually does not know what a satellite is made of, why space makes software hard, what partitioning or layers are, or what cFS is. By the end of the first run they have sent commands to a running cFS, written their own app and command, fed it sensor data and tested it, and they know how to repeat all of it on their own computer without Flight Studio.

## The ten rules

1. **Show, don't tell.** Visual, animated, interactive. Text only where it truly explains something the picture cannot. No paragraphs on screen.
2. **One screen.** Each screen fits 1440×900 without page scrolling. Panels may scroll their own lists (a log, a file tree), never the page.
3. **One look.** The same components everywhere: card, panel, chip, flat button, token button, caption pill, coach ring, step bar. Same spacing scale, same two fonts (Inter for text, JetBrains Mono for code and values), same colours (see `05_ANIMATION_SPEC.md` for tokens). Nothing childish: no hand pointers, no emoji, no bouncy cartoon effects, flat refined buttons.
4. **Tap the thing itself.** Interaction happens on the object in the scene (the station, the satellite part, the app box, the board) rather than in a separate configuration panel.
5. **Real operations.** Scenarios are what real teams do: request battery level, enable telemetry with to_lab, send NOOP and watch CommandCounter go up, book a ground station pass, lose a photo because memory is full. Wording is what an operator would say, without exaggeration.
6. **Guided first run.** At every moment of the first run, exactly one next action is highlighted with the coach ring. The person does each first thing themselves. Autonomy grows step by step: early steps highlight a single control; later steps highlight less and leave more choice.
7. **Nothing pre-done.** Don't show results the person didn't produce (no fake telemetry counters already at non-zero, no app already created, no command already written, no "0 received" grids of apps they haven't met yet). Show only the parts of the system that matter for the current step; reveal the rest as it becomes relevant.
8. **No extra notices.** No warning banners, no "note:" boxes, no tooltips that repeat a label. If something can't be done yet, the control is not offered, or is offered in a disabled state that is visually obvious.
9. **Real cFS environment.** Use real names and real tools. The screen shows the same app names, message IDs, function codes, events and files the person will see in the official nasa/cFS checkout and its logs. Anything Flight Studio adds (the emulator image, the sensor models, the guided tests) is labelled as added by Flight Studio.
10. **Navigation never lies.** Every button leads exactly where its label says. Back goes back. Next goes to the next step and only appears when that step is reachable. Revisiting a teaching screen replays it from the start. No dead ends: a failed action shows what failed and offers the one action that fixes it.

## Wording

- Short, plain English. Verbs for actions ("Send", "Book", "Run cFS"), nouns for objects ("Ground station", "to_lab").
- Write what happens, not what to feel. "Photo 3 saved", "No telemetry from the satellite", "Over budget · tap one to cancel".
- Numbers carry units (°C, %, $/min, ms, Hz).
- Captions: at most about 50 characters, one at a time, shown for 2 to 6 seconds, placed near the thing they describe.
- Never "simply", "just", "easily", "magic", "awesome", exclamation marks or emoji.

## The coach ring (single highlight)

- One element at a time gets the class `fs-coach`: a soft pulsing ring (`fsCoach2`, 1.8 s, ease-out, infinite). See `05_ANIMATION_SPEC.md`.
- The ring goes on the exact control the person should use next: the station to book, the command row to select, then the Send button, the app box to open, the Next button of the step bar once a step is complete.
- When a choice is genuinely open (for example the two answers of the sorting game), both options get the ring.
- While an animation is playing out and the person is expected to watch, nothing is highlighted.
- When a step is complete, the ring moves to the step bar's Next button.

## Scenes and text budget per screen

- Title (one line, at most about 30 characters) and the step label above it.
- At most one caption visible at a time.
- Labels on objects: one or two words.
- Logs show real-looking lines with time, direction arrow and message.

## What not to do (seen in the current build)

- A "System overview" grid of 20 tiles all saying "0 received" before the person has done anything.
- A diagram with every route of the system and port numbers in the first step, when the step only needs one path.
- Empty grey strips and boxes that hold nothing yet.
- Two highlighted buttons at once, or a highlighted step in the bar that doesn't match the screen.
- Buttons that open a different screen from the one their label names.
