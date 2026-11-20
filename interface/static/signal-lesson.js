import { api, readJourney } from './api.js';
import { guide } from './coach.js';
import { deploymentControls } from './deployment-controls.js';
import { escapeHtml as esc, paint } from './dom.js';
import { orbitCard, orbitControls, orbitToolbar, drawOrbit } from './orbit-preview.js';
import { stepUrl } from './router.js';
import { onUpdate } from './updates.js';
import { icon } from './ui.js';

const cases = [
  ['orbit', 'One orbit'],
  ['eclipse', 'Eclipse entry'],
  ['dropout', 'Sensor drops out'],
];
const tick =
  '<svg class="fs-draw" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
function trend(samples, key) {
  const points = samples.map((s) => s[key]).filter(Number.isFinite);
  if (!points.length) return '';
  const min = Math.min(...points),
    max = Math.max(...points);
  const coordinates = points.map((v, i) =>
    [4 + (292 * i) / Math.max(1, points.length - 1), 56 - ((v - min) * 48) / (max - min || 1)].join(','),
  );
  return `<svg class="signal-line" viewBox="0 0 300 64" preserveAspectRatio="none" aria-label="${esc(key)}"><polyline points="${coordinates.join(' ')}" vector-effect="non-scaling-stroke"/></svg>`;
}
export function mountSignalLesson(root, { state, startJob, advanceDeployment, refreshMission, saveSimulation }) {
  const target = state.target,
    test = state.activity === 'test';
  let journey,
    station,
    picker = false,
    chosen = null,
    selectedCase = 'orbit',
    disposed = false,
    busy = false,
    error = '';
  let enabling = false,
    address = '',
    pendingEnable = false,
    replyTimer,
    loaded = false,
    flightInstance;
  const traces = new Map();
  const latest = (action, device, scenario) =>
    state.jobs.findLast(
      (j) =>
        j.action === action &&
        j.target === target &&
        (j.device === device || (action === 'simulate' && !j.device)) &&
        (!scenario || j.scenario === scenario),
    );
  function draw() {
    if (disposed || !journey || !loaded) return;
    const owner = journey.steps.send.ref?.app || journey.steps.app.ref?.app;
    const conf = state.workspace.project;
    const app = conf.apps.find((a) => a.name === owner),
      devices = conf.devices;
    const device = devices.find((d) => Object.values(app?.sensors || {}).includes(d.id));
    const deployed = deploymentControls(state),
      plan = deployed.plan;
    const connected = station?.target === target && station.connected;
    const flight = connected ? station.first_flight : {};
    const downlink = !!flight.downlink_receipt;
    const job = latest('simulate', device?.id),
      running = job?.status === 'running';
    const run = latest('simulate-preview', device?.id, selectedCase);
    const report = run?.scenario_result,
      checks = run?.checks || report?.checks || {};
    const frame = job?.samples,
      reading = frame?.devices?.find((d) => d.id === device?.id);
    if (reading && frame.received_at !== traces.get('at')) {
      traces.set('at', frame.received_at);
      const series = traces.get('samples') || [];
      series.push(reading.values);
      if (series.length > 120) series.shift();
      traces.set('samples', series);
    }
    const source = state.simulation,
      orbit = source?.settings?.orbit;
    const tabs = ['Signals', 'Test']
      .map((name, i) => {
        const id = i ? 'test' : 'sensor';
        return journey.steps[id].reachable
          ? `<a href="${esc(stepUrl(id, location, target))}" ${test === !!i ? 'aria-current="page"' : ''}>${name}</a>`
          : `<span>${name}</span>`;
      })
      .join('');
    let action = null;
    if (test) {
      if (run?.status !== 'running') action = 'test';
    } else if (!device) action = picker ? (chosen ? 'link' : 'device') : 'add';
    else if (plan) action = 'deploy';
    else if (!connected) action = 'connect';
    else if (!downlink && !pendingEnable)
      action = !enabling
        ? 'enable'
        : /^\d{1,3}(\.\d{1,3}){3}$/.test(address) && address.split('.').every((v) => +v <= 255)
          ? 'send'
          : 'address';
    else if (downlink && !running) action = 'start';
    const stripTitle = !device
      ? 'Sensors'
      : target === 'physical'
        ? running
          ? 'Reading board'
          : 'Board readings are off'
        : running
          ? 'Synthetic data is on'
          : 'Synthetic data is off';
    const button = (a, label, disabled = false) =>
      `<button type="button" data-signal-action="${a}" ${busy || disabled ? 'disabled' : ''}>${esc(label)}</button>`;
    const groundAction =
      !device || plan || test
        ? ''
        : !connected
          ? button('connect', 'Connect')
          : !downlink
            ? !enabling
              ? button('enable', 'to_lab · ENABLE_OUTPUT')
              : `<label>dest_IP<input data-signal-action="address" value="${esc(address)}" placeholder="${esc(flight.return_host)}" autocomplete="off" spellcheck="false"></label>${button('send', 'Send', action !== 'send')}`
            : '';
    const errorText = error || (test ? run?.error : job?.error || deployed.failure);
    const sidebar = `<aside class="signal-devices"><h2>Synthetic data</h2>${device ? `<article class="fs-panel"><strong>${esc(device.name)}</strong><code>${esc(device.model)}</code><small>${esc(device.bus)} · 0x${Number(device.address).toString(16)}</small></article>` : ''}
      ${!device ? button('add', 'Add sensor') : ''}
      ${picker ? `<section class="fs-panel signal-chooser"><h3>Add sensor</h3>${devices.map((d) => `<button data-signal-action="device" data-id="${esc(d.id)}" aria-pressed="${chosen === d.id}">${esc(d.model)} · ${esc(d.bus)}</button>`).join('')}${button('link', 'Link to ' + owner, !chosen)}</section>` : ''}</aside>`;
    const measurements = reading
      ? Object.entries(reading.values)
          .map(
            ([key, v]) =>
              `<article class="fs-panel reading"><h3>${esc(key)}</h3><strong>${esc(v)} ${esc(reading.units?.[key])}</strong>${trend(traces.get('samples') || [], key)}</article>`,
          )
          .join('')
      : '';
    const strip = `<section class="fs-panel signal-strip"><i class="${running ? 'fs-pulse' : ''}"></i><div><strong>${stripTitle}</strong><small>${esc(owner || '')}</small></div>${
      groundAction ||
      (device && !plan && downlink ? button(running ? 'cancel' : 'start', running ? 'Stop' : 'Start') : '')
    }${device && plan && !deployed.button ? button('deploy', plan.label, deployed.working) : ''}</section>`;
    const tester = `<section class="scenario-choices">${cases.map(([id, label]) => `<button data-case="${id}" aria-pressed="${id === selectedCase}" ${run?.status === 'running' ? 'disabled' : ''}>${label}</button>`).join('')}</section>
      <section class="fs-panel case-results"><h2>${cases.find(([id]) => id === selectedCase)[1]}</h2>
      ${button('test', run?.status === 'running' ? 'Running' : report ? 'Run again' : 'Run test', !device || run?.status === 'running')}
      <ul>${Object.entries(checks)
        .map(
          ([k, v], i) =>
            `<li data-scene="check-${esc(run.id)}-${i}" style="--check:${i}">${v ? tick : '×'}${esc(k)}</li>`,
        )
        .join('')}</ul>
      ${
        report
          ? `<small>${report.samples.length} samples · ${esc(report.device)}</small>${Object.keys(
              report.units,
            )
              .map((key) =>
                trend(
                  report.samples.map((s) => s.read),
                  key,
                ),
              )
              .join('')}`
          : ''
      }</section>`;
    const cli = test
      ? './start --no-ui simulate-preview --device ' + (device?.id || '<id>') + ' --scenario ' + selectedCase
      : !device
        ? './start --no-ui project link-hal ' +
          (owner || '<app>') +
          ' ' +
          (chosen || '<reader>') +
          ' --device ' +
          (chosen || '<id>')
        : plan
          ? './start --no-ui ' + plan.action + ' --target ' + target
          : !connected
            ? './start --no-ui ground connect --target ' + target
            : !downlink
              ? './start --no-ui ground send to_lab ENABLE_OUTPUT --arg dest_IP=' + (address || '<address>')
              : './start --no-ui simulate --device ' + device.id + ' --target ' + target;
    paint(
      root,
      `<section class="signal-lesson fs-in">${sidebar}<div class="signal-content"><nav class="signal-tabs">${tabs}</nav>
      ${test ? tester : strip + orbitToolbar() + orbitCard() + '<section class="signal-readings">' + measurements + '</section>'}
      ${errorText ? `<p role="alert">${esc(errorText)}</p>` : ''}<details class="terminal-twin"><summary>In the terminal</summary><pre>${esc(cli)}</pre></details></div>
      ${!test && orbit ? `<aside class="signal-orbit"><details><summary>Orbit</summary>${orbitControls(orbit, running)}${button('save-orbit','Save',!state.simulationDirty||running)}</details></aside>` : ''}</section>`,
    );
    if (!test) drawOrbit();
    let cue = root.querySelector('[data-signal-action="' + action + '"]');
    if (action === 'deploy' && deployed.button) cue = deployed.button;
    guide(!busy && !deployed.working && cue);
  }
  async function read() {
    const [progress, link] = await Promise.all([readJourney(target), api('ground')]);
    if (disposed) return;
    journey = progress;
    station = link;
    if (flightInstance !== link.communication.since) {
      enabling = false;
      address = '';
      pendingEnable = false;
      clearTimeout(replyTimer);
      flightInstance = link.communication.since;
    }
    if (link.first_flight.downlink_receipt) {
      pendingEnable = false;
      clearTimeout(replyTimer);
    }
    draw();
  }
  async function act(a, id) {
    if (busy || a === 'address') return;
    busy = true;
    error = '';
    draw();
    try {
      const owner = journey.steps.send.ref?.app || journey.steps.app.ref?.app;
      const app = state.workspace.project.apps.find((x) => x.name === owner);
      const device = Object.values(app?.sensors || {})[0];
      if (a === 'add') {
        picker = true;
        chosen = null;
      }
      if (a === 'device') chosen = id;
      if (a === 'link') {
        await api('hardware/device', {
          action: 'link',
          app: owner,
          id: chosen,
          expected_hash: state.workspace.mission.source.hash,
        });
        picker = false;
        await refreshMission();
      }
      if (a === 'save-orbit') await saveSimulation();
      if (a === 'deploy') await advanceDeployment(deploymentControls(state).plan);
      if (a === 'connect') await api('ground/start', { target });
      if (a === 'enable') enabling = true;
      if (a === 'send') {
        await api('ground/send', {
          target,
          app: 'to_lab',
          command: 'ENABLE_OUTPUT',
          args: { dest_IP: address },
        });
        pendingEnable = true;
        replyTimer = setTimeout(() => {
          pendingEnable = false;
          error = 'No telemetry. Check dest_IP and send again.';
          draw();
        }, station.reply_timeout * 1000);
      }
      if (a === 'start') await startJob('simulate', { device }, false);
      if (a === 'cancel') await api('job/cancel', { id: latest('simulate', device).id });
      if (a === 'test') await startJob('simulate-preview', { device, scenario: selectedCase }, false);
      await read();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
      draw();
    }
  }
  const click = (e) => {
    const node = e.target.closest('button');
    if (!node) return;
    if (node.dataset.case) {
      selectedCase = node.dataset.case;
      draw();
    }
    if (node.dataset.signalAction) act(node.dataset.signalAction, node.dataset.id);
  };
  const edit = (e) => {
    if (e.target.matches('[data-signal-action=address]')) {
      address = e.target.value;
      draw();
    }
  };
  const fail = (e) => {
    if (!disposed) {
      error = e.message;
      if (loaded) draw();
      else paint(root, `<p role="alert">${esc(error)}</p>`);
    }
  };
  root.addEventListener('click', click);
  root.addEventListener('input', edit);
  const unsub = onUpdate(['journey', 'ground', 'jobs'], () => read().catch(fail));
  api('simulation')
    .then((s) => {
      if (!disposed) {
        if (!state.simulationDirty) state.simulation = s;
        loaded = true;
        return read();
      }
    })
    .catch(fail);
  return {
    update: draw,
    close() {
      disposed = true;
      unsub();
      clearTimeout(replyTimer);
      root.removeEventListener('click', click);
      root.removeEventListener('input', edit);
    },
  };
}
