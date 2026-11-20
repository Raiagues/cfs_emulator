import { api, checkFrames } from './api.js';
import { finishWelcome, registerBrand } from './router.js';
import { mountScene } from './scene-template.js';
import { Welcome } from './welcome-scenes.js';

const lesson = new Welcome();
const root = document.querySelector('#welcome');
const template = document.querySelector('#welcome-scenes');
let project = '';
let failure = '';
let pending = false;

async function start() {
  if (pending) return;
  const target = { native: 'native', emu: 'qemu', board: 'physical' }[lesson.state.place];
  pending = true;
  failure = '';
  draw();
  try {
    if (target) {
      await api('hardware/target', { target });
      if (target !== 'physical') {
        for await (const report of checkFrames(target)) {
          if (report.status === 'complete') break;
        }
      }
    }
    finishWelcome(target);
  } finally {
    pending = false;
  }
}

const render = mountScene(template, root, (fn, event) => {
  if (!fn || pending) return;
  const result = fn(event);
  draw();
  if (result instanceof Promise)
    result.catch((error) => {
      failure = error.message;
      draw();
    });
});

function draw() {
  render({ ...lesson.values(), project, failure, skip: () => finishWelcome(null), start });
  const next = root.querySelector('[data-act="next"],[data-act="start"]');
  if (next?.classList.contains('ready')) {
    for (const item of root.querySelectorAll('section .fs-coach')) item.classList.remove('fs-coach');
  }
  if (next) next.disabled = pending;
}

draw();
registerBrand(root);
function sizeFrame() {
  root.style.setProperty('--welcome-scale', Math.min(1, innerWidth / 1244, innerHeight / 700));
}
sizeFrame();
window.addEventListener('resize', sizeFrame);
api('infrastructure')
  .then((data) => { project = data.project; })
  .catch((error) => { failure = error.message; })
  .finally(draw);
let clock;
function syncClock() {
  clearInterval(clock);
  if (!document.hidden)
    clock = setInterval(() => {
      lesson.tick();
      draw();
    }, 100);
}
document.addEventListener('visibilitychange', syncClock);
window.addEventListener('pagehide', () => clearInterval(clock));
window.addEventListener('pageshow', syncClock);
syncClock();
