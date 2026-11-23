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
const countText=value=>Number.isFinite(value)?value.toLocaleString():'0';
function commandTree(v) {
  const groups=new Map();
  for(const app of v.catalog?.apps||[])groups.set(app.name,[]);
  for(const app of v.catalog?.unavailable_apps||[])groups.set(app.app,[]);
  for(const command of v.catalog?.commands||[]){if(!groups.has(command.app))groups.set(command.app,[]);groups.get(command.app).push(command);}
  const unresolved=v.catalog?.unresolved_commands||[];
  return [...groups].sort(([a],[b])=>rank(a)-rank(b)||a.localeCompare(b)).map(([app,commands])=>{
    const missing=unresolved.filter(c=>c.app===app), open=v.commandGroups.has(app), unavailable=v.catalog?.unavailable_apps?.find(a=>a.app===app);
    return `<section class="contact-tree">${groupButton(app,commands.length+missing.length,open,'command')}${open?`<div>${commands.map(c=>`<button type="button" class="contact-pick" data-pick="${esc(c.id)}" aria-pressed="${v.command?.id===c.id}" title="${esc(c.id)} · ${hex(c.mid)}">${icon('send')}<span>${esc(commandName(c))}</span><small>FC ${c.code}</small><small class="contact-count" title="Commands sent in this connection">↑ ${countText(v.station.communication?.commands?.[c.id]||0)}</small></button>`).join('')}${missing.map(c=>`<button type="button" class="contact-pick" disabled title="${esc(c.reason)}"><span>${esc(c.id)}</span><small>Unavailable</small></button>`).join('')}${!commands.length&&!missing.length?'<p class="contact-none">'+esc(unavailable?.reason||'No command definitions')+'</p>':''}</div>`:''}</section>`;
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
      return `<button type="button" class="contact-packet" data-packet="${esc(p.id)}" aria-expanded="${expanded}" aria-pressed="${v.routePacket?.id===p.id}" title="${esc(p.id)}"><span class="chevron">${expanded?'⌄':'›'}</span>${icon('download')}<span>${esc(p.id.replace(new RegExp('^'+app.toUpperCase()+'_'),''))}</span><small>${hex(p.mid)}</small><small class="contact-count" title="Packets received in this connection">↓ ${countText(live?.count||0)}</small></button>${expanded?`<div class="contact-fields">${(p.fields||[]).map(f=>{const value=live?.values?.[f.name];const text=value==null?'—':typeof value==='object'?JSON.stringify(value):String(value);return `<div class="contact-value"><code title="${esc(f.name)}">${esc(f.name)}</code><small>${esc(typeName(f))}</small><output title="${esc(text)}">${esc(text)}</output></div>`;}).join('')}<small class="packet-meta">${p.size} bytes${live?' · '+new Date(live.received_at*1000).toLocaleTimeString():''}</small></div>`:''}`;
    }).join('')||'<p class="contact-none">No telemetry definitions</p>':''}</section>`;
  }).join('');
}
// Display only participants whose configured relationships match the selected MID.
// A confirmed reply adds its own MID; it is never inferred from an unrelated app.
export function contactRouteModel(catalog, selection, replyMid) {
  const routes=catalog?.first_contact_routes||{},names=new Set((catalog?.apps||[]).map(a=>a.name));
  const selectedMid=Number.isInteger(selection?.mid)?selection.mid:null,isCommand=selectedMid!==null&&!!(selectedMid&0x1000);
  const downMid=Number.isInteger(replyMid)?replyMid:!isCommand?selectedMid:null;
  const mids=new Set([selectedMid,downMid].filter(mid=>mid!==null));
  const applications=routes.applications||{},relations=new Map([...names].map(name=>[name,{subscriptions:[],publications:[]}]));
  function add(app,direction,row) {
    if(!names.has(app)||!mids.has(row.mid))return;
    const rows=relations.get(app)[direction];
    if(!rows.some(ref=>ref.mid===row.mid&&ref.pipe===row.pipe))rows.push(row);
  }
  for(const [app,io] of Object.entries(applications))for(const direction of ['subscriptions','publications'])
    for(const row of io[direction]||[])add(app,direction,row);
  if(isCommand)for(const row of routes.commands?.[selection.id]||[])
    if(row.mid===selectedMid)add(row.app,'subscriptions',row);
  for(const mid of mids)for(const ref of routes.returns?.[mid]?.publishers||[])
    add(ref.app||routes.returns[mid].app,'publications',{...ref,mid});
  const members=(direction,mid)=>[...relations].filter(([,io])=>io[direction].some(row=>row.mid===mid)).map(([name])=>name);
  const receivers=isCommand?members('subscriptions',selectedMid):[];
  const recipients=[...new Set([selection?.app,...receivers].filter(name=>receivers.includes(name)))];
  const packet=downMid!==null?routes.returns?.[downMid]:null;
  const producers=downMid!==null?members('publications',downMid):[];
  const ingress=isCommand&&recipients.length&&names.has(routes.ingress?.app)?routes.ingress.app:null;
  const downlink=downMid!==null&&(packet||(catalog?.transport?.subscriptions||[]).some(row=>row.mid===downMid));
  const egress=(downlink||recipients.includes(routes.egress?.app))&&names.has(routes.egress?.app)?routes.egress.app:null;
  if(ingress)add(ingress,'publications',{mid:selectedMid,source:routes.ingress.publish,transport:true});
  if(egress&&downMid!==null)add(egress,'subscriptions',{mid:downMid,pipe:routes.egress.pipe,source:routes.egress.subscribe,transport:true});
  const involved=[...relations].filter(([,io])=>io.subscriptions.length||io.publications.length).map(([name])=>name);
  const returnsTo=downMid!==null?members('subscriptions',downMid).filter(name=>!recipients.includes(name)):[];
  const lower=[...new Set([egress,...returnsTo,...(isCommand?producers.filter(name=>!recipients.includes(name)):[])].filter(name=>name&&involved.includes(name)))];
  const upper=[...new Set([ingress,...recipients,...involved].filter(name=>name&&involved.includes(name)&&!lower.includes(name)))];
  // Keep the real uplink above the bus, even when it also publishes the reply.
  if(ingress&&lower.includes(ingress)){lower.splice(lower.indexOf(ingress),1);upper.unshift(ingress);}
  const columns=Math.max(2,upper.length,lower.length),width=Math.max(760,240+columns*180),height=270,busY=135;
  const nodes=[upper,lower].flatMap((row,index)=>row.map((name,column)=>({name,row:index,
    x:300+column*(width-450)/(columns-1),y:index?213:58,...relations.get(name)})));
  return {width,height,busY,nodes,ingress,egress,recipients,producers,packet,selectedMid,downMid,isCommand};
}
function routeCard(node,model){
  const transport=node.name===model.ingress?'commands in':node.name===model.egress?'telemetry out':null;
  const note=transport||`${node.subscriptions.length} in · ${node.publications.length} out`;
  return `<div class="contact-route-node" data-route-node="app" data-app="${esc(node.name)}" data-row="${node.row}" style="left:${node.x/model.width*100}%;top:${node.y/model.height*100}%"><span class="node-tile">${icon(transport?'inbox':'app-window')}</span><span><strong title="${esc(node.name)}">${esc(node.name)}</strong><small title="${esc(note)}">${esc(note)}</small></span></div>`;
}
export function routeMarkup(catalog, selection, replyMid, target, replay) {
  const model=contactRouteModel(catalog,selection,replyMid),{width,height,busY,nodes,ingress,egress,recipients,producers}=model;
  const port=catalog?.transport||{};
  const branches=nodes.map(node=>['subscriptions','publications'].map(direction=>[true,false].map(isCommand=>{
    const rows=node[direction].filter(r=>!!(r.mid&0x1000)===isCommand);
    if(!rows.length)return '';
    const incoming=direction==='subscriptions',description=[...new Set(rows.map(r=>hex(r.mid)+(r.pipe?' · '+r.pipe:'')))].join('\n');
    return `<path class="bus-branch ${isCommand?'command-route':'return-route'}" data-bus-app="${esc(node.name)}" data-direction="${incoming?'in':'out'}" data-packet-kind="${isCommand?'command':'telemetry'}"><title>${esc(node.name+' '+(incoming?'subscribes':'publishes')+'\n'+description)}</title></path>`;
  }).join('')).join('')).join('');
  const midLabel=[...new Set([model.selectedMid,model.downMid].filter(mid=>mid!==null))].map(hex).join(' · ');
  return `<section class="contact-trip" aria-label="Configured route for the selected MID"><header><strong>Round trip <small>${esc(midLabel)}${midLabel?' · ':''}${nodes.length} apps</small></strong><span><i></i>command <i></i>telemetry</span></header><div class="contact-route-scroll" tabindex="0" aria-label="Selected message route diagram"><div class="contact-route" style="height:${height}px;min-width:${width}px" data-width="${width}" data-height="${height}" data-bus-y="${busY}" data-ingress="${esc(ingress||'')}" data-egress="${esc(egress||'')}">
    <svg class="contact-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><defs><marker id="contact-command-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M1 0L4 3L1 6"/></marker><marker id="contact-telemetry-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M1 0L4 3L1 6"/></marker></defs><rect class="flight-area" x="180" y="8" width="${width-192}" height="${height-16}" rx="8"/><rect class="software-bus" x="220" y="${busY-5}" width="${width-252}" height="10" rx="3"/>
    ${branches}${ingress?recipients.map(app=>`<path class="command-route selected-route" data-up data-recipient="${esc(app)}" marker-end="url(#contact-command-arrow)"/>`).join(''):''}${egress?producers.map(app=>`<path class="return-route selected-route" data-down data-producer="${esc(app)}" marker-end="url(#contact-telemetry-arrow)"/>`).join(''):''}<circle class="contact-dot" r="4" style="display:none"/></svg>
    <span class="route-system" style="left:${186/width*100}%">cFS · ${esc({native:'this computer · native',qemu:'Raspberry Pi 4B · emulator',physical:'Raspberry Pi 4B · board'}[target])}</span><span class="route-ground">GROUND</span>${ingress?`<span class="route-port up" style="left:${166/width*100}%;top:${120/height*100}%">UDP ${esc(port.command_port??'')}</span>`:''}${egress?`<span class="route-port down" style="left:${166/width*100}%;top:${152/height*100}%">UDP ${esc(port.telemetry_port??'')}</span>`:''}<span class="route-bus" style="left:${224/width*100}%;top:${151/height*100}%">Software Bus</span>
    <div class="contact-route-node vertical" data-route-node="ground" style="left:${78/width*100}%;top:50%"><span class="node-tile">${icon('ground-link')}</span><span><strong>Ground</strong><small>your computer</small></span></div>${nodes.map(n=>routeCard(n,model)).join('')}${!nodes.length?'<span class="contact-route-empty">No resolved route for this MID</span>':''}
    </div></div>${replay?`<div class="contact-playback"><span class="play-bars">${'<i></i>'.repeat(7)}</span><span data-caption>Confirmed response · route replay</span><button type="button" data-play aria-label="Pause or resume replay">Ⅱ</button><button type="button" data-step aria-label="Next hop">›</button></div>`:''}</section>`;
}
// Match actual card edges after layout, keeping readable labels at every width.
export function layoutContactRoute(root) {
  const route=root.querySelector('.contact-route'),svg=route?.querySelector('.contact-svg');
  if(!svg)return;const bounds=svg.getBoundingClientRect(),height=Number(route.dataset.height),width=Number(route.dataset.width),busY=Number(route.dataset.busY);
  if(!bounds.width||!bounds.height)return;
  const boxes=new Map();let ground;
  for(const node of route.querySelectorAll('[data-route-node]')){
    const rect=node.getBoundingClientRect(),sx=width/bounds.width,sy=height/bounds.height;
    const left=(rect.left-bounds.left)*sx,top=(rect.top-bounds.top)*sy,w=rect.width*sx,h=rect.height*sy;
    const box={left,top,right:left+w,bottom:top+h,cx:left+w/2,cy:top+h/2,width:w,height:h,anchor:Number(node.dataset.row)?top:top+h};
    if(node.dataset.routeNode==='ground')ground=box;else boxes.set(node.dataset.app,box);
  }
  const ingress=boxes.get(route.dataset.ingress),egress=boxes.get(route.dataset.egress);
  for(const path of svg.querySelectorAll('[data-bus-app]')){
    const node=boxes.get(path.dataset.busApp);if(!node)continue;
    const incoming=path.dataset.direction==='in',cmd=path.dataset.packetKind==='command',x=node.cx+(incoming?-1:1)*(cmd?8:4),y=busY+(cmd?-2:2);
    path.setAttribute('d',incoming?`M${x} ${y} V${node.anchor}`:`M${x} ${node.anchor} V${y}`);
    path.setAttribute('marker-end',`url(#contact-${cmd?'command':'telemetry'}-arrow)`);
  }
  if(!ground)return;
  for(const path of svg.querySelectorAll('[data-up]')){
    const recipient=boxes.get(path.dataset.recipient);if(!ingress||!recipient)continue;
    const toBus=recipient===ingress?'':` M${ingress.cx-8} ${ingress.anchor} V${busY-2} H${recipient.cx-8} V${recipient.anchor}`;
    path.setAttribute('d',`M${ground.right} ${ground.cy-ground.height*.15} H166 V${ingress.cy} H${ingress.left}${toBus}`);
  }
  for(const path of svg.querySelectorAll('[data-down]')){
    const producer=boxes.get(path.dataset.producer);if(!producer||!egress)continue;
    const fromBus=producer===egress?'':`M${producer.cx+8} ${producer.anchor} V${busY+2} H${egress.cx+8} V${egress.anchor} `;
    path.setAttribute('d',`${fromBus}M${egress.left} ${egress.cy} H166 V${ground.cy+ground.height*.15} H${ground.right}`);
  }
}
function history(v) {
  const rows=(v.station.commands||[]).filter(c=>!c.automatic).slice(-30).reverse();
  return `<section class="contact-history" aria-label="Sent and received"><header><span>Sent</span><span class="history-labels">${['Ground',v.catalog?.first_contact_routes?.ingress?.app||'—','app',v.catalog?.first_contact_routes?.egress?.app||'—','Ground'].map(x=>`<span>${x}</span>`).join('')}</span><span>Came back</span><span></span></header><div class="contact-history-rows">${rows.map(c=>{const r=v.receipts.get(c.event_id),done=!!r,routes=v.catalog?.first_contact_routes||{},appHop=(routes.commands?.[c.id]||[]).some(sub=>![routes.ingress?.app,routes.egress?.app].includes(sub.app));return `<div class="contact-history-row"><span><strong>${esc(c.app+' '+commandName(c))}</strong><small>${esc(Object.entries(c.values||{}).map(([k,x])=>k+' = '+(typeof x==='object'?JSON.stringify(x):x)).join(', '))}</small></span><span class="history-dots" data-done="${done}">${[0,1,2,3,4].map((_,i)=>{const skipped=i===2&&!appHop;return `<i class="${skipped?'skipped':done?'done':i===0?'sent':''}"${skipped?' title="No separate application hop"':''}>${skipped?'':done?'✓':i===0?'·':''}</i>`;}).join('')}</span><span class="history-reply">${r?`<span><b>${r.message?'INFO':'TLM'}</b>${esc(r.message||'Telemetry received')}</span>${r.increase?`<span><b>HK</b>CommandCounter ${r.baseline} → ${r.count}</span>`:''}`:'<small>Sent · awaiting a confirmed reply</small>'}</span><time>${new Date(c.sent_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time></div>`;}).join('')||'<span class="contact-history-empty">—</span>'}</div></section>`;
}
export function renderContact(v) {
  const f=v.station.first_flight||{},command=v.command, fields=userFields(command);
  const enabled=!!f.downlink_receipt,answer=!!(f.answer&&f.receipt?.reply&&f.receipt?.increase),stage=answer?2:enabled?1:0;
  return `<div class="contact-layout"><aside class="contact-browser" aria-label="Commands"><header>Commands <span class="contact-total" title="Commands sent since this connection opened">↑ ${countText(v.station.communication?.totals?.commands_sent??(v.station.communication?.apps||[]).reduce((n,a)=>n+a.commands_sent,0))} sent</span></header><nav>${commandTree(v)}</nav></aside><main class="contact-main">
    ${v.guided?`<section class="contact-stages" aria-label="Your first event">${['Telemetry on','First command','Answer'].map((label,i)=>`<button type="button" data-stage="${i}" data-fact="${i<stage||answer?'done':i===stage?'current':'waiting'}"><i>${i<stage||answer?'✓':i+1}</i><span>${label}<code>${['to_lab · ENABLE_OUTPUT','sample_app · NOOP','INFO + CommandCounter ↑'][i]}</code></span></button>`).join('')}</section>`:''}
    <form class="contact-command" data-scene="${esc((command?.id||'')+'/'+(v.station.communication?.since||'offline'))}" data-command="${esc(command?.id||'')}"><div class="contact-command-name"><div><small>${esc(command?.app||'')}</small><span>FC ${esc(command?.code??'')}</span></div><h2 title="${esc(commandName(command))}">${esc(commandName(command)||v.missingCommand||'Loading commands…')}</h2><span>${command?.id===f.enable_command?'telemetry → ground':command?.id===f.noop_command?'answers, changes nothing':hex(command?.mid)}</span></div><div class="contact-parameters"><header>Parameters <small>${esc(command?.struct||'')}</small></header>${fields.length?fields.map(fieldDef=>field(fieldDef,v.values[fieldDef.name])).join(''):'<span class="no-parameters">None. The packet is only the header.</span>'}</div><div class="contact-actions"><button type="submit" class="contact-send" ${v.disabled?'disabled':''}>${icon('send')}${esc(v.sendLabel)}</button><button type="button" data-bytes ${command?'':'disabled'}>See the ${command?.size??'…'} bytes</button></div></form>
    ${v.error?`<p class="contact-note" role="status">${esc(v.error)}</p>`:''}
    ${routeMarkup(v.catalog,v.routePacket||command,v.replay?.mid,v.target,v.replay)}${history(v)}
    ${answer&&v.guided?`<a class="contact-next" href="${v.nextUrl}">Next: create your app →</a>`:''}
    </main><aside class="contact-telemetry" aria-label="Telemetry"><header>Telemetry <span class="contact-total" title="CCSDS packets received since this connection opened">↓ ${countText(v.station.communication?.totals?.telemetry_received??v.station.received??0)} received</span></header><nav>${telemetryTree(v)}</nav></aside></div>`;
}
export function renderPacketPreview(preview, command) {
  const sections=preview.segments||[];
  return `<div class="contact-packet-preview"><header><strong>${esc(commandName(command))}</strong><span>${preview.size} bytes on the wire</span><button type="button" data-close-packet aria-label="Close packet preview">×</button></header><div class="packet-bands"><span>CCSDS header · 6 B</span><span>Command · ${command.header_size-6} B</span><span>Your data · ${command.size-command.header_size} B</span></div><div class="packet-cells">${sections.map(f=>`<section data-kind="${esc(f.kind==='header'&&f.offset>=6?'command':f.kind||'payload')}"><span>${esc(f.name)}</span><code>${esc(f.hex.match(/.{1,2}/g)?.join(' ').toUpperCase()||'')}</code><small>byte ${f.offset} · ${f.size} B</small></section>`).join('')}</div></div>`;
}
