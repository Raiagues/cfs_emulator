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

function commandList(state, helpers) {
 const {esc,hex,icon}=context(helpers),{commands}=stationCatalog(state);
 const query=(state.groundQuery||'').trim().toLowerCase();
 const visible=commands.filter(command=>!query||[command.id,command.name,command.app,hex(command.mid)].join(' ').toLowerCase().includes(query));
 const selected=visible.find(command=>command.id===state.groundSelection)||visible[0];
 if(!selected)return `<div class="gs-empty-list">${icon('search')}<span>${state.catalogLoading?'Reading flight definitions…':query?'No matching commands.':state.catalog?.errors?.length?'Command definitions are unavailable. Check the catalog issues above.':'No commands in this application.'}</span></div>`;
 const fields=(selected.fields||[]).filter(field=>!/^(padding|reserved|spare)/i.test(field.name.split('.').at(-1)));
 const draft=state.groundDrafts?.[selected.id]||{},connected=stationState(state).connected;
 const title=commandLabel(selected);
 const inputs=fields.map(field=>{
  const name=esc(field.name),value=esc(draft[field.name]??'');
  const input=field.format==='?'&&field.count===1?`<select name="${name}"><option value="true" ${value==='true'?'selected':''}>true</option><option value="false" ${value==='false'?'selected':''}>false</option></select>`:`<input name="${name}" value="${value}" required autocomplete="off" placeholder="${field.format==='raw'?'Hexadecimal bytes':field.count>1&&field.format!=='s'?'[0, 1, …]':field.format==='s'?'Text':'Value'}">`;
  return `<label><span>${name}<small>${esc(field.type||field.format)}${field.count>1?' ['+field.count+']':''}</small></span>${input}</label>`;
 }).join('');
 return `<div class="gs-browser"><nav class="gs-definition-list" aria-label="Commands">${visible.map(command=>`<button class="gs-definition ${command===selected?'selected':''}" data-gs-select="${esc(command.id)}" aria-pressed="${command===selected}"><strong>${esc(commandLabel(command))}</strong><small>${state.groundApp?'':esc(command.app)+' · '}${hex(command.mid)}${command.dispatch==='mid'?'':' · CC '+command.code}</small></button>`).join('')}</nav><section class="gs-detail" aria-label="Selected command"><div class="gs-detail-kicker">COMMAND · ${esc(selected.app)}</div><h2>${esc(title)}</h2><div class="gs-definition-meta"><span>MID <b>${hex(selected.mid)}</b></span>${selected.dispatch==='mid'?'':`<span>Code <b>${selected.code}</b></span>`}<span><b>${selected.size}</b> bytes</span></div><form id="gs-command-form" data-command-id="${esc(selected.id)}">${fields.length?`<div class="gs-parameter-heading">Parameters <span>${fields.length}</span></div>`:''}${inputs?`<div class="gs-parameter-form">${inputs}</div>`:'<p class="gs-no-parameters">No parameters required.</p>'}<button type="submit" class="gs-send" ${state.groundBusy||state.groundSending||state.catalogLoading?'disabled':''}>${icon('arrow-up-right')}${state.groundSending?'Sending…':state.groundBusy?'Connecting…':connected?'Send command':'Connect and send'}</button></form><div class="gs-source-actions" aria-label="Command source">${['dispatch','identifier','packet'].filter(section=>selected.locations?.[section]).map(section=>`<button data-gs-source="${esc(selected.id)}" data-source-kind="command" data-source-section="${section}" title="${esc(selected.locations[section].path)}">${icon('code')}${{dispatch:'Dispatch',identifier:'Identifier',packet:'Packet type'}[section]}${icon('arrow-up-right')}</button>`).join('')}</div></section></div>`;
}

