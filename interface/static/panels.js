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
  const allowed = new Set(['to_lab','sample_app',...state.workspace.project.apps.map(item=>item.name)]);
  const all = state.allGroundApps || stationState(state).first_flight?.event;
  const commands = (catalog.commands || []).filter(command => {
    if (app) return command.app === app;
    if (all || command.id === state.groundSelection) return true;
    if (command.app === 'to_lab') return command.id === 'TO_LAB_OUTPUT_ENABLE_CC';
    if (command.app === 'sample_app') return /_(NOOP|RESET_COUNTERS)_CC$/.test(command.id);
    return allowed.has(command.app) && command.dispatch !== 'mid';
  });
  const packets = (catalog.packets || []).filter(packet => !app || packet.app === app);
  const appNames = [...new Set((catalog.commands || []).map(item=>item.app).filter(name=>all || allowed.has(name) || name===app))].sort();
  return {commands, packets, appNames};
}

const stationTime = seconds => seconds ? new Date(seconds * 1000).toLocaleTimeString('en-GB', {hour12: false}) : '—';
const eventPacket = packet => Object.hasOwn(packet.values || {}, 'Message') && Object.hasOwn(packet.values, 'PacketID.AppName');
const commandLabel = command => command.id || command.name || '';

export function waitingForBaseline(state, command) {
 const flight=stationState(state).first_flight;
 if(!flight || flight.event || !flight.telemetry || flight.noop_command!==command?.id)return false;
 return (state.catalog?.packets||[]).some(p=>p.app===command.app && p.fields?.some(f=>f.name.split('.').at(-1)==='CommandCounter'))
   && !flight.baseline_apps?.includes(command.app);
}

