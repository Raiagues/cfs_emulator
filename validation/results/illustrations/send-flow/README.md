# Authored command workflow — Native

This is a live interface regression check of the existing `orbit_demo` app, separate from the thesis Q1–Q5 measurements. It does not add observations to those quantitative results. The application sources and local configuration were preserved.

The tested source revision is `677fdd5e3806dbccacebfe08268ecb2ea114f724`. The browser used the real Studio, compiler, cFS process and UDP Ground Station. Build concurrency was one worker. QEMU and the physical board were not rerun for this interface check.

## Observed sequence

1. Stop the running Native mission; Build remains disabled while its binaries are running.
2. Build and run using the interface. The Command page stays open until **Open Ground Station** is clicked.
3. Open Send with `orbit_demo / SET_RATE` selected and its compiled `Rate_Hz` field visible.
4. Send ENABLE_OUTPUT and wait for actual downlink and application HK.
5. Send `Rate_Hz = 17`: receive `Rate set to 17 Hz` and `CommandCounter 0 → 1`.
6. Send `Rate_Hz = 23`: receive a distinct event and `CommandCounter 1 → 2`.
7. Reload Send: retain the app selection and both independent confirmations. No JavaScript errors were recorded.

The command MID is `0x1A00`; its event reply uses `0x0808`. The visible route includes only actual participants for those MIDs. `hs` appears because its source subscribes to the event MID. Ground is outside the flight boundary, and the Software Bus connects the applications. The replay illustrates the configured route after a confirmed response; it does not measure internal hop timestamps. Both sidebars measured 272 pixels in the captured viewport.

## Files

- `verification.json`: source commit, installed build fingerprint, jobs, individual send IDs, response-event IDs and HK counters.
- `cfs-events.txt`: two selected literal lines from the live cFS terminal log.
- `01-command-ready.png`: compiled/running app with the explicit Ground Station link.
- `02-replay-17.png`, `02-replay-23.png`: real interface captures after the corresponding response.
- `03-confirmed.png`: the two confirmed sends and selected route.
- `04-reloaded.png`: the same history after reloading, with the selected command visible in its sidebar.
- `SHA256SUMS`: checksums of this evidence package.

## Repeat the check

First create an app through the Studio and complete its SET_RATE handler activity. Start the Studio. The opt-in script below stops, rebuilds and runs Native, sends values 17 and 23 to the chosen app, and writes a fresh evidence directory under the system temporary directory:

```sh
PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/google-chrome \
  node interface/tests/browser/live-authored-native.mjs orbit_demo
```

Replace `orbit_demo` with the completed app name. Set `FLIGHT_STUDIO_URL` if the local Studio uses a different port. Playwright must be installed for the browser checks. The script creates no app and makes no source edits.

Automated regressions additionally cover source generation from the installed NASA sample_app, preservation of sample_lib, command fields from the compiled catalog, repeated replies, wrong events, counter rollover, manual navigation, fresh catalog loading, sidebar selection, receipt history after reload, and completed lesson progress across subsequent runs. They are in `interface/tests/` and `interface/tests/browser/`.
