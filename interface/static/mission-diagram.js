import {appLabel} from './mission-labels.js';
/* Mission composition: native startup apps, cFE services and project hardware. */
const coreServices = [
  ['es', 'ES', 'Executive', 'Application lifecycle'],
  ['evs', 'EVS', 'Events', 'Event reporting'],
  ['sb', 'SB', 'Software Bus', 'Message routing'],
  ['time', 'TIME', 'Time', 'Mission time'],
  ['tbl', 'TBL', 'Tables', 'Table management'],
  ['fs', 'FS', 'Files', 'File services'],
];

function boardIllustration() {
  const pins = Array.from({length: 20}, (_, i) => `<path d="M${39 + i * 7} 18v22"/>`).join('');
  return `<svg class="mission-map-board-drawing" viewBox="0 0 240 155" aria-hidden="true">
    <rect class="mission-map-pcb" x="24" y="24" width="184" height="113" rx="5"/>
    <path class="mission-map-trace" d="M53 69h31v25h55m-8-40h43v25h27M72 115h63v-13h65M50 51h17v45h20M151 79h20v24M101 38v14"/>
    <g class="mission-map-pins">${pins}</g>
    <rect class="mission-map-silicon" x="49" y="60" width="25" height="30"/>
    <rect class="mission-map-silicon" x="145" y="58" width="27" height="28"/>
    <rect class="mission-map-chip" x="85" y="57" width="44" height="44" rx="1"/>
    <rect class="mission-map-port" x="188" y="47" width="34" height="29" rx="1"/>
    <rect class="mission-map-port" x="188" y="83" width="34" height="29" rx="1"/>
    <rect class="mission-map-port" x="44" y="126" width="20" height="15"/>
    <rect class="mission-map-port" x="85" y="128" width="14" height="12"/>
    <rect class="mission-map-port" x="110" y="128" width="14" height="12"/>
    <rect class="mission-map-silicon" x="139" y="124" width="18" height="17"/>
    <g class="mission-map-mounts"><circle cx="33" cy="49" r="3"/><circle cx="33" cy="124" r="3"/><circle cx="179" cy="124" r="3"/></g>
  </svg>`;
}

function libraryChips(items,esc,icon){
 return items?.length?`<div class="mission-map-library-chips">${items.map(lib=>`<button data-arch-library="${esc(lib.name)}" title="${lib.calls?.length?'API calls':'Build dependency'} · ${esc(lib.name)}">${icon('files')}${esc(lib.name)}</button>`).join('')}</div>`:'';
}

function application(app, state, {esc, icon}, available = false) {
 const busy=!!state.missionBusy,enabled=app.enabled,editing=state.missionEditing;
 return `<article class="mission-map-app ${app.managed?'mission-map-app-custom':''} change-${app.change||'clean'} ${!enabled&&!available?'is-disabled':''} ${state.missionBusy===app.name?'is-busy':''} ${state.archApp===app.name?'is-selected':''}" data-mission-block="${esc(app.name)}">
  <button class="mission-map-app-main" ${available?`data-mission-action="add" data-name="${esc(app.name)}"`:`data-arch-app="${esc(app.name)}"`} title="${available?'Add':'Open'} ${esc(app.name)}"><span class="mission-map-app-icon">${icon(app.managed?'code':'cube')}</span><span class="mission-map-app-copy"><strong>${esc(app.name)}</strong><small>${esc(appLabel(app))}</small></span></button>
  ${editing?`<div class="mission-map-app-controls">${available?`<button data-mission-action="add" data-name="${esc(app.name)}" title="Add ${esc(app.name)}" aria-label="Add ${esc(app.name)}" ${busy?'disabled':''}>${icon('plus')}</button>${app.managed?`<button data-module-options="app" data-name="${esc(app.name)}" title="Delete ${esc(app.name)} files" aria-label="Delete ${esc(app.name)} files" ${busy?'disabled':''}>${icon('minus')}</button>`:''}`:`<button class="mission-map-power ${enabled?'is-enabled':''}" data-mission-action="${enabled?'disable':'enable'}" data-name="${esc(app.name)}" title="${enabled?'Disable':'Enable'} ${esc(app.name)}" aria-label="${enabled?'Disable':'Enable'} ${esc(app.name)}" aria-pressed="${enabled}" ${busy?'disabled':''}>${icon('power')}</button><button data-module-options="app" data-name="${esc(app.name)}" title="Remove ${esc(app.name)} from mission" aria-label="Remove ${esc(app.name)} from mission" ${busy?'disabled':''}>${icon('minus')}</button>`}</div>`:''}
  ${libraryChips(app.libraries,esc,icon)}
 </article>`;
}

