import {icon} from './ui.js';
import {renderMissionDiagram} from './mission-diagram.js';
import {renderAppDiagram,layoutAppDiagram} from './app-diagram.js';
import {renderCommunication} from './communication.js';

function source(ref,label,esc){
 return `<button class="app-map-source" data-arch-source="${esc(ref.path)}" data-line="${ref.line||1}" data-end-line="${ref.end_line||ref.line||1}" data-symbol="${esc(ref.symbol||label)}">${icon('code')}${esc(label)}</button>`;
}

function libraryDiagram(state,lib,esc){
 const member=new Set(state.workspace.mission.included||[]);
 const users=lib.used_by.filter(user=>user.kind==='library'||member.has(user.name));
 return `<div class="library-map"><aside><h3>Used by</h3>${users.map(user=>`<button class="app-map-peer" ${user.kind==='app'?'data-arch-app':'data-arch-library'}="${esc(user.name)}"><span>${icon(user.kind==='app'?'code':'files')}<strong>${esc(user.name)}</strong>${icon('arrow-up-right')}</span><small>${user.calls.length?'API calls':'Build dependency'}</small></button>`).join('')||'<p>No mission callers</p>'}</aside><section class="app-map-container change-${lib.change}"><header>${icon('files')}<strong>${esc(lib.name)}</strong></header><div class="app-map-sections"><section class="library-map-api"><h3>Public API</h3>${lib.exports.map(ref=>`<div class="library-map-function">${source(ref,ref.symbol,esc)}${users.flatMap(user=>user.calls.filter(call=>call.definition.symbol===ref.symbol).map(call=>`<span>${esc(user.name)} → ${source(call.caller,call.caller.symbol,esc)}</span>`)).join('')}</div>`).join('')}</section>${lib.libraries.length?`<section><h3>Libraries used</h3><div class="mission-map-library-chips">${lib.libraries.map(dep=>`<button data-arch-library="${esc(dep.name)}">${icon('files')}${esc(dep.name)}</button>`).join('')}</div></section>`:''}<footer>${source({path:lib.path+'/CMakeLists.txt'},'Build configuration',esc)}</footer></div></section></div>`;
}

function draftDiagram(state,esc){
 const draft=state.missionDraft,preview=draft.preview,settings=draft.draft.settings;
 const field=(name,label,step='1')=>`<label>${label}<input name="${name}" type="number" step="${step}" min="${step==='any'?'0.000001':'0'}" value="${esc(settings[name])}" required ${state.missionBusy?'disabled':''}></label>`;
 return `<form class="mission-draft" id="mission-draft-form"><header>${icon(draft.draft.kind==='app'?'code':'files')}<strong>${esc(draft.draft.name)}</strong><span>${draft.draft.mode==='edit'?'Changes':'New '+draft.draft.kind} · not saved</span></header>
 <div class="mission-draft-blocks">
 ${draft.draft.kind==='app'?`<section class="mission-draft-block"><h3>Startup</h3><code>${esc(preview.entry_point)}</code><div class="mission-draft-fields">${field('priority','Priority')}${field('stack_size','Stack · bytes')}</div></section><div class="mission-draft-arrow">↓</div><section class="mission-draft-block"><h3>Scheduler</h3><div class="mission-draft-fields">${field('wakeup_hz','Wakeup · Hz','any')}${field('hk_hz','Housekeeping · Hz','any')}</div><small>SCH tick · ${esc(preview.schedule?.tick_hz)} Hz</small></section><div class="mission-draft-arrow">↓</div>`:''}
 <section class="mission-draft-block"><h3>${draft.draft.kind==='app'?'Application blocks':'Library API'}</h3><div class="mission-draft-functions">${(preview.blocks||[]).map(block=>`<div><strong>${esc(block.title)}</strong><code>${esc(block.symbol||'')}</code></div>`).join('')}</div>${draft.draft.kind==='library'?'<small>Called by apps · scheduling belongs to the caller</small>':''}</section>
 <details class="mission-draft-native"><summary>Native configuration</summary><small>${esc(preview.startup.path)}</small><pre>${esc(preview.startup.record)}</pre><small>${esc(preview.build.path)}</small><pre>${esc(preview.build.statement)}</pre></details>
 ${state.missionError?`<p class="mission-map-error" role="alert">${esc(state.missionError)}</p>`:''}
 <footer><button type="button" data-mission-draft-cancel ${state.missionBusy?'disabled':''}>Cancel</button><button class="primary" type="submit" ${state.missionBusy?'disabled':''}>${icon(state.missionBusy?'rotate':'check')}${state.missionBusy?'Saving…':'Save '+draft.draft.kind}</button></footer>
 </div></form>`;
}

