// Only the replay cutoff is local. Milestones are backed by observations from the Studio.
const stages = [
  ['target', 'Target', 'Choose where cFS will run', 'setup'],
  ['boot', 'Boot', 'Start cFS for the first time', 'boot'],
  ['event', 'Event', 'Send a first message and get an answer', 'ground'],
  ['app', 'App', 'Create your own app', 'architecture'],
  ['command', 'Command', 'Teach your app a new command', 'code'],
  ['send', 'Send', 'Send your new command', 'ground'],
  ['sensor', 'Sensor', 'Give your app sensor data', 'simulation'],
  ['test', 'Test', 'Check that everything works', 'simulation'],
  ['board', 'Board', 'Run it on the real board', 'board']
];

export function stepUrl(step) {
  if (step === 'target') return '/';
  if (step === 'board') return '/?target=physical';
  return '/studio#' + step;
}

const bar = document.querySelector('#flight-guide');
const cutoffKey = 'fs-journey-reset';
const tick = '<svg class="fs-tick" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
const arrow = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8h11M8 3l5 5-5 5"/></svg>';
let since = 0, observations, requestSequence = 0;
try { since = Number(localStorage.getItem(cutoffKey)) || 0; } catch {}
export function journeyResetAt() { return since; }

function currentArea() {
  if (document.body.classList.contains('code-only')) return 'code';
  if (document.body.dataset.view) return document.body.dataset.view;
  return document.querySelector('#targets [aria-pressed=true]')?.dataset.target === 'physical' ? 'board' : 'setup';
}

function update() {
  if (!bar) return;
  const done = stages.map(([id]) => {
    const fact = observations?.steps[id];
    return !!fact?.done && fact.observed_at > since;
  });
  const next = done.indexOf(false);
  document.body.dataset.journeyStep = stages[next]?.[0] || 'complete';
  bar.querySelector('output').textContent = done.filter(Boolean).length + '/9';

  stages.forEach(([id,label], i) => {
    const link = bar.querySelector('[data-flight="' + id + '"]');
    if (link.classList.contains('done') !== done[i]) {
      link.classList.toggle('done', done[i]);
      link.querySelector('.flight-number').innerHTML = done[i] ? tick : String(i+1);
    }
    link.setAttribute('aria-label', done[i] ? label + ', complete' : label);
    if (next === i) link.setAttribute('aria-current','step');
    else link.removeAttribute('aria-current');
    if (i) link.previousElementSibling.classList.toggle('complete', done[i-1] && done[i]);
  });

  const nextLink = bar.querySelector('.flight-next');
  nextLink.hidden = next < 0 || stages[next][3] === currentArea();
  if (next >= 0) {
    const [id,label,title] = stages[next];
    nextLink.href = stepUrl(id);
    nextLink.title = title;
    nextLink.querySelector('b').textContent = label;
  }
}

export async function refreshJourney() {
  if (!bar) return;
  const number = ++requestSequence;
  const selector = '#targets [aria-pressed=true], .target-switch [aria-pressed=true]';
  const target = document.querySelector(selector)?.dataset.target;
  const query = target ? '?target=' + encodeURIComponent(target) : '';
  try {
    const response = await fetch('/api/journey' + query, {cache:'no-store'});
    if (!response.ok) return;
    const snapshot = await response.json();
    if (number !== requestSequence) return;
    observations = snapshot;
    update();
  } catch { /* Retain the last observation while reconnecting. */ }
}

if (bar) {
  bar.setAttribute('aria-label','First flight');
  bar.innerHTML = '<span class="flight-count">First flight <output>0/9</output></span><div class="flight-stops">' +
    stages.map(([id,label,title], i) => (i ? '<span aria-hidden="true" class="flight-line"></span>' : '') +
      '<a href="' + stepUrl(id) + '" data-flight="' + id + '" title="' + title + '"><span class="flight-number" aria-hidden="true">' +
      (i+1) + '</span><span class="flight-label">' + label + '</span></a>').join('') +
    '</div><div class="flight-guide-actions"><a class="flight-next" hidden>Next <b></b>' + arrow + '</a>' +
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
  new MutationObserver(update).observe(document.body, {attributes:true, attributeFilter:['data-view','class']});
  update();
  refreshJourney();
  setInterval(() => { if (!document.hidden) refreshJourney(); }, 3500);
}
