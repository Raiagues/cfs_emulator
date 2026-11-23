// The source index supplies navigation even before a compiled packet catalog exists.
import {icon} from './ui.js';
import {renderActivityProgress} from './activity-progress.js';

const tags = [
  ['brief','Description'],
  ['unit','Field unit'],
  ['range','Allowed range'],
  ['check','Validation rationale']
];
const tabs = [['source','Tags'],['packet','Packet'],['dispatch','Dispatch']];
const editAnchor = /^\s*\/\*\s*@studio\.edit ([a-z][a-z0-9_.-]*)\s*\*\/\s*$/;
const isC = path => /\.[ch]$/i.test(path);
const hex = number => Number.isInteger(number) ? '0x' + number.toString(16).toUpperCase() : '';

function commandEntries(state, app) {
  if (!app) return [];
  const routes = app?.behavior?.details?.commands || [];
  const build = state.workspace.builds?.[state.target];
  const compiled = state.catalogTarget===state.target && build?.current && build.fingerprint && state.catalog?.build_fingerprint===build.fingerprint ? state.catalog.commands || [] : [];
  const packets = compiled.filter(c => c.app === app?.name);
  const entries = routes.flatMap(route => (route.handlers || []).map(handler => {
    const id = handler.cc?.symbol || route.mid?.symbol;
    return {id,route,handler,packet:packets.find(p => p.id === id && p.mid === route.mid?.value)};
  })).filter(item => item.id);
  for (const packet of packets) {
    if (!entries.some(item => item.packet === packet)) entries.push({id:packet.id,packet});
  }
  return entries;
}

function sourceTags(content) {
  const found = [];
  // Consume strings and character literals so comment delimiters in them are ignored.
  const tokens = /"(?:\\[\s\S]|[^"\\\n])*("|$)|'(?:\\[\s\S]|[^'\\\n])*('|$)|\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$)/gm;
  let start = 0, line = 1;
  for (const token of content.matchAll(tokens)) {
    if (!token[0].startsWith('/')) continue;
    line += content.slice(start,token.index).split('\n').length - 1;
    start = token.index;
    const rows = token[0].slice(2).replace(/\*\/$/,'').split('\n');
    rows.forEach((row,i) => {
      for (const m of row.matchAll(/(?:^|(?<=\W))[@\\](brief|unit|range|check)\b(.*?)(?=\s*[@\\](?:brief|unit|range|check)\b|$)/g))
        found.push({tag:m[1],value:m[2].trim(),line:line+i});
    });
  }
  return found;
}

const selectKey = item => item.id + '/' + (item.route?.mid?.value ?? item.packet?.mid ?? '');

const stepNames=['Code','Struct','Prototype','Dispatch','Events','Handler','Test'];
const stepTitles=['Function code','Message struct','Handler prototype','Command dispatch','Event IDs','Command handler','Ground test'];

function sourcesFor(item) {
  const {handler:h,route,packet}=item;
  return [
    [h?.cc?.source || packet?.locations?.identifier || route?.mid?.source],
    [h?.packet_source || packet?.locations?.packet],
    h?.prototypes || [],
    [h?.source || packet?.locations?.dispatch],
    (h?.events||[]).flatMap(event=>[event.id.source,event.source]),
    [h?.handler || packet?.locations?.handler],
    []
  ].map(refs=>refs.filter(ref=>ref?.path));
}

