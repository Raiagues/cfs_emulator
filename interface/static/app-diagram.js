import {icon} from './ui.js';

const unique=items=>[...new Map(items.filter(Boolean).map(item=>[item.id||item.path+':'+item.line+':'+item.symbol,item])).values()];
const reference=item=>item?.path?item:item?.source?.path?{...item.source,symbol:item.symbol||item.name||item.source.symbol}:null;
const packetId=item=>item?.mid||item;
const packetName=item=>packetId(item)?.symbol||packetId(item)?.expression||'Message';
const sameMessage=(a,b)=>{a=packetId(a);b=packetId(b);return a&&b&&(a.value!=null&&b.value!=null?a.value===b.value:!!a.symbol&&a.symbol===b.symbol);};
const labelFunction=(app,symbol)=>{const prefix=app.name.toUpperCase()+'_';return symbol?.startsWith(prefix)?symbol.slice(prefix.length):symbol||'Source';};

function sourceButton(state,source,label,esc,classes='',extra=''){
 const ref=reference(source);if(!ref)return `<span class="${classes}">${label}</span>`;
 const selected=state.archSource===ref.path+':'+ref.line;
 return `<button class="app-map-source ${classes} ${selected?'selected':''}" data-arch-source="${esc(ref.path)}" data-line="${ref.line||1}" data-end-line="${ref.end_line||ref.line||1}" data-symbol="${esc(ref.symbol||source?.name||'Source')}" ${extra} title="${esc(ref.path+':'+(ref.line||1))}">${label}</button>`;
}

function functionCard(state,app,fn,esc){
 const resources=app.behavior?.details?.function_resources?.[fn.symbol]||{};
 const chips=[...new Map([...(resources.tables||[]).map(resource=>({...resource,kind:'table'})),...(resources.libraries||[]).map(resource=>({...resource,kind:'library'}))].map(resource=>[resource.kind+':'+resource.name,resource])).values()];
 return `<div class="app-map-function">${sourceButton(state,fn,`<i>ƒ</i><code>${esc(labelFunction(app,fn.symbol))}</code>${fn.symbol===app.behavior?.entry?.symbol?'<small>entry</small>':''}`,esc,'app-map-function-name')}${chips.length?`<div class="app-map-resources">${chips.map(resource=>sourceButton(state,resource.definition||resource.source,`${icon(resource.kind==='table'?'table':'files')}<span>${esc(resource.name)}</span>`,esc,'app-map-resource')).join('')}</div>`:''}</div>`;
}

function functionGrid(state,app,functions,esc){
 const items=unique(functions);if(!items.length)return '';
 return `<div class="app-map-functions">${items.slice(0,8).map(fn=>functionCard(state,app,fn,esc)).join('')}</div>${items.length>8?`<details class="app-map-more" data-detail-key="functions-${esc(app.name)}-${esc(items[0].symbol)}"><summary>${items.length-8} more functions</summary><div class="app-map-functions">${items.slice(8).map(fn=>functionCard(state,app,fn,esc)).join('')}</div></details>`:''}`;
}

function packetFields(state,packet,esc){
 const fields=packet.fields||[];if(!fields.length)return '';
 return `<details class="app-map-fields" data-detail-key="fields-${esc(packetName(packet))}-${esc(packet.packet_type||'')}"><summary>${icon('chevron-right')}Fields <small>${fields.length}</small></summary><div>${fields.map(field=>sourceButton(state,field,`<code>${esc(field.name)}</code><small>${esc(field.type)}${field.array?'['+esc(field.array)+']':''}</small>`,esc,'app-map-field')).join('')}</div></details>`;
}

function messages(state,app,esc,fallback){
 const details=app.behavior?.details||{},commands=details.commands||[],telemetry=details.telemetry||[];
 if(!commands.length&&!telemetry.length)return functionGrid(state,app,fallback,esc);
 return `<div class="app-map-messages">${commands.map(command=>`<section class="app-map-packet" data-bus-rx><div class="app-map-packet-title">${sourceButton(state,command.mid?.source||command.source,`<small class="app-map-tag">RX</small><code>${esc(packetName(command))}</code>${icon('link')}`,esc)}</div><div class="app-map-handlers">${(command.handlers||[]).map(handler=>`<div class="app-map-handler">${handler.cc?sourceButton(state,handler.cc.source||handler.source,`<small class="app-map-tag command">CC</small><code>${esc(handler.cc.symbol||handler.cc.expression)}</code>`,esc,'app-map-command-code'):''}${handler.handler?functionCard(state,app,handler.handler,esc):''}${packetFields(state,handler,esc)}</div>`).join('')}</div></section>`).join('')}${telemetry.map(packet=>`<section class="app-map-packet ${packet.publishers?.length?'published':''}" ${packet.publishers?.length?'data-bus-tx':''}><div class="app-map-packet-title"><span>${packet.publishers?.length?'Published telemetry':'Telemetry packet'}</span>${sourceButton(state,packet.mid?.source||packet.source,`<small class="app-map-tag">${packet.publishers?.length?'TX':'TLM'}</small><code>${esc(packetName(packet))}</code>${icon('link')}`,esc)}</div><div class="app-map-publishers">${functionGrid(state,app,packet.publishers||[],esc)}${packetFields(state,packet,esc)}</div></section>`).join('')}</div>`;
}