function selectedCommand(state, commands) {
 const managed=state.workspace.project.apps.map(app=>app.name);
 const contact=stationState(state).first_flight;
 return commands.find(item=>item.id===state.groundSelection) ||
   (!contact?.telemetry && !contact?.event && commands.find(item=>item.id===(contact?.enable_command||'TO_LAB_OUTPUT_ENABLE_CC'))) ||
   (contact?.telemetry && !contact?.event && commands.find(item=>item.id===contact.noop_command)) ||
   commands.find(item=>managed.includes(item.app)&&/_NOOP_CC$/.test(item.id)) ||
   commands.find(item=>item.app==='sample_app'&&/_NOOP_CC$/.test(item.id)) ||
   commands.find(item=>/_NOOP_CC$/.test(item.id)) || commands[0];
}
function displayCommand(command) {
 if(command.id==='TO_LAB_OUTPUT_ENABLE_CC')return 'ENABLE_OUTPUT';
 const prefix=command.app.toUpperCase()+'_';
 const name=commandLabel(command);
 return (name.startsWith(prefix)?name.slice(prefix.length):name).replace(/_CC$/,'');
}
function filteredCommands(state,hex) {
 const query=(state.groundQuery||'').trim().toLowerCase();
 return stationCatalog(state).commands.filter(command=>!query||[command.id,command.name,command.app,hex(command.mid)].join(' ').toLowerCase().includes(query));
}
function commandTree(visible, selected, query, managed, esc, firstContact) {
 const groups=new Map();
 for(const command of visible){
  if(!groups.has(command.app))groups.set(command.app,[]);
  groups.get(command.app).push(command);
 }
 const order=app=>firstContact && app==='to_lab' ? 0 : firstContact && app==='sample_app' ? 1 : managed.has(app) ? 2 : 3;
 return [...groups].sort(([a],[b])=>order(a)-order(b)||a.localeCompare(b)).map(([app,commands])=>
  `<details class="gs-command-group" data-detail-key="command-group-${esc(app)}" ${query||app===selected?.app||firstContact&&['to_lab','sample_app'].includes(app)?'open':''}><summary>${esc(app)}<small>${commands.length}</small></summary>${commands.map(command=>`<button class="gs-definition ${command===selected?'selected':''}" data-gs-select="${esc(command.id)}" title="${esc(command.id)}" aria-pressed="${command===selected}"><strong>${esc(displayCommand(command))}</strong><small>${command.dispatch==='mid'?'MID':'FC '+Number(command.code)}</small></button>`).join('')}</details>`).join('');
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
 if(!selected)return `<div class="gs-empty-list">${icon('search')}<span>${state.catalogLoading?'Reading catalog…':query?'No matches':'No commands'}</span></div>`;
 const fields=(selected.fields||[]).filter(field=>!/^(padding|reserved|spare)/i.test(field.name.split('.').at(-1)));
 const draft=state.groundDrafts?.[selected.id]||{},connected=stationState(state).connected;
 const title=displayCommand(selected), plan=planFor(state,selected);
 const inputs=fields.map(field=>{
  const destination=selected.id===stationState(state).first_flight?.enable_command && field.name==='dest_IP';
  const name=esc(field.name),value=esc(draft[field.name]??(destination?stationState(state).first_flight.return_host:''));
  const input=field.format==='?'&&field.count===1?`<select name="${name}"><option value="true" ${value==='true'?'selected':''}>true</option><option value="false" ${value==='false'?'selected':''}>false</option></select>`:`<input name="${name}" value="${value}" required autocomplete="off" placeholder="${field.format==='raw'?'Hexadecimal bytes':field.count>1&&field.format!=='s'?'[0, 1, …]':field.format==='s'?'Text':'Value'}">`;
  return `<label><span>${name}<small>${esc(field.type||field.format)}${field.count>1?' ['+field.count+']':''}</small></span>${input}</label>`;
 }).join('');
 const locations=Object.keys(selected.locations||{}).filter(section=>['dispatch','identifier','packet'].includes(section));
 return `<section class="flight-selection"><div class="selected-command"><small>${esc(selected.app)} · ${selected.dispatch==='mid'?hex(selected.mid):'FC '+selected.code}${locations.includes('identifier')?` <button type="button" class="command-source" data-gs-source="${esc(selected.id)}" data-source-kind="command" data-source-section="identifier" aria-label="Open command source">${icon('edit')}</button>`:''}</small><h2 title="${esc(title)}">${esc(title)}</h2></div><form id="gs-command-form" data-command-id="${esc(selected.id)}"><div class="ground-parameters">${inputs||'<span class="command-no-fields">No parameters</span>'}</div>
 <details class="packet-wire"><summary aria-label="Packet layout"><i class="packet-bytes" aria-hidden="true"><b></b><b></b><b></b><b></b></i>${Number(selected.size)} B</summary><div>${commandBytes(selected,esc,hex)}${locations.map(s=>`<button type="button" data-gs-source="${esc(selected.id)}" data-source-kind="command" data-source-section="${s}">${icon('code')}${esc(s)}</button>`).join('')}</div></details>
 ${!connected && selected.id==='TO_LAB_OUTPUT_ENABLE_CC' ? `<button type="button" data-ground="start" class="gs-send" ${state.groundBusy?'disabled':''}>${icon('antenna')} Connect</button>` :
 `<button type="submit" class="gs-send" ${state.groundBusy||state.groundSending||state.catalogLoading||waitingForBaseline(state,selected)||stationState(state).runs?.some(run=>run.status==='waiting')?'disabled':''}>${icon('send')}${state.groundBusy?'Connecting…':state.groundSending?'Sending…':waitingForBaseline(state,selected)?'Waiting for HK':plan?'Run test':connected?'Send':'Connect & send'}</button>`}</form></section>`;
}
function contactCoach(state, esc, icon) {
 const flight=stationState(state).first_flight || {};
 if(flight.automatic || (flight.answer && state.coachDismissed))return '';
 const commands=state.catalog?.commands||[];
 const enable=commands.find(c=>c.id===(flight.enable_command||'TO_LAB_OUTPUT_ENABLE_CC'));
 const noop=commands.find(c=>c.id===flight.noop_command)||commands.find(c=>c.app==='sample_app' && c.id.endsWith('_NOOP_CC'));
 const steps=[
   ['Telemetry on',enable?enable.app+' · ENABLE_OUTPUT':'to_lab',flight.telemetry,enable],
   ['First command',noop?noop.app+' · NOOP':'NOOP',flight.event,noop],
   ['Answer','INFO + CommandCounter ↑',flight.answer,null]
 ];
 const current=steps.findIndex(([, , done])=>!done);
 return '<nav class="first-event-coach" aria-label="First event">'+steps.map(([label,detail,done,cmd],i)=>
   `<${cmd?'button':'span'} ${cmd?'data-open-trip-command="'+esc(cmd.id)+'"':''} ${i===current?'aria-current="step"':''} data-seen="${Boolean(done)}"><i>${done?icon('check'):i+1}</i><span><strong>${label}</strong><small>${esc(detail)}</small></span></${cmd?'button':'span'}>`).join('')+(flight.answer?'<a href="/studio#app">Next · create app '+icon('chevron-right')+'</a>':'')+'</nav>';
}
export function renderGround(state,helpers){
  const {esc,icon,hex}=context(helpers), ground=stationState(state), catalog=stationCatalog(state);
  const visible=filteredCommands(state,hex), selected=selectedCommand(state,visible);
  const managed=new Set(state.workspace.project.apps.map(app=>app.name));
  const firstContact=!ground.first_flight?.event && !state.allGroundApps;
  const errors=[...(state.catalog?.errors||[]),...(ground.subscription_errors||[])];
  const narrow=state.groundPane||'route';
  return `<section class="flight-ground" data-pane="${esc(narrow)}"><header class="ground-mobile-tabs">${['commands','route','telemetry'].map(key=>`<button data-ground-pane="${key}" aria-pressed="${key===narrow}">${esc(key)}</button>`).join('')}</header>
  <aside class="flight-library"><header>Commands<button data-ground="catalog" title="Refresh catalog">${icon('refresh')} From build</button></header>
  ${!firstContact || state.groundQuery ? `<label class="ground-search">${icon('search')}<input id="gs-search" type="search" aria-label="Search commands" placeholder="Search commands" value="${esc(state.groundQuery||'')}"></label>`:''}
  ${!firstContact || state.groundApp ? `<label class="ground-app-filter"><select id="ground-app" aria-label="Application"><option value="">Applications</option>${catalog.appNames.map(app=>`<option ${state.groundApp===app?'selected':''}>${esc(app)}</option>`).join('')}</select></label>` : ''}
  <nav class="gs-definition-list" aria-label="Commands">${selected?commandTree(visible,selected,state.groundQuery,managed,esc,firstContact):''}
  ${!ground.first_flight?.event?`<button class="ground-new-command" data-all-ground-apps aria-pressed="${!!state.allGroundApps}">${icon('layers')} All apps</button>`:''}</nav>
  ${managed.size?`<button class="ground-new-command" data-code-command="${esc([...managed].find(app=>app===state.groundApp)||[...managed][0])}">${icon('plus')} New command in code</button>`:''}
  <div class="ground-link"><span data-live="${!!ground.connected}">${ground.connected?'Connected':'Disconnected'}</span><button data-ground="${ground.connected?'stop':'start'}" ${state.groundBusy||state.catalogLoading?'disabled':''}>${ground.connected?'Disconnect':'Connect'}</button></div></aside>
  <main class="flight-command-column">${state.groundError?`<div class="gs-error" role="alert">${esc(state.groundError)}</div>`:''}
  ${errors.length?`<details class="gs-catalog-errors" data-detail-key="issues"><summary>Catalog details · ${errors.length}</summary><pre>${esc(errors.join('\n'))}</pre></details>`:''}
  ${contactCoach(state,esc,icon)}${commandList(state,helpers)}<div id="ground-route"></div></main><aside id="ground-live"></aside></section>`;
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
  return `<div class="gs-packet-status"><span>${packet ? 'Last received · ' + stationTime(packet.received_at) : 'Waiting for telemetry'}</span><strong>${packet?.count || 0} <small>packets</small></strong></div>${definition.warnings?.length ? `<div class="gs-packet-note">${definition.warnings.map(esc).join(' ')}</div>` : ''}${numeric ? `<div class="gs-reading ${!valid ? 'invalid' : ''}"><strong>${valid ? esc(numeric[1]) : '—'}</strong><span>${esc(numeric[0])}</span>${!valid ? '<small>Invalid data</small>' : ''}</div>${valid ? seriesChart(state, packet, numeric[0], helpers) : ''}` : ''}<div class="gs-envelope"><span>${icon('cube')}${hex(definition.mid)}</span><code>${packet?.bytes || definition.size || '—'} bytes</code></div><details class="gs-packet-fields" data-detail-key="fields-${definition.mid}" open><summary>${icon('chevron-right')}Fields<span>${packet ? Object.keys(fields).length : definitionFields.length}</span></summary><div class="gs-values">${packet ? Object.entries(fields).map(([key, value]) => `<div${stale(key) ? ' class="gs-invalid-field" title="Valid = 0: not a current sample"' : ''}><code>${esc(key)}</code>${packetValue(value, definitionFields.find(field => field.name === key), esc, definition.mid + '-' + key)}</div>`).join('') || '<span class="gs-hint">No decoded fields</span>' : definitionFields.map(field => `<div><code>${esc(field.name)}</code><span class="gs-field-type">${esc(field.type)}${field.count > 1 ? '[' + field.count + ']' : ''}</span></div>`).join('') || '<span class="gs-hint">No fields</span>'}</div></details>${packet?.hex ? `<details class="gs-packet-fields" data-detail-key="bytes-${definition.mid}"><summary>${icon('chevron-right')}Raw bytes</summary><pre class="gs-bytes">${esc(packet.hex)}</pre></details>` : ''}${packet?.errors?.length ? `<div class="gs-error">${esc(packet.errors.join(' · '))}</div>` : ''}${definition.source ? `<div class="gs-source-actions"><button data-gs-source="${esc(definition.id)}" data-source-kind="telemetry" data-source-section="packet">${icon('code')}Packet type${icon('arrow-up-right')}</button>${definition.locations?.identifier?`<button data-gs-source="${esc(definition.id)}" data-source-kind="telemetry" data-source-section="identifier">${icon('code')}Identifier${icon('arrow-up-right')}</button>`:''}</div>` : ''}`;
}

