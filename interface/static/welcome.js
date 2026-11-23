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
  const target = { native: 'native', emu: 'qemu', board: 'physical' }[lesson.state.place] || 'native';
  pending = true;
  failure = '';
  draw();
  try {
    const current = await api('infrastructure');
    lesson.setState({remoteUnlocked:current.remote_unlocked === true});
    if (target !== 'native' && !current.remote_unlocked) {
      lesson.setState({ch:9, lockedTarget:lesson.state.place, place:null, placed:false});
      failure = 'Complete first contact on Native to unlock Emulator and Board.';
      return;
    }
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
    draw();
  }
}

const render = mountScene(template, root, (fn, event) => {
  if (!fn || pending) return;
  const card = event.target.closest('[data-welcome-target]');
  if (card) delete card.dataset.dismissed;
  const result = fn(event);
  draw();
  if (result instanceof Promise)
    result.catch((error) => {
      failure = error.message;
      draw();
    });
});

function draw() {
  const targetLabel = {native:'Native', emu:'Emulator', board:'Board'}[lesson.state.place] || 'Native';
  render({ ...lesson.values(), project, failure, startLabel:'Start · ' + targetLabel, skip: () => finishWelcome(null), start });
  const next = root.querySelector('[data-act="next"],[data-act="start"]');
  if (next?.classList.contains('ready')) {
    for (const item of root.querySelectorAll('section .fs-coach')) item.classList.remove('fs-coach');
  }
  if (next) next.disabled = pending;
}

root.addEventListener('keydown', event => {
  const card = event.target.closest('[data-welcome-target]');
  if (event.key === 'Escape' && card) {
    lesson.setState({lockedTarget:null});
    card.dataset.dismissed = 'true';
    draw();
  }
});
root.addEventListener('pointerover', event => {
  const card = event.target.closest('[data-welcome-target]');
  if (card && !card.contains(event.relatedTarget)) delete card.dataset.dismissed;
});
root.addEventListener('focusout', event => {
  const card = event.target.closest('[data-welcome-target]');
  if (card && !card.contains(event.relatedTarget)) {
    lesson.setState({lockedTarget:null});
    delete card.dataset.dismissed;
    draw();
  }
});
draw();
registerBrand(root);
function sizeFrame() {
  root.style.setProperty('--welcome-scale', Math.min(1, innerWidth / 1244, innerHeight / 700));
}
sizeFrame();
window.addEventListener('resize', sizeFrame);
api('infrastructure')
  .then((data) => { project = data.project;lesson.setState({remoteUnlocked:data.remote_unlocked === true}); })
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
