import {targetDrawing} from './target-drawing.js';
import {icon} from './ui.js';

const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const drawnCheck = '<svg viewBox="0 0 24 24" aria-hidden="true"><path pathLength="1" d="m5 12 4 4 10-10"/></svg>';
const names={native:'Native',qemu:'Emulator',physical:'Board'};
const tooltips={apps:'Mission applications',cfe:'Core Flight Executive',osal:'Operating System Abstraction Layer',psp:'Platform Support Package',os:'Operating system',hw:'Execution hardware',build:'Build flight software'};
const serviceIcons={ES:['play','apps'],EVS:['antenna','events'],SB:['workflow','messages'],TBL:['table','tables'],TIME:['clock','clock'],FS:['files','files']};
const stagesFor=target=>target==='native'?[['build','Build cFS'],['run','Start cFS']]: target==='physical'?[['build','Cross-build'],['copy','Copy to board'],['run','Start cFS service']]:[['build','Build cFS'],['boot','Start emulator'],['run','Start cFS']];
const chip=(name,lit)=>`<span class="boot-chip" data-lit="${!!lit}">${escape(name)}</span>`;

function model(data) {
  const {flight,job}=data,initialized=flight.initialized||{},es=flight.states||[];
  const phase=job.phase||(job.action==='run' || es.length?'run':'build');
  const process=Boolean(flight.process_started);
  const machine=process || phase==='copy' || (phase==='run' && data.target!=='native');
  const core=es.includes('CORE_READY');
  const apps=data.apps.map(app=>[app.name,Boolean(initialized[app.task])]);
  const svc=data.services.map(name=>[name,core || Boolean(initialized['CFE_'+name])]);
  const layers=[
    ['apps','Apps','cube',apps,apps.some(([,lit])=>lit)],
    ['cfe','cFE','layers',svc,es.includes('CORE_STARTUP') || core],
    ['osal','OSAL','layers',['tasks','queues','files','timers'].map(x=>[x,process]),process],
    ['psp','PSP','cpu',[['pc-linux',process]],process],
    ['os',data.os,'terminal',[['Linux',machine]],machine],
    ['hw',data.hardware,data.target==='native'?'monitor':'circuit',[[data.architecture,machine]],machine]
  ];
  return {layers,phase,auto:layers.find(row=>row[4])?.[0]||'build',es};
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
    const processes=Array.from({length:8},(_,i)=>i===5?'<b>cFS</b>':'<i aria-hidden="true"></i>').join('');
    figure=`<div class="boot-os-window"><header>${icon('terminal')}${escape(data.os)}</header>
      <div class="boot-processes" aria-label="Operating system processes">${processes}</div></div>`;
  } else if(id==='osal' || id==='psp') {
    const psp=id==='psp', options=psp?['pc-linux','pc-rtems','vxworks']:['Linux','RTEMS','VxWorks'];
    figure=`<div class="boot-portability"><span class="boot-object">${icon(psp?'layers':'cube')}${psp?'OSAL':'Your app'}</span>
      <i></i><strong>${name}</strong>
      <svg class="boot-branches" aria-hidden="true" viewBox="0 0 300 28" preserveAspectRatio="none">
        <path d="M150 0v13h100v14 M150 13v14"/><path class="selected" d="M150 0v13H50v14"/></svg>
      <div class="boot-options">${options.map((text,index)=>chip(text,index===0)).join('')}</div></div>`;
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
  return `<header><span class="boot-picture-icon">${icon(layer?.[2]||'build')}</span><h2 title="${tooltips[id]}">${escape(name)}</h2><i class="boot-picture-dot" data-lit="${!!layer?.[4] || id==='build'}"></i></header><div class="boot-figure">${figure}</div>`;
}

