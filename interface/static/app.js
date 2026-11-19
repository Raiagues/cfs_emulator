import {openModuleAction} from './module-actions.js';
import {mountSelector} from './selectors.js';
import {designSensor} from './sensor-designer.js';
import {mountLayout} from './layout.js';
import {mountTerminal,actionLabel} from './terminal.js';
import {icon,highlight} from './ui.js';
import {mountBoard,sensorHeaderPins} from './board.js';
import {renderArchitecture,renderGround,renderTelemetry} from './panels.js';
import {renderCommunication} from './communication.js';
import {layoutArchitecture} from './architecture.js';
import {renderSimulationBoard,renderSimulationSettings,changePattern,updateSignalValues} from './simulation.js';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {showLibraries:localStorage.getItem('mission.showLibraries')!=='false',token:'', workspace:null, hardware:null, ground:null, catalog:null, catalogTarget:null, catalogLoading:false, groundBusy:false, groundError:'', groundApp:'', view:'bench', files:new Map(), path:null, target:'native', sensorless:false, jobs:[], selectedJob:null, selectedDevice:null, inspected:null, archApp:'', simulation:null,simulationDirty:false, groundTab:'commands', groundSelection:null, groundPacket:null, terminalStream:null, history:new Map()};
let boardRenderer=null;
const treeStates=new Map(), lastFiles=new Map();
let treeRequest=0;
const isWorkbench=()=>['bench','simulation'].includes(state.view);
const fileRoot=()=>state.view==='simulation'?state.workspace?.simulation?.root||'sensors':'flight';
const scriptFor=device=>state.workspace?.simulation?.scripts[device?.model];
const simulationJob=()=>state.jobs.find(job=>job.action==='simulate'&&job.status==='running');
const communicationVisible=()=>state.view==='communication';
const button = (label, attrs='') => `<button type="button" ${attrs}>${label}</button>`;
const hex = n => Number.isInteger(n) ? '0x'+n.toString(16).toUpperCase().padStart(4,'0') : '—';
function paintIcons(root=document){root.querySelectorAll('[data-icon]').forEach(node=>{node.innerHTML=icon(node.dataset.icon);});}
function fileType(path){const ext=path.split('.').pop();return ({c:'C',h:'H',py:'PY',json:'{}',cmake:'CM',md:'M',sh:'SH',js:'JS',css:'#'})[ext]||'·';}
let feedbackTimer;
function feedback(message, error=false) { clearTimeout(feedbackTimer);$('#feedback').textContent=message; $('#feedback').classList.toggle('error',error);if(!error)feedbackTimer=setTimeout(()=>{$('#feedback').textContent='';},5000); }
function backendState(connected){
 const wasOffline=document.body.classList.contains('backend-offline');
 document.body.classList.toggle('backend-offline',!connected);
 if(!connected)$('#job-status').textContent='Disconnected from server';
 if(connected&&wasOffline&&$('#feedback').dataset.network==='true'){feedback('Connection restored');delete $('#feedback').dataset.network;}
}
async function api(path,body,retry=true){
 let response;
 try{response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':state.token},body:JSON.stringify(body)});}
 catch{
  backendState(false);$('#feedback').dataset.network='true';
  throw Error(body===undefined?'Local server disconnected. Reconnecting…':'Connection interrupted. Check the terminal before retrying the operation.');
 }
 backendState(true);
 const data=await response.json();
 if(response.status===403&&body!==undefined&&retry){state.token=(await api('session')).token;return api(path,body,false);}
 if(!response.ok)throw Error(data.error||response.statusText);
 return data;
}
function guarded(fn) { return (...args) => Promise.resolve().then(()=>fn(...args)).catch(e=>feedback(e.message,true)); }
let workspaceRequest=0, snapshotSequence=0, appliedSnapshot=0;
async function refresh(tree=false) {
  // A poll may overlap the mandatory refresh after a mutation. Finish that
  // refresh even when another read is in flight, and never apply an older snapshot.
  const epoch=workspaceRequest, request=++snapshotSequence, snapshot=await api('workspace');
  if(epoch!==workspaceRequest)return;
  if(request<appliedSnapshot){if(tree)await renderTree();return;}
  appliedSnapshot=request;
  const changed=JSON.stringify(snapshot)!==JSON.stringify(state.workspace);state.workspace=snapshot;state.coreServices=snapshot.core_modules||[];
 $('#project-title').textContent=state.workspace.name||'cFS';
  backendState(true);
  renderToolbar();if(tree||changed||!document.body.classList.contains('no-tree'))await renderTree();if(changed||tree)renderView();
}
async function renderTree() {
 const root=$('#tree'), path=fileRoot(), previous=root.dataset.root;
 if(previous)treeStates.set(previous,{expanded:[...root.querySelectorAll('details[open]')].map(folder=>folder.dataset.path),scroll:root.scrollTop});
 const saved=treeStates.get(path)||{expanded:path==='flight'?['mission','cFS','cFS/apps']:[],scroll:0};
 const request=++treeRequest,fragment=document.createDocumentFragment();
 await loadTree(path,fragment);
 if(request!==treeRequest)return;
 root.replaceChildren(fragment);root.dataset.root=path;
 $('#explorer-title').textContent=state.view==='simulation'?'SYNTHETIC DATA':'FLIGHT SOFTWARE';
 root.setAttribute('aria-label',state.view==='simulation'?'Simulation files':'Flight software files');
 for(const path of saved.expanded){
  const folder=[...root.querySelectorAll('details')].find(folder=>folder.dataset.path===path);
  if(folder){folder.open=true;await folder._load();}
 }
 root.scrollTop=saved.scroll;markFiles();
}
function gitBadge(entry){
 const status={new:['A','New'],modified:['M','Modified']}[entry.change];
 return status?`<small class="tree-git ${entry.change}" title="${status[1]}" aria-label="${status[1]}">${status[0]}</small>`:'';
}
async function loadTree(path, parent) {
  const listing=await api('tree?path='+encodeURIComponent(path)); parent.replaceChildren();
  for(const entry of listing.entries) {
    if(entry.type==='directory') {
      const details=document.createElement('details'), summary=document.createElement('summary'), children=document.createElement('div');
      summary.innerHTML='<span class="icon">'+icon('folder')+'</span><span>'+esc(entry.name)+'</span>'+gitBadge(entry);details.className='tree-group';details.dataset.path=entry.path;details.append(summary,children);parent.append(details);
      details._load=async()=>{if(!details._pending)details._pending=loadTree(entry.path,children);await details._pending;};
      details.addEventListener('toggle',guarded(async()=>{if(details.open)await details._load();}));
    } else {
      const b=document.createElement('button'); b.className='file file-row'; b.innerHTML='<span class="file-type '+(entry.name.endsWith('.h')?'header':entry.name.endsWith('.json')?'json':'')+'">'+fileType(entry.path)+'</span><span>'+esc(entry.name)+'</span>'+gitBadge(entry); b.dataset.file=entry.path; b.title=entry.path;
      parent.append(b);
    }
  }
  markFiles();
}
async function openFile(path, line, reveal=true, inspection=null) {
  if(state.view==='simulation'&&state.simulationDirty)await saveSimulation();
   if(!state.files.has(path)) {
    const data=await api('file?path='+encodeURIComponent(path));
    if(data.binary) throw Error(data.reason || 'Binary file; open the artifacts on disk.');
    state.files.set(path,{...data,saved:data.content});
  }
  state.sourcePreview=inspection;
  state.path=path;lastFiles.set(path.startsWith((state.workspace.simulation?.root||'sensors')+'/')?'simulation':'flight',path);
  const sourceDevice=state.workspace.project.devices.find(device=>scriptFor(device)===path);
  if(sourceDevice)state.selectedDevice=sourceDevice.id;
  state.activeLine=line||1; const selectedApp=state.workspace?.apps.find(a=>path.startsWith(a.path+'/'));if(selectedApp&&!inspection)state.groundApp=selectedApp.name; const file=state.files.get(path);
  $('#code').value=file.content; $('#code').disabled=false;$('#code').readOnly=!file.editable||!!inspection;
  $('#source-location').hidden=!inspection;$('#source-location span').textContent=inspection?inspection.symbol+' · '+path.split('/').at(-1)+':'+line:'';
  if(reveal||document.body.classList.contains('code-only'))document.body.classList.remove('no-editor');
 renderTabs(); lineNumbers(); markFiles(); renderView();renderToolbar();
  if(line){const offset=file.content.split('\n').slice(0,line-1).join('\n').length+(line>1?1:0);$('#code').setSelectionRange(offset,offset);$('#code').scrollTop=Math.max(0,(line-4)*parseFloat(getComputedStyle($('#code')).lineHeight));syncScroll();}
 if(reveal)await revealFile(path);document.body.classList.remove('mobile-tree');
}
function renderTabs() {
 $('#tabs').innerHTML=[...state.files].map(([p,f])=>`<div class="file-tab ${state.path===p?'active':''}"><button data-file="${esc(p)}" title="${esc(p)}"><span class="file-type">${fileType(p)}</span><span class="tab-label">${esc(p.split('/').pop())}</span>${f.content!==f.saved?'<i class="tab-dirty"></i>':''}</button><button data-close-file="${esc(p)}" title="Close file">${icon('close')}</button></div>`).join('');
}
async function revealFile(path){const parts=path.split('/');for(let i=1;i<parts.length;i++){const folder=[...document.querySelectorAll('#tree details')].find(d=>d.dataset.path===parts.slice(0,i).join('/'));if(folder){folder.open=true;await folder._load();}}markFiles();[...document.querySelectorAll('.file')].find(b=>b.dataset.file===path)?.scrollIntoView({block:'nearest'});}
function markFiles(){document.querySelectorAll('.file').forEach(b=>b.classList.toggle('selected',b.dataset.file===state.path));}
function syncScroll(){
 const code=$('#code'),layer=$('#highlight-layer'),marker=$('#source-line');
 layer.scrollTop=code.scrollTop;layer.scrollLeft=code.scrollLeft;
 $('#line-numbers').scrollTop=layer.scrollTop;
 marker.hidden=!state.sourcePreview;
 if(!marker.hidden){
  const height=parseFloat(getComputedStyle(code).lineHeight);
  marker.style.height=height+'px';
  marker.style.top=((state.activeLine-1)*height-layer.scrollTop)+'px';
 }
}
function lineNumbers(){const value=$('#code').value;$('#line-numbers').textContent=Array.from({length:value.split('\n').length},(_,i)=>i+1).join('\n');$('#highlight-code').innerHTML=highlight(value,state.path||'');syncScroll();}
async function saveFile(path) {
 const file=state.files.get(path);
 if(!file?.editable)return;
 if(file.saving)await file.saving;
 if(file.content===file.saved)return;
 const content=file.content;
 file.saving=api('file',{path,content,expected_hash:file.hash});
 try{const saved=await file.saving;Object.assign(file,{hash:saved.hash,saved:content});renderTabs();}
 finally{delete file.saving;}
}
async function save(){if(state.path){await saveFile(state.path);feedback('File saved');await refresh();}}
async function saveAll(){for(const path of state.files.keys())await saveFile(path);}
async function refreshSimulation(){
 try{state.simulation=await api('simulation');state.simulationError='';state.simulationDirty=false;if(!state.simulation.available.some(device=>device.id===state.selectedDevice))state.selectedDevice=null;}
 catch(error){state.simulationError=error.message;throw error;}
 finally{renderSimulationPanel(true);}
}
function renderSimulationPanel(force=false){
 const visible=state.view==='simulation',job=simulationJob();
 document.body.classList.toggle('editing-signals',visible&&state.signalSidebar!==false);
 $('#simulation-toolbar').hidden=!visible||!state.selectedDevice;
 $('#simulation-fields').hidden=!visible||state.signalSidebar===false;
 document.body.classList.toggle('simulation-widgets',visible);
 const previewBusy=state.jobs.some(job=>job.action==='simulate-preview'&&job.status==='running');
 $('[data-simulation-test]').textContent=previewBusy?'Stop test':'Start test';
 $('[data-simulation-test]').disabled=!!job||state.simulationSaving||!state.selectedDevice;
 const saveButton=$('#simulation-toolbar [data-simulation-save]');saveButton.textContent=state.simulationSaving?'Saving…':state.simulationDirty?'Save •':'Save';saveButton.disabled=!!job||previewBusy||state.simulationSaving;
 $('[data-simulation-start]').hidden=!!job;$('[data-simulation-stop]').hidden=!job;
 $('#simulation-reason').textContent=state.target==='physical'?'Physical sensors supply their own data.':state.target==='native'?'Select Emulator to send samples.':!state.hardware?.qemu?.running?'Start the emulator to send samples.':'';
 $('[data-simulation-start]').disabled=previewBusy||state.target!=='qemu'||!state.hardware?.qemu?.running||!!operation();
 const fields=$('#simulation-fields'),viewKey=[state.target,state.simulation?.available.map(d=>d.id).join(','),state.selectedDevice,state.signalOutput,!!job,previewBusy,state.simulationSaving].join('/');
 if(visible&&(force||fields.dataset.viewKey!==viewKey)){
  fields.innerHTML=renderSimulationSettings(state,{esc});
  fields.dataset.viewKey=viewKey;
 }
}
async function saveSimulation(){
 if(simulationJob())throw Error('Stop synthetic data before changing its session settings');
 if($('#simulation-form')&&!$('#simulation-form').reportValidity())throw Error('Complete the signal settings before saving');
 state.simulationSaving=true;renderSimulationPanel();
 try{
   const dirty=[...state.files.values()].find(file=>file.path.startsWith('sensors/')&&file.content!==file.saved);
   if(dirty)throw Error('Save '+dirty.path.split('/').at(-1)+' before saving signal settings');
   state.simulation=await api('simulation',{settings:state.simulation.settings,expected_hash:state.simulation.hash});
   state.simulationDirty=false;
   for(const path of state.simulation.sources){if(!state.files.has(path))continue;const file=await api('file?path='+encodeURIComponent(path));state.files.set(path,{...file,saved:file.content});if(state.path===path){$('#code').value=file.content;lineNumbers();renderTabs();}}
  state.simulationError='';
 }catch(error){state.simulationError=error.message;throw error;}
 finally{state.simulationSaving=false;renderSimulationPanel(true);}
}
async function selectSimulationDevice(id){
 state.signalSidebar=true;
 if(id!==state.selectedDevice)state.signalOutput=null;
 state.selectedDevice=id;
 if(!state.simulation?.settings.sensors.some(s=>s.device===id))addSimulationSensor(id);
 renderView();
}
function addSimulationSensor(id){
 if(simulationJob())return;
 const device=state.simulation?.available.find(device=>device.id===id);
 if(!device||state.simulation.settings.sensors.some(sensor=>sensor.device===id))return;
 state.simulation.settings.sensors.push(structuredClone(device.defaults));state.selectedDevice=id;state.simulationDirty=true;renderView();
}
async function startSimulation(){
 if(state.view!=='simulation')await selectView('simulation');
 if(state.target!=='qemu'||!state.hardware?.qemu?.running)throw Error('Start the emulator before sending synthetic data');
 if(state.simulationDirty)await saveSimulation();
 for(const path of state.files.keys())if(path.startsWith('sensors/'))await saveFile(path);
 await startJob('simulate');terminal.selectContext('simulation',{reveal:false});
}
async function testSimulation(){
 const active=state.jobs.find(j=>j.action==='simulate-preview'&&j.status==='running');
 if(active)return stopSimulation('simulate-preview');
 if(state.simulationDirty)await saveSimulation();
 if(!state.selectedDevice)throw Error('Select a sensor to test.');
 await startJob('simulate-preview',{device:state.selectedDevice});terminal.selectContext('simulation',{reveal:false});
}
async function stopSimulation(action='simulate'){
 for(const job of state.jobs.filter(job=>job.action===action&&job.status==='running'))await api('job/cancel',{id:job.id});
 await pollJobs();renderSimulationPanel(true);
}
document.addEventListener('input',event=>{
 if(!event.target.closest('#simulation-form')||!state.simulation||simulationJob())return;
 const field=event.target;
 if(field.name==='interval')state.simulation.settings.interval=Number(field.value);
 else if(field.dataset.signalProperty){
  const sensor=state.simulation.settings.sensors.find(sensor=>sensor.device===state.selectedDevice);
  if(sensor){
   const settings=sensor.signals[field.dataset.signalProperty];
   if(field.name==='variation'){
    const saved=state.simulation.available.find(device=>device.id===sensor.device).defaults.signals[field.dataset.signalProperty];
    sensor.signals[field.dataset.signalProperty]=changePattern(settings,field.value,saved);
   }else if(field.name==='enabled')settings.enabled=field.checked;
   else settings[field.name]=Number(field.value);
  }
 }else return;
 state.simulationDirty=true;renderSimulationPanel();
});
document.addEventListener('change',event=>{
 const field=event.target;
 if(field.id==='simulation-add')addSimulationSensor(field.value);
 else if(field.dataset.simulationEnable){const sensor=state.simulation?.settings.sensors.find(sensor=>sensor.device===field.dataset.simulationEnable);if(sensor){sensor.enabled=field.checked;state.simulationDirty=true;renderView();}}
 else if(field.closest('#simulation-form')&&['variation','enabled'].includes(field.name))renderSimulationPanel(true);
});
document.addEventListener('submit',event=>{if(event.target.id==='simulation-form'){event.preventDefault();guarded(saveSimulation)();}});
let launchPending=null;
const boardSelector=mountSelector('board-select',value=>{state.board=value||null;state.os=null;renderToolbar();if(!value)guarded(configureProfile)();},esc);
const osSelector=mountSelector('os-select',value=>{state.os=value||null;renderToolbar();if(value)guarded(configureProfile)();},esc);
const operation=()=>state.jobs.find(job=>job.status==='running'&&!job.streaming)||launchPending;
const progressLabels={build:'Building cFS',run:'Starting cFS',stop:'Stopping cFS',connect:'Connecting to board',probe:'Checking connection',values:'Updating sensor values',simulate:'Starting synthetic data',logs:'Opening log'};
function renderProgress(){
 const completedBoot=state.jobs.find(j=>j.action==='boot'&&j.target===state.target&&j.operation_complete&&Date.now()/1000-(j.ready_at||0)<6);
 const job=operation()||completedBoot,status=$('#operation-status');
 status.hidden=!job;document.body.classList.toggle('is-operating',!!job);
 const pipeline=$('#boot-stages');
 pipeline.hidden=job?.action!=='boot'||job.target!=='qemu';
 if(!pipeline.hidden){
  const stage=job.operation_complete?5:job.boot_stage??(job.retry?4:0);
  pipeline.innerHTML=['Check image','Open disk','Prepare SSH key','Boot OS','Connect SSH','Ready'].map((name,i)=>`<li class="${i<stage||stage===5?'done':i===stage?'current':''}">${i<stage?'✓ ':''}${name}</li>`).join('');
 }
 if(!job)return;
 const physical=job.target==='physical',label=job.action==='boot'?(physical?'Connecting to board':job.operation_complete?'Emulator ready':job.retry?'Checking emulator SSH':'Starting emulator'):job.action==='shutdown'?(physical?'Shutting down board':'Stopping emulator'):job.action==='setup'?(physical?'Preparing board':'Setting up QEMU'):progressLabels[job.action]||'Working';
 $('#operation-label').textContent=label+' · '+(job.target==='native'?'Native':physical?'Board':'Emulator');
 $('#operation-time').textContent=Math.max(0,Math.floor(Date.now()/1000-job.started))+'s';
 status.title='Execution controls become available when this operation finishes.';
}
function renderToolbar(){
 const catalog=state.workspace?.catalog,project=state.workspace?.project;
 const profiles=state.hardware?.profiles||(catalog?.os||[]).map(os=>({board:catalog.board,board_label:catalog.name,os,os_label:catalog.os_labels?.[os]||os,targets:catalog.targets||[]}));
 if(!project)return;
 const boards=[{value:'',label:'Select board'},...[...new Map(profiles.filter(profile=>profile.board).map(profile=>[profile.board,{value:profile.board,label:profile.board_label||profile.board}])).values()]];
 if(state.board===undefined)state.board=project.board;
 if(state.os===undefined)state.os=project.os;
 const systems=[{value:'',label:state.board?'Select OS':'Host OS'},...profiles.filter(profile=>profile.board===state.board&&profile.os).map(profile=>({value:profile.os,label:profile.os_label||profile.os}))];
 const profile=profiles.find(profile=>profile.board===project.board&&profile.os===project.os),job=operation(),busy=!!job||state.profileBusy||!state.hardware;
 const targets=['native',...(profile?.targets||[])];
 boardSelector.update(boards,state.board||'',busy);osSelector.update(systems,state.os||'',busy||!state.board);
 for(const target of document.querySelectorAll('.target-switch button')){target.disabled=busy;target.setAttribute('aria-pressed',String(state.target===target.dataset.target));}
 const boot=$('.boot-action'),physical=state.target==='physical',native=state.target==='native';
 $('.profile-selectors').hidden=native;
 $('#native-host').hidden=!native;
 $('#native-host').textContent=['This computer',state.hardware?.native?.os,state.hardware?.native?.architecture].filter(Boolean).join(' · ');
 const needsSetup=state.target==='qemu'&&state.hardware&&(!state.hardware.docker?.available||!state.hardware.qemu?.ssh_configured||state.hardware.qemu?.image_ready===false);
 boot.hidden=native;boot.dataset.job=physical?(state.hardware?.physical?.connection?'probe':'connect'):needsSetup?'setup':'boot';
 boot.querySelector('.action-label').textContent=actionLabel(boot.dataset.job,state.target);
 if(!physical&&!native&&!needsSetup&&state.hardware?.qemu?.can_retry_boot)boot.querySelector('.action-label').textContent='Retry QEMU connection';
 boot.classList.toggle('connected',physical&&!!state.hardware?.physical?.last_probe?.connected);
 boot.title=physical?'Connect to the powered-on board over SSH':needsSetup?'Prepare QEMU and its Linux image':'Start the QEMU emulator and boot Linux';
 $('.shutdown-action').hidden=physical||native;
 for(const button of document.querySelectorAll('.top-actions [data-job]')){
  button.disabled=busy||!targets.includes(state.target);
  const active=!!job&&job.action===button.dataset.job;
  button.classList.toggle('is-running',active);button.setAttribute('aria-busy',String(active));
 }
 if(state.target==='qemu'&&!needsSetup&&state.hardware)boot.disabled=busy||!(state.hardware.qemu.can_boot||state.hardware.qemu.can_retry_boot);
 if(state.target==='qemu'&&state.hardware?.qemu?.linux_ready)boot.title='QEMU is already running. Stop QEMU before starting again.';
 else if(state.target==='qemu'&&state.hardware?.qemu?.can_retry_boot)boot.title='Retry the Linux connection in the existing QEMU instance';
 $('.shutdown-action').disabled=busy||!state.hardware?.qemu?.running;
 const active=native?state.hardware?.native?.running:physical?state.hardware?.physical?.last_probe?.flight_running:state.hardware?.qemu?.flight_running;
 const runningTarget=state.hardware?.execution?.target;
 $('.stop-action').disabled=busy||(!active&&!runningTarget);
 $('.stop-action').title=runningTarget?'Stop cFS · '+({native:'this computer',qemu:'emulator',physical:'physical board'}[runningTarget]):'Stop cFS';
 const build=state.workspace.builds?.[state.target];
 const buildButton=$('.build-action');
 const stale=build?.exists && build?.stale;
 buildButton.classList.toggle('needs-build',!!stale);
 buildButton.lastElementChild.textContent=stale?'Rebuild cFS':'Build cFS';
 $('.run-action').disabled=!build?.exists||!build.current||busy||!targets.includes(state.target)||state.hardware?.execution?.can_start!==true;
 $('.run-action').title=!build?.exists||!build.current?'Build cFS for this target first':state.hardware?.execution?.block_reason||(native?'Run cFS on this computer':'Run cFS on the selected target');
 buildButton.title=stale?'Mission sources have changed since the last build for this target':native?'Compile cFS for this computer':'Compile cFS for the configured board and OS';
 renderProgress();
 renderSimulationPanel();
}
function architecture(){return renderArchitecture(state,{esc,hex,icon});}
function bench() {
 const w=state.workspace,h=state.hardware,physical=state.target==='physical';
 if(state.target==='native')return `<div class="bench-shell native-bench"><div class="board-title"><div class="board-identity">${icon('monitor')}<div><h1>This computer</h1><span class="board-status"><i class="${h?.native?.running?'active':''}"></i>${h?.native?.running?'cFS running':'Native execution'} · ${esc(h?.native?.os||'Host OS')} · ${esc(h?.native?.architecture||'')}</span></div></div></div><div class="bench-canvas"><div id="board-stage" class="board-stage"></div></div></div>`;
 if(!w.project.board)return `<div class="hardware-empty">${icon('cpu')}<h2>Select a board and OS</h2>${button('Select board','data-choose-board')}</div>`;
 const probe=h?.physical?.last_probe,connection=h?.physical?.connection;
 const selected=w.project.devices.find(d=>d.id===state.selectedDevice)||w.project.devices[0];
 state.selectedDevice=selected?.id||null;
 const active=physical?(probe?.connected?probe.service==='active':null):h?.qemu?.flight_running;
 const available=physical?probe?.connected:h?.qemu?.running;
 const status=physical&&!connection?'Not connected':active?'cFS running':available===false?'Powered off':active===false&&available?'Linux ready':h?'Status unavailable':'Checking…';
 const boardName=h?.profiles?.find(profile=>profile.board===w.project.board)?.board_label||w.project.board;
 return `<div class="bench-shell">
   <div class="board-title"><div class="board-identity">${icon('cpu')}<div><h1><button data-inspect="board" title="Board details">${esc(boardName)}</button></h1>${physical?`<button class="board-status" data-connect title="Connect or change physical board"><i class="${active?'active':''}"></i>${esc(connection?.host||'Connect board')}${icon('chevron-down')}</button>`:`<span class="board-status"><i class="${active?'active':''}"></i>${status}</span>`}</div></div><div class="bench-title-actions">${button(icon('plus')+' Add sensor','data-create="device" class="add-sensor"')}</div></div>
   <div class="bench-canvas"><div id="board-stage" class="board-stage"></div>${hardwareDetails()}</div>
 </div>`;
}
function hardwareDetails(){
 const w=state.workspace,id=state.inspected;
 if(!id)return '';
 const board=id==='board',device=w.project.devices.find(device=>device.id===id);
 if(!board&&!device)return '';
 const model=device&&w.catalog.models[device.model],binding=device&&w.simulation.bindings?.[id];
 const profile=state.hardware?.profiles?.find(profile=>profile.board===w.project.board&&profile.os===w.project.os);
 const title=board?profile?.board_label||w.project.board:device.name;
 const fields=board?[['QEMU machine',w.project.board],['System',profile?.os_label||w.project.os],['I²C buses',Object.keys(w.catalog.buses).join(', ')]]:
  [['Bus',device.bus],['I²C address',hex(device.address).replace('0x00','0x')],['Linux device',binding?.linux_device||'—'],['Flight driver',model.cfs_driver||'Not available']];
 return `<section class="cad-details" aria-label="${board?'Board':'Sensor'} details"><header><div><strong>${esc(title)}</strong>${device?`<span>${esc(device.model)}</span>`:''}</div>${!board?button(icon('pencil'),`class="icon-button" data-hardware-settings="${esc(device.id)}" title="Configure bus and address" aria-label="Configure bus and address"`)+button(icon('more'),'class="icon-button" data-sensor-menu title="Sensor options" aria-label="Sensor options"'):''}${button(icon('close'),'class="icon-button" data-close-inspection title="Close details" aria-label="Close details"')}</header><dl>${fields.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>${device?`<div class="sensor-test-actions">${button('Test sensor',`data-test-device="${esc(device.id)}" ${state.target==='native'?'disabled title="Select a board or emulator to read I²C."':''}`)}${model.register_model?button('Validate model',`data-test-model="${esc(device.id)}" title="Check the compiled QEMU model on a separate emulated board"`):''}</div>${sensorReadings(device)}`:''}</section>`;
}
function sensorReadings(device){
 const readings={};
 for(const job of state.jobs){
  const result=job.result;
  if(job.action==='sensor-test'&&job.status==='succeeded'&&job.device===device.id&&result?.model===device.model&&result.address===device.address&&result.bus===device.bus)readings[job.target]=job;
 }
 const names=[...new Set(Object.values(readings).flatMap(job=>Object.keys(job.result.values)))];
 const sleepNotice=Object.entries(readings).filter(([,job])=>job.result.asleep).map(([target,job])=>
  `<p class="sensor-sleep">${target==='qemu'?'Emulator':'Board'} · ID ${esc(hex(job.result.identity))} verified. Start the flight reader to wake this sensor.</p>`).join('');
 if(!names.length)return sleepNotice;
 const value=(job,name)=>{const sample=job?.result.values[name];return sample?esc(sample.value.toFixed(3)+' '+sample.unit):'—';};
 const stamp=job=>job?`<small>${esc(new Date(job.ended*1000).toLocaleTimeString())}</small>`:'';
 return sleepNotice+`<table class="sensor-comparison"><caption>Last measured samples</caption><thead><tr><th>Output</th><th>Emulator${stamp(readings.qemu)}</th><th title="${esc(readings.physical?.connection?.host||'')}">Board${stamp(readings.physical)}</th></tr></thead><tbody>${names.map(name=>`<tr><th>${esc(name)}</th><td>${value(readings.qemu,name)}</td><td>${value(readings.physical,name)}</td></tr>`).join('')}</tbody></table>`;
}
function wireStorageKey(){return "studio-wires:"+location.host+":"+state.workspace.project.board;}
async function hardwareSettings(id){
 const settings=await api('hardware/device?id='+encodeURIComponent(id)),device=settings.device;
 const wiring=JSON.parse(localStorage.getItem(wireStorageKey())||'{}');
 const options=sensorHeaderPins;
 const pins=Object.entries(options).map(([signal,list])=>`<label>${signal}<select name="${signal}">${list.map(pin=>`<option value="${pin}" ${wiring[id]?.[signal]===pin?'selected':''}>Pin ${pin} · ${signal==='VCC'?'3.3 V':signal}</option>`).join('')}</select></label>`).join('');
 dialog(device.model,`<label>Bus<select name="bus">${Object.entries(settings.buses).map(([name,bus])=>`<option value="${esc(name)}" ${name===device.bus?'selected':''}>${esc(name)} · ${esc(bus.device)}</option>`).join('')}</select></label><label>I²C address<input name="address" value="${hex(device.address)}" required pattern="(0[xX][0-9a-fA-F]+|[0-9]+)"></label><fieldset><legend>Pi header wiring</legend>${pins}<label>2D bend offset (px)<input type="number" min="-400" max="400" name="bend" value="${wiring[id]?.bend||0}"></label></fieldset>`,async values=>{
  requireSavedMission();const result=await api('hardware/device',{id,bus:values.bus,address:values.address,expected_hash:settings.source.hash});
  wiring[id]=Object.fromEntries(Object.keys(options).map(key=>[key,Number(values[key])]));wiring[id].bend=Number(values.bend);localStorage.setItem(wireStorageKey(),JSON.stringify(wiring));
  await reloadMissionFiles(result.changed,result.deleted);feedback('Sensor configuration saved · restart QEMU to apply');
 });
}
function sensorMenu(){
 const d=state.workspace.project.devices.find(d=>d.id===state.selectedDevice);if(!d)return;
 const readers=state.workspace.project.apps.flatMap(app=>Object.entries(app.sensors).filter(([,device])=>device===d.id).map(([name])=>({app:app.name,name,telemetry:Object.entries(app.telemetry_bindings).filter(([,sensor])=>sensor===name).map(([name])=>name)})));
 dialog(d.name,`<p>${esc(d.model)} · ${esc(d.bus)} · ${hex(d.address)}</p>${readers.length?`<p>Detach app readers before removing this device.</p>${readers.map(reader=>`<div class="settings-actions"><code>${esc(reader.app)} / ${esc(reader.name)}</code>${reader.telemetry.map(name=>button('Remove '+esc(name)+' telemetry',`data-remove="telemetry" data-app="${esc(reader.app)}" data-name="${esc(name)}"`)).join('')}${button('Remove reader',`data-remove="sensor" data-app="${esc(reader.app)}" data-name="${esc(reader.name)}" ${reader.telemetry.length?'disabled':''}`)}</div>`).join('')}`:''}<div class="settings-actions">${button('Open settings','data-file="project/config.json"')}${state.target==='qemu'?button('Reset all signals',`data-job="values" ${!state.hardware?.qemu?.running||state.jobs.some(job=>job.action==='simulate'&&job.status==='running')?'disabled title="Stop Python signals before resetting"':''}`):''}${button('Remove sensor',`data-remove="device" data-name="${esc(d.id)}" ${readers.length?'disabled':''}`)}</div>`);
}
function ground(){return renderGround(state,{esc,hex,icon});}
function renderView(){
 if(!state.workspace)return;
 const detailState=new Map([...(state.view==='architecture'?Object.entries(state.archDetails||{}):[]),...(document.body.dataset.view===state.view?[...$('#view').querySelectorAll('details[data-detail-key]')].map(d=>[d.dataset.detailKey,d.open]):[])]);
 const groundScroll=$('.gs-definition-list')?.scrollTop||0;
 const architectureScroll=$('.architecture-scroll')?.scrollTop||0;
 const paneScroll=[...document.querySelectorAll('.architecture-pane-content,.communication-browser>nav,.communication-message')].map(node=>({className:node.className,top:node.scrollTop}));
 const oldBoard=isWorkbench()&&document.body.dataset.view===state.view?$('#board-stage'):null;
 if(!oldBoard&&boardRenderer){boardRenderer.destroy();boardRenderer=null;}
 document.body.dataset.view=state.view;
 document.body.classList.toggle('simulation-mode',state.view==='simulation');
 document.body.classList.toggle('simulation-widgets',state.view==='simulation');
 const html=({architecture,bench,communication:()=>renderCommunication(state,{esc,icon}),simulation:()=>renderSimulationBoard(state,{esc}),ground}[state.view])();
 if(oldBoard && html.includes('id="board-stage"')){
  // Keep the canvas connected while hardware status and sensor settings refresh.
  const next=document.createElement('template');next.innerHTML=html;
  const shell=$('#view').firstElementChild,nextShell=next.content.firstElementChild;
  shell.className=nextShell.className;
  shell.firstElementChild.replaceWith(nextShell.firstElementChild);
  const nextStage=next.content.querySelector('#board-stage');
  while(oldBoard.nextElementSibling)oldBoard.nextElementSibling.remove();
  oldBoard.after(...Array.from(nextStage.parentElement.children).filter(el=>el!==nextStage));
 }else $('#view').innerHTML=html;
 $('#visual-heading').hidden=isWorkbench();
 $('#visual-title').innerHTML=isWorkbench()?'':icon({architecture:'layers',ground:'antenna',communication:'link'}[state.view])+({architecture:'Architecture',ground:'Ground Station',communication:'Communication'}[state.view]);
 syncNavigation();
 if($('#board-stage')&&isWorkbench()&&(state.workspace.project.board||state.target==='native')){
  const native=state.target==='native';
  const options={hostOS:state.hardware?.native?.os,board:native?'native':state.workspace.project.board,context:state.view,devices:native?[]:state.workspace.project.devices,pinAssignments:JSON.parse(localStorage.getItem(wireStorageKey())||"{}"),selected:state.inspected==='board'?'board':state.selectedDevice,onInspect:id=>{if(state.view!=='simulation'){state.inspected=id;renderView();}},onSelect:id=>guarded(async()=>{if(state.view==='simulation')await selectSimulationDevice(id);else{state.selectedDevice=id;state.inspected=id;renderView();}})()};
  if(oldBoard&&boardRenderer)boardRenderer.update(options);
  else boardRenderer=mountBoard($('#board-stage'),options);
 }
 if(!$('#board-stage')&&boardRenderer){boardRenderer.destroy();boardRenderer=null;}
 if(state.view==='ground'){updateTelemetry();if($('.gs-definition-list'))$('.gs-definition-list').scrollTop=groundScroll;}
 if(!state.archQuery&&!state.archCategory)[...$('#view').querySelectorAll('details[data-detail-key]')].forEach(d=>{if(detailState.has(d.dataset.detailKey))d.open=detailState.get(d.dataset.detailKey);});
 paintIcons();
 renderSimulationPanel();
 if($('.architecture-scroll'))$('.architecture-scroll').scrollTop=architectureScroll;
 document.querySelectorAll('.architecture-pane-content,.communication-browser>nav,.communication-message').forEach((node,index)=>{if(paneScroll[index]?.className===node.className)node.scrollTop=paneScroll[index].top;});
 layoutArchitecture(state);
}
function updateTelemetry(){
 const parent=$('#ground-live');
 if(!parent||parent.contains(document.activeElement)&&['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return;
 const opened=new Map([...parent.querySelectorAll('details[data-detail-key]')].map(d=>[d.dataset.detailKey,d.open]));
 const scroll=new Map([...parent.querySelectorAll('.gs-journal,.gs-telemetry-list,.gs-detail')].map(node=>[node.className,{top:node.scrollTop,left:node.scrollLeft}]));
 const active=parent.contains(document.activeElement)?document.activeElement:null;
 const focusAttribute=['data-gs-activity','data-gs-packet'].find(key=>active?.hasAttribute(key));
 const focusSelector=focusAttribute?`[${focusAttribute}="${CSS.escape(active.getAttribute(focusAttribute))}"]`:active?.tagName==='SUMMARY'?`[data-detail-key="${CSS.escape(active.parentElement.dataset.detailKey||'')}"] > summary`:null;
 parent.innerHTML=renderTelemetry(state,{esc,hex,icon});
 parent.querySelectorAll('details[data-detail-key]').forEach(d=>{if(opened.has(d.dataset.detailKey))d.open=opened.get(d.dataset.detailKey);});
 if(focusSelector)parent.querySelector(focusSelector)?.focus({preventScroll:true});
 parent.querySelectorAll('.gs-journal,.gs-telemetry-list,.gs-detail').forEach(node=>{const previous=scroll.get(node.className);if(previous){node.scrollTop=previous.top;node.scrollLeft=previous.left;}});
}
function field(name,label,options) {return `<label>${esc(label)}${options?`<select name="${name}" ${['device','model'].includes(name)?'required':''}>${options.length?'':'<option value="">No options available</option>'}${options.map(o=>`<option value="${esc(o.value)}" ${o.disabled?'disabled':''}>${esc(o.label)}</option>`).join('')}</select>`:`<input name="${name}" required autocomplete="off" pattern="[a-z][a-z0-9_]*">`}</label>`;}
function dialog(title,body,submit,submitLabel='Apply') {
 $('#dialog-title').textContent=title;$('#dialog-body').innerHTML=body;$('#dialog-error').textContent='';
 $('#dialog-form button[type=submit]').textContent=submitLabel;$('#dialog-form button[type=submit]').hidden=!submit;$('#cancel-dialog').textContent=submit?'Cancel':'Close';
 $('#dialog-form').onsubmit=async e=>{e.preventDefault();if(!submit)return;const b=$('#dialog-form button[type=submit]');b.disabled=true;try{await submit(Object.fromEntries(new FormData(e.currentTarget)));$('#dialog').close();}catch(error){$('#dialog-error').textContent=error.message;}finally{b.disabled=false;}};
 $('#dialog').showModal();
}
function create(kind,app) {
 const w=state.workspace,m=w.apps.find(a=>a.name===app)?.manifest;
 const labels={app:'app',device:'QEMU device',sensor:'sensor reader',command:'command',telemetry:'telemetry'};
 let body=kind==='device'?field('model','Model',Object.entries(w.catalog.models).map(([id,d])=>({value:id,label:id+(d.cfs_driver?'':' · no cFS driver')+(!d.can_add?' · configuration not validated':''),disabled:!d.can_add})))+field('id','Device ID')+field('bus','Bus',Object.entries(w.catalog.buses).map(([value,bus])=>({value,label:value+' · '+bus.device})))+'<label>I²C address<input name="address" required pattern="(0[xX][0-9a-fA-F]+|[0-9]+)"></label>':kind==='sensor'?'':field('name','Name');
 if(kind==='sensor'){
  const attached=w.project.apps.find(item=>item.name===app)?.sensors||{};
  const devices=w.project.devices.filter(device=>w.catalog.models[device.model]?.cfs_driver&&!Object.values(attached).includes(device.id));
  if(!devices.length){
   dialog('Add sensor to '+app,'<p>Add a device with a flight driver in Hardware to attach another sensor.</p><button type="button" data-view="bench">Open hardware</button>',null);return;
  }
  body=field('device','Hardware sensor',devices.map(d=>({value:d.id,label:d.id+' · '+hex(d.address)})))+field('name','Reader name');
 }
 if(kind==='telemetry') body+=field('sensor','Source',[{value:'',label:'Custom payload'},...(m?.sensors||[]).map(s=>({value:s.name,label:s.name}))]);
 if(kind==='device'&&!Object.values(w.catalog.models).some(entry=>entry.can_add)){
  dialog('Add sensor','<p>All configured I²C addresses are in use. You can define a model at another available address.</p><button type="button" data-design-sensor>Create a new I²C model</button>',null);
  return;
 }
 if(kind==='device')body+='<button type="button" data-design-sensor>Create a new I²C model</button>';
 dialog(kind==='sensor'?'Add sensor to '+app:'Add '+labels[kind],body,async values=>{requireSavedMission();const result=await api('mutate',{action:'add-'+kind,payload:{...values,...(app?{app}:{})}});await reloadMissionFiles(result.changed,result.deleted);feedback('Files created · build to apply');});
 if(kind==='sensor'){
  const select=$('#dialog-body [name=device]'),reader=$('#dialog-body [name=name]');
  const setReaderName=()=>{reader.value=select.value;};
  select.onchange=setReaderName;setReaderName();
 }
 if(kind==='device'){
  const model=$('#dialog-body [name=model]');
  const defaults=()=>{let id=model.value,index=2;while(w.project.devices.some(d=>d.id===id))id=model.value+'_'+index++;$('#dialog-body [name=id]').value=id;$('#dialog-body [name=address]').value=hex(w.catalog.models[model.value].default_address);};
  const bus=$('#dialog-body [name=bus]'),address=$('#dialog-body [name=address]');
  const occupied=value=>w.project.devices.some(device=>device.bus===bus.value && device.address===Number(value));
  const checkAddress=()=>address.setCustomValidity(occupied(address.value)?'This address is in use on the selected bus. Choose the address configured on your sensor.':'');
  const unused=Object.entries(w.catalog.models).find(([,details])=>details.can_add&&!occupied(details.default_address));
  if(unused)model.value=unused[0];
  model.onchange=()=>{defaults();checkAddress();};bus.onchange=address.oninput=checkAddress;
  defaults();checkAddress();
 }
}
function remove(kind,app,name) {
 dialog('Remove '+(name||app),`<p>Remove ${kind==='device'?'the device and its unused generated drivers':'the source files for'} <strong>${esc(name||app)}</strong>? Build and run to apply.</p>`,async()=>{requireSavedMission();const result=await api('mutate',{action:'remove-'+kind,payload:kind==='device'?{id:name}:{app,name}});await reloadMissionFiles(result.changed,result.deleted);feedback('Removed from project');});
}
function connect() {
 const current=state.hardware?.physical?.connection||{};
 dialog('Check board connection',`<p>Power on the board, enable SSH and connect it to this network.</p><p><a href="/infrastructure?target=physical">Configure SSH host and key ↗</a></p>${current.host?`<p>${esc(current.user||'SSH')} @ ${esc(current.host)}</p>`:''}`,current.host?()=>startJob('probe'):null);

}
async function startJob(action, extra={}) {
 if(action==='setup'&&state.target==='qemu'){location.href='/infrastructure?target=qemu';return;}
 if(launchPending)throw Error('Wait for the current operation to start.');
 if(['build','run'].includes(action)&&state.missionDraft)throw Error('Save or cancel the architecture draft before building.');
 const options={target:action==='stop'?state.hardware?.execution?.target||state.target:state.target,...(['boot','build','run'].includes(action)&&state.target!=='native'?{board:state.board,os:state.os}:{}),...(action==='boot'&&state.target==='qemu'&&state.hardware?.qemu?.can_retry_boot?{retry:true}:{}),...(state.target==='physical'&&['build','run'].includes(action)?{sensorless:state.sensorless}:{}),...extra};
 launchPending={action,target:options.target,retry:!!options.retry,started:Date.now()/1000};renderToolbar();
 try{
  if(['build','run'].includes(action))await saveAll();
  const result=await api('job',{action,options});if(action!=='boot'){terminal.open(result.id);if(!['simulate','simulate-preview'].includes(action))terminal.show();}feedback('Operation started');await pollJobs();
 }finally{launchPending=null;renderToolbar();}
}
let jobsPolling=false;
async function openLiveLogs(kind='flight'){
 state.terminalStream=kind;
 state.selectedJob=state.jobs.filter(j=>j.target===state.target&&['logs','boot','run'].includes(j.action)&&j.kind===kind).at(-1)?.id||null;
 terminal.show();
 if(state.target==='physical'&&!state.hardware?.physical?.connection){connect();return;}
 if(state.target==='qemu'&&state.hardware?.qemu?.running===false)return;
 await startJob('logs',{kind});
}
function selectTargetTerminal(){terminal.selectTarget();}
async function pollJobs() {
 if(jobsPolling)return;jobsPolling=true;
 try{
  const before=state.jobs.filter(j=>j.status==='running'&&['simulate','simulate-preview'].includes(j.action)).map(j=>j.id).join();
  state.jobs=await api('jobs');
  if(!state.terminalStream&&(!state.selectedJob||!state.jobs.some(j=>j.id===state.selectedJob)))selectTargetTerminal();
  for(const job of state.jobs){
   const phase=job.operation_complete&&job.status!=='failed'?'ready':job.status,key=job.id+':'+phase;
   if(phase!=='running'&&!state.history.has(key)){
    state.history.set(key,true);
    if(!['logs','shell'].includes(job.action)){
     if(job.action==='shutdown'&&job.target==='qemu'&&job.status==='succeeded'&&job.result?.stopped&&state.hardware){
      Object.assign(state.hardware.qemu,{running:false,flight_running:false,service:'inactive'});
      if(isWorkbench())renderView();
     }
     hardwareRefresh(true).catch(e=>feedback(e.message,true));refresh(true).catch(e=>feedback(e.message,true));
     if(job.status==='failed')feedback(job.error||'Operation failed. Check the terminal.',true);
     else if(job.target===state.target)feedback(job.result?.shutdown_requested?'Board accepted the shutdown request':job.operation_complete?(job.action==='boot'?(job.target==='qemu'?'Emulator ready':'Board connected'):'cFS running'):job.action==='connect'?'Board connected':actionLabel(job.action,job.target)+' completed');
    }
   }
  }
  const after=state.jobs.filter(j=>j.status==='running'&&['simulate','simulate-preview'].includes(j.action)).map(j=>j.id).join();
  if(before!==after&&isWorkbench())renderView();
  if(before!==after&&state.view==='simulation')renderSimulationPanel(true);
  if(state.view==='simulation')updateSignalValues(state);
  terminal.render();renderToolbar();
 }finally{jobsPolling=false;}
}
let hardwareRequest=null,hardwareVersion=0;
function hardwareRefresh(fresh=false){
 // A status request started before an operation ended must not restore stale state.
 if(fresh&&hardwareRequest){hardwareVersion++;return hardwareRequest.then(()=>hardwareRefresh());}
 if(!hardwareRequest){
  const version=hardwareVersion;
  hardwareRequest=api('hardware').then(h=>{if(version!==hardwareVersion)return;state.hardware=h;renderToolbar();if(isWorkbench())renderView();}).finally(()=>{hardwareRequest=null;});
 }
 return hardwareRequest;
}
function updateGround(snapshot){
 const previous=state.ground;
 state.ground=snapshot;
 if(snapshot.connected&&snapshot.target===state.target)state.groundError='';
 if(communicationVisible()){if(!previous||JSON.stringify(previous.communication)!==JSON.stringify(snapshot.communication)||previous.connected!==snapshot.connected||previous.receiving!==snapshot.receiving||previous.error!==snapshot.error)renderView();return;}
 if(state.view!=='ground')return;
 if(!previous||['connected','target','error'].some(key=>previous[key]!==snapshot[key])||JSON.stringify(previous.subscription_errors)!==JSON.stringify(snapshot.subscription_errors))renderView();else updateTelemetry();
}
async function groundRefresh(){
 if(state.catalogLoading)return;
 const target=state.target;
 state.catalogLoading=true;state.groundError='';if(state.view==='ground')renderView();
 try{
  const [catalog,ground]=await Promise.all([api('ground/catalog?target='+target),api('ground')]);
  if(target!==state.target)return;
  state.catalog=catalog;state.catalogTarget=target;state.ground=ground;
  const apps=new Set([...(catalog.apps||[]).map(app=>app.name),...[...catalog.commands,...catalog.packets].map(item=>item.app)]);
  if(state.groundApp&&!apps.has(state.groundApp))state.groundApp='';
 }catch(error){state.groundError=error.message;throw error;}
 finally{
  state.catalogLoading=false;
  if(state.view==='ground'||communicationVisible()){renderView();if(target!==state.target)groundRefresh().catch(e=>feedback(e.message,true));}
 }
}
async function groundConnection(connect){
 if(state.groundBusy)throw Error('Wait for the connection to complete.');
 state.groundBusy=true;state.groundError='';renderView();
 try{
  const snapshot=await api(connect?'ground/start':'ground/stop',connect?{target:state.target}:{});
  updateGround(connect?snapshot:{...snapshot,target:state.ground?.target});
  feedback(connect?'Ground Station connected':'Ground Station disconnected');
 }catch(error){state.groundError=error.message;throw error;}
 finally{state.groundBusy=false;if(state.view==='ground'||communicationVisible())renderView();}
}
let groundPolling=false;
async function pollGround(){
 if(groundPolling)return;groundPolling=true;
 try{updateGround(await api('ground'));}finally{groundPolling=false;}
}
async function sendGroundCommand(id,values){
 if(state.groundSending)return;
 if(state.catalogTarget!==state.target)await groundRefresh();
 const cmd=state.catalog.commands.find(command=>command.id===id),target=state.target;
 if(!cmd)throw Error('Command not found in this target build. Refresh the catalog.');
 const fields=(cmd.fields||[]).filter(f=>!/^(padding|reserved|spare)/i.test(f.name.split('.').at(-1)));
 for(const field of fields){
  if(field.format==='s'||field.format==='raw'||(['Q','q'].includes(field.format)&&field.count===1))continue;
  if(field.count>1){
   values[field.name]=JSON.parse(values[field.name]);
   if(!Array.isArray(values[field.name])||values[field.name].length!==field.count)throw Error(field.name+': enter '+field.count+' elements.');
   if(['Q','q'].includes(field.format)&&values[field.name].some(v=>typeof v==='number'&&!Number.isSafeInteger(v)))throw Error(field.name+': quote 64-bit integers to preserve precision.');
  }else if(field.format==='?')values[field.name]=JSON.parse(values[field.name]);
  else{const value=Number(values[field.name]);if(!Number.isFinite(value))throw Error(field.name+': invalid number');values[field.name]=value;}
 }
 state.groundSending=true;state.groundError='';renderView();
 try{
  if(!state.ground?.connected||state.ground.target!==target)await groundConnection(true);
  if(target!==state.target)throw Error('Target changed before sending. Select the command again.');
  await api('ground/send',{command_id:cmd.id,values,target});
  await pollGround();feedback('Command sent · check telemetry for the response');
 }finally{state.groundSending=false;renderView();}
}
document.addEventListener('input',event=>{
 const form=event.target.closest('#gs-command-form');if(!form)return;
 state.groundDrafts??={};state.groundDrafts[form.dataset.commandId]=Object.fromEntries(new FormData(form));
});
document.addEventListener('submit',async event=>{
 if(event.target.id!=='gs-command-form')return;event.preventDefault();
 try{await sendGroundCommand(event.target.dataset.commandId,Object.fromEntries(new FormData(event.target)));}
 catch(error){state.groundError=error.message;renderView();}
});

async function selectView(view){
 const codeOnly=view==='code',next=codeOnly?'architecture':view,previous=state.view;
 const changedRoot=(previous==='simulation')!==(next==='simulation');
 document.body.classList.toggle('code-only',codeOnly);state.view=next;state.inspected=null;
 state.archFollowSource=false;
 document.body.classList.toggle('no-editor',!codeOnly);
 document.body.classList.toggle('no-tree',!codeOnly);
 if(next==='simulation'){
  state.selectedDevice=null;
  if(!state.simulation||!state.simulationDirty)await refreshSimulation();
 }else if(codeOnly){
  await renderTree();
  await openFile(lastFiles.get('flight')||state.workspace.mission.source.path,undefined,false);
 }
 if(next==='simulation'){
  terminal.selectContext('simulation',{reveal:false});
  if(previous!==next)terminal.show(false);
 }else terminal.selectContext('flight',{reveal:previous==='simulation'});
 renderView();renderToolbar();
 if(isWorkbench())await hardwareRefresh();if(next==='ground'||communicationVisible())await groundRefresh();if(communicationVisible())await pollGround();
}
$('#code').addEventListener('input',()=>{if(state.path){state.files.get(state.path).content=$('#code').value;lineNumbers();renderTabs();}});
$('#code').addEventListener('scroll',syncScroll);
$('#code').addEventListener('keydown',e=>{if(e.key==='Tab'&&!e.target.readOnly){e.preventDefault();const t=e.target,s=t.selectionStart;t.setRangeText('    ',s,t.selectionEnd,'end');t.dispatchEvent(new Event('input'));}});
document.addEventListener('input',e=>{if(e.target.id==='architecture-search'){state.archQuery=e.target.value;const caret=e.target.selectionStart;renderView();$('#architecture-search')?.focus();try{$('#architecture-search')?.setSelectionRange(caret,caret);}catch{}}if(e.target.id==='gs-search'){state.groundQuery=e.target.value;renderView();$('#gs-search')?.focus();}});
document.addEventListener('toggle',e=>{if(e.target.matches('details[data-detail-key]')&&e.target.closest('.architecture-surface')){state.archDetails||={};state.archDetails[e.target.dataset.detailKey]=e.target.open;}},true);
document.addEventListener('change',e=>{
 if(e.target.id==='ground-app'){state.groundApp=e.target.value;state.groundSelection=null;state.groundPacket=null;state.groundQuery='';renderView();}
 });
document.addEventListener('submit',event=>{
 if(event.target.id==='mission-draft-form'){event.preventDefault();saveMissionDraft();}
});
document.addEventListener('input',event=>{if(event.target.closest('#mission-draft-form')&&event.target.name&&state.missionDraft)state.missionDraft.draft.settings[event.target.name]=Number(event.target.value);});
function requireSavedMission(){
 const dirty=[...state.files.values()].find(file=>file.content!==file.saved&&(file.path.startsWith('mission/')||file.path.startsWith('project/')));
 if(dirty)throw Error('Save '+dirty.path.split('/').at(-1)+' before changing the mission.');
}
async function prepareMissionDraft(kind,name,mode='create',revision=state.workspace.mission.source.hash){
 if(state.missionBusy)return;
 state.missionBusy=name;state.missionError='';renderView();
 try{
  requireSavedMission();
  state.missionDraft=await api('mission/draft',{kind,name,mode,expected_hash:revision});state.archOverview=false;
  state.archLibrary='';state.archApp='';
  document.body.classList.add('no-editor');state.archFollowSource=false;
 }catch(error){if(!$('#dialog').open)state.missionError=error.message;throw error;}
 finally{state.missionBusy=null;renderView();$('.architecture-scroll')?.scrollTo(0,0);}
}
async function reloadMissionFiles(changed=[],deleted=[],moved={}){
 workspaceRequest++;
 for(const [oldPath,newPath] of Object.entries(moved)){
  if(!state.files.has(oldPath))continue;
  const file=state.files.get(oldPath);
  state.files.delete(oldPath);state.files.set(newPath,{...file,path:newPath});
  if(state.path===oldPath){state.path=newPath;state.sourcePreview=null;}
  if(lastFiles.get('flight')===oldPath)lastFiles.set('flight',newPath);
 }
 for(const path of deleted)state.files.delete(path);
 if(deleted.includes(state.path)){state.path=null;state.sourcePreview=null;await openFile(state.workspace.mission.source.path,undefined,false);}
 for(const path of changed){
  if(deleted.includes(path))continue;
  const cached=state.files.get(path);if(!cached||cached.content!==cached.saved)continue;
  const latest=await api('file?path='+encodeURIComponent(path));
  if(cached.content===cached.saved){state.files.set(path,{...latest,saved:latest.content});if(state.path===path)await openFile(path,state.activeLine,false,state.sourcePreview);}
 }
 await refresh(true);
}
async function saveMissionDraft(){
 if(state.missionBusy||!state.missionDraft)return;
 const draft=state.missionDraft,payload={...draft.draft,expected_hash:draft.expected_hash};
 state.missionBusy=draft.draft.name;state.missionError='';workspaceRequest++;renderView();
 try{
  requireSavedMission();
  const preview=await api('mission/draft',payload);
  const result=await api('mission/save',{...preview.draft,expected_hash:preview.expected_hash,plan_hash:preview.plan_hash});
  workspaceRequest++;state.workspace.mission=result.mission;
  state.missionDraft=null;
  await reloadMissionFiles(result.changed,result.deleted);
  if(result.app)state.archApp=result.app.name;
  if(result.library)state.archLibrary=result.library.name;
  document.body.classList.add('no-editor');state.archFollowSource=false;
  feedback(payload.name+' saved · build to apply');
 }catch(error){state.missionError=error.message;feedback(error.message,true);}
 finally{state.missionBusy=null;renderTabs();renderView();}
}

async function missionAction(action,name,kind='app',revision=state.workspace.mission.source.hash){
 if(state.missionBusy||state.missionDraft)return;
 workspaceRequest++;
 state.missionBusy=name||'new';state.missionError='';renderView();
 const source=state.workspace.mission.source.path;
 let result;
 try{
  requireSavedMission();
  result=await api('mission/'+kind,{action,name,expected_hash:revision});
 }catch(error){state.missionError=error.message;state.missionBusy=null;renderView();throw error;}
 if(result){
  workspaceRequest++;
  const saved=result.mission||result;
  state.workspace.mission=saved;
  for(const app of state.workspace.apps)app.enabled=saved.enabled.includes(app.name);
  if(kind==='library'&&['remove','delete'].includes(action)){if(state.archLibrary===name)state.archLibrary='';}
  if(!(saved.included||saved.enabled).includes(state.archApp))state.archApp='';
  try{
   await reloadMissionFiles(result.changed||[source],result.deleted);
   feedback(name+' '+({add:'added',enable:'enabled',disable:'disabled',remove:'removed from mission',delete:'deleted'}[action])+' · build to apply');
  }catch(error){state.missionError='Mission updated; could not refresh: '+error.message;feedback(state.missionError,true);}
 }
 state.missionBusy=null;renderTabs();renderView();
 if(state.missionError&&/changed|Reload/i.test(state.missionError)){try{await refresh();}catch{}}
}

async function renameModule(kind,name,newName,revision){
 if(state.missionBusy)return;
 requireSavedMission();
 state.missionBusy=name;state.missionError='';workspaceRequest++;renderView();
 try{
  const result=await api('mission/rename',{kind,name,new_name:newName,expected_hash:revision});
  workspaceRequest++;
  state.workspace.mission=result.mission;
  for(const key of ['archApp','archLibrary','groundApp','commApp'])if(state[key]===name)state[key]=newName;
  try{
   await reloadMissionFiles(result.changed,result.deleted,result.moved);
   feedback(name+' renamed to '+newName+' · build to apply');
  }catch(error){state.missionError='Renamed to '+newName+'. Workspace refresh failed: '+error.message;feedback(state.missionError,true);}
 }finally{state.missionBusy=null;renderTabs();renderView();}
}

async function configureProfile(){
 if(!state.workspace||state.profileBusy)return;
 state.profileBusy=true;workspaceRequest++;renderToolbar();feedback('Configuring execution target…');
 try{
  requireSavedMission();
  const result=await api('mission/profile',{board:state.board,os:state.os,expected_hash:state.workspace.mission.source.hash});
  workspaceRequest++;state.workspace.mission=result.mission;await reloadMissionFiles(result.changed,result.deleted);
  await api('hardware/target',{target:state.target});await hardwareRefresh(true);renderView();feedback(state.board?'Board and toolchain configured':'Native execution selected');
 }catch(error){state.board=state.workspace.project.board;state.os=state.workspace.project.os;throw error;}
 finally{state.profileBusy=false;renderToolbar();}
}
async function selectTarget(target){
 await api('hardware/target',{target});
 state.target=target;state.catalog=null;state.catalogTarget=null;state.groundError='';state.groundSelection=null;state.groundPacket=null;
 renderToolbar();selectTargetTerminal();await hardwareRefresh();renderView();if(state.view==='ground'||communicationVisible())await groundRefresh();
}
$('#toggle-editor').onclick=()=>{document.body.classList.toggle('no-editor');renderView();};
$('#close-dialog').onclick=$('#cancel-dialog').onclick=()=>$('#dialog').close();
window.addEventListener('beforeunload',e=>{if([...state.files.values()].some(f=>f.content!==f.saved)){e.preventDefault();e.returnValue='';}});
document.addEventListener('keydown',e=>{if(e.ctrlKey||e.metaKey){if(e.key==='s'){e.preventDefault();guarded(save)();}if(e.key==='f'&&document.activeElement===$('#code')){e.preventDefault();openFind();}}});
function openFind(){$('#find-bar').classList.remove('hidden');$('#find-query').focus();}
function findNext(){const query=$('#find-query').value;if(!query)return;const editor=$('#code');let at=editor.value.indexOf(query,editor.selectionEnd);if(at<0)at=editor.value.indexOf(query);if(at>=0){editor.focus();editor.setSelectionRange(at,at+query.length);editor.scrollTop=Math.max(0,(editor.value.slice(0,at).split('\n').length-4)*24);syncScroll();}}
$('#find-toggle').onclick=openFind;$('#find-close').onclick=()=>$('#find-bar').classList.add('hidden');$('#find-next').onclick=findNext;$('#find-query').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();findNext();}if(e.key==='Escape')$('#find-bar').classList.add('hidden');};
$('#editor-expand').onclick=()=>{document.body.classList.toggle('code-only');document.body.classList.remove('no-editor');renderView();};
paintIcons();
const layout=mountLayout();
mountSidebar();
const terminal=mountTerminal({state,esc,layout,api,onStream:openLiveLogs,onCloseJob:job=>api('job/cancel',{id:job.id}),onError:e=>feedback(e.message,true)});
$('#operation-output').onclick=()=>{const job=operation();if(job?.id)terminal.open(job.id);terminal.show();};
setInterval(renderProgress,1000);
document.addEventListener('click',guarded(async e=>{
 const b=e.target.closest('button');if(!b||b.disabled)return;
 const d=b.dataset;
 if('archFollow' in d){
  state.archFollowSource=!state.archFollowSource;
  document.body.classList.toggle('no-editor',!state.archFollowSource);
  document.body.classList.toggle('no-tree',!state.archFollowSource);
  if(state.archFollowSource){
   const app=state.workspace.apps.find(item=>item.name===state.archApp);
   const lib=state.workspace.libraries.find(item=>item.name===state.archLibrary);
   await openFile(app?.entry||lib?.exports?.[0]?.path||state.workspace.mission.source.path,lib?.exports?.[0]?.line||1,true);
  }
  renderView();
 }
 else if(d.archSource){
  document.body.classList.remove('no-tree','code-only');
  state.archFollowSource=true;
  e.preventDefault();
  const details=b.closest('details');if(details)details.open=true;
  const source={path:d.archSource,line:Number(d.line)||1,end_line:Number(d.endLine)||Number(d.line)||1,symbol:d.symbol||'Source'};
  state.archSource=source.path+':'+source.line;
  await openFile(source.path,source.line,true,source);
 }
 else if('chooseBoard' in d){$('#board-select').click();}
 else if(d.file){state.inspected=null;$('#dialog').close();await openFile(d.file,Number(d.line)||undefined);}
 else if(d.view){if($('#dialog').open)$('#dialog').close();await selectView(d.view);if(d.device)state.selectedDevice=d.device;if(d.inspect){state.inspected=d.inspect;renderView();}}
 else if(d.closeFile){await saveFile(d.closeFile);state.files.delete(d.closeFile);if(state.path===d.closeFile){const next=[...state.files.keys()].at(-1);state.path=null;if(next)await openFile(next);else{$('#code').value='';$('#code').disabled=true;lineNumbers();}}renderTabs();}
 else if(d.archApp||d.archLibrary||d.archTab){
  if(d.archApp||d.archLibrary){
   state.archApp=d.archApp||'';state.archLibrary=d.archLibrary||'';
  }
  state.archOverview=d.archTab==='overview';
  state.archFollowSource=false;state.archSource='';
  document.body.classList.remove('code-only','mobile-tree');
  document.body.classList.add('no-editor','no-tree');renderView();
  $('.architecture-scroll')?.scrollTo(0,0);
 }
 else if('archClear' in d){state.archApp='';state.archLibrary='';state.archFollowSource=false;document.body.classList.add('no-editor','no-tree');renderView();}
 else if(d.signalTab){state.signalOutput=d.signalTab;renderSimulationPanel(true);updateSignalValues(state);}
 else if('signalSidebar' in d){state.signalSidebar=state.signalSidebar===false;renderView();}
 else if(d.signalDevice){await selectSimulationDevice(d.signalDevice);}
 else if('signalHardware' in d){
  await selectView('bench');
  if(state.workspace.project.board)create('device');
  else location.href='/infrastructure?target=qemu';
 }
 else if('backSensors' in d){state.selectedDevice=null;renderView();}
 else if('simulationSave' in d)await saveSimulation();
 else if('simulationStart' in d)await startSimulation();
 else if('simulationTest' in d)await testSimulation();
 else if('simulationStop' in d)await stopSimulation();
 else if(d.boardStop)await stopSimulation(d.boardStop);
 else if(d.simulationDevice)await selectSimulationDevice(d.simulationDevice);
 else if(d.simulationAdd)addSimulationSensor(d.simulationAdd);
 else if(d.simulationRemove){if(!simulationJob()){state.simulation.settings.sensors=state.simulation.settings.sensors.filter(sensor=>sensor.device!==d.simulationRemove);state.simulationDirty=true;renderView();}}
 else if('toggleLibraries' in d){
  state.showLibraries=!state.showLibraries;
  localStorage.setItem('mission.showLibraries',String(state.showLibraries));
  renderView();
  document.querySelector('[data-toggle-libraries]')?.focus({preventScroll:true});
 }
 else if(d.moduleGroup && d.moduleAction){
  openModuleAction(d.moduleGroup,d.moduleAction,state.workspace,{dialog,esc,prepare:prepareMissionDraft,change:missionAction,rename:renameModule});
 }
 else if(d.missionConfigure){await prepareMissionDraft('app',d.missionConfigure,'edit');}
 else if('missionDraftCancel' in d){state.missionDraft=null;state.missionError='';renderView();}
 else if('missionErrorClose' in d){state.missionError='';renderView();}
 else if('expandPanel' in d){document.body.classList.toggle('no-editor');renderView();}
 else if(d.commApp){
  state.commApp=state.commApp===d.commApp?null:d.commApp;
  renderView();
  document.querySelector('[data-comm-app="'+CSS.escape(d.commApp)+'"]')?.focus({preventScroll:true});
 }
 else if(d.gsSource){await inspectGroundSource(d.sourceKind,d.gsSource,d.sourceSection);}
 else if(d.gsTab){state.groundTab=d.gsTab;state.groundQuery='';renderView();}
 else if(d.gsActivity){state.groundActivity=d.gsActivity;renderView();}
 else if(d.gsSelect){state.groundSelection=d.gsSelect;renderView();}
 else if(d.gsPacket){state.groundPacket=Number(d.gsPacket);updateTelemetry();}
 else if(d.device){state.selectedDevice=d.device;renderView();}
 else if(d.simulationFile){await selectView('simulation');await openFile(d.simulationFile);}
 else if('sensorMenu' in d)sensorMenu();
 else if(d.hardwareSettings)await hardwareSettings(d.hardwareSettings);
 else if(d.inspect){state.inspected=d.inspect;renderView();}
 else if('closeInspection' in d){state.inspected=null;renderView();}
 else if(d.target)await selectTarget(d.target);
 else if(d.job){if(d.job==='connect')connect();else{$('#dialog').close();await startJob(d.job,d.kind?{kind:d.kind}:{});}}
 else if('designSensor' in d){$('#dialog').close();designSensor({dialog,api,refresh,feedback});}
 else if(d.testModel)await startJob('model-test',{device:d.testModel});
 else if(d.testDevice)await startJob('sensor-test',{device:d.testDevice});
 else if(d.create)create(d.create,d.app);
 else if(d.remove)remove(d.remove,d.app,d.name);
 else if('connect' in d)connect();
 else if('copySetup' in d){await navigator.clipboard.writeText(state.hardware.physical.last_probe.admin_setup_command);feedback('Command copied');}
 else if('hardwareRefresh' in d){$('#dialog').close();if(state.target==='physical'&&state.hardware?.physical?.connection)await startJob('probe');else await hardwareRefresh();}
 else if(d.ground){if(d.ground==='catalog')await groundRefresh();else await groundConnection(d.ground==='start');}

}));
(async()=>{try{
 state.token=(await api('session')).token;
 // A job that finishes meanwhile replaces this request; wait for the newer state.
 while(!state.hardware)await hardwareRefresh();
 if(state.hardware.execution?.preferred_target){
  state.target=state.hardware.execution.preferred_target;
 }
 await refresh(true);
 selectTargetTerminal();
}catch(e){feedback(e.message,true);}})();
setInterval(()=>{if(document.hidden||!state.workspace)return;pollJobs().catch(e=>feedback(e.message,true));if(state.view==='ground'||communicationVisible())pollGround().catch(e=>feedback(e.message,true));},1500);
setInterval(()=>{if(!document.hidden){if(state.workspace&&!state.missionBusy&&!state.profileBusy)refresh().catch(e=>feedback(e.message,true));if(isWorkbench())hardwareRefresh().catch(e=>feedback(e.message,true));}},15000);

function syncNavigation(){
 const onlyCode=document.body.classList.contains('code-only');
 const active={communication:!onlyCode&&communicationVisible(),code:onlyCode,bench:!onlyCode&&state.view==='bench',simulation:!onlyCode&&state.view==='simulation',architecture:!onlyCode&&state.view==='architecture',ground:!onlyCode&&state.view==='ground'};
 document.querySelectorAll('.rail-button[data-view]').forEach(button=>{const visible=!!active[button.dataset.view];button.classList.toggle('active',visible);button.setAttribute('aria-pressed',String(visible));});
}
new MutationObserver(syncNavigation).observe(document.body,{attributes:true,attributeFilter:['class']});
function mountSidebar(){
 const setVisible=visible=>{document.body.classList.toggle('no-tree',!visible);document.body.classList.toggle('mobile-tree',visible&&window.innerWidth<=760);layout.apply();};
 $('#hide-explorer').onclick=()=>setVisible(false);$('#show-explorer').onclick=()=>setVisible(true);
 let request=0,timer;
 const search=async()=>{
  const id=++request,q=$('#file-query').value.trim(),root=fileRoot();
  $('#file-results').textContent=q?'Searching…':'Type a file name';
  if(!q)return;
  try{
   const result=await api('files/search?root='+encodeURIComponent(root)+'&q='+encodeURIComponent(q));
   if(id!==request||root!==fileRoot())return;
   $('#file-results').innerHTML=result.files.map(path=>`<button class="file-result" data-file="${esc(path)}"><span>${esc(path.split('/').at(-1))}</span><small>${esc(path.slice(0,path.lastIndexOf('/')))}</small></button>`).join('')||'No matching files';
   if(result.limited)$('#file-results').insertAdjacentHTML('beforeend','<small>First 100 matches. Refine your search.</small>');
  }catch(error){if(id===request)$('#file-results').textContent=error.message;}
 };
 const openSearch=()=>{setVisible(true);$('#file-search').hidden=false;$('#tree').hidden=true;$('#search-files').setAttribute('aria-expanded','true');$('#file-query').focus();search();};
 $('#search-files').onclick=()=>{if($('#file-search').hidden)openSearch();else{$('#file-search').hidden=true;$('#tree').hidden=false;$('#search-files').setAttribute('aria-expanded','false');request++;}};
 $('#file-query').oninput=()=>{request++;clearTimeout(timer);timer=setTimeout(search,160);};
 $('#file-query').onkeydown=e=>{if(e.key==='Escape')$('#search-files').click();if(e.key==='Enter')$('#file-results button')?.click();};
 document.addEventListener('keydown',e=>{if(!(e.ctrlKey||e.metaKey)||e.target.closest('#shell-terminal')||isWorkbench())return;if(e.key==='p'){e.preventDefault();openSearch();}if(e.key==='b'){e.preventDefault();setVisible(window.innerWidth<=760?!document.body.classList.contains('mobile-tree'):document.body.classList.contains('no-tree'));}});
}

let sourceRequest=0;
async function inspectGroundSource(kind,id,section=''){
 const request=++sourceRequest,target=state.target;
 const source=await api('ground/source?'+new URLSearchParams({kind,id,section,target}));
 if(request!==sourceRequest||target!==state.target||state.view!=='ground'&&!communicationVisible())return;
 if(state.view==='ground')await selectView('code');
 await openFile(source.path,source.line,true,{...source,definitionId:id,definitionKind:kind});
}

setInterval(()=>{if(!document.hidden && state.view==='simulation')updateSignalValues(state);},180);
