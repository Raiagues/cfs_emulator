import {icon} from './ui.js';
import {mountShells} from './shell.js';

const actionLabels = {run:'Run cFS',build:'Build cFS',stop:'Stop cFS',connect:'Connect board',probe:'Connection check',simulate:'Synthetic data','simulate-preview':'Test sensor code',values:'Sensor values'};
export function actionLabel(action,target){
 if(action==='boot')return target==='physical'?'Connect board':'Start QEMU + Linux';
 if(action==='shutdown')return target==='physical'?'Shut down board':'Stop QEMU';
 if(action==='setup')return target==='physical'?'Set up board':'Set up QEMU';
 return actionLabels[action]||action;
}

export function mountTerminal({state,esc,layout,api,onStream,onCloseJob,onError}) {
 const output=document.querySelector('#logs');
 const shells=mountShells({api,onError});
 const sessions=document.querySelector('#terminal-sessions');
 const toggle=document.querySelector('#toggle-terminal');
 const positions=new Map();
 const contextJobs=new Map();
 let context='flight',contextKey=null;
 let closed;
 try{closed=new Set(JSON.parse(sessionStorage.getItem('flight-studio.closed-terminals')||'[]'));}catch{closed=new Set();}
 const saveClosed=()=>{try{sessionStorage.setItem('flight-studio.closed-terminals',JSON.stringify([...closed].slice(-100)));}catch{}};
 const visibleJobs=()=>state.jobs.filter(job=>!closed.has(job.id));
 const label=job=>job.action==='shell'?(job.name||'Shell'):job.action==='simulate'&&job.script?job.script.split('/').at(-1):job.action==='boot'&&job.retry?'Retry QEMU connection':job.action==='logs'?(job.kind==='boot'?'Linux output':'Run cFS'):actionLabel(job.action,job.target);
 const status=job=>job.status==='running'?'Running':({succeeded:'Completed',failed:'Failed',cancelled:'Ended'}[job.status]||job.status);
 const menu=document.createElement('details');
 menu.className='terminal-open';
 menu.innerHTML=`<summary class="icon-button" aria-label="Open terminal" title="Open terminal">${icon('plus')}</summary><div class="terminal-open-menu"></div>`;
 document.querySelector('#minimize-terminal').before(menu);
 document.addEventListener('click',event=>{if(!menu.contains(event.target))menu.open=false;});
 menu.addEventListener('keydown',event=>{if(event.key==='Escape'){menu.open=false;menu.querySelector('summary').focus();}});
 function remember(){if(output.dataset.job)positions.set(output.dataset.job,{top:output.scrollTop,left:output.scrollLeft,bottom:output.scrollTop+output.clientHeight>=output.scrollHeight-30});}
 output.addEventListener('scroll',remember);
 function show(visible=true){
  document.body.classList.toggle('no-terminal',!visible);
  toggle.classList.toggle('active',visible);toggle.setAttribute('aria-expanded',String(visible));
  layout.apply();
  if(visible)render();
 }
 function open(id){closed.delete(id);saveClosed();state.selectedJob=id;state.terminalStream=null;contextJobs.set(contextKey||state.target+':'+context,id);render();shells.focus();}
 function selectContext(next,{reveal=true}={}){
  context=next==='simulation'?'simulation':'flight';
  const key=(context==='simulation'?'qemu':state.target)+':'+context,jobs=visibleJobs();
  if(key!==contextKey||!jobs.some(job=>job.id===state.selectedJob)){
   const remembered=jobs.find(job=>job.id===contextJobs.get(key));
   const candidates=jobs.filter(job=>context==='simulation'?['simulate','simulate-preview'].includes(job.action):job.target===state.target&&!['simulate','simulate-preview','shell'].includes(job.action));
   const activeFlight=context==='flight'&&candidates.findLast(job=>job.status==='running'&&job.kind==='flight');
   const selected=remembered||activeFlight||candidates.findLast(job=>job.status==='running')||candidates.at(-1);
   state.selectedJob=selected?.id||null;
   state.terminalStream=null;
  }
  contextKey=key;
  if(reveal)show(!!state.selectedJob);else render();
 }
 function selectTarget(){
  selectContext(context,{reveal:false});
 }
 function row(job){
  const selected=job.id===state.selectedJob;
  const time=new Date(job.started*1000);
  const stamp=Number.isNaN(time.getTime())?'':time.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
  const closeTitle=job.action==='shell'?'Close shell and its running commands':job.status==='running'?(job.streaming&&job.action!=='simulate'?'Close output · Linux and cFS keep running':'Close output · operation keeps running'):'Close terminal';
  return `<div class="terminal-session-row ${selected?'selected':''}"><button type="button" class="terminal-session" data-terminal-job="${esc(job.id)}" aria-pressed="${selected}" title="${esc(label(job)+' · '+(job.target==='local'?'Local shell':job.target==='native'?'Native':job.target==='qemu'?'Emulator':'Board')+' · '+status(job))}">${icon(job.action==='build'?'build':job.action==='run'?'arrow-up-right':job.kind==='boot'?'cpu':'terminal')}<span>${esc(label(job))}</span><small>${stamp}</small><i class="session-dot ${job.status}"></i></button><button type="button" class="terminal-close" data-close-terminal="${esc(job.id)}" title="${closeTitle}" aria-label="Close ${esc(label(job))}">${icon('close')}</button></div>`;
 }
 function replaceKeepingFocus(parent,html){
  if(parent.innerHTML===html)return;
  const active=parent.contains(document.activeElement)?document.activeElement:null;
  const attr=['data-terminal-job','data-close-terminal','data-terminal-stream'].find(key=>active?.hasAttribute(key));
  const value=attr?active.getAttribute(attr):null;
  parent.innerHTML=html;
  if(attr)parent.querySelector(`[${attr}="${CSS.escape(value)}"]`)?.focus({preventScroll:true});
 }
 function render(){
  const jobs=visibleJobs(),job=jobs.find(job=>job.id===state.selectedJob);
  replaceKeepingFocus(sessions,[...jobs].reverse().map(row).join(''));
  sessions.hidden=!jobs.length;
  const streams=state.target==='native'?['flight']:['flight','boot'];
  const closedJobs=state.jobs.filter(job=>closed.has(job.id)).reverse();
  replaceKeepingFocus(menu.querySelector('.terminal-open-menu'),'<button type="button" data-new-shell>'+icon('terminal')+'<span>New terminal</span><small>Local shell</small></button>'+streams.map(kind=>`<button type="button" data-terminal-stream="${kind}">${icon(kind==='boot'?'cpu':'terminal')}<span>${kind==='boot'?'Linux output':'Run cFS output'}</span></button>`).join('')+(closedJobs.length?'<div class="terminal-menu-label">Closed outputs</div>'+closedJobs.map(job=>`<button type="button" data-terminal-job="${esc(job.id)}" title="${esc(status(job))}">${icon('terminal')}<span>${esc(label(job))}</span>${job.status==='running'?'<i class="session-dot running"></i>':''}</button>`).join(''):''));
  shells.select(job?.action==='shell'?job:null);
  output.hidden=job?.action==='shell';
  const key=job?.id||'empty',changed=output.dataset.job!==key;
  if(changed)remember();
  const position=positions.get(key),bottom=changed?position?.bottom!==false:output.scrollTop+output.clientHeight>=output.scrollHeight-30;
  const text=job?(job.lines.join('\n').replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,'')||'Waiting for process output…'):'No open terminal';
  if(output.textContent!==text)output.textContent=text;
  output.classList.toggle('terminal-empty',!job);
  output.dataset.job=key;
  if(bottom)output.scrollTop=output.scrollHeight;
  else if(changed)output.scrollTop=position?.top||0;
  if(changed)output.scrollLeft=position?.left||0;
  document.querySelector('#terminal-title').textContent=job?label(job)+' · '+(job.target==='local'?'Local shell':job.target==='native'?'Native':job.target==='qemu'?'Emulator':'Board'):'';
  document.querySelector('#job-status').textContent=document.body.classList.contains('backend-offline')?'Server disconnected':job?status(job):'';
  document.querySelector('#job-status').dataset.status=job?.status||'';
 }
 async function select(event){
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.closeTerminal){
   const job=state.jobs.find(job=>job.id===button.dataset.closeTerminal);if(!job)return;
   if(job.action==='shell'){await api('terminal/close',{id:job.id});shells.dispose(job.id);}
   else if(job.streaming&&job.action!=='simulate'&&job.status==='running')await onCloseJob(job);
   closed.add(job.id);saveClosed();
   if(state.selectedJob===job.id)state.selectedJob=null;
   selectTarget();
   sessions.querySelector('.selected .terminal-session')?.focus({preventScroll:true});
  }else if(button.hasAttribute('data-new-shell')){menu.open=false;const job=await api('terminal/create',{});state.jobs.push(job);show();open(job.id);}
  else if(button.dataset.terminalJob){open(button.dataset.terminalJob);menu.open=false;}
  else if(button.dataset.terminalStream){menu.open=false;await onStream(button.dataset.terminalStream);}
 }
 sessions.addEventListener('click',event=>select(event).catch(onError));
 menu.addEventListener('click',event=>select(event).catch(onError));
 function togglePanel(){show(document.body.classList.contains('no-terminal'));}
 toggle.onclick=togglePanel;
 document.querySelector('#minimize-terminal').onclick=()=>show(false);
 document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.code==='Backquote'){event.preventDefault();togglePanel();}});
 return {show,render,open,selectTarget,selectContext};
}
