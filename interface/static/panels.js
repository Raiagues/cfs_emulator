import {tripPanel,planFor} from './round-trip-view.js';
/* Ground Station surfaces, fed by the deployed packet catalog. */
export {renderArchitecture} from './architecture.js';
const fallbackIcon=()=>'';
const context=helpers=>({icon:fallbackIcon,...helpers});
function stationState(state) {
  return state.ground?.target === state.target ? state.ground : {};
}

function stationCatalog(state) {
  const catalog = state.catalog || {}, app = state.groundApp || '';
  const commands = (catalog.commands || []).filter(command => !app || command.app === app);
  const packets = (catalog.packets || []).filter(packet => !app || packet.app === app);
  const appNames = [...new Set([...(catalog.apps || []).map(app => app.name), ...[...(catalog.commands || []), ...(catalog.packets || [])].map(item => item.app)].filter(Boolean))].sort();
  return {commands, packets, appNames};
}

const stationTime = seconds => seconds ? new Date(seconds * 1000).toLocaleTimeString('en-GB', {hour12: false}) : '—';
const eventPacket = packet => Object.hasOwn(packet.values || {}, 'Message') && Object.hasOwn(packet.values, 'PacketID.AppName');
const commandLabel = command => command.id || command.name || '';

function selectedCommand(state, commands) {
 const managed=state.workspace.project.apps.map(app=>app.name);
 return commands.find(item=>item.id===state.groundSelection) ||
   commands.find(item=>managed.includes(item.app)&&/_NOOP_CC$/.test(item.id)) ||
   commands.find(item=>item.app==='sample_app'&&/_NOOP_CC$/.test(item.id)) ||
   commands.find(item=>/_NOOP_CC$/.test(item.id)) || commands[0];
}
function displayCommand(command) {
 const prefix=command.app.toUpperCase()+'_';
 const name=commandLabel(command);
 return (name.startsWith(prefix)?name.slice(prefix.length):name).replace(/_CC$/,'');
}
function filteredCommands(state,hex) {
 const query=(state.groundQuery||'').trim().toLowerCase();
 return stationCatalog(state).commands.filter(command=>!query||[command.id,command.name,command.app,hex(command.mid)].join(' ').toLowerCase().includes(query));
}
function commandTree(visible, selected, query, managed, esc) {
 const groups=new Map();
 for(const command of visible){
  if(!groups.has(command.app))groups.set(command.app,[]);
  groups.get(command.app).push(command);
 }
 return [...groups].sort(([a],[b])=>Number(managed.has(b))-Number(managed.has(a))||a.localeCompare(b)).map(([app,commands])=>
  `<details class="gs-command-group" data-detail-key="command-group-${esc(app)}" ${query||app===selected?.app?'open':''}><summary>${esc(app)}<small>${commands.length}</small></summary>${commands.map(command=>`<button class="gs-definition ${command===selected?'selected':''}" data-gs-select="${esc(command.id)}" title="${esc(command.id)}" aria-pressed="${command===selected}"><strong>${esc(displayCommand(command))}</strong><small>${command.dispatch==='mid'?'MID':'FC '+Number(command.code)}</small></button>`).join('')}</details>`).join('');
}
function commandBytes(selected,esc,hex) {
 return `<dl><div><dt>Message ID</dt><dd>${hex(selected.mid)}</dd></div>${selected.dispatch==='mid'?'':`<div><dt>Function code</dt><dd>${Number(selected.code)}</dd></div>`}${(selected.fields||[]).map(field=>`<div><dt>${esc(field.name)}</dt><dd>${Number(field.size)} B · offset ${Number(field.offset)}</dd></div>`).join('')}</dl>`;
}
export function renderGroundRoute(state, helpers) {
  return tripPanel(state, selectedCommand(state,filteredCommands(state,helpers.hex)), helpers);
}

