import {icon} from './ui.js';

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
    const used = lib.used_by.some(user => user.kind === 'app' && included.has(user.name));
    if ((lib.built || lib.loaded || used) && !libraries.get(lib.name)?.included) {
      libraries.set(lib.name, {...lib, included: true, editable: false});
    }
  }
  return {
    mission: {title: 'Mission apps', kind: 'app', create: true, modules: apps.filter(app => app.managed)},
    cfs: {title: 'cFS apps', kind: 'app', create: false, modules: apps.filter(app => !app.managed)},
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
  const actions = [['new', 'plus', 'New'], ['edit', 'pencil', 'Edit'], ['remove', 'minus', 'Remove']];
  return `<div class="map-actions" role="group" aria-label="${group.title} actions">${actions.map(([action, glyph, label]) => {
    const available = action === 'new' && group.create || moduleChoices(group, action).length > 0;
    const hint = available ? label + ' · ' + group.title : {
      new: 'All available modules are already included',
      edit: group.kind === 'library' ? 'Only project-created libraries can be renamed' : 'No editable apps in this group',
      remove: 'No removable modules in this group',
    }[action];
    return `<button class="map-action" data-module-group="${key}" data-module-action="${action}" title="${hint}" ${locked || !available ? 'disabled' : ''}>${icon(glyph)}${label}</button>`;
  }).join('')}</div>`;
}

function moduleTile(item, group, state, esc) {
  const library = group.kind === 'library';
  const name = esc(item.name);
  const status = esc(item.change || 'clean');
  const deps = state.showLibraries ? item.libraries || [] : [];
  const disabled = !library && !item.enabled;
  return `<article class="map-tile map-module change-${status}" data-mission-block="${name}">
    <button class="map-module-open" ${library ? 'data-arch-library' : 'data-arch-app'}="${name}" title="Open ${name}">
      <span class="map-tile-title">${icon(library ? 'files' : item.managed ? 'code' : 'cube')}<strong>${name}</strong></span>
      ${disabled ? '<small>Startup disabled</small>' : ''}
    </button>
    ${deps.length ? `<div class="map-dependencies">${deps.map(dep => `<button data-arch-library="${esc(dep.name)}" title="Open library ${esc(dep.name)}">${icon('files')}${esc(dep.name)}</button>`).join('')}</div>` : ''}
  </article>`;
}

function groupSection(key, group, state, esc) {
  const members = group.modules.filter(item => item.included);
  return `<section class="map-group" aria-label="${group.title}">
    <div class="map-group-head"><h3>${group.title}<small>${members.length}</small></h3>${controls(key, group, state.missionBusy || state.missionDraft)}</div>
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
    <rect x="36" y="12" width="168" height="106" rx="5" fill="#354650" stroke="#8a9fa8"/>
    <rect x="43" y="19" width="154" height="89" rx="2" fill="#1c2930" stroke="#57716e"/>
    <text x="120" y="71" text-anchor="middle" stroke="none" fill="#c0d5ca" font-size="19">${esc(osName)}</text>
    <path d="M111 118h18v14h31v6H80v-6h31z" fill="#839b9d" stroke="none"/></svg>` : boardIllustration();
  const devices = project.devices || [];
  return `<section class="map-panel map-hardware" aria-label="Hardware"><header class="map-panel-head">${icon('cpu')}<h2>Hardware</h2></header>
    ${native || project.board ? `<button class="map-computer change-${native ? 'clean' : esc(state.workspace.changes?.board || 'clean')}" data-view="bench" data-inspect="board" title="Open hardware workbench">
      ${drawing}<strong>${native ? 'This computer' : esc(boardName)}</strong><small>${[osName, native && state.hardware?.native?.architecture].filter(Boolean).map(esc).join(' · ')}</small></button>` :
    '<div class="hardware-empty"><button data-choose-board>Select board</button></div>'}
    ${!native && project.board ? `<section class="map-peripherals"><div class="map-group-head"><h3>Sensors<small>${devices.length}</small></h3><button class="map-action" data-create="device">${icon('plus')}New</button></div>
      ${devices.map(device => `<button class="map-tile map-system-tile change-${esc(state.workspace.changes?.devices?.[device.id] || 'clean')}" data-view="bench" data-device="${esc(device.id)}" data-inspect="${esc(device.id)}" title="${esc(device.model)}"><span class="map-tile-title">${icon('cpu')}<strong>${esc(device.id)}</strong></span><small>${esc(device.bus)} · 0x${Number(device.address).toString(16).toUpperCase().padStart(2, '0')}</small></button>`).join('')}</section>` : ''}
  </section>`;
}

export function renderMissionDiagram(state, {esc}) {
  const {mission, project, catalog} = state.workspace;
  const groups = moduleGroups(state.workspace);
  const native = state.target === 'native';
  const osName = native ? state.hardware?.native?.os || 'Host OS' : catalog.os_labels?.[project.os] || project.os || 'Host OS';
  const active = new Set(mission.core_services.map(service => service.name.toUpperCase()));
  const serviceTile = ([short, name]) => {
    const id = short.toLowerCase();
    const path = `cFS/cfe/modules/${id}/fsw/src/cfe_${id}_${id === 'fs' ? 'api' : 'task'}.c`;
    return systemTile(short, name, id === 'sb' ? 'workflow' : 'cube', `data-arch-source="${path}" data-symbol="${name}"`, mission.source_changes?.core);
  };
  return `<div class="mission-map">
    <header class="map-heading"><h1>${icon('layers')}Mission architecture</h1><button class="map-action map-library-toggle" data-toggle-libraries aria-pressed="${!!state.showLibraries}">${icon('files')}${state.showLibraries ? 'Hide libraries' : 'Show libraries'}</button></header>
    ${state.missionError ? `<div class="mission-map-error" role="alert">${esc(state.missionError)}<button data-mission-error-close aria-label="Dismiss error">${icon('close')}</button></div>` : ''}
    <div class="map-columns"><section class="map-panel map-software" aria-label="Software"><header class="map-panel-head">${icon('code')}<h2>Flight software</h2></header>
      ${groupSection('mission', groups.mission, state, esc)}${groupSection('cfs', groups.cfs, state, esc)}${state.showLibraries ? groupSection('library', groups.library, state, esc) : ''}
      <section class="map-group map-core" aria-label="Core Flight Executive services"><div class="map-group-head"><h3>cFE core</h3></div>
        ${active.has('SB') ? `<div class="map-grid map-bus">${serviceTile(services[0])}</div>` : ''}
        <div class="map-grid">${services.slice(1).filter(([id]) => active.has(id)).map(serviceTile).join('')}</div>
      </section>
      <section class="map-group" aria-label="Platform"><div class="map-group-head"><h3>Platform</h3></div><div class="map-grid">
        ${systemTile('OSAL', 'OS abstraction', 'layers', 'data-arch-source="cFS/osal/README.md" data-symbol="OSAL"', mission.source_changes?.osal)}
        ${systemTile('PSP', 'Platform support', 'cpu', 'data-arch-source="cFS/psp/README.md" data-symbol="PSP"', mission.source_changes?.psp)}
        ${systemTile(esc(osName), 'Operating system', 'terminal', 'data-view="bench"')}
      </div></section>
    </section>${hardwarePanel(state, esc, native, osName)}</div>
    <footer class="map-legend" aria-label="Git source status"><span>Git</span><span class="change-clean">Unchanged</span><span class="change-modified">Modified</span><span class="change-new">New</span></footer>
  </div>`;
}
