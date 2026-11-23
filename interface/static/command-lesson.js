import { api } from './api.js';
import { guide } from './coach.js';
import { escapeHtml as esc, paint } from './dom.js';
import { highlight, icon } from './ui.js';
import { refreshJourney } from './journey.js';
import { stepUrl } from './router.js';
import { renderActivityProgress } from './activity-progress.js';
import { sourceCommandTestEvidence } from './source-guide.js';
import { onUpdate } from './updates.js';

function excerpt(source, editable) {
  const lines = source.content.trimEnd().split('\n'), ranges = source.ranges || [];
  const visible = new Set();
  for (const [a, b] of ranges) {
    for (let i = Math.max(1, a - 3); i <= Math.min(b + 3, lines.length); ++i) visible.add(i);
  }
  const numbers = visible.size ? [...visible].sort((a, b) => a - b) : lines.map((_, i) => i + 1);
  return numbers.map((n, i) => {
    const current = ranges.some(([a, b]) => n >= a && n <= b), text = lines[n - 1];
    const body = editable && text.includes(source.stub)
      ? `<input data-handler-line spellcheck="false" aria-label="Handler line" placeholder="${esc(source.ghost)}">`
      : highlight(text, source.path).trimEnd();
    return (i && numbers[i - 1] !== n - 1 ? '<div class="source-gap">…</div>' : '') +
      `<div class="command-line" data-change="${current}"><small>${n}</small><code>${body}</code></div>`;
  }).join('');
}