function commandList(state, helpers) {
 const {esc,hex,icon}=context(helpers);
 const query=(state.groundQuery||'').trim().toLowerCase();
 const visible=filteredCommands(state,hex);
 const selected=selectedCommand(state,visible);
 if(!selected)return `<div class="gs-empty-list">${icon('search')}<span>${state.catalogLoading?'Reading flight definitions…':query?'No matching commands.':state.catalog?.errors?.length?'Command definitions are unavailable. Check the catalog issues above.':'No commands in this application.'}</span></div>`;
 const fields=(selected.fields||[]).filter(field=>!/^(padding|reserved|spare)/i.test(field.name.split('.').at(-1)));
 const draft=state.groundDrafts?.[selected.id]||{},connected=stationState(state).connected;
 const title=displayCommand(selected), plan=planFor(state,selected);
 const inputs=fields.map(field=>{
  const name=esc(field.name),value=esc(draft[field.name]??'');
  const input=field.format==='?'&&field.count===1?`<select name="${name}"><option value="true" ${value==='true'?'selected':''}>true</option><option value="false" ${value==='false'?'selected':''}>false</option></select>`:`<input name="${name}" value="${value}" required autocomplete="off" placeholder="${field.format==='raw'?'Hexadecimal bytes':field.count>1&&field.format!=='s'?'[0, 1, …]':field.format==='s'?'Text':'Value'}">`;
  return `<label><span>${name}<small>${esc(field.type||field.format)}${field.count>1?' ['+field.count+']':''}</small></span>${input}</label>`;
 }).join('');
 const locations=Object.keys(selected.locations||{}).filter(section=>['dispatch','identifier','packet'].includes(section));
 return `<section class="flight-selection"><div class="selected-command"><small>${esc(selected.app)} · ${selected.dispatch==='mid'?hex(selected.mid):'FC '+selected.code}</small><h2 title="${esc(title)}">${esc(title)}</h2></div><form id="gs-command-form" data-command-id="${esc(selected.id)}"><div class="ground-parameters">${inputs}</div>
 <details class="packet-wire"><summary>${Number(selected.size)} B</summary><div>${commandBytes(selected,esc,hex)}${locations.map(s=>`<button type="button" data-gs-source="${esc(selected.id)}" data-source-kind="command" data-source-section="${s}">${icon('code')}${esc(s)}</button>`).join('')}</div></details>
 <button type="submit" class="gs-send" ${state.groundBusy||state.groundSending||state.catalogLoading||stationState(state).runs?.some(run=>run.status==='waiting')?'disabled':''}>${icon('send')}${state.groundBusy?'Connecting…':state.groundSending?'Sending…':plan?'Run test':connected?'Send':'Connect & send'}</button></form></section>`;
}
export function renderGround(state,helpers){
  const {esc,icon,hex}=context(helpers), ground=stationState(state), catalog=stationCatalog(state);
  const visible=filteredCommands(state,hex), selected=selectedCommand(state,visible);
  const managed=new Set(state.workspace.project.apps.map(app=>app.name));
  const errors=[...(state.catalog?.errors||[]),...(ground.subscription_errors||[])];
  const narrow=state.groundPane||'route';
  return `<section class="flight-ground" data-pane="${esc(narrow)}"><header class="ground-mobile-tabs">${['commands','route','telemetry'].map(key=>`<button data-ground-pane="${key}" aria-pressed="${key===narrow}">${esc(key)}</button>`).join('')}</header>
  <aside class="flight-library"><header>Commands<button data-ground="catalog" title="Refresh catalog">${icon('refresh')} From build</button></header>
  <label class="ground-search">${icon('search')}<input id="gs-search" type="search" aria-label="Search commands" placeholder="Search commands" value="${esc(state.groundQuery||'')}"></label>
  <label class="ground-app-filter"><select id="ground-app" aria-label="Application"><option value="">All applications</option>${catalog.appNames.map(app=>`<option ${state.groundApp===app?'selected':''}>${esc(app)}</option>`).join('')}</select></label>
  <nav class="gs-definition-list" aria-label="Commands">${selected?commandTree(visible,selected,state.groundQuery,managed,esc):''}</nav>
  ${managed.size?`<button class="ground-new-command" data-code-command="${esc([...managed].find(app=>app===state.groundApp)||[...managed][0])}">${icon('plus')} New command in code</button>`:''}
  <div class="ground-link"><span data-live="${!!ground.connected}">${ground.connected?'Connected':'Disconnected'}</span><button data-ground="${ground.connected?'stop':'start'}" ${state.groundBusy?'disabled':''}>${ground.connected?'Disconnect':'Connect'}</button></div></aside>
  <main class="flight-command-column">${state.groundError?`<div class="gs-error" role="alert">${esc(state.groundError)}</div>`:''}
  ${errors.length?`<details class="gs-catalog-errors" data-detail-key="issues"><summary>Catalog details · ${errors.length}</summary><pre>${esc(errors.join('\n'))}</pre></details>`:''}
  ${commandList(state,helpers)}<div id="ground-route"></div></main><aside id="ground-live"></aside></section>`;
}