function newModule(state,{esc,icon},kind){
 if(state.missionCreating!==kind)return `<button class="mission-map-add-tile" data-mission-create="${kind}" ${state.missionBusy?'disabled':''}>${icon('plus')}<span>New ${kind}</span></button>`;
 return `<form class="mission-map-new-app" id="mission-new-app" data-kind="${kind}"><div><label for="mission-new-name">New ${kind}</label><button type="button" data-mission-create-close title="Cancel" aria-label="Cancel" ${state.missionBusy?'disabled':''}>${icon('close')}</button></div><input id="mission-new-name" name="name" aria-label="Name" placeholder="${kind==='app'?'app_name':'name_lib'}" value="${esc(state.missionNewName||'')}" pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*" maxlength="19" title="snake_case, up to 19 characters" required autocomplete="off" ${state.missionBusy?'disabled':''}><button class="mission-map-create-submit" type="submit" ${state.missionBusy?'disabled':''}>${icon('arrow-up-right')}${state.missionBusy?'Preparing…':'Configure '+kind}</button></form>`;
}

function libraries(state,{esc,icon}){
 const included=new Set(state.workspace.mission.included||[]);
 const visible=(state.workspace.libraries||[]).filter(lib=>lib.built||lib.loaded||lib.used_by.some(user=>user.kind==='app'&&included.has(user.name)));
 const available=(state.workspace.mission.available_libraries||[]).filter(lib=>!lib.included&&lib.editable);
 const tile=(lib,available=false)=>`<article class="mission-map-library change-${lib.change||'clean'} ${state.archLibrary===lib.name?'is-selected':''}"><button class="mission-map-app-main" ${available?`data-mission-library-action="add" data-name="${esc(lib.name)}"`:`data-arch-library="${esc(lib.name)}"`} title="${available?'Add':'Open'} ${esc(lib.name)}">${icon('files')}<span class="mission-map-app-copy"><strong>${esc(lib.name)}</strong></span></button>${state.missionEditing?`<div class="mission-map-app-controls"><button ${available?`data-mission-library-action="add"`:'data-module-options="library"'} data-name="${esc(lib.name)}" title="${available?'Add':'Remove'} ${esc(lib.name)}" aria-label="${available?'Add':'Remove'} ${esc(lib.name)}" ${state.missionBusy?'disabled':''}>${icon(available?'plus':'minus')}</button>${available&&lib.deletable?`<button data-module-options="library" data-name="${esc(lib.name)}" title="Delete ${esc(lib.name)} files" aria-label="Delete ${esc(lib.name)} files">${icon('minus')}</button>`:''}</div>`:''}${libraryChips(lib.libraries,esc,icon)}</article>`;
 return `<section class="mission-map-app-group" aria-label="Libraries"><div class="mission-map-group-heading"><h3>Libraries <small>${visible.length}</small></h3>${state.missionEditing?'<button data-library-catalog>'+icon('plus')+'Add library</button>':''}</div><div class="mission-map-library-grid">${visible.map(lib=>tile(lib)).join('')}${state.missionEditing?newModule(state,{esc,icon},'library'):''}</div></section>${state.missionEditing&&state.libraryCatalog?`<section class="mission-map-catalog"><div class="mission-map-group-heading"><h3>Available libraries</h3><button data-library-catalog aria-label="Close available libraries">${icon('close')}</button></div><div class="mission-map-library-grid">${available.map(lib=>tile(lib,true)).join('')||'<span class="mission-map-empty">All available libraries are in the mission.</span>'}</div></section>`:''}`;
}

