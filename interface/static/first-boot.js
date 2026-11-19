import {targetDrawing} from './target-drawing.js';
import {icon} from './ui.js';

const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const drawnCheck = '<svg viewBox="0 0 24 24" aria-hidden="true"><path pathLength="1" d="m5 12 4 4 10-10"/></svg>';
const names={native:'Native',qemu:'Emulator',physical:'Board'};
const tooltips={apps:'Mission applications',cfe:'Core Flight Executive',osal:'Operating System Abstraction Layer',psp:'Platform Support Package',os:'Operating system',hw:'Execution hardware',build:'Build flight software'};
const serviceIcons={ES:['play','apps'],EVS:['antenna','events'],SB:['workflow','messages'],TBL:['table','tables'],TIME:['clock','clock'],FS:['files','files']};
const stagesFor=target=>target==='native'?[['build','Build cFS'],['run','Start cFS']]: target==='physical'?[['build','Cross-build'],['copy','Copy to board'],['run','Start cFS service']]:[['build','Build cFS'],['boot','Start emulator'],['run','Start cFS']];
const chip=(name,lit)=>`<span class="boot-chip" data-lit="${!!lit}">${escape(name)}</span>`;
const esLabels={EARLY_INIT:'Early init',CORE_STARTUP:'Starting core',CORE_READY:'Core ready',APPS_INIT:'Loading apps',OPERATIONAL:'Operational'};
const guestLabels=['Starting emulator','Opening disk','Preparing SSH key','Starting kernel','Booting Linux','Waiting for SSH','SSH connected'];

export function stageProgress(id,job,states) {
  if(id==='build'){
    const measured=job.build_activity==='Compiling' && Number.isFinite(job.build_percent) && job.build_percent<100;
    return {label:job.build_activity||'Preparing build',percent:measured?job.build_percent:null};
  }
  const label=id==='boot'?guestLabels[job.guest_stage||0]:id==='copy'?'Transferring files':esLabels[states.at(-1)]||'Starting process';
  return {label,percent:null};
}

export function bootLayers(data) {
  const {flight,job}=data,initialized=flight.initialized||{},es=flight.states||[];
  const phase=job.phase||(job.action==='run' || es.length?'run':'build');
  const process=Boolean(flight.process_started);
  const machine=process || phase==='copy' || (phase==='run' && data.target!=='native');
  const guest=phase==='boot'?job.guest_stage||0:0;
  const core=es.includes('CORE_READY'), coreStarted=es.length>0;
  // Earlier receipts captured process entry, but did not distinguish PSP from OSAL.
  const psp=flight.platform_layers ? flight.platform_layers.includes('psp') || coreStarted : process;
  const osal=Boolean(flight.platform_layers?.includes('osal') || coreStarted);
  const apps=data.apps.map(app=>[app.name,Boolean(initialized[app.task])]);
  const svc=data.services.map(name=>[name,core || Boolean(initialized['CFE_'+name])]);
  const layers=[
    ['apps','Apps','cube',apps,apps.some(([,lit])=>lit) || es.includes('APPS_INIT')],
    ['cfe','cFE','layers',svc,coreStarted || svc.some(([,lit])=>lit)],
    ['osal','OSAL','layers',['tasks','queues','files','timers'].map(x=>[x,osal]),osal],
    ['psp','PSP','cpu',[['pc-linux',psp]],psp],
    ['os',data.os,'terminal',[['Linux',machine||guest>=4]],machine||guest>=4],
    ['hw',data.hardware,data.target==='native'?'monitor':'circuit',[[data.architecture,machine||guest>=3]],machine||guest>=3]
  ];
  return {layers,phase,auto:layers.find(row=>row[4])?.[0]||'build',es};
}
// The infrastructure steps report completed jobs; each startup card requires its own ES line.
export function bootStages(data, {phase,es}=bootLayers(data)) {
  const steps=stagesFor(data.target);
  const stepIndex=steps.findIndex(([id])=>id===phase);
  const job=data.job, last=es.at(-1);
  const fault=data.unverified?'Unverified':data.stopped?'Stopped':
    job.status==='failed'?'Failed':job.status==='cancelled'?'Cancelled':'';
  const preparation=steps.slice(0,-1).map(([key,label],index)=>{
    const reached=stepIndex>index && data.trace.some(event=>event.phase===key);
    const active=stepIndex===index && job.phase===key && Boolean(job.id);
    const progress=stageProgress(key,job,es);
    return {key,label,layer:key==='build'?'build':key==='boot'&&job.guest_stage>=4?'os':'hw',
      state:reached?'done':active?(fault?'failed':'active'):'waiting',
      caption:reached?'Ready':active?(fault || progress.label):'', percent:active&&!fault?progress.percent:null};
  });
  const startup=data.es_states.map(key=>{
    const observed=es.includes(key);
    const current=observed && key===last && key!=='OPERATIONAL';
    const state=current && fault?'failed':current?'active':observed?'done':'waiting';
    return {key,label:esLabels[key]||key,state,layer:['APPS_INIT','OPERATIONAL'].includes(key)?'apps':'cfe'};
  });
  return {preparation,startup,runStatus:phase==='run'?(fault || (!last?'Starting process':'')):''};
}

