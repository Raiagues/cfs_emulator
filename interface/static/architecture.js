import {icon} from './ui.js';
import {renderMissionDiagram, mountMissionMap} from './mission-diagram.js';
import {renderAppDiagram,layoutAppDiagram} from './app-diagram.js';

function source(ref,label,esc){
 return `<button class="app-map-source" data-arch-source="${esc(ref.path)}" data-line="${ref.line||1}" data-end-line="${ref.end_line||ref.line||1}" data-symbol="${esc(ref.symbol||label)}">${icon('code')}${esc(label)}</button>`;
}

function libraryDiagram(state,lib,esc){
 const member=new Set(state.workspace.mission.included||[]);
 const users=lib.used_by.filter(user=>user.kind==='library'||member.has(user.name));
 return `<div class="library-map"><aside><h3>Used by</h3>${users.map(user=>`<button class="app-map-peer" ${user.kind==='app'?'data-arch-app':'data-arch-library'}="${esc(user.name)}"><span>${icon(user.kind==='app'?'code':'files')}<strong>${esc(user.name)}</strong>${icon('arrow-up-right')}</span><small>${user.calls.length?'API calls':'Build dependency'}</small></button>`).join('')||'<p>No mission callers</p>'}</aside><section class="app-map-container change-${lib.change}"><header>${icon('files')}<strong>${esc(lib.name)}</strong></header><div class="app-map-sections"><section class="library-map-api"><h3>Public API</h3>${lib.exports.map(ref=>`<div class="library-map-function">${source(ref,ref.symbol,esc)}${users.flatMap(user=>user.calls.filter(call=>call.definition.symbol===ref.symbol).map(call=>`<span>Called by ${source(call.caller,call.caller.symbol,esc)} in ${esc(user.name)}</span>`)).join('')}</div>`).join('')}</section>${lib.libraries.length?`<section><h3>Libraries used</h3><div class="mission-map-library-chips">${lib.libraries.map(dep=>`<button data-arch-library="${esc(dep.name)}">${icon('files')}${esc(dep.name)}</button>`).join('')}</div></section>`:''}</div></section></div>`;
}

function draftDiagram(state,esc){
 const draft=state.missionDraft,preview=draft.preview,settings=draft.draft.settings;
 const field=(name,label,step='1')=>`<label>${label}<input name="${name}" type="number" step="${step}" min="${step==='any'?'0.000001':'0'}" value="${esc(settings[name])}" required ${state.missionBusy?'disabled':''}></label>`;
 return `<form class="mission-draft" id="mission-draft-form"><header>${icon(draft.draft.kind==='app'?'code':'files')}<strong>${esc(draft.draft.name)}</strong><span>${draft.draft.mode==='edit'?'Changes':'New '+draft.draft.kind} · not saved</span></header>
 <div class="mission-draft-blocks">
 ${draft.draft.kind==='app'?`<section class="mission-draft-block"><h3>Startup</h3><code>${esc(preview.entry_point)}</code><div class="mission-draft-fields">${field('priority','Priority')}${field('stack_size','Stack · bytes')}</div></section><div class="mission-draft-arrow">↓</div><section class="mission-draft-block"><h3>Scheduler</h3><div class="mission-draft-fields">${field('wakeup_hz','Wakeup · Hz','any')}${field('hk_hz','Housekeeping · Hz','any')}</div><small>SCH tick · ${esc(preview.schedule?.tick_hz)} Hz</small></section><div class="mission-draft-arrow">↓</div>`:''}
 <section class="mission-draft-block"><h3>${draft.draft.kind==='app'?'Application blocks':'Library API'}</h3><div class="mission-draft-functions">${(preview.blocks||[]).map(block=>`<div><strong>${esc(block.title)}</strong><code>${esc(block.symbol||'')}</code></div>`).join('')}</div>${draft.draft.kind==='library'?'<small>Scheduled by caller</small>':''}</section>
 <details class="mission-draft-native"><summary>Native configuration</summary><small>${esc(preview.startup.path)}</small><pre>${esc(preview.startup.record)}</pre><small>${esc(preview.build.path)}</small><pre>${esc(preview.build.statement)}</pre></details>
 ${state.missionError?`<p class="mission-map-error" role="alert">${esc(state.missionError)}</p>`:''}
 <footer><button type="button" data-mission-draft-cancel ${state.missionBusy?'disabled':''}>Cancel</button><button class="primary" type="submit" ${state.missionBusy?'disabled':''}>${icon(state.missionBusy?'rotate':'check')}${state.missionBusy?'Saving…':'Save '+draft.draft.kind}</button></footer>
 </div></form>`;
}