function seriesChart(state, packet, field, helpers) {
  const {esc} = context(helpers);
  const samples = (stationState(state).history || []).filter(sample => sample.mid === packet.mid && typeof sample.values?.[field] === 'number' && (!Object.hasOwn(sample.values, 'Valid') || sample.values.Valid)).slice(-48);
  if (samples.length < 2) return '';
  const values = samples.map(sample => sample.values[field]), lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const path = values.map((value, index) => `${index ? 'L' : 'M'}${(index / (values.length - 1) * 360).toFixed(1)} ${(hi === lo ? 40 : 70 - (value - lo) / span * 60).toFixed(1)}`).join(' ');
  return `<div class="gs-trace"><svg viewBox="0 0 360 80" preserveAspectRatio="none" role="img" aria-label="Received samples for ${esc(field)}, ${esc(lo)} to ${esc(hi)}"><path d="M0 20H360 M0 60H360" class="gs-trace-grid"/><path d="${path}" class="gs-trace-line"/></svg><div><span>${stationTime(samples[0].received_at)} — ${stationTime(samples.at(-1).received_at)}</span><span>${values.length} samples · ${esc(lo)}–${esc(hi)}</span></div></div>`;
}

function packetValue(value, field, esc, key = '') {
  const raw = field?.format === 'raw' && typeof value === 'string';
  const text = Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (raw || Array.isArray(value) && value.length > 8) {
    const label = raw ? value.length / 2 + ' bytes · hex' : value.length + ' values';
    return `<details class="gs-field-data" data-detail-key="${esc(key)}"><summary>${esc(label)}</summary><pre>${esc(text)}</pre></details>`;
  }
  return `<span>${esc(text)}</span>`;
}

// Fields that describe a sample rather than hold one.
const NOT_A_SAMPLE = /counter|status|valid|reserved|padding|packetid/i;

function packetDetail(state, packet, definition, helpers) {
  const {esc, hex, icon} = context(helpers), fields = packet?.values || {};
  const numeric = Object.entries(fields).find(([name, value]) => typeof value === 'number' && definition.fields?.some(field => field.name === name && ['f','d'].includes(field.format)) && !NOT_A_SAMPLE.test(name));
  const valid = !Object.hasOwn(fields, 'Valid') || Boolean(fields.Valid);
  // A packet with Valid = 0 still carries its last or zeroed sample; never show it as current.
  const stale = name => !valid && !NOT_A_SAMPLE.test(name);
  const definitionFields = definition.fields || [];
  return `<div class="gs-packet-status"><span>${packet ? 'Last received · ' + stationTime(packet.received_at) : 'Waiting for telemetry'}</span><strong>${packet?.count || 0} <small>packets</small></strong></div>${definition.warnings?.length ? `<div class="gs-packet-note">${definition.warnings.map(esc).join(' ')}</div>` : ''}${numeric ? `<div class="gs-reading ${!valid ? 'invalid' : ''}"><strong>${valid ? esc(numeric[1]) : '—'}</strong><span>${esc(numeric[0])}</span>${!valid ? '<small>Invalid data</small>' : ''}</div>${valid ? seriesChart(state, packet, numeric[0], helpers) : ''}` : ''}<div class="gs-envelope"><span>${icon('cube')}${hex(definition.mid)}</span><code>${packet?.bytes || definition.size || '—'} bytes</code></div><details class="gs-packet-fields" data-detail-key="fields-${definition.mid}" open><summary>${icon('chevron-right')}Fields<span>${packet ? Object.keys(fields).length : definitionFields.length}</span></summary><div class="gs-values">${packet ? Object.entries(fields).map(([key, value]) => `<div${stale(key) ? ' class="gs-invalid-field" title="Valid = 0: not a current sample"' : ''}><code>${esc(key)}</code>${packetValue(value, definitionFields.find(field => field.name === key), esc, definition.mid + '-' + key)}</div>`).join('') || '<span class="gs-hint">No decoded fields in this packet.</span>' : definitionFields.map(field => `<div><code>${esc(field.name)}</code><span class="gs-field-type">${esc(field.type)}${field.count > 1 ? '[' + field.count + ']' : ''}</span></div>`).join('') || '<span class="gs-hint">No fields in this packet definition.</span>'}</div></details>${packet?.hex ? `<details class="gs-packet-fields" data-detail-key="bytes-${definition.mid}"><summary>${icon('chevron-right')}Raw bytes</summary><pre class="gs-bytes">${esc(packet.hex)}</pre></details>` : ''}${packet?.errors?.length ? `<div class="gs-error">${esc(packet.errors.join(' · '))}</div>` : ''}${definition.source ? `<div class="gs-source-actions"><button data-gs-source="${esc(definition.id)}" data-source-kind="telemetry" data-source-section="packet">${icon('code')}Packet type${icon('arrow-up-right')}</button>${definition.locations?.identifier?`<button data-gs-source="${esc(definition.id)}" data-source-kind="telemetry" data-source-section="identifier">${icon('code')}Identifier${icon('arrow-up-right')}</button>`:''}</div>` : ''}`;
}