function telemetryEvents(state, helpers) {
  const {esc} = context(helpers);
  const events = (stationState(state).events || (stationState(state).history || []).filter(eventPacket)).slice().reverse();
  return `<section class="gs-event-log"><h2>Telemetry events <small>${events.length} recent</small></h2><div class="gs-journal" role="log">
    ${events.map(packet => `<article><time>${stationTime(packet.received_at)}</time><b>${esc(packet.values['PacketID.AppName'])}</b><span>${esc(packet.values.Message)}</span></article>`).join('') || '<span class="trip-empty-track"></span>'}
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
  const receiver=state.catalog?.transport;
  const status=ground.first_flight?.telemetry || packets.length ? [receiver?.subscription_app,receiver?.telemetry_port && 'UDP '+receiver.telemetry_port].filter(Boolean).join(' · ') : 'Off';
  const heading = '<section class="gs-desk"><h2>Telemetry <small>'+esc(status)+'</small></h2>';
  const footer = '</section>' + telemetryEvents(state,helpers);
  if(!ground.received && !packets.length){
    const enable=state.catalog?.commands?.find(c=>c.id==='TO_LAB_OUTPUT_ENABLE_CC');
    return `${heading}${error}<div class="first-no-telemetry">${icon('antenna')}<strong>No telemetry</strong>${enable?`<button data-open-trip-command="${esc(enable.id)}">Select ENABLE_OUTPUT</button>`:''}</div></section>`;
  }
  if(state.groundPacket==null) {
    const order=[...new Set(['ci_lab',app].filter(Boolean))];
    const groups=order.map(owner=>{
      const fields=(ground.packets||[]).filter(p=>p.app===owner && !p.errors?.length).flatMap(p=>{
        const def=(state.catalog?.packets||[]).find(d=>d.mid===p.mid);
        if(!def || !/HK/i.test(def.id||''))return [];
        const previous=(ground.history||[]).findLast(q=>q.mid===p.mid && q.event_id<p.event_id && !q.errors?.length);
        return Object.entries(p.values||{}).filter(([key,val])=>typeof val==='number' &&
          (owner==='ci_lab'?/^(IngestPackets|IngestErrors)$/.test(key):!(/padding|reserved|spare/i.test(key)))).map(([key,val])=>{
          const prior=previous?.values[key], delta=typeof prior==='number'?val-prior:0;
          return `<button data-system-packet="${p.mid}" class="gs-field-card"><span><code>${esc(key)}</code><small>${esc(def.fields?.find(f=>f.name===key)?.type||'')}</small></span><span>${delta?`<small class="gs-delta">${delta>0?'+':''}${esc(delta)}</small>`:''}<b>${esc(val)}</b></span></button>`;
        });
      });
      return fields.length?`<section class="gs-field-group"><h3>${esc(owner)}</h3>${fields.join('')}</section>`:'';
    }).join('');
    return `${heading}${error}<div class="gs-telemetry-inspector"><div class="gs-detail">${groups || '<span class="gs-hint">Waiting for housekeeping</span>'}</div>${selected?`<button data-system-packet="${selected.mid}">Packet inspector</button>`:''}</div>${footer}`;
  }
  if(!selected)return `${heading}${error}<div class="gs-empty-list">${icon('antenna')}<span>No packets</span></div>${footer}`;
  const counts=new Map(packets.map(packet=>[packet.mid,packet.count]));
  return `${heading}${error}<div class="gs-telemetry-inspector"><button data-ground-summary>Field overview</button><label>Packet<select id="ground-packet">${visible.map(definition=>`<option value="${definition.mid}" ${selected===definition?'selected':''}>${esc(definition.id||definition.name||hex(definition.mid))}${counts.has(definition.mid)?' · '+counts.get(definition.mid):''}</option>`).join('')}</select></label><section class="gs-detail" aria-label="Selected telemetry"><div class="gs-detail-kicker">${esc(selected.app)} · ${hex(selected.mid)}</div>${packetDetail(state,packets.find(packet=>packet.mid===selected.mid),selected,helpers)}</section></div>${footer}`;
}
