/* UDP traffic observed by the Ground Station; internal Software Bus traffic is not shown. */
const midLabel = mid => Number.isInteger(mid) ? '0x'+mid.toString(16).toUpperCase().padStart(4,'0') : '—';
const clock = seconds => seconds ? new Date(seconds*1000).toLocaleTimeString('en-GB',{hour12:false}) : '—';
const eventKey = (event,kind) => kind+':'+(event.event_id??[event.received_at||event.sent_at,event.mid,event.sequence??event.id].join('-'));
const textValue = value => typeof value==='object' ? JSON.stringify(value) : String(value);

function messageDetails(event,kind,catalog,{esc,icon}){
 if(!event)return '<div class="communication-empty">No messages received</div>';
 const telemetry=kind==='telemetry',definition=telemetry?(catalog.packets||[]).find(packet=>packet.mid===event.mid):(catalog.commands||[]).find(command=>command.id===event.id);
 const title=telemetry?event.name:event.id;
 return `<article class="communication-message"><header><span>${telemetry?'Telemetry received':'Command sent'}</span><strong>${esc(title)}</strong></header>
  <dl class="communication-envelope"><div><dt>MID</dt><dd>${midLabel(event.mid)}</dd></div><div><dt>${telemetry?'Sequence':'CC'}</dt><dd>${esc(telemetry?event.sequence:event.code)}</dd></div><div><dt>Time</dt><dd>${clock(telemetry?event.received_at:event.sent_at)}</dd></div><div><dt>Bytes</dt><dd>${esc(event.bytes)}</dd></div>${event.automatic?'<div><dt>Sender</dt><dd>Ground setup</dd></div>':''}</dl>
  <div class="communication-values">${Object.entries(event.values||{}).map(([name,value])=>`<div><code>${esc(name)}</code><span>${esc(textValue(value))}</span></div>`).join('')||'<span class="communication-empty">No payload fields</span>'}</div>
  ${event.errors?.length?`<p class="communication-error">${event.errors.map(esc).join(' · ')}</p>`:''}
  ${event.hex?`<details class="communication-bytes" data-detail-key="communication-bytes-${eventKey(event,kind)}"><summary>Packet bytes</summary><pre>${esc(event.hex.match(/.{1,2}/g)?.join(' ')||'')}</pre></details>`:''}
  ${definition?.source?`<button class="communication-source" data-gs-source="${esc(definition.id)}" data-source-kind="${telemetry?'telemetry':'command'}" data-source-section="packet">${icon('code')}Packet definition</button>`:''}
 </article>`;
}

export function renderCommunication(state,{esc,icon}){
 const ground=state.ground?.target===state.target?state.ground:{},catalog=state.catalogTarget===state.target?state.catalog||{}:{};
 const observed=new Map((ground.communication?.apps||[]).map(item=>[item.app||'',item]));
 const names=[...new Set([...(state.workspace.mission.enabled||[]),...observed.keys()])];
 names.sort((a,b)=>a.localeCompare(b));
 const selected=names.includes(state.communicationApp)?state.communicationApp:names.find(name=>observed.get(name)?.telemetry_received)||names[0];
 const kind=state.communicationKind==='commands'?'commands':'telemetry',telemetry=kind==='telemetry';
 const events=(telemetry?ground.history||[]:ground.commands||[]).filter(event=>(event.app||'')===selected).slice().reverse();
 const selectedEvent=events.find(event=>eventKey(event,kind)===state.communicationMessage)||events[0];
 const connected=!!ground.connected,busy=!!state.groundBusy,target=state.target==='native'?'Native':state.target==='physical'?'Board':'QEMU';
 const helpers={esc,icon};
 return `<div class="communication-view">
  <header class="communication-link"><div>${icon('antenna')}<strong>Ground Station</strong><span class="${connected?'is-connected':''}"><i></i>${target} · ${busy?'Connecting…':connected?'Connected':'Disconnected'}</span></div><button data-ground="${connected?'stop':'start'}" ${busy?'disabled':''}>${busy?'Connecting…':connected?'Disconnect':'Connect'}${icon('arrow-up-right')}</button></header>
  ${state.groundError||ground.error?`<p class="communication-error" role="alert">${esc(state.groundError||ground.error)}</p>`:''}
  <div class="communication-bus" aria-hidden="true"><span>Telemetry ↑</span><i></i><span>Commands ↓</span></div>
  <div class="communication-app-grid">${names.map(name=>{
   const counts=observed.get(name)||{},active=name===selected;
   return `<article class="communication-app ${active?'is-selected':''}"><header>${icon('code')}<strong>${esc(name||'Unknown MID')}</strong></header><div class="communication-counts"><button data-communication-app="${esc(name)}" data-communication-kind="telemetry" aria-pressed="${active&&telemetry}" title="Telemetry packets received by Ground Station">${icon('arrow-up-right')}<span>Telemetry</span><strong>${counts.telemetry_received||0}</strong></button><button data-communication-app="${esc(name)}" data-communication-kind="commands" aria-pressed="${active&&!telemetry}" title="Commands sent by Ground Station">${icon('arrow-down')}<span>Commands</span><strong>${counts.commands_sent||0}</strong></button></div></article>`;
  }).join('')||'<div class="communication-empty">No active applications</div>'}</div>
  <section class="communication-inspector"><header><div><strong>${esc(selected||'Unknown MID')}</strong><span>${telemetry?'→ Ground Station':'← Ground Station'}</span></div><span>${telemetry?'Telemetry received':'Commands sent'} · ${events.length} recent</span></header><div class="communication-browser"><nav aria-label="Recent messages">${events.map(event=>`<button data-communication-message="${esc(eventKey(event,kind))}" aria-pressed="${event===selectedEvent}"><strong>${esc(telemetry?event.name:event.id)}</strong><span>${clock(telemetry?event.received_at:event.sent_at)}<code>${midLabel(event.mid)}</code></span></button>`).join('')||`<span class="communication-empty">${telemetry?(connected?'Waiting for telemetry':'Connect to receive telemetry'):'No commands sent'}</span>`}</nav>${selectedEvent?messageDetails(selectedEvent,kind,catalog,helpers):'<div class="communication-empty">No messages in this session</div>'}</div></section>
 </div>`;
}