export function renderMissionDiagram(state, {esc, icon}) {
  const workspace = state.workspace, project = workspace.project, mission = workspace.mission || {};
  const included=new Set(mission.included||mission.enabled||[]);
  const members=workspace.apps.filter(app=>included.has(app.name));
  const custom=members.filter(app=>app.managed),standard=members.filter(app=>!app.managed);
  const available=(mission.available||[]).filter(item=>!included.has(item.name)&&item.editable).map(item=>({...workspace.apps.find(app=>app.name===item.name),...item}));
  const selectedCore = new Set((mission.core_services || []).map(service => service.name.toLowerCase()));
  const services = coreServices.filter(([name]) => selectedCore.has(name));
  const profile = state.hardware?.profiles?.find(item => item.board === project.board && item.os === project.os);
  const boardName = profile?.board_label || workspace.catalog.name || project.board, osName = profile?.os_label || workspace.catalog.os_labels?.[project.os] || project.os || 'Host OS';
  const devices = project.devices || [];
  const address = value => Number.isInteger(value) ? '0x' + value.toString(16).toUpperCase().padStart(2, '0') : '—';
  const helpers = {esc, icon},editing=!!state.missionEditing;

  return `<div class="mission-map ${editing?'is-editing':''}">
    <div class="mission-map-heading"><div>${icon('layers')}<span>Mission architecture</span><i>/</i><small>Software &amp; hardware</small></div>${mission.pending_build?'<span class="mission-map-pending">Build to apply</span>':''}</div>
    ${state.missionError?`<div class="mission-map-error" role="alert">${esc(state.missionError)}<button data-mission-error-close aria-label="Dismiss error">${icon('close')}</button></div>`:''}
    <div class="mission-map-columns">
      <section class="mission-map-software" aria-label="Flight software architecture">
        <header class="mission-map-section-heading"><span class="mission-map-section-icon">${icon('code')}</span><div><h2>Software</h2><p>Flight software</p></div><span class="mission-map-tag">cFS</span></header>
        <div class="mission-map-software-body">
          <section class="mission-map-app-group" aria-label="Mission applications"><div class="mission-map-group-heading"><h3>Mission apps</h3>${editing?`<button data-mission-create="app" ${state.missionBusy?'disabled':''}>${icon('plus')}New app</button>`:''}</div><div class="mission-map-custom-grid">${custom.map(app=>application(app,state,helpers)).join('')}${editing?newModule(state,helpers,'app'):''}</div></section>
          <section class="mission-map-app-group" aria-label="cFS applications"><div class="mission-map-group-heading"><h3>cFS apps <small>${standard.length}</small></h3>${editing?`<button data-mission-catalog ${state.missionBusy?'disabled':''}>${icon('plus')}Add app</button>`:''}</div><div class="mission-map-app-grid">${standard.map(app=>application(app,state,helpers)).join('')}${editing?`<button class="mission-map-add-tile compact" data-mission-catalog ${state.missionBusy?'disabled':''}>${icon('plus')}<span>Add app</span></button>`:''}</div></section>
          ${editing&&state.missionCatalog?`<section class="mission-map-catalog"><div class="mission-map-group-heading"><h3>Available apps</h3><button data-mission-catalog-close aria-label="Close available apps">${icon('close')}</button></div><div class="mission-map-app-grid">${available.map(app=>application(app,state,helpers,true)).join('')||'<span class="mission-map-empty">All available apps are in the mission.</span>'}</div></section>`:''}
          ${libraries(state,helpers)}
          <div class="mission-map-layer-link" aria-hidden="true"><span></span><small>cFE services</small><span></span></div>
          <section class="mission-map-core change-${mission.source_changes?.core||'clean'}" aria-label="Core Flight Executive services"><div class="mission-map-group-heading"><h3>cFE core</h3></div><div class="mission-map-service-grid">${services.filter(([name])=>name==='sb').concat(services.filter(([name])=>name!=='sb')).map(([id, short, name, purpose]) => `<div class="mission-map-service ${id==='sb'?'mission-map-service-bus':''}" title="${esc(purpose)}"><strong>${short}</strong><small>${esc(name)}</small></div>`).join('')}</div></section>
          <div class="mission-map-platform-label">Platform</div>
          <div class="mission-map-platform-grid">
            <button class="mission-map-platform-block change-${mission.source_changes?.osal||'clean'}" data-file="cFS/osal/README.md">${icon('layers')}<span><strong>OSAL</strong><small>OS abstraction</small></span>${icon('arrow-up-right')}</button>
            <button class="mission-map-platform-block change-${mission.source_changes?.psp||'clean'}" data-file="cFS/psp/README.md">${icon('cpu')}<span><strong>PSP</strong><small>Platform support</small></span>${icon('arrow-up-right')}</button>
          </div>
          <div class="mission-map-system">${icon('terminal')}<span><strong>${esc(osName)}</strong><small>${esc(project.board||'Native')}</small></span><span class="mission-map-system-label">Operating system</span></div>
        </div>
      </section>
      <div class="mission-map-bridge" aria-hidden="true"><span>↔</span></div>
      <section class="mission-map-hardware" aria-label="Board and sensors">
        <header class="mission-map-section-heading"><span class="mission-map-section-icon">${icon('cpu')}</span><div><h2>Hardware</h2><p>Board and sensors</p></div></header>
        <div class="mission-map-hardware-body">
          ${project.board?`<button class="mission-map-board change-${workspace.changes?.board||'clean'}" data-view="bench" data-inspect="board" title="Open board in the hardware workbench"><span class="mission-map-computer-label">Flight computer</span>${boardIllustration()}<strong>${esc(boardName)}</strong><small>${esc(project.board)}</small><span class="mission-map-board-footer">Hardware workbench ${icon('arrow-up-right')}</span></button>
          ${devices.length ? `<div class="mission-map-bus-link" aria-hidden="true"><span></span><small>${devices.every(device => String(device.bus).startsWith('i2c')) ? 'I²C' : 'Peripherals'}</small><span></span></div><section class="mission-map-sensors" aria-label="Connected sensors"><div class="mission-map-group-heading"><h3>Sensors</h3>${editing?`<button data-create="device">${icon('plus')}Add</button>`:''}</div>${devices.map(device => `<button class="mission-map-sensor change-${workspace.changes?.devices?.[device.id]||'clean'}" data-view="bench" data-device="${esc(device.id)}" data-inspect="${esc(device.id)}" title="Open ${esc(device.model)} in the hardware workbench">${icon('cpu')}<span><strong>${esc(device.model)}</strong><small>${esc(device.bus)} · ${address(device.address)}</small></span>${icon('arrow-up-right')}</button>`).join('')}</section>` : editing?`<button class="mission-map-add-tile" data-create="device">${icon('plus')}Add sensor</button>`:''}
          <button class="mission-map-open-workbench" data-view="bench">${icon('circuit')}Open workbench${icon('arrow-up-right')}</button>`:`<div class="hardware-empty">${icon('cpu')}<strong>Native execution</strong><span>This computer · Host OS</span><button data-choose-board>${icon('plus')}Select board</button></div>`}
        </div>
      </section>
    </div>
    <div class="mission-map-legend" aria-label="Source changes in Git"><span class="change-clean">Unchanged</span><span class="change-modified">Modified</span><span class="change-new">New</span><small>Git · source files</small></div>
  </div>`;
}
