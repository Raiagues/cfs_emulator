import {refreshCoach} from './coach.js';
import {onUpdate} from './updates.js';
import {api, readJourney} from './api.js';
import {navigate, pageStep, stepUrl} from './router.js';

const labels = {
  target:'Target', boot:'Boot', event:'Event', app:'App', command:'Command', send:'Send', sensor:'Sensor', test:'Test', board:'Board'
};
const tick = '<svg class="fs-tick fs-draw" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
const bar = globalThis.document?.getElementById('flight-guide');
let observations, requestId = 0, bootState = null;

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

export function journeyLine(previous, status, failed=false) {
  return {complete:Boolean(previous.done && status.reachable && !failed),failed};
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
    stop.querySelector('.flight-number').classList.toggle('fs-ping2', current === id);
    if (current === id) stop.setAttribute('aria-current', 'step');
    else stop.removeAttribute('aria-current');
    const attempt=snapshot.boot_attempt;
    const liveFailure=bootState?.target===snapshot.target&&(!attempt||bootState.id===attempt.id)&&bootState.failed;
    const failed = id === 'boot' && !status.done && (['failed','cancelled'].includes(attempt?.status)||liveFailure);
    stop.classList.toggle('failed', failed);
    if (failed) stop.setAttribute('aria-label', label + ', failed');
    if (index) {
      const line = stop.previousElementSibling;
      const state=journeyLine(snapshot.steps[Object.keys(labels)[index-1]],status,Boolean(failed));
      line.classList.toggle('complete', state.complete);
      line.classList.toggle('failed', state.failed);
    }
  }
  const forward = bar.querySelector('.flight-next');
  forward.hidden = !next;
  forward.classList.toggle('fs-coach', Boolean(next));
  if (next) {
    forward.href = next;
    forward.textContent = 'Next · ' + labels[snapshot.current];
  }
  else forward.removeAttribute('href');
  bar.querySelector('.flight-complete').hidden = !snapshot.optional_board && current !== null;
  const resume = bar.querySelector('[data-tutorial="resume"]');
  resume.href = snapshot.next_route || stepUrl('target');
  resume.textContent = current ? 'Continue · ' + labels[current] : 'Choose target';
  const targetName = {native:'Native', qemu:'Emulator', physical:'Board'}[snapshot.target];
  bar.querySelector('.flight-tutorial-title').textContent = 'First flight' + (targetName ? ' · ' + targetName : '');
  bar.querySelector('[data-flight="reset"]').disabled = !snapshot.target;

  if (next) refreshCoach();
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
    '<a class="flight-next" hidden>Next</a><details class="flight-tutorial"><summary>Tutorial' +
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>' +
    '<div class="flight-tutorial-menu"><strong class="flight-tutorial-title">First flight</strong>' +
    '<a data-tutorial="resume" href="/#target">Continue tutorial</a>' +
    '<a href="/welcome">Introduction · cFS basics</a><a href="/#target">Choose target</a>' +
    '<button type="button" data-flight="reset" title="Start over" disabled>Restart first flight</button>' +
    '<small>Restart resets the tutorial for this target. Your code and builds stay in place.</small></div></details></div>';
  const tutorial = bar.querySelector('.flight-tutorial');
  tutorial.addEventListener('keydown', event => {
    if (event.key === 'Escape') {tutorial.open = false;tutorial.querySelector('summary').focus();}
  });
  document.addEventListener('click', event => {if (!tutorial.contains(event.target)) tutorial.open = false;});
  tutorial.addEventListener('click', event => {if (event.target.closest('a')) tutorial.open = false;});
  bar.querySelector('[data-flight="reset"]').onclick = async event => {
    const button = event.currentTarget;
    if (button.disabled) return;
    button.disabled = true;
    try {
      await api('journey/reset', {target:observations?.target || context()});
      const destination = stepUrl('target');
      if (new URL(destination, location.href).href === location.href) location.reload();
      else navigate(destination);
    } catch (error) {button.disabled = false;failure(error);}
  };
  const refresh = () => refreshJourney().catch(failure);
  window.addEventListener('flight:boot-state', event => {bootState=event.detail;if(observations)render(observations);});
  window.addEventListener('flight:updated', refresh);
  window.addEventListener('flight:navigate', () => {if (observations) render(observations);});
  new MutationObserver(refresh).observe(document.body, {attributes:true, attributeFilter:['data-flight-target']});
  refresh();
  onUpdate(['journey', 'target'], refresh);
}