function stageCard(card,index,pickKey) {
  const {key,label,caption,state,percent,layer}=card;
  const measured=state==='active' && Number.isFinite(percent);
  const complete=state==='done';
  const status=measured?caption+' '+percent+'%':caption;
  const spoken={waiting:'Waiting', active:'In progress', done:'Complete', failed:'Interrupted'}[state];
  return `<button type="button" class="boot-stage" data-stage="${key}" data-stage-layer="${layer}" data-state="${state}"
    data-boot-focus="stage-${key}" aria-label="${escape(label+', '+(status||spoken))}" aria-pressed="${pickKey===key}" title="${escape(status||key)}">
    <span class="boot-stage-caption"><i aria-hidden="true">${complete?drawnCheck:index+1}</i><strong>${escape(label)}</strong></span>
    <span class="boot-meter" aria-hidden="true" data-indeterminate="${state==='active'&&!measured}"><b style="width:${complete?100:measured?percent:0}%"></b></span>
  </button>`;
}

function picture(id,data,layers) {
  const layer = layers.find(row=>row[0]===id);
  const name = layer?.[1] || 'Build';
  let figure;
  if(id==='build') {
    const sources=['cfe','osal','psp','apps'].map(folder=>`<span>${icon('folder')}${folder}/</span>`).join('');
    figure=`<div class="boot-build-diagram"><div class="boot-sources">${sources}</div>
      <svg class="boot-compile-arrow" aria-hidden="true" viewBox="0 0 56 12"><path d="M1 6h48" stroke-dasharray="4 4"/><path d="m46 1 7 5-7 5"/></svg>
      <strong class="boot-object">${icon('cube')}core-cpu1</strong></div>`;
  } else if(id==='hw') {
    figure=`<div class="boot-hardware">${targetDrawing(data.target)}</div><code>${escape(data.architecture)}</code>`;
  } else if(id==='os') {
    const processes=Array.from({length:8},(_,i)=>i===5?`<b data-lit="${Boolean(data.flight.process_started)}">cFS</b>`:'<i aria-hidden="true"></i>').join('');
    figure=`<div class="boot-os-window"><header>${icon('terminal')}${escape(data.os)}</header>
      <div class="boot-processes" aria-label="Operating system processes">${processes}</div></div>`;
  } else if(id==='osal' || id==='psp') {
    const psp=id==='psp', options=psp?['pc-linux','pc-rtems','vxworks']:['Linux','RTEMS','VxWorks'];
    figure=`<div class="boot-portability"><span class="boot-object">${icon(psp?'layers':'cube')}${psp?'OSAL':'Your app'}</span>
      <i></i><strong>${name}</strong>
      <svg class="boot-branches" aria-hidden="true" viewBox="0 0 300 28" preserveAspectRatio="none">
        <path d="M150 0v13h100v14 M150 13v14"/><path class="${layer[4]?'selected':''}" d="M150 0v13H50v14"/></svg>
      <div class="boot-options">${options.map((text,index)=>chip(text,index===0 && layer[4])).join('')}</div></div>`;
  } else if(id==='cfe') {
    figure=`<div class="boot-services">${layer[3].map(([service,lit])=>{
      const [glyph,label]=serviceIcons[service];
      return `<span data-lit="${lit}">${icon(glyph)}<strong>${service}</strong><small>${label}</small></span>`;
    }).join('')}</div>`;
  } else {
    const apps=new Map(layer[3]);
    const draw=name=>apps.has(name)?chip(name,apps.get(name)):'';
    figure=`<div class="boot-app-diagram"><div class="boot-ground">${icon('antenna')}Ground</div>
      <div class="boot-app-bus"><div class="boot-app-row">${draw('ci_lab')}${draw('to_lab')}</div>
      <span class="boot-sb">Software Bus</span><div class="boot-app-row">${draw('sch_lab')}${draw('sample_app')}<span class="boot-slot">+ App</span></div></div></div>`;
  }
  return `<header><span class="boot-picture-icon">${icon(layer?.[2]||'build')}</span><h2 title="${tooltips[id]}">${escape(name)}</h2><i class="boot-picture-dot" data-lit="${!!layer?.[4] || id==='build'}"></i></header><div class="boot-figure" data-scene="${id}">${figure}</div>`;
}

