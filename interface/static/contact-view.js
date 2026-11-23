import {escapeHtml as esc} from './dom.js';
import {icon} from './ui.js';
export const hex = value => Number.isInteger(value) ? '0x'+value.toString(16).toUpperCase().padStart(4,'0') : '';
export function commandName(command) {
  if (!command) return '';
  if (command.id.endsWith('_OUTPUT_ENABLE_CC')) return 'ENABLE_OUTPUT';
  const prefix=command.app.toUpperCase()+'_';
  return command.id.replace(new RegExp('^'+prefix),'').replace(/_(CC|MID)$/,'');
}
export const userFields = command => (command?.fields||[]).filter(f=>! /^(padding|reserved|spare)/i.test(f.name.split('.').at(-1)));
export function fieldValues(command, draft={}) {
  return Object.fromEntries(userFields(command).map(f=>{
    let value=draft[f.name]??(f.format==='?'?false:'');
    if(f.count>1 && !['s','raw'].includes(f.format)) {
      try {value=JSON.parse(value);} catch {throw Error(f.name+': enter an array of '+f.count+' values, such as [1, 2].');}
      if(!Array.isArray(value)||value.length!==f.count)throw Error(f.name+': expected '+f.count+' values.');
      if('bBhHiIqQ'.includes(f.format)&&value.some(v=>typeof v==='number'&&!Number.isSafeInteger(v)))throw Error(f.name+': quote large integers to preserve every digit.');
      // Keep 64-bit integers exact: users can enter them as quoted decimal strings.
    }
    return [f.name,value];
  }));
}
const typeName=f=>f.type+(f.format==='raw'?' · '+f.size+' B hex':f.count>1?'['+f.count+']':'');
function field(f, value) {
  const common=`name="${esc(f.name)}" data-field="${esc(f.name)}" aria-label="${esc(f.name)}"`;
  let input;
  if(f.format==='?'&&f.count===1)input=`<select ${common}><option value="false" ${value?'':'selected'}>false</option><option value="true" ${value?'selected':''}>true</option></select>`;
  else if(f.count>1&&!['s','raw'].includes(f.format))input=`<textarea ${common} rows="2" placeholder="${esc(f.format==='q'||f.format==='Q'?'[\"123\", \"456\", …]':'[1, 2, …]')}" required spellcheck="false">${esc(value??'')}</textarea>`;
  else input=`<input ${common} value="${esc(value??'')}" ${f.format==='s'?'maxlength="'+(f.count-1)+'"':f.format==='raw'?'placeholder="Hex bytes"':'placeholder="Value" required'} spellcheck="false" autocomplete="off">`;
  return `<label class="contact-field"><span title="${esc(f.name)}">${esc(f.name)}<small>${esc(typeName(f))}</small></span>${input}</label>`;
}
const groupButton=(app, count, open, kind)=>`<button type="button" class="contact-group" data-${kind}-group="${esc(app)}" aria-expanded="${open}"><span class="chevron">${open?'⌄':'›'}</span><span>${esc(app)}</span><small>${count}</small></button>`;
function commandTree(v) {
  const groups=new Map();
  for(const app of v.catalog?.apps||[])groups.set(app.name,[]);
  for(const app of v.catalog?.unavailable_apps||[])groups.set(app.app,[]);
  for(const command of v.catalog?.commands||[]){if(!groups.has(command.app))groups.set(command.app,[]);groups.get(command.app).push(command);}
  const unresolved=v.catalog?.unresolved_commands||[];
  return [...groups].sort(([a],[b])=>rank(a)-rank(b)||a.localeCompare(b)).map(([app,commands])=>{
    const missing=unresolved.filter(c=>c.app===app), open=v.commandGroups.has(app), unavailable=v.catalog?.unavailable_apps?.find(a=>a.app===app);
    return `<section class="contact-tree">${groupButton(app,commands.length+missing.length,open,'command')}${open?`<div>${commands.map(c=>`<button type="button" class="contact-pick" data-pick="${esc(c.id)}" aria-pressed="${v.command?.id===c.id}" title="${esc(c.id)} · ${hex(c.mid)}">${icon('send')}<span>${esc(commandName(c))}</span><small>FC ${c.code}</small></button>`).join('')}${missing.map(c=>`<button type="button" class="contact-pick" disabled title="${esc(c.reason)}"><span>${esc(c.id)}</span><small>Unavailable</small></button>`).join('')}${!commands.length&&!missing.length?'<p class="contact-none">'+esc(unavailable?.reason||'No command definitions')+'</p>':''}</div>`:''}</section>`;
  }).join('');
}
function rank(app){return app==='to_lab'?0:app==='sample_app'?1:2;}
function telemetryTree(v) {
  const groups=new Map((v.catalog?.apps||[]).map(app=>[app.name,[]]));
  for(const p of v.catalog?.packets||[]){if(!groups.has(p.app))groups.set(p.app,[]);groups.get(p.app).push(p);}
  return [...groups].sort(([a],[b])=>rank(a)-rank(b)||a.localeCompare(b)).map(([app,packets])=>{
    const open=v.telemetryGroups.has(app);
    return `<section class="contact-tree">${groupButton(app,packets.length,open,'telemetry')}${open?packets.map(p=>{
      const live=(v.station.packets||[]).find(row=>row.mid===p.mid), expanded=v.packetGroups.has(p.id);
      return `<button type="button" class="contact-packet" data-packet="${esc(p.id)}" aria-expanded="${expanded}" title="${esc(p.id)}"><span class="chevron">${expanded?'⌄':'›'}</span>${icon('download')}<span>${esc(p.id.replace(new RegExp('^'+app.toUpperCase()+'_'),''))}</span><small>${hex(p.mid)}</small></button>${expanded?`<div class="contact-fields">${(p.fields||[]).map(f=>{const value=live?.values?.[f.name];const text=value==null?'—':typeof value==='object'?JSON.stringify(value):String(value);return `<div class="contact-value"><code title="${esc(f.name)}">${esc(f.name)}</code><small>${esc(typeName(f))}</small><output title="${esc(text)}">${esc(text)}</output></div>`;}).join('')}<small class="packet-meta">${p.size} bytes${live?' · '+new Date(live.received_at*1000).toLocaleTimeString():''}</small></div>`:''}`;
    }).join('')||'<p class="contact-none">No telemetry definitions</p>':''}</section>`;
  }).join('');
}
function routeCard(x,y,name,note,glyph,kind,vertical=false){return `<div class="contact-route-node ${vertical?'vertical':''}" data-route-node="${kind}" style="left:${x/7.6}%;top:${y/2.7}%"><span class="node-tile">${icon(glyph)}</span><span><strong title="${esc(name)}">${esc(name)}</strong><small title="${esc(note)}">${esc(note)}</small></span></div>`;}
export function routeMarkup(catalog, command, replyMid, target, replay) {
  const routes=catalog?.first_contact_routes||{}, ingress=routes.ingress,egress=routes.egress;
  const sub=routes.commands?.[command?.id]?.[0], returns=routes.returns||{};
  const app=sub?.app||command?.app||'Application', special=[ingress?.app,egress?.app].includes(app);
  const context=special?(catalog?.apps||[]).find(a=>a.name==='sample_app')?.name:app;
  const packet=returns[replyMid]||Object.values(returns).find(p=>p.app===(context||app)&&p.publishers?.length)||Object.values(returns).find(p=>p.app===app&&p.publishers?.length);
  const producer=packet?.app;
  const up=ingress&&sub?`M143 122 H205 V58 H236 M292 83 V132 ${app===egress?.app?'H308 V188':app===ingress.app?'H308 V83':'H604 V83'}`:'';
  const starts={[ingress?.app]:'M308 83',[egress?.app]:'M308 188',[app]:'M620 83'};
  if(app===ingress?.app)starts[app]='M308 83';if(app===egress?.app)starts[app]='M308 188';
  if(context&&!special)starts[context]='M620 83';
  if(context&&special)starts[context]='M620 83';
  const separate=producer&&![ingress?.app,egress?.app,app,context].includes(producer);
  const start=separate?'M612 194':starts[producer];
  const down=egress&&packet?.publishers?.length&&start?start+' V138 H308 V188 M236 212 H205 V148 H143':'';
  const port=catalog?.transport||{};
  return `<section class="contact-trip" aria-label="Where the command goes"><header><strong>Round trip</strong><span><i></i>command <i></i>telemetry</span></header><div class="contact-route-scroll" tabindex="0" aria-label="Command route diagram"><div class="contact-route" data-recipient="${app===egress?.app?'egress':app===ingress?.app?'ingress':'app'}" data-producer="${separate?'producer':producer===egress?.app?'egress':producer===ingress?.app?'ingress':'app'}">
    <svg class="contact-svg" viewBox="0 0 760 270" preserveAspectRatio="none" aria-hidden="true"><defs><marker id="contact-command-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M1 0L4 3L1 6"/></marker><marker id="contact-telemetry-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M1 0L4 3L1 6"/></marker></defs><rect class="flight-area" x="180" y="8" width="568" height="254" rx="8"/><rect class="software-bus" x="222" y="128" width="506" height="14" rx="3"/>
    ${up?`<path class="command-route" data-up d="${up}" marker-end="url(#contact-command-arrow)"/>`:''}${down?`<path class="return-route" data-down d="${down}" marker-end="url(#contact-telemetry-arrow)"/>`:''}<circle class="contact-dot" r="4" style="display:none"/></svg>
    <span class="route-system">cFS · ${esc({native:'this computer · native',qemu:'Raspberry Pi 4B · emulator',physical:'Raspberry Pi 4B · board'}[target])}</span><span class="route-ground">GROUND</span><span class="route-port up">UDP ${esc(port.command_port??'')}</span><span class="route-port down">UDP ${esc(port.telemetry_port??'')}</span><span class="route-bus" title="${esc(sub?hex(sub.mid)+' · '+sub.pipe:'')}">Software Bus</span>
    ${routeCard(78,135,'Ground','your computer','ground-link','ground',true)}${ingress?routeCard(300,58,ingress.app,'commands in','inbox','ingress'):''}
    ${context?routeCard(612,58,context,context==='sample_app'?'example app':'command destination','app-window','app'):''}${egress?routeCard(300,212,egress.app,'telemetry out','inbox','egress'):''}
    ${separate?routeCard(612,212,producer,'telemetry publisher','layers','producer'):(catalog?.apps||[]).some(a=>a.name==='cfe_evs')&&app!=='cfe_evs'?'<span class="route-passive" style="left:80.53%;top:78.52%">cfe_evs</span>':''}${(catalog?.apps||[]).some(a=>a.name==='sch_lab')&&app!=='sch_lab'?'<span class="route-passive" style="left:61.58%;top:78.52%">sch_lab</span>':''}
    </div></div>${replay?`<div class="contact-playback"><span class="play-bars">${'<i></i>'.repeat(7)}</span><span data-caption>Confirmed response · route replay</span><button type="button" data-play aria-label="Pause or resume replay">Ⅱ</button><button type="button" data-step aria-label="Next hop">›</button></div>`:''}</section>`;
}
// Cards retain readable CSS sizes while their anchors follow the SVG coordinate space.
// Only resize paths that the source-derived catalog already resolved.
export function layoutContactRoute(root) {
  const route=root.querySelector('.contact-route'),svg=route?.querySelector('.contact-svg');
  if(!svg)return;
  const bounds=svg.getBoundingClientRect();
  if(!bounds.width||!bounds.height)return;
  const box=kind=>{
    const node=route.querySelector('[data-route-node="'+kind+'"]');
    if(!node)return null;
    const rect=node.getBoundingClientRect(),sx=760/bounds.width,sy=270/bounds.height;
    const left=(rect.left-bounds.left)*sx,top=(rect.top-bounds.top)*sy;
    const width=rect.width*sx,height=rect.height*sy;
    return {left,top,right:left+width,bottom:top+height,cx:left+width/2,cy:top+height/2,width,height};
  };
  const ground=box('ground'),ingress=box('ingress'),egress=box('egress');
  if(!ground||!ingress)return;
  const elbow=ground.right+(ingress.left-ground.right)*.65;
  const command=svg.querySelector('[data-up]'),recipient=box(route.dataset.recipient);
  if(command&&recipient){
    const endX=recipient.cx+(route.dataset.recipient==='app'?-8:8);
    const endY=route.dataset.recipient==='egress'?recipient.top:recipient.bottom;
    command.setAttribute('d',`M${ground.right} ${ground.cy-ground.height*.15} H${elbow} V${ingress.cy} H${ingress.left} M${ingress.cx-8} ${ingress.bottom} V132 H${endX} V${endY}`);
  }
  const returned=svg.querySelector('[data-down]'),producer=box(route.dataset.producer);
  if(returned&&producer&&egress){
    const lower=['egress','producer'].includes(route.dataset.producer);
    const startX=producer.cx+(route.dataset.producer==='egress'?-8:8);
    const startY=lower?producer.top:producer.bottom;
    returned.setAttribute('d',`M${startX} ${startY} V138 H${egress.cx+8} V${egress.top} M${egress.left} ${egress.cy} H${elbow} V${ground.cy+ground.height*.15} H${ground.right}`);
  }
}
function history(v) {
  const rows=(v.station.commands||[]).filter(c=>!c.automatic).slice(-30).reverse();
  return `<section class="contact-history" aria-label="Sent and received"><header><span>Sent</span><span class="history-labels">${['Ground','ci_lab','app','to_lab','Ground'].map(x=>`<span>${x}</span>`).join('')}</span><span>Came back</span><span></span></header><div class="contact-history-rows">${rows.map(c=>{const r=v.receipts.get(c.event_id),done=!!r,routes=v.catalog?.first_contact_routes||{},appHop=(routes.commands?.[c.id]||[]).some(sub=>![routes.ingress?.app,routes.egress?.app].includes(sub.app));return `<div class="contact-history-row"><span><strong>${esc(c.app+' '+commandName(c))}</strong><small>${esc(Object.entries(c.values||{}).map(([k,x])=>k+' = '+(typeof x==='object'?JSON.stringify(x):x)).join(', '))}</small></span><span class="history-dots" data-done="${done}">${[0,1,2,3,4].map((_,i)=>{const skipped=i===2&&!appHop;return `<i class="${skipped?'skipped':done?'done':i===0?'sent':''}"${skipped?' title="No separate application hop"':''}>${skipped?'':done?'✓':i===0?'·':''}</i>`;}).join('')}</span><span class="history-reply">${r?`<span><b>${r.message?'INFO':'TLM'}</b>${esc(r.message||'Telemetry received')}</span>${r.increase?`<span><b>HK</b>CommandCounter ${r.baseline} → ${r.count}</span>`:''}`:'<small>Sent · awaiting a confirmed reply</small>'}</span><time>${new Date(c.sent_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time></div>`;}).join('')||'<span class="contact-history-empty">—</span>'}</div></section>`;
}
export function renderContact(v) {
  const f=v.station.first_flight||{},command=v.command, fields=userFields(command);
  const enabled=!!f.downlink_receipt,answer=!!(f.answer&&f.receipt?.reply&&f.receipt?.increase),stage=answer?2:enabled?1:0;
  return `<div class="contact-layout"><aside class="contact-browser" aria-label="Commands"><header>Commands</header><nav>${commandTree(v)}</nav></aside><main class="contact-main">
    ${v.guided?`<section class="contact-stages" aria-label="Your first event">${['Telemetry on','First command','Answer'].map((label,i)=>`<button type="button" data-stage="${i}" data-fact="${i<stage||answer?'done':i===stage?'current':'waiting'}"><i>${i<stage||answer?'✓':i+1}</i><span>${label}<code>${['to_lab · ENABLE_OUTPUT','sample_app · NOOP','INFO + CommandCounter ↑'][i]}</code></span></button>`).join('')}</section>`:''}
    <form class="contact-command" data-scene="${esc((command?.id||'')+'/'+(v.station.communication?.since||'offline'))}" data-command="${esc(command?.id||'')}"><div class="contact-command-name"><div><small>${esc(command?.app||'')}</small><span>FC ${esc(command?.code??'')}</span></div><h2 title="${esc(commandName(command))}">${esc(commandName(command)||'Loading commands…')}</h2><span>${command?.id===f.enable_command?'telemetry → ground':command?.id===f.noop_command?'answers, changes nothing':hex(command?.mid)}</span></div><div class="contact-parameters"><header>Parameters <small>${esc(command?.struct||'')}</small></header>${fields.length?fields.map(fieldDef=>field(fieldDef,v.values[fieldDef.name])).join(''):'<span class="no-parameters">None. The packet is only the header.</span>'}</div><div class="contact-actions"><button type="submit" class="contact-send" ${v.disabled?'disabled':''}>${icon('send')}${esc(v.sendLabel)}</button><button type="button" data-bytes ${command?'':'disabled'}>See the ${command?.size??'…'} bytes</button></div></form>
    ${v.error?`<p class="contact-note" role="status">${esc(v.error)}</p>`:''}
    ${routeMarkup(v.catalog,command,v.replay?.mid,v.target,v.replay)}${history(v)}
    ${answer&&v.guided?`<a class="contact-next" href="${v.nextUrl}">Next: create your app →</a>`:''}
    </main><aside class="contact-telemetry" aria-label="Telemetry"><header>Telemetry</header><nav>${telemetryTree(v)}</nav></aside></div>`;
}
export function renderPacketPreview(preview, command) {
  const sections=preview.segments||[];
  return `<div class="contact-packet-preview"><header><strong>${esc(commandName(command))}</strong><span>${preview.size} bytes on the wire</span><button type="button" data-close-packet aria-label="Close packet preview">×</button></header><div class="packet-bands"><span>CCSDS header · 6 B</span><span>Command · ${command.header_size-6} B</span><span>Your data · ${command.size-command.header_size} B</span></div><div class="packet-cells">${sections.map(f=>`<section data-kind="${esc(f.kind==='header'&&f.offset>=6?'command':f.kind||'payload')}"><span>${esc(f.name)}</span><code>${esc(f.hex.match(/.{1,2}/g)?.join(' ').toUpperCase()||'')}</code><small>byte ${f.offset} · ${f.size} B</small></section>`).join('')}</div></div>`;
}