export function mountCommandLesson(root, { state, startJob }) {
  let lesson, fileView = null, busy = false, disposed = false, error = '', draft = '', lastScene;
  const target = state.target;
  let proof = null, proofRequest = null;
  function testComplete() {
    if (!proof || lesson?.stage !== 6) return false;
    const app = proof.workspace.apps?.find(app => app.name === lesson.app);
    const route = app?.behavior?.details?.commands?.find(route => route.handlers?.some(handler => handler.cc?.symbol === lesson.symbol));
    return sourceCommandTestEvidence({...proof, target, files:state.files}, lesson.app, lesson.symbol, route?.mid?.value).test;
  }
  async function refreshProof() {
    if (disposed || lesson?.stage !== 6) return;
    if (proofRequest) return proofRequest;
    proofRequest = Promise.all([api('workspace'), api('ground')]).then(([workspace, ground]) => {
      if (!disposed) proof = {workspace, ground};
    }).catch(() => {proof = null;}).finally(() => {proofRequest = null; draw();});
    return proofRequest;
  }
  const view = () => lesson?.view ?? lesson?.stage;
  function job() {
    return state.jobs?.find(j => j.target === target && ['build', 'stop'].includes(j.action) && j.status === 'running');
  }
  function revealStep() {
    const button = root.querySelector('[data-command-view][aria-current=step]');
    if (!button) return;
    const nav = button.parentElement, item = button.getBoundingClientRect(), frame = nav.getBoundingClientRect();
    if (item.left < frame.left) nav.scrollLeft += item.left - frame.left - 4;
    else if (item.right > frame.right) nav.scrollLeft += item.right - frame.right + 4;
  }
  function draw() {
    if (disposed) return;
    if (!lesson) {
      if (error) paint(root, `<p role="alert">${esc(error)}</p>`);
      return;
    }
    if (lesson.needs_app) {
      paint(root, `<section class="fs-panel"><a href="${esc(stepUrl('app', location, target))}">Create your first app</a></section>`);
      guide(root.querySelector('a'));
      return;
    }
    const { stage, steps, app } = lesson, selected = view(), source = fileView || lesson;
    const { path } = source, name = path.split('/').at(-1), directory = path.slice(0, -name.length);
    const running = state.hardware?.execution?.running_targets?.includes(target), active = job();
    const action = fileView ? 'return' : selected < stage ? 'view-next' :
      stage < 5 ? 'next' : stage === 5 ? 'accept' : target === 'native' && running ? 'stop' : 'build';
    const label = {
      return: 'Back to ' + steps[selected],
      'view-next': 'Next · ' + steps[selected + 1],
      next: 'Next · ' + steps[stage + 1],
      accept: draft ? 'Save line' : 'Accept line', stop: 'Stop cFS', build: 'Build cFS',
    }[action];
    const next = `<button type="button" data-command-action="${action}" class="activity-next" ${busy || active ? 'disabled' : ''}>${active ? (active.action === 'build' ? 'Building cFS…' : 'Stopping cFS…') : busy ? 'Checking…' : esc(label)}</button>`;
    const progress = renderActivityProgress({
      steps: steps.map((label, i) => ({label, done: i === 6 ? testComplete() : lesson.completed?.[i] ?? i < stage,
        disabled: busy || i > stage, title: i > stage ? 'Complete ' + steps[stage] + ' first' : label})),
      selected, attribute:'data-command-view', next,
    });
    const files = lesson.files.map(f => `<li><button type="button" data-command-file="${esc(f)}" ${f === path ? 'aria-current="page"' : ''} ${busy ? 'disabled' : ''} title="${esc(f)}">${icon('file')}<span>${esc(f.split('/').at(-1))}</span></button></li>`).join('');
    const editable = !fileView && selected === stage && stage === 5, scene = path + ':' + selected + ':' + !!fileView;
    paint(root, `<section class="command-lesson"><aside class="command-tree"><h2>Files</h2>
      <div class="source-folder">${icon('folder')}<span>${esc(app)}</span></div><ul>${files}</ul></aside>
      <main class="command-editor">${progress}${error ? `<p class="activity-error" role="alert">${esc(error)}</p>` : ''}
      <section class="command-source"><header>${icon('file')}<strong>${esc(name)}</strong><small>${esc(directory)}</small></header>
      <div class="command-lines" data-scene="${esc(scene)}">${excerpt(source, editable)}</div></section></main></section>`);
    const editor = root.querySelector('[data-handler-line]');
    if (editor && editor.value !== draft) editor.value = draft;
    guide(!active && !busy && root.querySelector('[data-command-action]'));
    if (lastScene !== scene) {
      revealStep();
      if (editor) editor.focus({preventScroll:true});
    }
    lastScene = scene;
  }
  async function read(selected) {
    const params = new URLSearchParams({target});
    if (lesson?.app) params.set('app', lesson.app);
    if (selected !== undefined) params.set('view', selected);
    const result = await api('command/lesson?' + params);
    if (disposed) return;
    lesson = result;
    fileView = null;
    draw();
    await refreshProof();
  }
  async function navigate(selected) {
    if (busy || selected < 0 || selected > lesson.stage) return;
    busy = true; error = ''; draw();
    try {await read(selected);} catch (e) {error = e.message;}
    finally {busy = false; draw();}
  }
  async function openFile(path) {
    if (busy || !lesson.files.includes(path)) return;
    if (path === lesson.path) {fileView = null; draw(); return;}
    busy = true; error = ''; draw();
    try {
      const file = await api('file?' + new URLSearchParams({path}));
      if (!disposed) fileView = {...file, path, ranges:[]};
    } catch (e) {error = e.message;}
    finally {busy = false; draw();}
  }
  async function act(action) {
    if (busy || job()) return;
    if (action === 'return') {fileView = null; draw(); return;}
    if (action === 'view-next') {await navigate(view() + 1); return;}
    if (fileView || view() !== lesson.stage) return;
    busy = true; error = ''; draw();
    try {
      if (action === 'next') {
        lesson = await api('mutate', {
          action:'command-step', expected_hash:lesson.expected_hash,
          payload:{app:lesson.app, target, stage:lesson.stage, source_hash:lesson.source_hash},
        });
      } else if (action === 'accept') {
        const content = lesson.content.replace(lesson.stub, () => draft || lesson.ghost);
        await api('file', {command_lesson:true, path:lesson.path, app:lesson.app, target, content, expected_hash:lesson.file_hash});
        draft = '';
        await read();
      } else if (['stop', 'build'].includes(action)) await startJob(action, {}, false);
      await refreshJourney();
    } catch (e) {error = e.message;}
    finally {busy = false; draw();}
  }
  const click = event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.hasAttribute('data-command-view')) navigate(Number(button.dataset.commandView));
    else if (button.hasAttribute('data-command-file')) openFile(button.dataset.commandFile);
    else if (button.dataset.commandAction) act(button.dataset.commandAction);
  };
  const input = event => {
    if (event.target.matches('[data-handler-line]')) {draft = event.target.value; draw();}
  };
  const key = event => {
    if (event.target.matches('[data-handler-line]') && ['Tab', 'Enter'].includes(event.key) && !event.shiftKey) {
      event.preventDefault(); act('accept');
    }
  };
  const stopProofUpdates = onUpdate(['ground', 'workspace', 'jobs'], refreshProof);
  const resize = new ResizeObserver(revealStep);
  resize.observe(root);
  root.addEventListener('click', click);
  root.addEventListener('input', input);
  root.addEventListener('keydown', key);
  read().catch(e => {error = e.message; draw();});
  return {update:draw, close() {
    disposed = true;
    resize.disconnect();
    stopProofUpdates();
    root.removeEventListener('click', click); root.removeEventListener('input', input); root.removeEventListener('keydown', key);
  }};
}
