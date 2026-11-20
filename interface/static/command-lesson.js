import { api } from './api.js';
import { guide } from './coach.js';
import { escapeHtml as esc, paint } from './dom.js';
import { highlight, icon } from './ui.js';
import { refreshJourney } from './journey.js';
import { stepUrl } from './router.js';

const titles = [
  'Function code',
  'Packet layout',
  'Handler declaration',
  'Dispatch',
  'Event IDs',
  'Handler',
  'Test',
];
function excerpt(lesson) {
  const lines = lesson.content.trimEnd().split('\n');
  const visible = new Set();
  for (const [a, b] of lesson.ranges) {
    for (let i = Math.max(1, a - 3); i <= Math.min(b + 3, lines.length); ++i) visible.add(i);
  }
  const numbers = visible.size ? [...visible].sort((a, b) => a - b) : lines.map((_, i) => i + 1);
  return numbers
    .map((n, i) => {
      const current = lesson.ranges.some(([a, b]) => n >= a && n <= b);
      const text = lines[n - 1];
      const body =
        lesson.stage === 5 && text.includes(lesson.stub)
          ? `<input data-handler-line spellcheck="false" aria-label="Handler line" placeholder="${esc(lesson.ghost)}">`
          : highlight(text, lesson.path).trimEnd();
      return (
        (i && numbers[i - 1] !== n - 1 ? '<div class="source-gap">…</div>' : '') +
        `<div class="command-line" data-change="${current}"><small>${n}</small><code>${body}</code></div>`
      );
    })
    .join('');
}
function inspector(lesson, rate) {
  const descriptions = [
    lesson.symbol + ' = ' + lesson.code,
    'uint16 Rate_Hz · 1…50 Hz',
    lesson.app.toUpperCase() + '_SetRateCmd',
    lesson.symbol + ' → ' + lesson.app.toUpperCase() + '_SetRateCmd',
    'Rate set to %u Hz · Rate %u out of range',
    'Store the requested rate in the app data.',
  ];
  if (lesson.stage < 6) return `<p>${esc(descriptions[lesson.stage])}</p>`;
  const valid = rate >= 1 && rate <= 50;
  return `<label>Rate_Hz<input type="range" min="0" max="100" value="${rate}" data-rate aria-label="Rate_Hz value"></label>
    <output data-example-rate>${rate} Hz</output><p>${valid ? 'Rate set to ' + rate + ' Hz' : 'Rate ' + rate + ' out of range'}</p>
    ${valid ? `<small>One read every ${Math.round(1000 / rate)} ms</small>` : ''}`;
}

