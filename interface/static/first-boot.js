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
  const phase=job.phase||(job.action==='run'?'run':'build');
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
  const layer=layers.find(l=>l[0]===id),name=layer?.[1]||'Build';
  let figure;
  if(id==='build'){
    figure=`<div class="boot-sources">${['cfe/','osal/','psp/','apps/'].map(x=>`<span>${icon('folder')}${x}</span>`).join('')}</div><div class="boot-wire">↓</div><strong class="boot-object">${icon('cpu')}core-cpu1</strong>`;
  } else if(id==='hw'){
    figure=`<svg class="boot-hardware" viewBox="0 0 260 145" aria-label="${escape(data.hardware)}" role="img">${data.target==='native'?'<rect x="31" y="15" width="198" height="100" rx="6"/><rect x="40" y="23" width="180" height="81"/><path d="M105 130h50m-25-14v14M59 48h54m6 0h32M67 62h31m9 0h60M69 76h47"/>':'<g '+(data.target==='qemu'?'stroke-dasharray="6 4"':'')+'><rect x="23" y="14" width="202" height="119" rx="8"/><rect x="47" y="24" width="107" height="10"/><rect x="95" y="56" width="48" height="46"/><path d="M191 36h44v19h-44zm0 26h44v19h-44zm0 26h44v31h-44zM49 129v-12h19v12m16 0v-10h15v10"/></g>'}</svg><code>${escape(data.architecture)}</code>`;
  } else if(id==='os'){
    figure=`<div class="boot-processes" aria-label="Operating system processes">${Array.from({length:8},(_,i)=>i===5?'<b>cFS</b>':'<i></i>').join('')}</div><strong class="boot-object">${icon('terminal')}${escape(data.os)}</strong>`;
  } else if(id==='osal'||id==='psp'){
    const psp=id==='psp';
    figure=`<span class="boot-object">${psp?'OSAL':'Your app'}</span><span class="boot-wire">↓</span><strong class="boot-object">${name}</strong><div class="boot-fork"></div><div class="boot-options">${(psp?['pc-linux','pc-rtems','vxworks']:['Linux','RTEMS','VxWorks']).map((x,i)=>chip(x,i===0)).join('')}</div>`;
  } else if(id==='cfe'){
    figure=`<div class="boot-services">${layer[3].map(([service,lit])=>`<span data-lit="${lit}">${icon(serviceIcons[service][0])}<strong>${service}</strong><small>${serviceIcons[service][1]}</small></span>`).join('')}</div>`;
  } else {
    const preferred=['ci_lab','to_lab','sch_lab','sample_app'];
    const mapped=new Map(layer[3]);
    const ordered=[...preferred.filter(x=>mapped.has(x)),...mapped.keys()].filter((x,i,a)=>a.indexOf(x)===i).slice(0,4);
    const draw=(i)=>ordered[i]?chip(ordered[i],mapped.get(ordered[i])):'';
    figure=`<div class="boot-app-bus"><div>${draw(0)}${draw(1)}</div><span class="boot-sb">${icon('antenna')} ⇄ Software Bus</span><div>${draw(2)}${draw(3)}<span class="boot-slot">+ App</span></div></div>`;
  }
  return `<header><span class="boot-picture-icon">${icon(layer?.[2]||'build')}</span><h2 title="${tooltips[id]}">${escape(name)}</h2></header><div class="boot-figure">${figure}</div>`;
}
export function mountFirstBoot(container,{api,target,onNext}) {
  let disposed=false,timer=null,requested=false,data=null,pick='',consoleOpen=false,stateOpen=false,err='';
  const draw=()=>{
    if(disposed || !data)return;
    const {layers,phase,auto,es}=model(data),steps=stagesFor(target);
    const stage=steps.findIndex(([id])=>id===phase),job=data.job;
    const failed=job.status==='failed'||job.status==='cancelled',running=data.running;
    const focus=container.contains(document.activeElement)?document.activeElement.dataset.bootFocus:null;
    const output=container.querySelector('.boot-console pre');
    const oldScroll=output?.scrollTop||0,atEnd=!output||output.scrollTop+output.clientHeight>=output.scrollHeight-4;
    const title=names[target]+' · '+(target==='native'?data.hardware:data.os);
    const fragment=document.createElement('template');
    fragment.innerHTML=`<section class="first-boot">
      <header class="boot-title"><h1>First boot</h1><span>${icon(target==='native'?'monitor':'cpu')}${escape(title)}</span><a href="/">Change</a></header>
      <div class="boot-stages">${steps.map(([id,label],index)=>{
        const done=running || index<stage,active=!done&&index===stage&&Boolean(job.id),error=active&&failed;
        const percent=active&&id==='build'?job.build_percent:null;
        return `<div class="boot-stage" data-state="${done?'done':error?'failed':active?'active':'waiting'}"><i>${done?drawnCheck:index+1}</i><div><header><strong>${label}</strong><small>${done?(id==='run'?'OPERATIONAL':'Ready'):error?'Failed':percent!=null?percent+'%':active?'Running':''}</small></header><div class="boot-meter"><b style="width:${done?100:percent||0}%"></b></div></div></div>`;
      }).join('')}</div>
      <div class="boot-layout"><section class="boot-stack"><h2>cFS · layer by layer</h2>
      ${layers.map(([id,name,glyph,chips,lit])=>`<button type="button" class="boot-layer" data-layer="${id}" data-boot-focus="${id}" title="${tooltips[id]}" aria-pressed="${id===(pick||auto)}" data-lit="${!!lit}"><span>${icon(glyph)}</span><strong>${escape(name)}</strong><span class="boot-chips">${chips.map(([text,on])=>chip(text,on)).join('')}</span></button>`).join('')}
      <button class="boot-disclosure" data-states data-boot-focus="states" aria-expanded="${stateOpen}">${icon(stateOpen?'chevron-down':'chevron-right')}ES state <code>${escape(es.at(-1)||'—')}</code></button>
      ${stateOpen?`<div class="boot-es">${data.es_states.map(x=>chip(x,es.includes(x))).join('')}</div>`:''}</section>
      <section class="boot-picture" data-kind="${pick||auto}">${picture(pick||auto,data,layers)}</section></div>
      <section class="boot-console"><button class="boot-disclosure" data-console data-boot-focus="console" aria-expanded="${consoleOpen}">${icon(consoleOpen?'chevron-down':'chevron-right')}Console <code>${escape(data.lines.at(-1)||'—')}</code></button>${consoleOpen?`<pre>${escape(data.lines.join('\n'))}</pre>`:''}</section>
      <footer>${running?`<span class="boot-success">${drawnCheck}cFS is running</span><button class="primary" data-next data-boot-focus="next">Next</button>`:!data.verified?'<a href="/">Check target</a>':failed||data.stopped||err?'<button data-retry data-boot-focus="retry">Retry first boot</button>':''}<output>${escape(err||job.error||'')}</output></footer></section>`;
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
      const changed=JSON.stringify(next)!==JSON.stringify(data);
      data=next;
      if(changed)draw();
      if(data.verified&&!requested&&!data.running&&!data.job.id&&!data.stopped){await start();draw();}
    }catch(error){if(!disposed){err=error.message;if(data)draw();else container.textContent=err;}}
    if(!disposed)timer=setTimeout(poll,600);
  }
  const click=async event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.layer)pick=button.dataset.layer;
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