function telemetryEvents(state, helpers) {
  const {esc} = context(helpers);
  const events = (stationState(state).events || (stationState(state).history || []).filter(eventPacket)).slice().reverse();
  return `<section class="gs-event-log"><h2>Telemetry events <small>${events.length} recent</small></h2><div class="gs-journal" role="log">
    ${events.map(packet => `<article><time>${stationTime(packet.received_at)}</time><b>${esc(packet.values['PacketID.AppName'])}</b><span>${esc(packet.values.Message)}</span></article>`).join('') || '<p class="gs-hint">Waiting for an EVS telemetry packet.</p>'}
    </div></section>`;
}

export function renderTelemetry(state, helpers) {
  const {esc, hex, icon} = context(helpers), ground = stationState(state), catalog = stationCatalog(state);
  const error = ground.error && ground.error !== state.groundError ? `<div class="gs-error" role="alert">${esc(ground.error)}</div>` : '';

  const packets = (ground.packets || []).filter(packet => !state.groundApp || packet.app === state.groundApp);
  const definitions = [...catalog.packets];
  for (const packet of packets) if (!definitions.some(definition => definition.mid === packet.mid)) definitions.push(packet);
  const visible = definitions;
  const app=selectedCommand(state,filteredCommands(state,hex))?.app;
  const selected = visible.find(packet => packet.mid === Number(state.groundPacket)) ||
    visible.find(packet=>packet.app===app && /HK/i.test(packet.id||'')) ||
    visible.find(packet=>packet.app===app) || visible[0];
  const heading = '<section class="gs-desk"><h2>Received telemetry <small>Target → Ground</small></h2>';
  const footer = '</section>' + telemetryEvents(state,helpers);
  if(!selected)return `${heading}${error}<div class="gs-empty-list">${icon('antenna')}<span>${state.catalogLoading?'Reading telemetry definitions…':'No telemetry in this application.'}</span></div>${footer}`;
  const counts=new Map(packets.map(packet=>[packet.mid,packet.count]));
  return `${heading}${error}<div class="gs-telemetry-inspector"><label>Packet<select id="ground-packet">${visible.map(definition=>`<option value="${definition.mid}" ${selected===definition?'selected':''}>${esc(definition.id||definition.name||hex(definition.mid))}${counts.has(definition.mid)?' · '+counts.get(definition.mid):''}</option>`).join('')}</select></label><section class="gs-detail" aria-label="Selected telemetry"><div class="gs-detail-kicker">${esc(selected.app)} · ${hex(selected.mid)}</div>${packetDetail(state,packets.find(packet=>packet.mid===selected.mid),selected,helpers)}</section></div>${footer}`;
}
