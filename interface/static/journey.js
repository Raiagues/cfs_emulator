// Completion is recorded by the Studio. Selection follows the screen the user opened.
import {workspaceRoute} from './workspace-route.js';

const stages = [
  ['target', 'Target', 'Choose where cFS will run'],
  ['boot', 'Boot', 'Start cFS for the first time'],
  ['event', 'Event', 'Send a first message and get an answer'],
  ['app', 'App', 'Create your own app'],
  ['command', 'Command', 'Teach your app a new command'],
  ['send', 'Send', 'Send your new command'],
  ['sensor', 'Sensor', 'Give your app sensor data'],
  ['test', 'Test', 'Check that everything works'],
  ['board', 'Board', 'Run it on the real board']
];

const railSteps = {architecture: 'app', bench: 'sensor', code: 'command', ground: 'event', simulation: 'sensor'};
const isWorkspace = location => /^\/studio\/?$/.test(location.pathname);

export function journeyNavigation(location, {target, steps, bootReadyTarget, since = 0, setup = !isWorkspace(location)} = {}) {
  const board = location.hash !== '#target' && new URLSearchParams(location.search).get('target') === 'physical' &&
    (!target || target === 'physical');
  const {id} = workspaceRoute(location.hash);
  const current = setup ? (board ? 'board' : 'target') : (railSteps[id] || id);
  const done = stages.map(([step]) => Boolean(steps?.[step]?.done && steps[step].observed_at > since));
  const index = stages.findIndex(([step]) => step === current);
  // Setup has its own verified Continue action. Boot must refer to this live process, even during replay.
  const canAdvance = current === 'boot' ? Boolean(target && bootReadyTarget === target) : done[index];
  const next = !setup && canAdvance ? stages[index + 1]?.[0] : null;
  return {current, next: next || null, done};
}

export function stepUrl(step, location, target, setup = !isWorkspace(location)) {
  if (step === 'target') return target ? '/?target=' + encodeURIComponent(target) + '#target' : '/';
  if (step === 'board') return '/?target=physical';
  // A fragment keeps the workspace, its target and its live subscriptions mounted.
  if (!setup) return '#' + step;
  const search = target ? '?target=' + encodeURIComponent(target) : '';
  return '/studio' + search + '#' + step;
}

const bar = globalThis.document?.querySelector('#flight-guide');
const cutoffKey = 'fs-journey-reset';
const tick = '<svg class="fs-tick" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
let since = 0, observations, controller;
try { since = Number(localStorage.getItem(cutoffKey)) || 0; } catch {}
export function journeyResetAt() { return since; }

function selectedTarget() {
  return document.querySelector('#targets [aria-pressed=true]')?.dataset.target || document.body.dataset.flightTarget;
}

function update() {
  const target = selectedTarget();
  const setup = Boolean(document.getElementById('targets'));
  const snapshot = target && observations?.target === target ? observations : null;
  const {current, next, done} = journeyNavigation(location, {
    target, steps: snapshot?.steps, since, setup, bootReadyTarget: document.body.dataset.bootReadyTarget
  });
  document.body.dataset.journeyStep = current;
  bar.querySelector('output').textContent = (snapshot ? done.filter(Boolean).length : '–') + '/9';

  stages.forEach(([id,label], i) => {
    const link = bar.querySelector('[data-flight="' + id + '"]');
    link.setAttribute('href', stepUrl(id, location, target, setup));
    if (link.classList.contains('done') !== done[i]) {
      link.classList.toggle('done', done[i]);
      link.querySelector('.flight-number').innerHTML = done[i] ? tick : String(i + 1);
    }
    link.setAttribute('aria-label', done[i] ? label + ', complete' : label);
    if (current === id) link.setAttribute('aria-current', 'step');
    else link.removeAttribute('aria-current');
    if (i) link.previousElementSibling.classList.toggle('complete', done[i - 1] && done[i]);
  });

  const nextLink = bar.querySelector('.flight-next');
  nextLink.hidden = !next;
  if (next) {
    nextLink.setAttribute('href', stepUrl(next, location, target, setup));
    nextLink.title = stages.find(([id]) => id === next)[2];
  } else {
    nextLink.removeAttribute('href');
    nextLink.removeAttribute('title');
  }
}

export async function refreshJourney() {
  if (!bar) return;
  const target = selectedTarget();
  controller?.abort();
  if (!target) return;
  const request = new AbortController();
  controller = request;
  try {
    const response = await fetch('/api/journey?target=' + encodeURIComponent(target), {
      cache: 'no-store', signal: request.signal
    });
    if (!response.ok) return;
    const snapshot = await response.json();
    if (request.signal.aborted || snapshot.target !== selectedTarget()) return;
    observations = snapshot;
    update();
  } catch { /* Retain the last observation while reconnecting. */ }
  finally { if (controller === request) controller = null; }
}

if (bar) {
  bar.innerHTML = '<span class="flight-count">First flight <output>–/9</output></span><div class="flight-stops">' +
    stages.map(([id,label,title], i) => (i ? '<span aria-hidden="true" class="flight-line"></span>' : '') +
      '<a data-flight="' + id + '" title="' + title + '"><span class="flight-number" aria-hidden="true">' +
      (i+1) + '</span><span class="flight-label">' + label + '</span></a>').join('') +
    '</div><div class="flight-guide-actions"><a class="flight-next" hidden>Next</a>' +
    '<button type="button" data-flight="reset" title="Start over" aria-label="Start over"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10a8 8 0 1 1 1 7M4 4v6h6"/></svg></button></div>';

  bar.querySelector('[data-flight="reset"]').addEventListener('click', () => {
    since = Date.now()/1000;
    try { localStorage.setItem(cutoffKey, String(since)); } catch {}
    update();
  });
  window.addEventListener('storage', e => {
    if (e.key === cutoffKey) { since = Number(e.newValue) || 0; update(); }
  });
  window.addEventListener('flight:updated', refreshJourney);
  window.addEventListener('hashchange', update);
  window.addEventListener('flight:navigate', update);
  let lastTarget;
  const targetChanged = () => {
    const target = selectedTarget();
    if (lastTarget === target) return;
    lastTarget = target;
    update();
    refreshJourney();
  };
  new MutationObserver(targetChanged).observe(document.body, {attributes: true, attributeFilter: ['data-flight-target']});
  new MutationObserver(() => {
    update();
    if (document.body.dataset.bootReadyTarget) refreshJourney();
  }).observe(document.body, {attributes: true, attributeFilter: ['data-boot-ready-target']});
  const targets = document.getElementById('targets');
  if (targets) {
    new MutationObserver(targetChanged).observe(targets, {attributes: true, subtree: true, attributeFilter: ['aria-pressed']});
  }
  update();
  targetChanged();
  setInterval(() => { if (!document.hidden && !controller) refreshJourney(); }, 3500);
}
