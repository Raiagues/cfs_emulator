import {guide} from './coach.js';
import {escapeHtml as esc, paint} from './dom.js';
import {icon} from './ui.js';
import {targetDrawing} from './target-drawing.js';

function modules(title, names, tone) {
  return `<section class="fs-panel mission-level ${tone}"><h2>${title}</h2><div>${names.map(name=>`<code>${esc(name)}</code>`).join('')}</div></section>`;
}
export function mountMissionLesson(root,{state,openApp}) {
  let wizard;
  function render() {
    const {workspace} = state, mine=workspace.apps.filter(a=>a.managed && !a.example), names=mine.map(a=>a.name);
    const nasa = workspace.apps.filter(a=>!a.managed && a.enabled);
    const board=state.target==='native'?'This computer':workspace.project.board;
    paint(root,`<section class="mission-lesson fs-in">
      <div class="mission-levels"><section class="fs-panel mission-level own"><h2>Your apps</h2><div>
        ${names.map(name=>`<code class="fs-pop">${esc(name)}</code>`).join('')}
        <button type="button" data-create-app class="primary">${icon('plus')}${names.length?'New app':'Create your first app'}</button></div></section>
      ${modules('Libraries',workspace.libraries.map(x=>x.name),'libraries')}
      ${modules('cFS apps',nasa.map(x=>x.name),'nasa')}
      ${modules('cFE core',workspace.core_modules.filter(m=>['es','evs','sb','tbl','time','fs'].includes(m.name)).map(m=>m.name.toUpperCase()),'core')}
      ${modules('Platform',['OSAL','PSP',state.target==='native'?'Linux':'Raspberry Pi OS'],'platform')}
      <details class="terminal-twin"><summary>In the terminal</summary><pre>./start --no-ui app new &lt;name&gt;</pre></details></div>
      <aside class="mission-side"><section class="fs-panel mission-target"><h2>Hardware</h2>${targetDrawing(state.target)}<strong>${esc(board)}</strong></section>
      <section class="fs-panel mission-route" data-empty="${!mine.length}" title="${mine.length?'Software Bus':'Shows the whole mission once you have an app'}"><h2>Mission map</h2>
      ${[...names,'ci_lab','Software Bus','to_lab'].map(n=>`<code>${esc(n)}</code>`).join('')}</section></aside></section>`);
    if(!wizard?.open)guide(names.length ? null : root.querySelector('[data-create-app]'));
  }
  const click=event=>{
    if(event.target.closest('[data-create-app]'))wizard=openApp(()=>{wizard=null;render();});
  };
  root.addEventListener('click',click);render();
  return {update:render,close(){root.removeEventListener('click',click);if(wizard?.open)wizard.close();}};
}
