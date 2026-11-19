import {icon} from './ui.js';
import {renderStack, stackScene, homeCamera, navigation, drawStack} from './mission-stack.js';
import {missionGraph, missionBuses, sensorPins} from './mission-graph.js';

const maps = new WeakMap();

const services = [
  ['SB', 'Software Bus'], ['ES', 'Executive'], ['EVS', 'Events'],
  ['TIME', 'Time'], ['TBL', 'Tables'], ['FS', 'Files'],
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

export function moduleGroups(workspace) {
  const mission = workspace.mission;
  const appSources = new Map(workspace.apps.map(app => [app.name, app]));
  const apps = mission.available.map(recipe => ({...appSources.get(recipe.name), ...recipe}));
  const libSources = new Map(workspace.libraries.map(lib => [lib.name, lib]));
  const libraries = new Map(mission.available_libraries.filter(recipe => recipe.editable || libSources.has(recipe.name))
    .map(recipe => [recipe.name, {...libSources.get(recipe.name), ...recipe}]));
  const included = new Set(mission.included);
  // A dependency may have a native source tree without its own startup recipe.
  for (const lib of libSources.values()) {
    const used = (lib.used_by || []).some(user => user.kind === 'app' && included.has(user.name));
    if ((lib.built || lib.loaded || used) && !libraries.get(lib.name)?.included) {
      libraries.set(lib.name, {...lib, included: true, editable: false});
    }
  }
  return {
    mission: {title: 'Your apps', kind: 'app', create: true, modules: apps.filter(app => app.managed)},
    cfs: {title: 'cFS apps', kind: 'app', create: false, modules: apps.filter(app => !app.managed).sort((a,b)=>Number(!!b.required)-Number(!!a.required))},
    library: {title: 'Libraries', kind: 'library', create: true, modules: [...libraries.values()]},
  };
}

export function moduleChoices(group, action) {
  return group.modules.filter(item => {
    if (action === 'new') return !item.included && item.editable;
    if (!item.included || !item.editable) return false;
    if (action === 'edit') return group.kind === 'app' ? item.managed || !item.required : item.renamable;
    return !item.required && !item.required_by?.length;
  });
}

function controls(key, group, locked) {
  const actions = [['new', 'plus', 'New'], ['edit', 'pencil', 'Edit'], ['remove', 'trash', 'Remove']];
  return `<div class="map-actions" role="group" aria-label="${group.title} actions">${actions.map(([action, glyph, label]) => {
    const available = action === 'new' && group.create || moduleChoices(group, action).length > 0;
    const hint = available ? label + ' · ' + group.title : {
      new: 'All available modules are already included',
      edit: group.kind === 'library' ? 'Only project-created libraries can be renamed' : 'No editable apps in this group',
      remove: 'No removable modules in this group',
    }[action];
    return `<button class="map-action" data-module-group="${key}" data-module-action="${action}" title="${hint}" ${locked || !available ? 'disabled' : ''}>${icon(glyph)}${action === 'remove' ? '<span class="map-icon-text">Remove</span>' : label}</button>`;
  }).join('')}</div>`;
}

function moduleTile(item, group, state, esc) {
  const library = group.kind === 'library';
  const name = esc(item.name);
  const status = esc(item.change || 'clean');
  const deps = state.showLibraries ? item.libraries || [] : [];
  const disabled = !library && !item.enabled;
  return `<article class="map-tile map-module change-${status}" data-mission-block="${name}" data-flat-id="${library ? 'library' : 'app'}:${name}">
    <button class="map-module-open" ${library ? 'data-arch-library' : 'data-arch-app'}="${name}" title="Open ${name}">
      <span class="map-tile-title">${icon(library ? 'files' : item.managed ? 'code' : 'cube')}<strong>${name}</strong></span>
      ${disabled ? '<small>Startup disabled</small>' : item.title ? '<small title="'+esc(item.title)+'">'+esc(item.title)+'</small>' : ''}
      ${item.required ? '<i class="module-lock" title="Required">'+icon('lock')+'</i>' : ''}
    </button>
    ${deps.length ? `<div class="map-dependencies">${deps.map(dep => `<button data-arch-library="${esc(dep.name)}" title="Open library ${esc(dep.name)}">${icon('files')}${esc(dep.name)}</button>`).join('')}</div>` : ''}
  </article>`;
}

function pager(section) {
  return `<div class="map-pager" data-page-controls="${section}" hidden><button data-page-step="-1" aria-label="Previous page">‹</button><output></output><button data-page-step="1" aria-label="Next page">›</button></div>`;
}

function groupSection(key, group, state, esc) {
  const members = group.modules.filter(item => item.included);
  if(key==='mission' && !group.modules.length){
    const enabled=new Set(state.workspace.mission.enabled);
    return '<section class="map-group map-group-mission" data-section="mission"><div class="map-group-head"><h3>Your apps<small>0</small></h3></div><div class="empty-apps">'+
      ['ci_lab','to_lab','sch_lab','sample_app'].filter(name=>enabled.has(name)).map(name=>'<code>'+esc(name)+'</code>').join('')+
      '<code class="slot" aria-hidden="true">+</code><button class="primary" data-first-app>'+icon('plus')+'Create your first app</button></div></section>';
  }
  return `<section class="map-group map-group-${key}" data-section="${key}" aria-label="${group.title}">
    <div class="map-group-head"><h3>${group.title}<small>${members.length}</small></h3>${pager(key)}${controls(key, group, state.missionBusy || state.missionDraft)}</div>
    ${members.length ? `<div class="map-grid">${members.map(item => moduleTile(item, group, state, esc)).join('')}</div>` : ''}
  </section>`;
}

function systemTile(name, subtitle, glyph, attrs = '', change = 'clean') {
  const tag = attrs ? 'button' : 'div';
  return `<${tag} class="map-tile map-system-tile change-${change}" ${attrs}><span class="map-tile-title">${icon(glyph)}<strong>${name}</strong></span><small>${subtitle}</small></${tag}>`;
}

function hardwarePanel(state, esc, native, osName) {
  const {project, catalog} = state.workspace;
  const profile = state.hardware?.profiles?.find(item => item.board === project.board && item.os === project.os);
  const boardName = profile?.board_label || catalog.name || project.board;
  const drawing = native ? `<svg class="mission-map-board-drawing" viewBox="0 0 240 155" aria-hidden="true">
    <rect x="36" y="12" width="168" height="106" rx="5" fill="var(--fs-raised)" stroke="var(--fs-muted)"/>
    <rect x="43" y="19" width="154" height="89" rx="2" fill="var(--fs-bg)" stroke="var(--fs-success)"/>
    <text x="120" y="71" text-anchor="middle" stroke="none" fill="var(--fs-text)" style="font-size:var(--fs-title)">${esc(osName)}</text>
    <path d="M111 118h18v14h31v6H80v-6h31z" fill="var(--fs-muted)" stroke="none"/></svg>` : boardIllustration();
  const devices = project.devices || [];
  return `<section class="map-panel map-hardware" data-section="hardware" aria-label="Hardware"><header class="map-panel-head">${icon('cpu')}<h2>Hardware</h2></header>
    ${native || project.board ? `<button class="map-computer change-${native ? 'clean' : esc(state.workspace.changes?.board || 'clean')}" data-view="bench" data-inspect="board" title="Open hardware workbench">
      ${drawing}<strong>${native ? 'This computer' : esc(boardName)}</strong><small>${[osName, native && state.hardware?.native?.architecture].filter(Boolean).map(esc).join(' · ')}</small></button>` :
    '<div class="hardware-empty"><button data-choose-board>Select board</button></div>'}
    ${!native && project.board ? `<section class="map-peripherals"><div class="map-group-head"><h3>Connections<small>${devices.length} ${devices.length===1?'sensor':'sensors'}</small></h3>${Object.keys(missionBuses(state.workspace)).length?'<button class="map-action" data-create="device">'+icon('plus')+'Add sensor</button>':'<button class="map-action" data-add-bus>'+icon('plus')+'Add bus</button>'}</div>
      ${Object.entries(missionBuses(state.workspace)).map(([id,bus])=>`<div class="hardware-bus"><h4>${icon('link')}${esc(id)} <small>${esc(bus.device)}</small></h4>
      ${devices.filter(device=>device.bus===id).map(device => {
        const bound=(project.apps||[]).some(app=>Object.values(app.sensors||{}).includes(device.id));
        return `<div class="map-device-row"><button data-view="bench" data-device="${esc(device.id)}" data-inspect="${esc(device.id)}">${icon('cpu')}${esc(device.id)} <small>0x${Number(device.address).toString(16).toUpperCase().padStart(2,'0')}</small></button>${bound?'':`<button data-link-hal="${esc(device.id)}" title="Connect this sensor to an app reader">${icon('link')}Add HAL</button>`}</div>`;
      }).join('')}</div>`).join('')}
    </section>` : ''}
  </section>`;
}

export function renderMissionDiagram(state, {esc}) {
  const {mission, project, catalog} = state.workspace;
  const groups = moduleGroups(state.workspace);
  const native = state.target === 'native';
  const osName = native ? state.hardware?.native?.os || 'Host OS' : catalog.os_labels?.[project.os] || project.os || 'Host OS';
  const active = new Set(mission.core_services.map(service => service.name.toUpperCase()));
  const core = services.filter(([name]) => active.has(name)).map(([name, title]) => {
    const id = name.toLowerCase();
    return [id, title, `cFS/cfe/modules/${id}/fsw/src/cfe_${id}_${id === 'fs' ? 'api' : 'task'}.c`];
  });
  const serviceTile = ([id, name, path]) => systemTile(id.toUpperCase(), name, id === 'sb' ? 'workflow' : 'cube', `data-arch-source="${path}" data-symbol="${name}"`, mission.source_changes?.core);
  const board = native ? 'This computer' : catalog.name || project.board || 'Hardware';
  const stack = state.mapMode === '3d';
  const graph=missionGraph(state,groups,core,osName,board);
  const scene=stack ? stackScene(graph,state.showLibraries,native) : null;
  const camera=state.mapCamera || (state.mapCamera=homeCamera());
  if (!graph.nodes.has(state.mapSelected)) state.mapSelected='';
  maps.set(state,{graph,scene,esc});
  const sections=[['mission','Your apps'],...(state.showLibraries?[['library','Libraries']]:[]),['cfs','cFS apps'],['core','cFE'],['platform','Platform'],['hardware','Hardware']];
  if (!sections.some(([id])=>id===state.mapSection)) state.mapSection='cfs';
  return `<div class="mission-map" data-mode="${stack ? '3d' : '2d'}" data-flat-section="${state.mapSection}">
    <header class="map-heading"><div class="map-switch" role="group" aria-label="Mission architecture view">${[['3d','layers','3D'],['2d','table','2D']].map(([mode, glyph, name]) => `<button data-map-mode="${mode}" aria-pressed="${mode === (stack ? '3d' : '2d')}">${icon(glyph)}${name}</button>`).join('')}</div>
    <div class="map-key" aria-label="Module kinds"><span class="own">Your apps</span><span class="library">Libraries</span><span class="upstream">cFS apps</span></div><button class="map-action map-library-toggle" data-toggle-libraries aria-pressed="${!!state.showLibraries}">${icon('files')}${state.showLibraries ? 'Hide libraries' : 'Show libraries'}</button></header>
    ${state.missionError ? `<div class="mission-map-error" role="alert">${esc(state.missionError)}<button data-mission-error-close aria-label="Dismiss error">${icon('close')}</button></div>` : ''}
    ${stack ? renderStack(scene,graph,camera,state.mapSelected,state.showLibraries,esc) : `<nav class="map-section-switch" aria-label="Architecture layers"><label>Layer <select data-flat-section-picker>${sections.map(([id,label])=>'<option value="'+id+'"'+(id===state.mapSection?' selected':'')+'>'+label+'</option>').join('')}</select></label></nav><div class="map-columns"><section class="map-panel map-software" aria-label="Software"><header class="map-panel-head">${icon('code')}<h2>Flight software</h2></header>
      ${groupSection('mission', groups.mission, state, esc)}${state.showLibraries ? groupSection('library', groups.library, state, esc) : ''}${groupSection('cfs', groups.cfs, state, esc)}
      <section class="map-group map-core" data-section="core" aria-label="Core Flight Executive services"><div class="map-group-head"><h3>cFE core</h3></div>
        ${active.has('SB') ? `<div class="map-grid map-bus">${serviceTile(core.find(([id]) => id === 'sb'))}</div>` : ''}
        <div class="map-grid">${core.filter(([id]) => id !== 'sb').map(serviceTile).join('')}</div>
      </section>
      <section class="map-group map-group-platform" data-section="platform" aria-label="Platform"><div class="map-group-head"><h3>Platform</h3></div><div class="map-grid">
        ${systemTile('OSAL', 'OS abstraction', 'layers', 'data-arch-source="cFS/osal/README.md" data-symbol="OSAL"', mission.source_changes?.osal)}
        ${systemTile('PSP', 'Platform support', 'cpu', 'data-arch-source="cFS/psp/README.md" data-symbol="PSP"', mission.source_changes?.psp)}
        ${systemTile(esc(osName), 'Operating system', 'terminal', 'data-view="bench"')}
      </div></section>
    </section>${hardwarePanel(state, esc, native, osName)}</div>`}
    ${stack ? '<div class="cad-selection" aria-live="polite">'+inspector(graph,state.mapSelected,esc)+'</div>' : ''}
    <footer class="map-legend" aria-label="Git source status"><span>Git</span><span class="change-clean">Unchanged</span><span class="change-modified">Modified</span><span class="change-new">New</span></footer>
  </div>`;
}

const kinds={app:'App',library:'Library',service:'cFE service',platform:'Platform',os:'Operating system',board:'Hardware',device:'Sensor',bus:'Bus'};
function inspector(graph,selected,esc) {
  const node=graph.nodes.get(selected);
  if (!node) return '';
  const direct=graph.edges.filter(e=>e.from===selected||e.to===selected);
  const adjacent=direct.map(edge=>{
    const other=graph.nodes.get(edge.from===selected?edge.to:edge.from);
    return '<option value="'+esc(other.id)+'">'+esc(other.name+' · '+edge.detail)+'</option>';
  });
  const actions=[];
  const button=(attr,label,glyph,primary=false)=>'<button class="map-action'+(primary?' cad-primary':'')+'" '+attr+'>'+icon(glyph)+label+'</button>';
  if (node.source) actions.push(button('data-map-code="'+esc(node.source)+'"','Open code','code',true));
  if (node.kind==='app') actions.push(button('data-map-ground="'+esc(node.name)+'"','Commands','antenna'));
  if (node.kind==='device' && !direct.some(e=>e.kind==='reader')) actions.push(button('data-link-hal="'+esc(node.name)+'"','Add HAL','link',true));
  if (['board','device','bus','os'].includes(node.kind)) actions.push(button(navigation(node,esc),'Open hardware','circuit',actions.length===0));
  actions.push(button('data-map-section="'+node.section+'"','View in 2D','table'));
  const description=node.kind==='device'?[node.item.model,'0x'+Number(node.item.address).toString(16).toUpperCase(),...sensorPins(graph,node).map(({signal,pin})=>signal+' '+pin)].join(' · '):
    node.kind==='app'?node.item.entry_point||node.item.behavior?.entry_symbol||'':node.subtitle||'';
  return '<div class="cad-inspector"><span class="cad-kind tone-'+node.tone+'"></span><div class="cad-identity"><small>'+esc(node.section==='mission'?'Your app':kinds[node.kind])+'</small><strong>'+esc(node.name)+'</strong></div>'+
    (description?'<span class="cad-description">'+esc(description)+'</span>':'')+
    (direct.length?'<select aria-label="Explore connections" data-cad-neighbor><option value="">Connections ('+direct.length+')</option>'+adjacent.join('')+'</select>':'')+
    '<div class="cad-actions">'+actions.join('')+'<button class="cad-dismiss" data-clear-selection aria-label="Clear selection">'+icon('close')+'</button></div></div>';
}

function pageGroups(map,state) {
  const pages=state.mapPages || (state.mapPages={});
  for(const section of map.querySelectorAll('[data-page-controls]')) {
    const group=section.closest('[data-section]'), grid=group.querySelector('.map-grid');
    if (!grid || !grid.clientWidth) continue;
    const cols=getComputedStyle(grid).gridTemplateColumns.split(' ').length;
    const rows=Number(getComputedStyle(group).getPropertyValue('--visible-rows'))||2;
    const per=Math.max(1,cols*rows), id=group.dataset.section;
    const total=Math.ceil(grid.children.length/per);
    const selected=grid.querySelector('[data-flat-id="'+CSS.escape(state.mapSelected || '')+'"]');
    if (map.dataset.focusFlat && selected) pages[id]=Math.floor([...grid.children].indexOf(selected)/per);
    const page=Math.min(Math.max(0,pages[id]||0),total-1);
    pages[id]=page;
    [...grid.children].forEach((tile,i)=>{
      tile.hidden=i<page*per || i>=(page+1)*per;
      tile.classList.toggle('cad-flat-selected',tile===selected);
    });
    section.hidden=total<=1;
    section.querySelector('output').textContent=(page+1)+' / '+total;
    section.firstElementChild.disabled=page===0;
    section.lastElementChild.disabled=page>=total-1;
  }
  delete map.dataset.focusFlat;
}

export function mountMissionMap(state) {
  const map=document.querySelector('.architecture-surface .mission-map');
  const data=maps.get(state);
  if (!map || !data) return;
  const {graph,scene,esc}=data;
  if (map.dataset.mode==='2d') {
    map.dataset.focusFlat='true';
    function sync() {
      for (const group of map.querySelectorAll('[data-section]')) group.classList.toggle('current-section',group.dataset.section===state.mapSection);
      pageGroups(map,state);
    }
    const picker=map.querySelector('[data-flat-section-picker]');
    picker.onchange=()=>{state.mapSection=picker.value;map.dataset.flatSection=picker.value;sync();};
    map.addEventListener('click',event=>{
      const step=event.target.closest('[data-page-step]');if(!step)return;
      const id=step.closest('[data-page-controls]').dataset.pageControls;
      state.mapPages[id]=(state.mapPages[id]||0)+Number(step.dataset.pageStep);sync();
    });
    sync();
    const observer=new ResizeObserver(()=>{if(map.isConnected)sync();else observer.disconnect();});
    observer.observe(map);
    return;
  }
  const stage=map.querySelector('.cad-stage'), svg=stage.querySelector('.mission-cad'), panel=map.querySelector('.cad-selection');
  const camera=state.mapCamera, pointers=new Map();
  let drag=null, suppressClick=false, frame=0, pinch=0;
  function draw() {svg.innerHTML=drawStack(scene,graph,camera,state.mapSelected,state.showLibraries,esc);}
  function move(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;if(svg.isConnected)draw();});}
  function select(id,refocus=false) {
    state.mapSelected=graph.nodes.has(id)?id:'';
    draw();
    panel.innerHTML=inspector(graph,state.mapSelected,esc);
    if(refocus)(svg.querySelector('[data-cad-node="'+CSS.escape(state.mapSelected)+'"]')||svg).focus({preventScroll:true});
  }
  function zoom(factor){camera.zoom=Math.max(.48,Math.min(3.5,camera.zoom*factor));}
  function cameraAction(action) {
    if(action==='fit')Object.assign(camera,homeCamera(),{mode:'orbit'});
    else if(action==='in'||action==='out')zoom(action==='in'?1.2:1/1.2);
    else camera.mode=action;
    for(const b of stage.querySelectorAll('[data-camera][aria-pressed]')) b.setAttribute('aria-pressed',String(b.dataset.camera===(camera.mode||'orbit')));
    stage.classList.toggle('pan-mode',camera.mode==='pan');
    move();
  }
  map.addEventListener('click',event=>{
    const node=event.target.closest('[data-cad-node]');
    if (suppressClick && event.target.closest('.mission-cad')) {event.stopPropagation();suppressClick=false;return;}
    if(node){event.stopPropagation();select(state.mapSelected===node.dataset.cadNode?'':node.dataset.cadNode,event.detail===0);return;}
    const cameraBtn=event.target.closest('[data-camera]');
    if(cameraBtn){cameraAction(cameraBtn.dataset.camera);return;}
    if(event.target.closest('[data-clear-selection]')){select('',true);return;}
    if(event.target===svg)select('');
  });
  map.addEventListener('change',event=>{
    if(event.target.matches('[data-cad-neighbor]') && event.target.value) select(event.target.value,true);
  });
  svg.addEventListener('keydown',event=>{
    if(event.key==='Escape'){event.preventDefault();select('',true);return;}
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','Home'].includes(event.key))return;
    event.preventDefault();
    if(event.key==='Home')cameraAction('fit');
    else if(['+','=','-'].includes(event.key))zoom(event.key==='-'?1/1.2:1.2);
    else if(event.key==='ArrowLeft'||event.key==='ArrowRight')camera.yaw+=(event.key==='ArrowLeft'?-1:1)*.13;
    else camera.pitch=Math.max(.19,Math.min(1.02,camera.pitch+(event.key==='ArrowDown'?-.08:.08)));
    svg.focus({preventScroll:true});move();
  });
  svg.addEventListener('wheel',event=>{
    event.preventDefault();
    const units=event.deltaMode===1?16:event.deltaMode===2?svg.clientHeight:1;
    zoom(Math.exp(-Math.max(-180,Math.min(180,event.deltaY*units))*.002));
    move();
  },{passive:false});
  const distance=()=>{const [a,b]=[...pointers.values()];return Math.hypot(a.x-b.x,a.y-b.y);};
  svg.addEventListener('pointerdown',event=>{
    if(event.button!==0 && event.button!==1)return;
    suppressClick=false;
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    drag={x:event.clientX,y:event.clientY,moved:false,pan:event.shiftKey||event.button===1||camera.mode==='pan'};
    if(pointers.size===2){pinch=distance();for(const id of pointers.keys())svg.setPointerCapture(id);drag.moved=true;}
  });
  svg.addEventListener('pointermove',event=>{
    if(!drag || !pointers.has(event.pointerId))return;
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    if(pointers.size===2) {
      const next=distance();if(pinch>0)zoom(next/pinch);pinch=next;move();return;
    }
    const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
    if(!drag.moved && Math.hypot(dx,dy)<4)return;
    if(!drag.moved){svg.setPointerCapture(event.pointerId);stage.classList.add('dragging');}
    drag.moved=true;drag.x=event.clientX;drag.y=event.clientY;
    if(drag.pan){const scale=1/(svg.getScreenCTM()?.a||1);camera.panX+=dx*scale;camera.panY+=dy*scale;}
    else {camera.yaw+=dx*.009;camera.pitch=Math.max(.19,Math.min(1.02,camera.pitch+dy*.006));}
    move();
  });
  function finish(event){
    if(!pointers.has(event.pointerId))return;
    suppressClick=drag?.moved||false;
    pointers.delete(event.pointerId);
    if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);
    const remaining=[...pointers.values()][0];
    drag=remaining?{...remaining,moved:true,pan:camera.mode==='pan'}:null;
    stage.classList.remove('dragging');
  }
  svg.addEventListener('pointerup',finish);svg.addEventListener('pointercancel',finish);
  svg.addEventListener('pointerleave',event=>{if(!svg.hasPointerCapture(event.pointerId))finish(event);});
}
