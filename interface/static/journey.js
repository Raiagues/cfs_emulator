import {api, readJourney} from './api.js';
import {navigate, pageStep, stepUrl} from './router.js';

const labels = {
  target:'Target', boot:'Boot', event:'Event', app:'App', command:'Command', send:'Send', sensor:'Sensor', test:'Test', board:'Board'
};
const tick = '<svg class="fs-tick" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
const bar = globalThis.document?.getElementById('flight-guide');
let observations, requestId = 0;

function context() {
  return document.body.dataset.flightTarget || null;
}

export function journeyNavigation(page, snapshot) {
  const open = pageStep(page);
  const completed = Object.values(snapshot.steps).filter(s => s.done).length;
  const next = snapshot.steps[open]?.done && open !== 'target' && open !== snapshot.current && !snapshot.optional_board
    ? snapshot.next_route : null;
  return {current:snapshot.current, completed, next};
}

function render(snapshot) {
  const {current, completed, next} = journeyNavigation(location, snapshot);
  document.body.dataset.journeyStep = current || '';
  bar.querySelector('output').textContent = completed + '/9';
  for (const [index, [id, label]] of Object.entries(labels).entries()) {
    const status = snapshot.steps[id];
    let stop = bar.querySelector('[data-flight="' + id + '"]');
    const tag = status.reachable ? 'a' : 'span';
    if (stop.localName !== tag) {
      const replacement = document.createElement(tag);
      replacement.dataset.flight = id;
      replacement.append(...stop.childNodes);
      stop.replaceWith(replacement);
      stop = replacement;
    }
    if (status.reachable) stop.setAttribute('href', status.route);
    if (stop.classList.contains('done') !== status.done) {
      stop.classList.toggle('done', status.done);
      stop.querySelector('.flight-number').innerHTML = status.done ? tick : String(index + 1);
    }
    stop.setAttribute('aria-label', status.done ? label + ', complete' : label);
    if (current === id) stop.setAttribute('aria-current', 'step');
    else stop.removeAttribute('aria-current');
    if (index) stop.previousElementSibling.classList.toggle('complete', status.done);
  }
  const forward = bar.querySelector('.flight-next');
  forward.hidden = !next;
  forward.classList.toggle('fs-coach', Boolean(next));
  if (next) forward.href = next;
  else forward.removeAttribute('href');
  bar.querySelector('.flight-complete').hidden = !snapshot.optional_board && current !== null;
}

export async function refreshJourney() {
  if (!bar) return;
  const id = ++requestId;
  const snapshot = await readJourney(context(), pageStep() === 'board');
  if (id !== requestId) return;
  observations = snapshot;
  render(snapshot);
  return snapshot;
}

function failure(error) {
  bar.querySelector('output').textContent = error.message;
}

if (bar) {
  bar.innerHTML = '<span class="flight-count">First flight <output aria-live="polite">…</output></span>' +
    '<div class="flight-stops">' + Object.entries(labels).map(([id,label], i) =>
      (i ? '<span class="flight-line" aria-hidden="true"></span>' : '') + '<span data-flight="' + id + '">' +
      '<span class="flight-number" aria-hidden="true">' + (i+1) + '</span><span class="flight-label">' + label + '</span></span>'
    ).join('') + '</div><div class="flight-guide-actions"><span class="flight-complete" hidden>First flight done</span>' +
    '<a class="flight-next" hidden>Next</a><button type="button" data-flight="reset" title="Start over" aria-label="Start over">' +
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10a8 8 0 1 1 1 7M4 4v6h6"/></svg></button></div>';
  bar.querySelector('[data-flight="reset"]').onclick = async () => {
    try {
      await api('journey/reset', {target:observations?.target || context()});
      navigate(stepUrl('target'));
    } catch (error) {failure(error);}
  };
  const refresh = () => refreshJourney().catch(failure);
  window.addEventListener('flight:updated', refresh);
  window.addEventListener('flight:navigate', () => {if (observations) render(observations);});
  new MutationObserver(refresh).observe(document.body, {attributes:true, attributeFilter:['data-flight-target']});
  refresh();
  setInterval(() => {if (!document.hidden) refresh();}, 3500);
}