export function mountCommandLesson(root, { state, startJob }) {
  let lesson,
    busy = false,
    disposed = false,
    error = '',
    draft = '',
    rate = 10,
    lastStage;
  const target = state.target;
  const query = 'command/lesson?' + new URLSearchParams({ target });
  function job() {
    return state.jobs.find(
      (j) => j.target === target && ['build', 'stop'].includes(j.action) && j.status === 'running',
    );
  }
  function draw() {
    if (disposed) return;
    if (!lesson) {
      if (error) paint(root, `<p role="alert">${esc(error)}</p>`);
      return;
    }
    if (lesson.needs_app) {
      paint(root, `<section class="fs-panel"><a href="${esc(stepUrl('app',location,target))}">Create your first app</a></section>`);
      guide(root.querySelector('a'));
      return;
    }
    const { stage, steps, path, app } = lesson;
    const name = path.split('/').at(-1);
    const running = state.hardware?.execution?.running_targets.includes(target);
    const active = job(),
      action =
        stage < 5 ? 'next' : stage === 5 ? 'accept' : target === 'native' && running ? 'stop' : 'build';
    const label = {
      next: 'Next',
      accept: draft ? 'Save line' : 'Accept',
      stop: 'Stop cFS',
      build: 'Build cFS',
    }[action];
    const stepsHtml = steps
      .map(
        (s, i) => `<li data-done="${i < stage}" ${i === stage ? 'aria-current="step"' : ''}>
      <i>${i < stage ? '✓' : i + 1}</i>${s}</li>`,
      )
      .join('');
    const files = lesson.files
      .map(
        (f) =>
          `<li ${f === path ? 'aria-current="page"' : ''} title="${esc(f)}">${esc(f.split('/').at(-1))}</li>`,
      )
      .join('');
    paint(
      root,
      `<section class="command-lesson fs-in"><aside class="command-tree"><h2>Files</h2>
      <strong>${esc(app)}</strong><ul>${files}</ul></aside><main class="command-editor">
      <ol class="command-stops">${stepsHtml}</ol><section class="fs-panel command-source"><h2>${icon('code')}${esc(name)}</h2>
      <small>${esc(path)}</small><div class="command-lines" data-scene="source-${stage}">${excerpt(lesson)}</div></section></main>
      <aside class="fs-panel command-insight"><small>${stage < 5 ? 'written for you' : stage === 5 ? 'your turn' : 'run it'}</small>
      <h2>${titles[stage]}</h2>${inspector(lesson, rate)}${error ? `<p role="alert">${esc(error)}</p>` : ''}
      <button type="button" data-command-action="${action}" class="primary" ${busy || active ? 'disabled' : ''}>${active ? (active.action === 'build' ? 'Building cFS…' : 'Stopping cFS…') : busy ? 'Checking…' : label}</button>
      <details class="terminal-twin"><summary>In the terminal</summary><pre>${esc(
        stage < 5
          ? './start --no-ui project command-step ' + app + ' --confirm ' + steps[stage]
          : stage === 5
            ? './start --no-ui project command-step ' + app + " --line '" + lesson.ghost + "'"
            : './start --no-ui ' + action + ' --target ' + target,
      )}</pre></details></aside></section>`,
    );
    const editor = root.querySelector('[data-handler-line]');
    if (editor && editor.value !== draft) editor.value = draft;
    guide(!active && !busy && root.querySelector('[data-command-action]'));
    if (lastStage !== stage && editor) editor.focus({ preventScroll: true });
    lastStage = stage;
  }
  async function read() {
    lesson = await api(query);
    draw();
  }
  async function act(action) {
    if (busy || job()) return;
    busy = true;
    error = '';
    draw();
    try {
      if (action === 'next') {
        lesson = await api('mutate', {
          action: 'command-step',
          expected_hash: lesson.expected_hash,
          payload: { app: lesson.app, target, stage: lesson.stage, source_hash: lesson.source_hash },
        });
      } else if (action === 'accept') {
        const content = lesson.content.replace(lesson.stub, () => draft || lesson.ghost);
        await api('file', {
          command_lesson: true,
          path: lesson.path,
          app: lesson.app,
          target,
          content,
          expected_hash: lesson.file_hash,
        });
        draft = '';
        await read();
      } else await startJob(action, {}, false);
      await refreshJourney();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
      draw();
    }
  }
  const click = (e) => {
    const b = e.target.closest('[data-command-action]');
    if (b) act(b.dataset.commandAction);
  };
  const input = (e) => {
    if (e.target.matches('[data-handler-line]')) draft = e.target.value;
    else if (e.target.matches('[data-rate]')) rate = Number(e.target.value);
    else return;
    draw();
  };
  const key = (e) => {
    if (e.target.matches('[data-handler-line]') && ['Tab', 'Enter'].includes(e.key) && !e.shiftKey) {
      e.preventDefault();
      act('accept');
    }
  };
  root.addEventListener('click', click);
  root.addEventListener('input', input);
  root.addEventListener('keydown', key);
  read().catch((e) => {
    error = e.message;
    draw();
  });
  return {
    update: draw,
    close() {
      disposed = true;
      root.removeEventListener('click', click);
      root.removeEventListener('input', input);
      root.removeEventListener('keydown', key);
    },
  };
}