export function renderGround(state, helpers) {
  const {esc, icon} = context(helpers), ground = stationState(state), catalog = stationCatalog(state);
  const target = {native:'This computer',physical:'Physical board',qemu:'Emulator'}[state.target];
  const running = state.target==='native'?state.hardware?.native?.running:state.target==='physical'?state.hardware?.physical?.last_probe?.service==='active':state.hardware?.qemu?.flight_running;
  const errors = [...(state.catalog?.errors||[]), ...(ground.subscription_errors||[])];
  return `<div class="gs-shell gs-console"><header class="gs-link-bar">
    <span class="${ground.connected?'live':''}">${icon('antenna')} Ground Station <b>⇄</b> ${esc(target)} <i></i>${ground.connected?'Connected':'Disconnected'}</span>
    <button data-ground="${ground.connected?'stop':'start'}" ${state.groundBusy?'disabled':''}>${state.groundBusy?'Connecting…':ground.connected?'Disconnect':'Connect'}</button></header>
    ${state.groundError?`<div class="gs-error" role="alert">${esc(state.groundError)}</div>`:!running&&!ground.connected?'<p class="gs-hint">Run cFS on this target before connecting.</p>':''}
    <div class="gs-filter"><label>Application <select id="ground-app"><option value="">All applications</option>${catalog.appNames.map(app=>`<option ${state.groundApp===app?'selected':''}>${esc(app)}</option>`).join('')}</select></label>
    <label class="gs-search">${icon('search')}<input id="gs-search" type="search" aria-label="Filter commands and packets" placeholder="Filter commands and packets" value="${esc(state.groundQuery||'')}"></label>
    <button data-ground="catalog" title="Refresh definitions">${icon('refresh')}</button></div>
    ${errors.length?`<details class="gs-catalog-errors" data-detail-key="issues"><summary>Catalog and subscription details · ${errors.length}</summary><pre>${esc(errors.join('\n'))}</pre></details>`:''}
    <div class="gs-desks"><section class="gs-desk"><h2>Send commands <small>Ground → ${esc(target)}</small></h2>${commandList(state,helpers)}</section><div id="ground-live"></div></div></div>`;
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
  const {esc, hex, icon} = context(helpers), ground = stationState(state), catalog = stationCatalog(state), tab = state.groundTab || 'commands';
  const error = ground.error && ground.error !== state.groundError ? `<div class="gs-error" role="alert">${esc(ground.error)}</div>` : '';

  const packets = (ground.packets || []).filter(packet => !state.groundApp || packet.app === state.groundApp);
  const definitions = [...catalog.packets];
  for (const packet of packets) if (!definitions.some(definition => definition.mid === packet.mid)) definitions.push(packet);
  const query = (state.groundQuery || '').trim().toLowerCase();
  const visible = definitions.filter(definition => !query || [definition.id, definition.name, definition.app, hex(definition.mid)].join(' ').toLowerCase().includes(query));
  const selected = visible.find(packet => packet.mid === Number(state.groundPacket)) || visible[0];
  const heading = '<section class="gs-desk"><h2>Received telemetry <small>Target → Ground</small></h2>';
  const footer = '</section>' + telemetryEvents(state,helpers);
  if(!selected)return `${heading}${error}<div class="gs-empty-list">${icon('antenna')}<span>${query?'No matching telemetry.':state.catalogLoading?'Reading telemetry definitions…':'No telemetry in this application.'}</span></div>${footer}`;
  return `${heading}${error}<div class="gs-browser"><nav class="gs-definition-list gs-telemetry-list" aria-label="Telemetry packets">${visible.map(definition=>{
   const packet=packets.find(packet=>packet.mid===definition.mid);
   return `<button class="gs-definition ${selected===definition?'selected':''}" data-gs-packet="${definition.mid}" aria-pressed="${selected===definition}"><strong>${esc(definition.id||definition.name||hex(definition.mid))}</strong><small><i class="gs-packet-dot ${packet?'received':''}"></i>${hex(definition.mid)} · ${packet?packet.count+' received':'Waiting'}</small></button>`;
  }).join('')}</nav><section class="gs-detail" aria-label="Selected telemetry"><div class="gs-detail-kicker">TELEMETRY · ${esc(selected.app)}</div><h2>${esc(selected.id||selected.name||hex(selected.mid))}</h2>${packetDetail(state,packets.find(packet=>packet.mid===selected.mid),selected,helpers)}</section></div>${footer}`;
}