function groupsFor(app){
 const nodes=app.behavior?.nodes||[],functions=roles=>unique(nodes.filter(node=>roles.includes(node.role)).flatMap(node=>node.functions||[]));
 const entry=functions(['entry','initialize']),entryIds=new Set(entry.map(fn=>fn.id));
 const receive=functions(['receive','dispatch']).filter(fn=>!entryIds.has(fn.id)||fn.api);
 const packets=functions(['commands','publish']);
 const covered=new Set(nodes.flatMap(node=>node.functions.map(fn=>fn.id)));
 const helpers=new Set((app.call_edges||[]).filter(edge=>covered.has(edge.source)&&!covered.has(edge.target)).map(edge=>edge.target));
 const support=(app.functions||[]).filter(fn=>helpers.has(fn.id));
 const work=functions(['work','timer']);
 const groups=[{id:'entry',title:'Entry and initialization',roles:['entry','initialize'],functions:entry},
  {id:'messages',title:'Message handling',roles:['receive','dispatch'],functions:receive},
  {id:'packets',title:'Commands and telemetry',roles:['commands','publish'],functions:packets}];
 if(work.length)groups.push({id:'processing',title:nodes.find(node=>node.role==='work')?.title||'Application processing',roles:['work','timer'],functions:work});
 if(support.length)groups.push({id:'support',title:'Support routines',roles:[],functions:support});
 return groups.filter(group=>group.functions.length||(group.id==='packets'&&((app.behavior?.details?.commands?.length||0)+(app.behavior?.details?.telemetry?.length||0))));
}

function busProfile(app){
 const details=app.behavior?.details||{},nodes=app.behavior?.nodes||[];
 return {input:details.subscriptions||[],output:details.publications||details.telemetry||[],subscribes:!!details.subscriptions?.length||nodes.some(node=>node.apis?.some(api=>/^CFE_SB_Subscribe/.test(api))),publishes:!!details.publications?.length||!!details.telemetry?.length||nodes.some(node=>node.role==='publish')};
}

function peersFor(state,app){
 const own=busProfile(app);
 const peers=state.workspace.apps.filter(other=>other.enabled&&other!==app).map(other=>{
  const peer=busProfile(other),received=peer.input.filter(input=>own.output.some(output=>sameMessage(output,input))),sent=peer.output.filter(output=>own.input.some(input=>sameMessage(output,input))),receives=received.length>0,sends=sent.length>0;
  const conditions=[...new Set([...received,...sent].flatMap(item=>item.conditions||[]))];
  const special=other.behavior?.nodes.some(node=>node.role==='timer'||node.capabilities?.includes('network_send'));
  return {app:other,...peer,receives,sends,conditions,score:(receives||sends?10:0)+(special?2:0)};
 }).filter(peer=>peer.subscribes||peer.publishes).sort((a,b)=>b.score-a.score||a.app.name.localeCompare(b.app.name));
 const related=peers.filter(peer=>peer.sends||peer.receives);return related.length?related:peers;
}

export function renderAppDiagram(state,app,{esc}){
 const graph=app.behavior||{},groups=groupsFor(app),peers=peersFor(state,app),detail=graph.details||{};
 const countCommands=(detail.commands||[]).reduce((count,packet)=>count+(packet.handlers?.filter(handler=>handler.cc).length||0),0);
 const midHandlers=(detail.commands||[]).reduce((count,packet)=>count+(packet.handlers?.filter(handler=>!handler.cc).length||0),0);
 const peerCards=list=>list.map(peer=>`<button class="app-map-peer" data-arch-app="${esc(peer.app.name)}" data-peer="${esc(peer.app.name)}" title="${esc(peer.conditions.length?'Conditional source relationship: '+peer.conditions.join(' · '):peer.app.name)}" data-publishes="${peer.sends||peer.receives?peer.sends:peer.publishes}" data-subscribes="${peer.sends||peer.receives?peer.receives:peer.subscribes}"><span>${icon('cube')}<strong>${esc(peer.app.name.toUpperCase())}</strong>${icon('arrow-up-right')}</span><small>${peer.conditions.length?'Conditional MID match':peer.sends&&peer.receives?'Exchanges messages':peer.sends?'Publishes matching MIDs':peer.receives?'Subscribes to matching MIDs':peer.publishes&&peer.subscribes?'Publishes / subscribes':peer.publishes?'Publishes to SB':'Subscribes to SB'}</small></button>`).join('');
 return `<div class="app-map" data-app-map="${esc(app.name)}"><svg class="app-map-connections" aria-hidden="true"></svg><aside class="app-map-peers"><h3>Other apps</h3>${peerCards(peers.slice(0,3))}${peers.length>3?`<details class="app-map-peer-more" data-detail-key="peers-${esc(app.name)}"><summary>${peers.length-3} more apps</summary>${peerCards(peers.slice(3))}</details>`:''}${!peers.length?'<p>No other enabled bus participants.</p>':''}</aside><div class="app-map-bus-column"><span>cFE</span><div class="app-map-bus">Software Bus</div></div><section class="app-map-container"><header>${icon('code')}<strong>${esc(app.name.toUpperCase())}</strong></header>${app.libraries?.length?`<div class="app-map-library-row"><span>Libraries</span>${app.libraries.map(lib=>`<button data-arch-library="${esc(lib.name)}" title="${lib.calls.length?'API calls':'Build dependency'}">${icon('files')}${esc(lib.name)}</button>`).join('')}</div>`:''}<div class="app-map-sections">${groups.map(group=>{
 const packetSummary=group.id==='packets'&&(detail.commands?.length||detail.telemetry?.length)?`${countCommands?countCommands+' command codes':midHandlers+' MID handlers'} · ${detail.telemetry?.length||0} telemetry ${(detail.telemetry?.length||0)===1?'packet':'packets'}`:`${group.functions.length} functions`;
 const selected=group.functions.some(fn=>state.archSource===fn.path+':'+fn.line);
 return `<details class="app-map-section ${selected?'selected':''}" data-section="${group.id}" data-detail-key="app-${esc(app.name)}-${group.id}"><summary><span class="app-map-chevron">${icon('chevron-right')}</span><span class="app-map-section-title"><strong>${esc(group.title)}</strong><small>${packetSummary}</small></span>${sourceButton(state,group.functions[0],`${icon('code')}Code`,esc,'app-map-code',`data-arch-expand="${group.id}"`)}</summary><div class="app-map-section-body">${group.id==='packets'?messages(state,app,esc,group.functions):functionGrid(state,app,group.functions,esc)}</div></details>`;
 }).join('')}</div></section></div>`;
}