// Shared by indexed-source activities and the guided command lesson.
export function sourceCommandTestEvidence(state, app, command, mid) {
  const build=state.workspace?.builds?.[state.target];
  // An unsaved flight source or dependency has not been part of this build.
  const clean=[...(state.files||[])].every(([path,file])=>! /^(cFS|mission)\//.test(path)||file.content===file.saved);
  const currentSession=Number.isInteger(mid) && clean && build?.current && build.fingerprint && state.ground?.build_fingerprint===build.fingerprint && state.ground.target===state.target;
  const run=currentSession && state.ground.runs?.filter(r=>r.command===command && r.sent?.app===app && r.sent.mid===mid).at(-1);
  const sent=currentSession && state.ground.commands?.filter(c=>c.id===command&&c.app===app&&c.mid===mid&&!c.automatic).at(-1);
  const receipt=currentSession && sent && [state.ground.first_flight?.receipt,state.ground.authored_reply?.receipt].find(r=>
    r?.command===command && r.app===app && Number.isInteger(r.send_id) && r.send_id===sent.event_id &&
    Number.isInteger(r.reply) && r.reply>r.send_id && Number.isInteger(r.increase) && r.increase>r.send_id &&
    Number.isInteger(r.baseline) && Number.isInteger(r.count) && r.count===r.baseline+1);
  return {test:run?.status==='passed'||!!receipt,run,receipt,sent};
}

export function commandContext(state) {
  const apps=state.workspace?.apps || [];
  let app=apps.find(a=>state.path?.startsWith(a.path+'/'));
  let items=commandEntries(state,app);
  if (!app && state.sourceStep?.app) {
    // A mission override may define the selected module's type or identifier
    // outside its directory. Keep the trail only when it points to this file.
    app=apps.find(a=>a.name===state.sourceStep.app);
    items=commandEntries(state,app);
    const item=items.find(entry=>selectKey(entry)===state.sourceCommand);
    if (!item || !sourcesFor(item).flat().some(ref=>ref.path===state.path)) return null;
  }
  if (!items.length) return null;
  const selected=items.find(i=>i.id===state.commandTask?.id && app.name===state.commandTask.app) || items.find(i=>selectKey(i)===state.sourceCommand) || items[0];
  const refs=sourcesFor(selected);
  const inferred=refs.findIndex(group=>group.some(ref=>ref.path===state.path));
  const explicit=state.sourceStep?.command===selectKey(selected) && state.sourceStep?.app===app.name;
  const step=explicit?state.sourceStep.index:Math.max(0,inferred);
  const evidence=sourceCommandTestEvidence(state,app.name,selected.id,selected.packet?.mid??selected.route?.mid?.value);
  return {app,items,selected,refs,step,...evidence};
}

// Resolve a cursor jump within the C ranges returned by the backend. A header
// shared by several commands keeps the selected command until a symbol is picked.
export function syncCommandToFile(state, line) {
  const ctx=commandContext(state);
  if (!ctx) {state.sourceStep=null;return false;}
  const {app,items,selected}=ctx;
  const active=state.commandTask?.app===app.name && state.commandTask.id===selected.id;
  const ordered=active?[selected]:[selected,...items.filter(i=>i!==selected)];
  const matches=[];
  for(const item of ordered){
    sourcesFor(item).forEach((refs,index)=>refs.forEach(ref=>{
      if(ref.path!==state.path)return;
      const exact=line && ref.line===line,inside=line && line>=ref.line && line<=(ref.end_line||ref.line);
      if(!line && item!==selected)return;
      if(line && !exact && !inside)return;
      matches.push({item,index,rank:exact?2:inside?1:0});
    }));
  }
  matches.sort((a,b)=>b.rank-a.rank);
  if(matches.length){
    const {item,index}=matches[0];state.sourceCommand=selectKey(item);
    state.sourceStep={app:app.name,command:state.sourceCommand,index};
    return true;
  }
  if(state.sourceStep?.app!==app.name)state.sourceStep=null;
  return false;
}

function jumpRow(ref,title,meta,esc,attrs='',badge='') {
  if(!ref?.path && !attrs)return '<div class="source-index-row"><strong>'+esc(title)+'</strong><small>'+esc(meta||'')+'</small></div>';
  const target=attrs || 'data-source-jump="'+esc(ref.path)+'" data-line="'+Number(ref.line||1)+'"';
  return '<button class="source-index-row" '+target+'>'+
    (badge?'<em>'+esc(badge)+'</em>':'')+'<strong>'+esc(title)+'</strong>'+(meta?'<small>'+esc(meta)+'</small>':'')+
    (ref?.line?'<span>L'+Number(ref.line)+'</span>':'')+'</button>';
}

const tagGroup=(tag,title,rows,esc)=>rows.length?'<section class="guide-section"><h3><code>'+esc(tag)+'</code>'+esc(title)+'</h3>'+rows.join('')+'</section>':'';
const fallback=message=>'<p class="guide-empty">'+message+'</p>';
const guideRef=ref=>ref?.path?.split('/').pop() || '';

function annotationsFor(state,ref,scanned) {
  if(!ref?.path)return scanned || [];
  const file=state.files.get(ref.path);
  if(!file || file.content===file.saved)return scanned || [];
  // Unsaved edits belong to this tab. Re-read attached comments at the visible
  // declaration and ignore cached annotations for this file until the next save.
  const lines=file.content.split('\n');
  let first=ref.line-1;
  while(first>0 && /^\s*(?:\/\*|\*|\/\/|$)/.test(lines[first-1] || ''))first--;
  const current=sourceTags(file.content).filter(a=>a.line>=first+1 && a.line<=(ref.end_line||ref.line));
  return [...(scanned||[]).filter(a=>a.path!==ref.path),...current.map(a=>({...a,path:ref.path}))];
}

function fieldRows(state,item,esc) {
  return (item.handler?.fields || item.packet?.fields || []).map(f=>{
    const flags=annotationsFor(state,f.source,f.annotations).filter(a=>a.tag==='range'||a.tag==='unit').map(a=>a.value);
    const compiled=item.packet?.fields?.find(v=>v.name===f.name);
    if(Number.isInteger(compiled?.offset))flags.push('byte '+compiled.offset+' · '+compiled.size+' B');
    return jumpRow(f.source,f.name,[f.type||f.format,...flags].filter(Boolean).join(' · '),esc);
  });
}

function fileIndex(state,file,esc) {
  if(!file)return '';
  const app=state.workspace.apps.find(a=>file.path.startsWith(a.path+'/'));
  const lib=state.workspace.libraries.find(l=>file.path.startsWith(l.path+'/'));
  const annotations=file.content===file.saved?file.annotations||[]:sourceTags(file.content);
  const functions=[...app?.functions||[],...lib?.exports||[]].filter(f=>f.path===file.path);
  const points=file.editable && isC(file.path)?file.content.split('\n').flatMap((line,i)=>{
    const m=editAnchor.exec(line);return m?[jumpRow({path:file.path,line:i+1},m[1],'',esc)]:[];
  }):[];
  return tagGroup('@studio.edit','Edit points',points,esc)+tagGroup('@','Annotations',annotations.map(a=>jumpRow({path:file.path,line:a.line},'@'+a.tag,a.value,esc)),esc)+
    tagGroup('fn','Functions',functions.map(f=>jumpRow(f,f.symbol,'',esc)),esc);
}

function newCommandAction(state,app,esc) {
  const owned=state.workspace?.apps.filter(a=>a.managed) || [];
  const preferred=app?.managed?app.name:owned[0]?.name;
  return preferred
    ? '<button class="guide-new" data-code-command="'+esc(preferred)+'">'+icon('plus')+'New command</button>'
    : '<button class="guide-new" data-create="app">'+icon('plus')+'New mission app</button>';
}

export function renderSourceGuide(state,esc) {
  const ctx=commandContext(state),file=state.files.get(state.path);
  if(!ctx)return '<header class="guide-step-title"><strong>Source</strong>'+newCommandAction(state,null,esc)+'</header><section class="guide-body">'+(fileIndex(state,file,esc)||fallback('No declarations'))+'</section>';
  const {app,items,selected,step,refs,test,run}=ctx;
  const {handler:h,route,packet,id}=selected;
  const primary=refs[step][0], notes=annotationsFor(state,h?.handler,annotationsFor(state,h?.cc?.source,h?.annotations));
  const rows=tagGroup;
  let body='';
  if(step===0){
    body+='<button class="guide-shortcut" data-source-tab="packet">'+icon('cube')+'See the packet</button>';
    body+=rows('@brief','Commands',items.filter(item=>item.handler?.cc || Number.isInteger(item.packet?.code)).map(item=>{
      const fn=item.handler?.cc, ref=fn?.source||item.packet?.locations?.identifier||item.route?.mid?.source;
      const note=annotationsFor(state,ref,item.handler?.annotations).find(a=>a.tag==='brief');
      const fc=fn?.value??item.packet?.code;
      const prefix=app.name.toUpperCase()+'_';
      const name=(item.id.startsWith(prefix)?item.id.slice(prefix.length):item.id).replace(/_CC$/,'');
      const attrs=ref?'data-source-jump="'+esc(ref.path)+'" data-line="'+Number(ref.line)+'" aria-current="'+(item===selected)+'" title="'+esc(item.id)+'"':'';
      return jumpRow(ref,name,note?.value,esc,attrs,Number.isInteger(fc)?'FC '+fc:'');
    }),esc)+rows('struct','Parameters',fieldRows(state,selected,esc),esc);
  }else if(step===1){
    body+=rows('struct','Packet type',[jumpRow(primary,h?.packet_type||packet?.struct||id,'',esc)],esc)+rows('field','Payload',fieldRows(state,selected,esc),esc);
  }else if(step===2){
    body+=rows('fn','Declarations',refs[2].map(ref=>jumpRow(ref,ref.symbol,guideRef(ref),esc)),esc);
    if(h?.handler)body+=rows('C','Implementation',[jumpRow(h.handler,h.handler.symbol,guideRef(h.handler),esc)],esc);
  }else if(step===3){
    body+=rows('MID','Message ID',route?.mid?[jumpRow(route.mid.source,route.mid.symbol,hex(route.mid.value),esc)]:[],esc);
    body+=rows('case','Dispatch',refs[3].map(ref=>jumpRow(ref,id,h?.handler?.symbol,esc)),esc);
    if(h?.handler)body+=rows('fn','Handler',[jumpRow(h.handler,h.handler.symbol,guideRef(h.handler),esc)],esc);
  }else if(step===4){
    const events=h?.events || [];
    if(!events.length && h?.handler) {
      body+='<button class="guide-shortcut" data-edit-handler>'+icon('edit')+'Edit event emission</button>';
      const example=items.flatMap(item=>item.handler?.events||[]).find(event=>event.source?.path && event.id?.source?.path);
      if(example) body+=rows('EVS','App example',[
        jumpRow(example.id.source,example.id.symbol,'Event number',esc),
        jumpRow(example.source,example.source.symbol||'CFE_EVS_SendEvent',example.severity,esc)
      ],esc);
    }
    body+=rows('EVS','Emissions',events.map(event=>jumpRow(event.source,event.id.symbol,event.severity,esc)),esc);
    body+=rows('ID','Event definitions',events.filter(e=>e.id.source).map(e=>jumpRow(e.id.source,e.id.symbol,Number.isInteger(e.id.value)?String(e.id.value):e.id.expression,esc)),esc);
  }else if(step===5){
    if(h?.handler)body+='<button class="guide-shortcut" data-edit-handler>'+icon('edit')+'Edit handler</button>';
    body+=rows('fn','Handler',refs[5].map(ref=>jumpRow(ref,ref.symbol,guideRef(ref),esc)),esc);
    for(const tag of ['brief','check'])body+=rows('@'+tag,tag==='brief'?'Description':'Checks',notes.filter(a=>a.tag===tag).map(a=>jumpRow(a,a.value,'',esc)),esc);
    body+=rows('EVS','Reports',(h?.events||[]).map(e=>jumpRow(e.source,e.id.symbol,e.severity,esc)),esc);
  }else {
    body+='<div class="guide-test"><code>'+esc(id)+'</code><button type="button" class="guide-new" data-command-test>'+icon('antenna')+'Open Ground Station</button></div>';
  }
  if(!body)body=fallback(step===4?'No event emission':'No indexed declaration');
  const move=(direction,label)=>'<button data-step-move="'+(step+direction)+'" '+(step+direction<0 || step+direction>=stepNames.length?'disabled':'')+'>'+label+'</button>';
  const stepStatus=step===6?(test?'Passed':run?.status?.replaceAll('_',' ') || 'Pending'):(step===5&&h?.placeholder?'Edit handler':primary?'Indexed':'Pending');
  return '<header class="guide-step-title"><div><small>Step '+(step+1)+' of 7</small><span>'+esc(stepStatus)+'</span></div><strong>'+stepTitles[step]+'</strong>'+
    (primary?'<button data-source-jump="'+esc(primary.path)+'" data-line="'+Number(primary.line||1)+'">'+icon('link')+esc(guideRef(primary))+'</button>':'')+'</header><section class="guide-body">'+body+'</section><footer class="guide-pager">'+move(-1,'Back')+move(1,'Next step')+'</footer>';
}

export function renderCommandTrail(state,esc) {
  const ctx=commandContext(state);if(!ctx)return '';
  const {app,selected,refs,step,test}=ctx;
  const activity=state.sourceActivity;
  const belongs=activity?.target===state.target && activity.app===app.name && activity.command===selected.id;
  const active=state.commandTask?.app===app.name && state.commandTask.id===selected.id;
  if(!active && !refs.flat().some(ref=>ref.path===state.path))return '';
  const steps=stepNames.map((label,i)=>{
    const evidence=belongs?activity.steps[i]:null;
    const clean=refs[i].every(ref=>{const file=state.files.get(ref.path);return !file||file.content===file.saved;});
    return {label,done:i===6?!!test:!!evidence?.done&&clean,
      disabled:i!==6&&!refs[i].length,title:stepTitles[i]};
  });
  const ready=belongs && activity.steps[step]?.available && refs[step].every(ref=>{const file=state.files.get(ref.path);return !file||file.content===file.saved;});
  const next=step===6?'<button type="button" class="activity-next" data-command-test>Open Ground Station</button>':
    '<button type="button" class="activity-next" data-review-source '+(!ready||state.sourceReviewBusy?'disabled':'')+' title="Review this source step and continue">'+(state.sourceReviewBusy?'Saving…':'Next step')+'</button>';
  return renderActivityProgress({steps,selected:step,attribute:'data-guide-step',next});
}

export function renderSourceTools(state,esc) {
  const ctx=commandContext(state);
  return (!state.commandTask && state.workspace?.apps?.some(app=>app.managed) ? newCommandAction(state,null,esc) : '')+tabs.map(([id,label])=>'<button type="button" data-source-tab="'+id+'" aria-haspopup="dialog" '+(id!=='source'&&!ctx?'disabled':'')+'>'+
    (id==='source'?'@':icon(id==='packet'?'cube':'workflow'))+esc(label)+'</button>').join('');
}

function packetContent(state,selected,esc) {
  const {handler:h,route,packet,id}=selected;
  const mid=packet?.mid??route?.mid?.value,fc=packet?.code??h?.cc?.value;
  const heading='<code class="guide-object-name">'+esc(id)+'</code>';
  const summary='<div class="packet-layout">'+
    jumpRow(route?.mid?.source,hex(mid)||route?.mid?.symbol||'—','Message ID',esc)+
    jumpRow(h?.cc?.source,Number.isInteger(fc)?String(fc):'—','Function code',esc)+
    jumpRow(h?.packet_source,Number.isInteger(packet?.size)?packet.size+' B':h?.packet_type||'—',Number.isInteger(packet?.size)?'Compiled packet':'Source type',esc)+'</div>';
  const payload=tagGroup('field','Payload',fieldRows(state,selected,esc),esc);
  if(!packet || state.catalog?.transport?.command_header_size!==8)return heading+summary+payload;
  const build=state.workspace.builds[state.target];
  const sameBuild=state.ground?.target===state.target && state.ground?.build_fingerprint===build.fingerprint;
  const sent=sameBuild && state.ground.commands?.filter(c=>c.id===id && c.mid===mid && c.app===packet.app).at(-1);
  const shape=[['Message ID',0,2,route?.mid?.source],['Sequence',2,2],['Length',4,2],
    ['Function code',6,1,h?.cc?.source],['Checksum',7,1],
    ...(packet.fields||[]).map(f=>[f.name,f.offset,f.size,h?.fields?.find(p=>p.name===f.name)?.source])];
  const blocks=shape.filter(([,offset,length])=>Number.isInteger(offset)&&length>0).map(([name,offset,length,ref])=>{
    const bytes=sent?.hex?.slice(offset*2,(offset+length)*2).match(/../g)?.join(' ').toUpperCase();
    return '<div class="packet-word">'+jumpRow(ref,name,'byte '+offset+(length>1?'–'+(offset+length-1):''),esc)+
      (bytes?'<code>'+esc(bytes)+'</code>':'')+'</div>';
  }).join('');
  return heading+summary+'<h3>CCSDS'+(sent?' · last transmission':'')+'</h3><div class="packet-words">'+blocks+'</div>'+payload;
}

function dispatchContent(ctx,esc) {
  const {app,selected}=ctx,{route,handler:h,packet}=selected;
  const subscriptions=app.behavior?.details?.subscriptions||[];
  const receivers=subscriptions.filter(s=>s.mid?.symbol===route?.mid?.symbol || Number.isInteger(s.mid?.value) && s.mid.value===route?.mid?.value);
  const stages=[];
  if(receivers.length)stages.push(['Software Bus',receivers.map(s=>jumpRow(s.source,s.pipe,s.source?.symbol,esc))]);
  if(route?.mid)stages.push(['Message ID',[jumpRow(route.mid.source,route.mid.symbol,hex(route.mid.value),esc)]]);
  if(h?.cc)stages.push(['Function code',[jumpRow(h.cc.source,h.cc.symbol,'FC '+(h.cc.value??'—'),esc)]]);
  const dispatch=h?.source||packet?.locations?.dispatch;
  if(dispatch)stages.push(['Dispatch case',[jumpRow(dispatch,dispatch.symbol||selected.id,guideRef(dispatch),esc)]]);
  const fn=h?.handler||packet?.locations?.handler;
  if(fn)stages.push(['Handler',[jumpRow(fn,fn.symbol,guideRef(fn),esc)]]);
  return '<code class="guide-object-name">'+esc(selected.id)+'</code><div class="dispatch-graph">'+stages.map(([label,rows])=>
    '<section><h3>'+label+'</h3>'+rows.join('')+'</section>').join('')+'</div>';
}

export function renderInspectorDialog(state,tab,esc) {
  const ctx=commandContext(state),file=state.files.get(state.path);
  if(tab==='source')return {title:'Source tags',body:'<div class="guide-tag-key">'+tags.map(([tag,label])=>'<div><code>@'+tag+'</code><span>'+label+'</span></div>').join('')+'</div>'+fileIndex(state,file,esc)};
  if(!ctx)return {title:'Source',body:''};
  return tab==='packet'?{title:'Command packet',body:packetContent(state,ctx.selected,esc)}:{title:'Command dispatch',body:dispatchContent(ctx,esc)};
}

export function renderCommandTest(state,esc) {
  const ctx=commandContext(state);
  if(!ctx || ctx.step!==6)return '';
  const {run,selected,app,receipt,sent}=ctx;
  const received=run?.steps?.filter(step=>step.observation) || [];
  const item=(symbol,title,value)=>'<div class="source-test-node">'+icon(symbol)+'<strong>'+esc(title)+'</strong><small>'+esc(value)+'</small></div>';
  let trace=item('antenna','Ground Station',run?.sent?'Sent':'No test recorded');
  if(run?.sent){
    trace+='<span class="test-trace-arrow" aria-hidden="true">→</span>'+item('send',app.name,selected.id);
    for(const step of received)trace+='<span class="test-trace-arrow" aria-hidden="true">→</span>'+item('link',step.observation.name,'seq '+step.observation.sequence);
  }
  if(receipt){
    trace=item('antenna','Ground Station','Sent · '+sent.event_id)+
      '<span class="test-trace-arrow" aria-hidden="true">→</span>'+item('send',app.name,selected.id)+
      '<span class="test-trace-arrow" aria-hidden="true">→</span>'+item('link','Flight event',receipt.message||'Event '+receipt.reply)+
      '<span class="test-trace-arrow" aria-hidden="true">→</span>'+item('link','Housekeeping','CommandCounter '+receipt.baseline+' → '+receipt.count);
  }
  return '<header><strong>Ground test</strong><code>'+esc(selected.id)+'</code></header><div class="source-test-trace">'+trace+'</div>';
}

function prefixInComment(editor) {
  if (editor.readOnly || editor.disabled || editor.selectionStart !== editor.selectionEnd) return null;
  const prefix = editor.value.slice(0,editor.selectionStart);
  const suffix = /@(\w*)$/.exec(prefix);
  if (!suffix) return null;
  // An unterminated string is different from an unterminated block comment.
  const token = /"(?:\\[\s\S]|[^"\\\n])*(?:"|$)|'(?:\\[\s\S]|[^'\\\n])*(?:'|$)|\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$)/gm;
  let inComment = false;
  for (const match of prefix.matchAll(token)) {
    if (match.index + match[0].length === prefix.length) inComment = match[0].startsWith('//') || (match[0].startsWith('/*') && !match[0].endsWith('*/'));
  }
  return inComment ? suffix[1] : null;
}

