import {escapeHtml as esc} from './dom.js';
import {icon} from './ui.js';

// Percent coordinates keep the pill and the node centres on the same path as the panel resizes.
export function drawPath(app, connected) {
  const points = app === 'to_lab' ? [['Ground',14,56],['ci_lab',45,26],['to_lab',82,56]] :
    [['Ground',14,56],['ci_lab',40,26],['Software Bus',64,26],[app,84,56],['to_lab',50,80]];
  const segments = points.map(([,x,y], i) => {
    const [,endX,endY] = points[(i+1) % points.length];
    return `<line x1="${x}" y1="${y}" x2="${endX}" y2="${endY}" vector-effect="non-scaling-stroke" class="${connected?'fs-dash':''}"/>`;
  });
  return `<section class="lesson-path fs-panel" aria-label="Round trip">
    <h2>Round trip</h2><div class="lesson-track"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${segments.join('')}</svg>
    ${points.map(([name,x,y])=>`<span class="lesson-node" data-point="${esc(name)}" style="left:${x}%;top:${y}%">${icon(name==='Ground'?'antenna':name==='Software Bus'?'workflow':'cube')}${esc(name)}</span>`).join('')}
    <div class="lesson-flights" data-motion-layer></div></div></section>`;
}

export function packetFlight(track, nodes, text, downlink = false) {
  const path = nodes.map(name => track?.querySelector('[data-point="'+CSS.escape(name)+'"]')).filter(Boolean);
  if (path.length < 2) return () => {};
  const pill = document.createElement('span');
  pill.className = 'lesson-packet' + (downlink ? ' answer' : ''); pill.textContent = text;
  track.querySelector('.lesson-flights').append(pill);
  const position = (a, b, fraction) => {
    for (const axis of ['left','top']) {
      const from = parseFloat(a.style[axis]), to = parseFloat(b.style[axis]);
      pill.style[axis] = (from + (to-from)*fraction) + '%';
    }
  };
  position(path[0],path[0],0);
  let step = 0;
  const clear = () => {
    clearInterval(timer);
    pill.remove();
  };
  const timer = setInterval(() => {
    if (!track.isConnected) {clear();return;}
    if (document.hidden) return;
    if (++step > (path.length-1)*7+2) {clear();return;}
    const segment = Math.min(path.length-2,Math.floor((step-1)/7));
    position(path[segment],path[segment+1],Math.min(1,(step-segment*7)/7));
    if (step % 7 === 0) {
      path[segment+1].animate([{borderColor:'var(--fs-accent)'},{borderColor:'var(--fs-line)'}], {
        duration:matchMedia('(prefers-reduced-motion:reduce)').matches ? 0 : 600
      });
    }
  },100);
  return clear;
}