export function renderArchitecture(state,{esc}){
 const included=new Set(state.workspace.mission.included||state.workspace.mission.enabled||[]),apps=state.workspace.apps.filter(app=>included.has(app.name));
 const library=(state.workspace.libraries||[]).find(lib=>lib.name===state.archLibrary);
 const draft=state.archDraft&&state.missionDraft,app=!library&&!draft&&apps.find(app=>app.name===state.archApp);
 const fullscreen=!!state.archFullscreen,communication=state.archMode==='communication'&&!draft;
 const tabs=fullscreen?[]:[...new Set([...(state.archTabs||[]),app?.name])].map(name=>apps.find(app=>app.name===name)).filter(Boolean);
 const libs=fullscreen?[]:[...new Set([...(state.archLibraries||[]),library?.name])].map(name=>state.workspace.libraries?.find(lib=>lib.name===name)).filter(Boolean);
 const split=fullscreen&&!communication&&!draft&&(app||library);
 const detail=library?libraryDiagram(state,library,esc):app?renderAppDiagram(state,app,{esc}):'';
 const mission=()=>renderMissionDiagram(state,{esc,icon});
 const content=draft?draftDiagram(state,esc):communication?renderCommunication(state,{esc,icon}):split?
  `<div class="architecture-split"><section class="architecture-pane architecture-detail"><header><span>${icon(library?'files':'code')}${esc(library?.name||app.name)}</span><button data-arch-clear aria-label="Close detail" title="Close detail">${icon('close')}</button></header><div class="architecture-pane-content">${detail}</div></section><section class="architecture-pane architecture-mission"><div class="architecture-pane-content">${mission()}</div></section></div>`:detail||mission();
 return `<div class="architecture-surface"><header class="architecture-header"><nav class="architecture-tabs" aria-label="Architecture views"><button class="architecture-tab ${fullscreen||!app&&!library&&!draft?'active':''}" data-arch-app="">${icon('layers')}Mission</button>${tabs.map(tab=>`<div class="architecture-open-tab ${app===tab?'active':''}"><button data-arch-app="${esc(tab.name)}">${icon('code')}${esc(tab.name.toUpperCase())}</button><button class="architecture-close-tab" data-arch-close="${esc(tab.name)}" aria-label="Close ${esc(tab.name)}">${icon('close')}</button></div>`).join('')}${libs.map(lib=>`<div class="architecture-open-tab ${library===lib?'active':''}"><button data-arch-library="${esc(lib.name)}">${icon('files')}${esc(lib.name)}</button><button class="architecture-close-tab" data-arch-library-close="${esc(lib.name)}" aria-label="Close ${esc(lib.name)}">${icon('close')}</button></div>`).join('')}${state.missionDraft?`<button class="architecture-tab ${draft?'active':''}" data-arch-draft>${esc(state.missionDraft.draft.name)} · draft</button>`:''}</nav><div class="architecture-tools"><div class="architecture-mode" role="group" aria-label="Architecture mode"><button data-arch-mode="structure" aria-pressed="${!communication}">${icon('layers')}<span>Structure</span></button><button data-arch-mode="communication" aria-pressed="${communication}" ${state.missionDraft?'disabled':''}>${icon('antenna')}<span>Communication</span></button></div>${!communication&&state.missionEditing&&app?.managed?`<button data-mission-configure="${esc(app.name)}" title="Configure app">${icon('settings')}</button>`:''}${!communication&&state.missionEditing?`<button data-file="${esc(state.workspace.mission.build_config?.path||'cFS/sample_defs/targets.cmake')}" title="Build configuration">${icon('build')}</button>`:''}${!communication?`<button class="architecture-edit ${state.missionEditing?'active':''}" data-mission-edit aria-pressed="${!!state.missionEditing}" ${state.missionBusy||state.missionDraft?'disabled':''}>${icon(state.missionEditing?'check':'settings')}${state.missionEditing?'Done':'Edit'}</button>`:''}<button class="icon-button" data-expand-panel title="${fullscreen?'Restore editor':'Expand architecture'}" aria-label="${fullscreen?'Restore editor':'Expand architecture'}">${icon('expand')}</button></div></header><div class="architecture-scroll ${split?'is-split':''}">${content}</div></div>`;
}
export const layoutArchitecture=layoutAppDiagram;