export function attachTagPicker(editor, currentPath) {
  const menu = document.createElement('div');
  menu.className = 'source-tag-picker';
  menu.id = 'source-tag-picker';
  menu.hidden = true;
  menu.setAttribute('role','listbox');
  menu.setAttribute('aria-label','Source tags');
  editor.parentElement.append(menu);
  editor.setAttribute('aria-controls',menu.id);
  editor.setAttribute('aria-autocomplete','list');
  const canvas = document.createElement('canvas').getContext('2d');
  let options = [], active = 0, prefix = '';

  function close() {
    menu.hidden = true;
    editor.removeAttribute('aria-activedescendant');
  }
  function mark() {
    [...menu.children].forEach((row,i) => row.setAttribute('aria-selected',String(i === active)));
    editor.setAttribute('aria-activedescendant',menu.children[active].id);
  }
  function fill() {
    if (menu.hidden || prefixInComment(editor) !== prefix) return close();
    const pos = editor.selectionStart;
    editor.setRangeText(options[active][0] + ' ',pos-prefix.length,pos,'end');
    close();
    editor.dispatchEvent(new Event('input',{bubbles:true}));
  }
  editor.addEventListener('input',() => {
    prefix = isC(currentPath()) ? prefixInComment(editor) : null;
    options = prefix === null ? [] : tags.filter(([name]) => name.startsWith(prefix));
    if (!options.length) return close();
    active = 0;
    menu.innerHTML = options.map(([name,description],i) => `<div role="option" id="source-tag-${name}" data-index="${i}"><code>@${name}</code><small>${description}</small></div>`).join('');
    menu.hidden = false;
    mark();
    const style = getComputedStyle(editor), before = editor.value.slice(0,editor.selectionStart);
    canvas.font = style.fontSize + ' ' + style.fontFamily;
    const lines = before.split('\n'), line = lines.at(-1).replace(/\t/g,'    ');
    const caretX = canvas.measureText(line).width - editor.scrollLeft + parseFloat(style.paddingLeft);
    const caretY = lines.length * parseFloat(style.lineHeight) - editor.scrollTop + parseFloat(style.paddingTop);
    menu.style.left = Math.max(0,Math.min(caretX,editor.clientWidth-menu.offsetWidth)) + 'px';
    menu.style.top = Math.max(0,caretY + menu.offsetHeight > editor.clientHeight ? caretY-menu.offsetHeight-parseFloat(style.lineHeight) : caretY) + 'px';
  });
  editor.addEventListener('keydown',event => {
    if (menu.hidden) return;
    if (['ArrowDown','ArrowUp','Tab','Enter','Escape'].includes(event.key)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.key === 'Escape') return close();
      if (event.key === 'Tab' || event.key === 'Enter') return fill();
      active = (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      mark();
    } else if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) close();
  },true);
  menu.addEventListener('mousedown',event => {
    const option = event.target.closest('[data-index]');
    if (!option) return;
    event.preventDefault();
    active = Number(option.dataset.index);
    fill();
  });
  for (const name of ['blur','scroll','click']) editor.addEventListener(name,close);
}