// Keep live SVG strokes, focused buttons and scrolling console nodes across polls.
function updateNode(current,next){
  if(current.isEqualNode(next))return;
  if(current.nodeName!==next.nodeName || current.getAttribute?.('data-scene')!==next.getAttribute?.('data-scene')){
    current.replaceWith(next);
    return;
  }
  if(current.nodeType===Node.TEXT_NODE){current.nodeValue=next.nodeValue;return;}
  for(const attr of Array.from(current.attributes)){
    if(!next.hasAttribute(attr.name))current.removeAttribute(attr.name);
  }
  for(const attr of next.attributes){
    if(current.getAttribute(attr.name)!==attr.value)current.setAttribute(attr.name,attr.value);
  }
  const children=Array.from(next.childNodes);
  children.forEach((child,i)=>{
    if(current.childNodes[i])updateNode(current.childNodes[i],child);
    else current.append(child);
  });
  while(current.childNodes.length>children.length)current.lastChild.remove();
}

// Replay only observations that the backend had received at this instant.
export function bootFrame(snapshot,milliseconds,lastIndex=snapshot.trace.length-1) {
  const flight={states:[],initialized:{},process_started:false}, lines=[];
  const job={action:snapshot.job.action||'first-boot',id:snapshot.job.id||'recorded',status:'running'};
  for(let i=0;i<=lastIndex;i++){
    const event=snapshot.trace[i];
    if(event.ms>milliseconds)break;
    if(event.line) lines.push(event.line);
    if(event.phase) job.phase=event.phase;
    if('percent' in event) job.build_percent=event.percent;
    if(event.guest_stage) job.guest_stage=event.guest_stage;
    if(event.activity) job.build_activity=event.activity;
    if(event.fact) {
      flight.process_started=true;
      if(event.fact.layer) {
        flight.platform_layers ??= [];
        flight.platform_layers.push(event.fact.layer);
      }
      if(event.fact.state) flight.states.push(event.fact.state);
      if(event.fact.app) flight.initialized[event.fact.app]=event.fact;
    }
  }
  return {...snapshot,job,flight,lines,running:false,stopped:false,unverified:false};
}
function clock(milliseconds) {
  const seconds=Math.floor(Math.max(0,milliseconds)/1000);
  return [Math.floor(seconds/60), seconds%60].map(x=>String(x).padStart(2,'0')).join(':');
}
export function mountFirstBoot(container,{api,target,onNext}) {
  let disposed=false,timer=null,requested=false,data=null,pick='',pickKey='',lastCue='',consoleOpen=false,err='';
  let live=null, pausedAt=null, pausedIndex=null, replayStart=null, replayTimer=null;
  function elapsed() {
    if(pausedAt!=null) return pausedAt;
    if(replayStart!=null) return performance.now()-replayStart;
    const trace=live?.trace||[];
    const completed=trace.find(item=>item.fact?.state==='OPERATIONAL');
    if(completed) return completed.ms;
    if(!live?.job.started || live.job.status!=='running') return trace.at(-1)?.ms||0;
    return Math.max(0,Date.now()-live.job.started*1000);
  }
  const draw=()=>{
    clearTimeout(replayTimer);
    if(!live) return;
    const ms=elapsed();
    if(replayStart!=null && pausedAt==null && ms>=(live.trace.at(-1)?.ms||0)) replayStart=null;
    data=pausedAt!=null||replayStart!=null ? bootFrame(live,ms,pausedIndex??live.trace.length-1) : live;
    if(disposed || !data)return;
    const {layers,phase,auto,es}=bootLayers(data);
    const {preparation,startup,runStatus}=bootStages(data,{phase,es});
    const currentStep=preparation.find(card=>card.state==='active'||card.state==='failed');
    const prepStatus=currentStep?.percent!=null?currentStep.caption+' '+currentStep.percent+'%':currentStep?.caption;
    const job=data.job,running=data.running,failed=['failed','cancelled'].includes(job.status);
    const cue=[job.id,phase,job.guest_stage,auto,es.at(-1)].join('/');
    if(cue!==lastCue && pausedAt==null){pick='';pickKey='';}
    lastCue=cue;
    const selected=pick||auto;
    const focus=container.contains(document.activeElement)?document.activeElement.dataset.bootFocus:null;
    const output=container.querySelector('.boot-console pre:not([hidden])');
    const oldScroll=output?.scrollTop||0,atEnd=!output||output.scrollTop+output.clientHeight>=output.scrollHeight-4;
    const title=[names[target],data.hardware,data.os].join(' · ');
    const fragment=document.createElement('template');
    fragment.innerHTML=`<section class="first-boot">
      <header class="boot-title"><h1>First boot</h1><span>${icon(target==='native'?'monitor':'cpu')}${escape(title)}</span><a href="/">Change</a>
      <time class="boot-clock" aria-label="Boot elapsed">${clock(elapsed())}</time>
      <button class="boot-control" data-pause data-boot-focus="pause" aria-label="${pausedAt==null?'Pause view':'Resume view'}" title="${pausedAt==null?'Pause view':'Resume view'}" ${!live.trace.length || (!replayStart && pausedAt==null && live.running)?'disabled':''}>${pausedAt==null?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14m8-14v14"/></svg>':icon('play')+'<span>Resume</span>'}</button>
      <button class="boot-control" data-replay data-boot-focus="replay" aria-label="Replay boot" title="Replay boot" ${live.trace.length<2?'disabled':''}>${icon('rotate')}</button></header>
      <div class="boot-stages" style="--prep-width:${preparation.length}fr">
        <section class="boot-stage-group"><h2>${escape(names[target])}<small>${escape(prepStatus||'')}</small></h2>
        <div class="boot-track">${preparation.map((card,i)=>stageCard(card,i,pickKey)).join('')}</div></section>
        <section class="boot-stage-group"><h2>Start cFS<small>${escape(runStatus)}</small></h2>
        <div class="boot-track">${startup.map((card,i)=>stageCard(card,preparation.length+i,pickKey)).join('')}</div></section>
      </div>
      <div class="boot-layout"><section class="boot-stack"><h2>cFS · layer by layer</h2>
      ${layers.map(([id,name,glyph,chips,lit])=>`<button type="button" class="boot-layer" data-layer="${id}" data-boot-focus="${id}" title="${tooltips[id]}" aria-pressed="${id===selected}" data-current="${id===auto && !running && !failed}" data-lit="${!!lit}"><span>${icon(glyph)}</span><strong>${escape(name)}</strong><span class="boot-chips">${chips.map(([text,on])=>chip(text,on)).join('')}</span></button>`).join('')}
      </section>
      <section class="boot-picture" data-kind="${selected}" data-animating="${selected===auto && job.status==='running'&&!failed&&!running&&pausedAt==null}">${picture(selected,data,layers)}</section></div>
      <section class="boot-console" data-open="${consoleOpen}" aria-label="Boot console">
        <div class="boot-console-sheet">
          <div class="boot-console-heading">
            <strong>${icon('terminal')}Console</strong>
            <code aria-hidden="true">${consoleOpen?'':escape(data.lines.at(-1)||'')}</code>
            <button class="boot-console-toggle" type="button" data-console data-boot-focus="console" aria-expanded="${consoleOpen}" aria-controls="boot-console-output">${icon(consoleOpen?'close':'expand')}${consoleOpen?'Close console':'Open console'}</button>
          </div>
          <pre id="boot-console-output" aria-label="Boot log" tabindex="0" ${consoleOpen?'':'hidden'}>${consoleOpen?escape(data.lines.join('\n')):''}</pre>
        </div>
      </section>
      <footer>${running?`<span class="boot-success">${drawnCheck}cFS is running</span><button class="primary" data-next data-boot-focus="next">Ground Station</button>`:(!data.verified||data.unverified)?'<a href="/">Check target</a>':failed||data.stopped||err?'<button data-retry data-boot-focus="retry">Retry first boot</button>':''}<output>${escape(err||job.error||'')}</output></footer></section>`;
    const next=fragment.content.firstElementChild, existing=container.firstElementChild;
    if(existing?.classList.contains('first-boot'))updateNode(existing,next);
    else container.replaceChildren(next);
    if(focus&&!container.contains(document.activeElement))container.querySelector(`[data-boot-focus="${CSS.escape(focus)}"]`)?.focus({preventScroll:true});
    const nextOutput=container.querySelector('.boot-console pre:not([hidden])');
    if(nextOutput)nextOutput.scrollTop=atEnd?nextOutput.scrollHeight:oldScroll;
    if(replayStart!=null&&pausedAt==null){
      const nextEvent=live.trace.find(event=>event.ms>ms);
      if(nextEvent)replayTimer=setTimeout(draw,Math.max(16,nextEvent.ms-ms));
    }
  };
  async function start(){
    requested=true;err='';
    try{await api('job',{action:'first-boot',options:{target}});}
    catch(error){err=error.message;}
  }
  async function poll(){
    try{
      const next=await api('first-boot?target='+encodeURIComponent(target));
      if(disposed)return;
      live=next;
      draw();
      if(next.verified&&!requested&&!next.running&&!next.job.id&&!next.stopped&&!next.unverified){await start();draw();}
    }catch(error){if(!disposed){err=error.message;if(data)draw();else container.textContent=err;}}
    if(!disposed)timer=setTimeout(poll,600);
  }
  const click=async event=>{
    const button=event.target.closest('button');
    if(!button)return;
    if(button.dataset.stageLayer){
      const key=button.dataset.stage;
      if(pickKey===key){
        pick='';pickKey='';pausedAt=null;pausedIndex=null;
      } else {
        pick=button.dataset.stageLayer;pickKey=key;
        // Journald can deliver several real milestones in the same read.
        const index=live.trace.findIndex(e=>e.phase===key || e.fact?.state===key);
        if(index>=0){
          pausedAt=live.trace[index].ms;pausedIndex=index;replayStart=null;
        }
      }
    }
    else if(button.dataset.layer){pickKey='';pick=pick===button.dataset.layer?'':button.dataset.layer;}
    else if(button.hasAttribute('data-replay')){replayStart=performance.now();pausedAt=null;pausedIndex=null;pick='';pickKey='';}
    else if(button.hasAttribute('data-pause')){
      if(pausedAt==null) pausedAt=elapsed();
      else {
        if(replayStart!=null) replayStart=performance.now()-pausedAt;
        pausedAt=null;pausedIndex=null;pick='';pickKey='';
      }
    }
    else if(button.hasAttribute('data-console'))consoleOpen=!consoleOpen;
    else if(button.hasAttribute('data-next')){onNext();return;}
    else if(button.hasAttribute('data-retry')){button.disabled=true;await start();}
    draw();
  };
  container.innerHTML='<section class="first-boot"><h1>First boot</h1></section>';
  const closeDetails=event=>{
    if(event.key==='Escape' && consoleOpen && !event.defaultPrevented && !document.querySelector('dialog[open]')){
      const fromConsole=event.target.closest?.('.boot-console');
      consoleOpen=false;draw();
      if(fromConsole)container.querySelector('[data-console]').focus({preventScroll:true});
    }
  };
  container.addEventListener('click',click);
  document.addEventListener('keydown',closeDetails);poll();
  return ()=>{disposed=true;clearTimeout(timer);clearTimeout(replayTimer);container.removeEventListener('click',click);document.removeEventListener('keydown',closeDetails);};
}