// Replay only observations that the backend had received at this instant.
export function bootFrame(snapshot,milliseconds) {
  const flight={states:[],initialized:{},process_started:false}, lines=[];
  const job={action:snapshot.job.action||'first-boot',id:snapshot.job.id||'recorded',status:'running'};
  for(const event of snapshot.trace) {
    if(event.ms>milliseconds) break;
    if(event.line) lines.push(event.line);
    if(event.phase) job.phase=event.phase;
    if(event.percent!=null) job.build_percent=event.percent;
    if(event.activity) job.build_activity=event.activity;
    if(event.fact) {
      flight.process_started=true;
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
  let disposed=false,timer=null,requested=false,data=null,pick='',consoleOpen=false,stateOpen=false,err='';
  let live=null, pausedAt=null, replayStart=null;
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
    if(!live) return;
    const ms=elapsed();
    if(replayStart!=null && pausedAt==null && ms>=(live.trace.at(-1)?.ms||0)) replayStart=null;
    data=pausedAt!=null||replayStart!=null ? bootFrame(live,ms) : live;
    if(disposed || !data)return;
    const {layers,phase,auto,es}=model(data),steps=stagesFor(target);
    const stage=steps.findIndex(([id])=>id===phase),job=data.job;
    const failed=job.status==='failed'||job.status==='cancelled',running=data.running;
    const focus=container.contains(document.activeElement)?document.activeElement.dataset.bootFocus:null;
    const output=container.querySelector('.boot-console pre');
    const oldScroll=output?.scrollTop||0,atEnd=!output||output.scrollTop+output.clientHeight>=output.scrollHeight-4;
    const title=[names[target],data.hardware,data.os].join(' · ');
    const fragment=document.createElement('template');
    fragment.innerHTML=`<section class="first-boot">
      <header class="boot-title"><h1>First boot</h1><span>${icon(target==='native'?'monitor':'cpu')}${escape(title)}</span><a href="/">Change</a>
      <time class="boot-clock" aria-label="Boot elapsed">${clock(elapsed())}</time>
      <button class="boot-control" data-pause data-boot-focus="pause" aria-label="${pausedAt==null?'Pause view':'Resume view'}" title="${pausedAt==null?'Pause view':'Resume view'}" ${!live.trace.length || (!replayStart && pausedAt==null && live.running)?'disabled':''}>${pausedAt==null?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14m8-14v14"/></svg>':icon('play')}</button>
      <button class="boot-control" data-replay data-boot-focus="replay" aria-label="Replay boot" title="Replay boot" ${live.trace.length<2?'disabled':''}>${icon('rotate')}</button></header>
      <div class="boot-stages">${steps.map(([id,label],index)=>{
        const done=running || index<stage,active=!done&&index===stage&&Boolean(job.id||es.length),error=active&&(failed||data.stopped||data.unverified);
        const percent=active&&id==='build'?job.build_percent:null;
        return `<div class="boot-stage" data-state="${done?'done':error?'failed':active?'active':'waiting'}"><i>${done?drawnCheck:index+1}</i><div><header><strong>${label}</strong><small>${done?(id==='run'?'OPERATIONAL':'Ready'):error?(data.unverified?'Unverified':data.stopped?'Stopped':'Failed'):percent!=null?[job.build_activity,percent+'%'].filter(Boolean).join(' '):active?(id==='build'&&job.build_activity||'Running'):''}</small></header><div class="boot-meter"><b style="width:${done?100:percent||0}%"></b></div></div></div>`;
      }).join('')}</div>
      <div class="boot-layout"><section class="boot-stack"><h2>cFS · layer by layer</h2>
      ${layers.map(([id,name,glyph,chips,lit])=>`<button type="button" class="boot-layer" data-layer="${id}" data-boot-focus="${id}" title="${tooltips[id]}" aria-pressed="${id===(pick||auto)}" data-lit="${!!lit}"><span>${icon(glyph)}</span><strong>${escape(name)}</strong><span class="boot-chips">${chips.map(([text,on])=>chip(text,on)).join('')}</span></button>`).join('')}
      <button class="boot-disclosure" data-states data-boot-focus="states" aria-expanded="${stateOpen}">${icon(stateOpen?'chevron-down':'chevron-right')}ES state <code>${escape(es.at(-1)||'—')}</code></button>
      ${stateOpen?`<div class="boot-es">${data.es_states.map(x=>`<span data-lit="${es.includes(x)}">${x}</span>`).join('')}</div>`:''}</section>
      <section class="boot-picture" data-kind="${pick||auto}">${picture(pick||auto,data,layers)}</section></div>
      <section class="boot-console"><button class="boot-disclosure" data-console data-boot-focus="console" aria-expanded="${consoleOpen}">${icon(consoleOpen?'chevron-down':'chevron-right')}Console <code>${escape(data.lines.at(-1)||'—')}</code></button>${consoleOpen?`<pre>${escape(data.lines.join('\n'))}</pre>`:''}</section>
      <footer>${running?`<span class="boot-success">${drawnCheck}cFS is running</span><button class="primary" data-next data-boot-focus="next">Next · Ground Station</button>`:(!data.verified||data.unverified)?'<a href="/">Check target</a>':failed||data.stopped||err?'<button data-retry data-boot-focus="retry">Retry first boot</button>':''}<output>${escape(err||job.error||'')}</output></footer></section>`;
    const next=fragment.content.firstElementChild, existing=container.firstElementChild;
    if(existing?.children.length!==next.children.length)container.replaceChildren(next);
    else Array.from(next.children).forEach((node,i)=>{
      const current=existing.children[i];if(!current.isEqualNode(node))current.replaceWith(node);
    });
    if(focus)container.querySelector(`[data-boot-focus="${CSS.escape(focus)}"]`)?.focus({preventScroll:true});
    const nextOutput=container.querySelector('.boot-console pre');
    if(nextOutput)nextOutput.scrollTop=atEnd?nextOutput.scrollHeight:oldScroll;
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
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.layer)pick=pick===button.dataset.layer?'':button.dataset.layer;
    else if(button.hasAttribute('data-replay')){replayStart=performance.now();pausedAt=null;pick='';}
    else if(button.hasAttribute('data-pause')){
      if(pausedAt==null) pausedAt=elapsed();
      else {
        if(replayStart!=null) replayStart=performance.now()-pausedAt;
        pausedAt=null;
      }
    }
    else if(button.hasAttribute('data-console'))consoleOpen=!consoleOpen;
    else if(button.hasAttribute('data-states'))stateOpen=!stateOpen;
    else if(button.hasAttribute('data-next')){onNext();return;}
    else if(button.hasAttribute('data-retry')){button.disabled=true;await start();}
    draw();
  };
  container.innerHTML='<section class="first-boot"><h1>First boot</h1></section>';
  container.addEventListener('click',click);poll();
  return ()=>{disposed=true;clearTimeout(timer);container.removeEventListener('click',click);};
}