let observer,events;
export function layoutAppDiagram(state){
 observer?.disconnect();events?.abort();
 const diagram=document.querySelector('.app-map');if(!diagram)return;
 const app=state.workspace.apps.find(app=>app.name===diagram.dataset.appMap);if(!app)return;
 const groups=groupsFor(app),graph=app.behavior||{},own=busProfile(app);
 const draw=()=>{
  if(!diagram.isConnected)return;
  const bounds=diagram.getBoundingClientRect(),svg=diagram.querySelector('.app-map-connections'),bus=diagram.querySelector('.app-map-bus').getBoundingClientRect();
  svg.setAttribute('viewBox',`0 0 ${bounds.width} ${bounds.height}`);
  const paths=[],line=(x1,y1,x2,y2,kind='')=>paths.push(`<path class="${kind}" d="M${x1-bounds.x} ${y1-bounds.y} H${x2-bounds.x}" marker-end="url(#app-map-arrow)"/>`);
  for(const peer of diagram.querySelectorAll('.app-map-peer')){
   if(peer.getClientRects().length===0||peer.closest('details')&&!peer.closest('details').open)continue;
   const r=peer.getBoundingClientRect(),y=r.y+r.height/2;
   if(peer.dataset.publishes==='true')line(r.right,y-3,bus.left-3,y-3);
   if(peer.dataset.subscribes==='true')line(bus.left,y+3,r.right+3,y+3);
  }
  const section=diagram.querySelector('[data-section=packets]')||diagram.querySelector('[data-section=messages]');
  if(section){
   const packets=section.open?[...section.querySelectorAll('[data-bus-rx],[data-bus-tx]')]:[];
   if(packets.length){for(const packet of packets){const r=packet.getBoundingClientRect(),y=r.y+25;if(packet.hasAttribute('data-bus-rx'))line(bus.right,y,r.left-3,y);else line(r.left,y,bus.right+3,y);}}
   else{const r=section.getBoundingClientRect(),y=r.y+Math.min(r.height/2,34);if(own.subscribes)line(bus.right,y-4,r.left-3,y-4);if(own.publishes)line(r.left,y+4,bus.right+3,y+4);}
  }
  // Vertical arrows exist only where source calls connect neighboring groups.
  for(let i=1;i<groups.length;i++){
   const before=groups[i-1],after=groups[i];
   if(!(graph.edges||[]).some(edge=>before.roles.includes(edge.source)&&after.roles.includes(edge.target)))continue;
   const a=diagram.querySelector(`[data-section="${before.id}"]`).getBoundingClientRect(),b=diagram.querySelector(`[data-section="${after.id}"]`).getBoundingClientRect(),x=a.x+a.width/2-bounds.x;
   paths.push(`<path class="app-map-flow" d="M${x} ${a.bottom-bounds.y} V${b.top-bounds.y-3}" marker-end="url(#app-map-arrow)"/>`);
  }
  svg.innerHTML='<defs><marker id="app-map-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M1 1L5 3L1 5"/></marker></defs>'+paths.join('');
 };
 events=new AbortController();(diagram.closest('.architecture-pane-content')||diagram.closest('.architecture-scroll')).addEventListener('scroll',draw,{passive:true,signal:events.signal});
 observer=new ResizeObserver(draw);observer.observe(diagram);for(const section of diagram.querySelectorAll('details'))observer.observe(section);requestAnimationFrame(draw);
}