function sensorsForApp(state,app,esc){
 const bindings=state.workspace.project.apps.find(item=>item.name===app.name);
 if(!bindings)return '';
 const name=esc(app.name);
 const readers=Object.entries(bindings.sensors);
 return `<section class="app-sensor-bindings"><header><strong>App sensors</strong><button data-create="sensor" data-app="${name}">${icon('plus')}Add sensor</button></header>${readers.map(([reader,device])=>{
  const packets=Object.entries(bindings.telemetry_bindings).filter(([,source])=>source===reader);
  return `<div class="app-sensor-binding"><span>${icon('cpu')}<strong>${esc(device)}</strong></span>${packets.map(([packet])=>`<button data-remove="telemetry" data-app="${name}" data-name="${esc(packet)}" title="Remove telemetry">${esc(packet)} ×</button>`).join('')}<button data-remove="sensor" data-app="${name}" data-name="${esc(reader)}" ${packets.length?'disabled title="Remove linked telemetry first"':''}>Detach</button></div>`;
 }).join('')}${readers.length?`<button data-create="telemetry" data-app="${name}">${icon('plus')}Add telemetry</button>`:''}</section>`;
}

export function renderArchitecture(state,{esc}){
 const included=state.workspace.mission.included||state.workspace.mission.enabled||[];
 const app=state.workspace.apps.find(item=>item.name===state.archApp && included.includes(item.name));
 const library=state.workspace.libraries?.find(item=>item.name===state.archLibrary);
 const draft=state.missionDraft;
 const selected=draft?.draft.name||library?.name||app?.name;
 if(!selected)return `<div class="architecture-surface"><div class="architecture-scroll">${renderMissionDiagram(state,{esc,icon})}</div></div>`;
 let detail,actions;
 if(draft){
  detail=draftDiagram(state,esc);
  actions='';
 }else{
  detail=library?libraryDiagram(state,library,esc):sensorsForApp(state,app,esc)+renderAppDiagram(state,app,{esc});
  actions=`${app?.managed?`<button data-mission-configure="${esc(app.name)}">Configure app</button>`:''}<button data-arch-follow>${icon('code')}Show source</button><button data-arch-clear title="Close detail" aria-label="Close detail">${icon('close')}</button>`;
 }
 const panel=`<section class="architecture-pane architecture-detail"><header><span>${icon(library?'files':'code')}${esc(selected)}</span><div>${actions}</div></header><div class="architecture-pane-content">${detail}</div></section>`;
 const overview=!!state.archOverview&&!draft;
 const tabs=draft?'':`<nav class="arch-tabs" aria-label="Architecture views"><button data-arch-tab="overview" aria-pressed="${overview}">${icon('layers')}Mission architecture</button><button data-arch-tab="detail" aria-pressed="${!overview}">${icon(library?'files':'code')}${esc(selected)}</button></nav>`;
 return `<div class="architecture-surface">${tabs}<div class="architecture-scroll">${overview?renderMissionDiagram(state,{esc,icon}):panel}</div></div>`;
}
export function layoutArchitecture(state) {
  layoutAppDiagram(state);
  mountMissionMap(state);
}
