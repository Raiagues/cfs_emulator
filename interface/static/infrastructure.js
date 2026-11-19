import {icon} from './ui.js';
import {mountShells} from './shell.js';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modes = {native:['monitor','Native','This computer'],qemu:['cube','Emulator','QEMU'],physical:['circuit','Physical board','Connect over SSH']};
let token='', settings=null, target='native', busy=false, dirty=false, checks=null, job=null, shell=null;
const commands = new Map();

function feedback(message='', error=false){$('#feedback').textContent=message;$('#feedback').classList.toggle('error',error);}
async function api(path, body){
 const response=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':token},body:JSON.stringify(body)});
 if(response.status===403&&path!=='session'){token=(await api('session')).token;return api(path,body);}
 const data=await response.json();if(!response.ok)throw Error(data.error||response.statusText);return data;
}
function controls(){
 for(const element of document.querySelectorAll('#infrastructure-form button,#infrastructure-form input,#infrastructure-form select'))element.disabled=busy||!settings;
 $('#enter').disabled=busy||!settings?.sources_ready;
 $('#save-state').textContent=busy?'Working…':dirty?'Unsaved configuration':'';
}
async function perform(action){
 if(busy)return;busy=true;controls();feedback();
 try{await action();}catch(error){feedback(error.message,true);}
 finally{busy=false;controls();}
}
const shells=mountShells({api,onError:error=>feedback(error.message,true)});
async function terminal(command){
 if(!shell)shell=await api('terminal/create',{});
 $('#setup-terminal').hidden=false;
 shells.select(shell);shells.focus();
 if(command)await api('terminal/input',{id:shell.id,data:command+'\r'});
}
function readForm(){
 if(!settings)return;
 const field=name=>$('#configuration [name="'+name+'"]');
 if(target==='native')settings.build_jobs=Number(field('build_jobs').value);
 if(target!=='native'){
  settings.board=field('board').value;settings.os=field('os').value;
 }
 if(target==='qemu')settings.emulator={ssh_port:Number(field('ssh_port').value),image:field('image').value.trim()};
 if(target==='physical')settings.connection={host:field('host').value.trim(),user:field('user').value.trim(),port:Number(field('port').value),identity_file:field('identity_file').value.trim(),directory:settings.connection?.directory||'cfs-arm64'};
}
function options(items, selected){return items.map(([value,label])=>`<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`).join('');}
function profileFields(){
 const profiles=settings.profiles.filter(p=>p.targets.includes(target));
 if(!profiles.some(p=>p.board===settings.board))settings.board=profiles[0]?.board||'';
 const systems=profiles.filter(p=>p.board===settings.board);
 if(!systems.some(p=>p.os===settings.os))settings.os=systems[0]?.os||'';
 const boards=[...new Map(profiles.map(p=>[p.board,p.board_label])).entries()];
 return `<label>Board<select name="board" required>${options(boards,settings.board)}</select></label><label>Operating system<select name="os" required>${options(systems.map(p=>[p.os,p.os_label]),settings.os)}</select></label>`;
}
function render(){
 if(!settings)return;
 $('#targets').innerHTML=Object.entries(modes).map(([key,[glyph,name,description]])=>`<button type="button" class="target-option" data-target="${key}" aria-pressed="${key===target}">${icon(glyph)}<span><strong>${name}</strong><small>${description}</small></span></button>`).join('');
 let fields='';
 if(target==='native'){
  fields=`<div class="host-preview">${icon('monitor')}<div><strong>This computer</strong><span>${esc(settings.host.os)} · ${esc(settings.host.architecture)}</span></div></div><label>Parallel build jobs<input type="number" name="build_jobs" value="${settings.build_jobs||4}" min="1" max="64" required></label>`;
 }else{
  fields=profileFields();
  if(target==='qemu'){
   fields+=`<label>Local SSH port<input name="ssh_port" type="number" required min="1024" max="65535" value="${settings.emulator.ssh_port}"></label><label>SSH address<input value="127.0.0.1" readonly aria-label="Emulator SSH address"></label><label class="full">Emulator image<input name="image" required value="${esc(settings.emulator.image)}" spellcheck="false"></label>`;
  }else{
   const c=settings.connection||{};
   fields+=`<label class="full">SSH host or alias<input name="host" placeholder="hostname or IP address" value="${esc(c.host)}" list="ssh-hosts" autocomplete="off"></label><datalist id="ssh-hosts">${settings.ssh_hosts.map(h=>`<option value="${esc(h.host)}">`).join('')}</datalist><label>SSH user<input name="user" placeholder="From SSH config" value="${esc(c.user)}" autocomplete="off"></label><label>SSH port<input name="port" type="number" required min="1" max="65535" value="${c.port||22}"></label><label class="full">SSH private key path <span class="optional">Optional · uses SSH config / agent when empty</span><input name="identity_file" value="${esc(c.identity_file)}" placeholder="~/.ssh/id_ed25519" list="ssh-keys" spellcheck="false"></label><datalist id="ssh-keys">${settings.ssh_keys.map(k=>`<option value="${esc(k)}">`).join('')}</datalist>`;
  }
  fields=`<div class="fields">${fields}</div>`;
  if(target==='qemu'||target==='physical')fields+='<div id="field-commands" class="field-actions"></div>';
  if(target==='physical')fields+=`<div class="field-actions"><button type="button" data-job="probe">Test SSH</button><button type="button" data-job="connect">Prepare cFS service</button></div>`;
 }
 $('#configuration').innerHTML=fields;
 renderChecks();renderCommands();controls();
}
function renderChecks(){
 const panel=$('#verification');
 panel.hidden=!checks;
 if(!checks){panel.open=false;return;}
 const passed=checks.checks.filter(check=>check.ready).length;
 panel.dataset.ready=String(checks.ready);
 panel.open=!checks.ready;
 $('#check-status').textContent=checks.ready?'All checks passed':'Setup needs attention';
 $('#check-count').textContent=passed+' / '+checks.checks.length+' passed';
 $('#checks').innerHTML=checks.checks.map(c=>`<div class="check-row" data-ready="${!!c.ready}"><span class="check-mark" aria-label="${c.ready?'Passed':'Needs setup'}">${c.ready?'✓':'!'}</span><div><strong>${esc(c.label)}</strong><small>${esc(c.detail)}</small></div></div>`).join('');
}
function commandRow(label, command){
 commands.set(label,command);
 return `<button type="button" data-command="${esc(label)}">${esc(label)}</button>`;
}
function renderCommands(){
 commands.clear();
 const rows=[], inline=[];
 const source=settings.source;
 $('#source-icon').innerHTML=icon('cube');
 const sourceLabel=$('#source-state'), clone=$('#clone-source');
 sourceLabel.dataset.state=source.state;
 sourceLabel.textContent=({ready:'Installed · '+source.revision,missing:'Not installed',incomplete:'Submodules missing',occupied:'Move the existing cFS directory to install the official source.'})[source.state];
 clone.hidden=!['missing','incomplete'].includes(source.state);
 clone.textContent=source.state==='incomplete'?'Complete download':'Clone NASA cFS';
 if(target==='native' && settings.host.package_manager==='apt')
  rows.push(commandRow('Install native tools','sudo apt-get update && sudo apt-get install -y build-essential cmake git python3 python3-pyqt5 python3-zmq'));
 if(target!=='native')rows.push(commandRow('Install dependencies','./scripts/setup.sh --build-only'));
 if(target==='qemu'){
  inline.push(commandRow('Install emulator image','./scripts/setup.sh'));
  inline.push('<a href="/emulator-guide.html" target="_blank" rel="noopener">Local image instructions ↗</a>');
 }
 if(target==='physical'){
  rows.push('<a href="https://www.raspberrypi.com/documentation/computers/getting-started.html#install-an-operating-system" target="_blank" rel="noopener">Install Raspberry Pi OS ↗</a>');
  rows.push('<a href="https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh" target="_blank" rel="noopener">Enable SSH ↗</a>');
  for(const [key,label] of [['create_key','Create SSH key'],['authorize_key','Authorize SSH key'],['ssh','SSH terminal'],['authorize_service','Authorize cFS service']]){
   if(settings.commands[key])inline.push(commandRow(label,settings.commands[key]));
  }
 }
 if(checks?.checks.some(c=>c.label==='Ground Station Python packages'&&!c.ready)){
  rows.push(commandRow('Install Ground Station packages',checks.checks.find(c=>c.label==='Ground Station Python packages').command));
 }
 const actions=$('#field-commands');if(actions)actions.innerHTML=inline.join('');
 $('#preparation').innerHTML=rows.join('');
}
async function refreshSource(){
 const {source,sources_ready}=await api('infrastructure');
 settings.source=source;settings.sources_ready=sources_ready;
 renderCommands();controls();
}
async function save(){
 readForm();
 const updated=await api('infrastructure',{target,build_jobs:settings.build_jobs,board:settings.board,os:settings.os,connection:settings.connection||{},emulator:settings.emulator});
 settings=updated;dirty=false;
 renderCommands();
}
async function followJob(action, id){
 job=id;
 const download=action==='clone-cfs';
 $('#job-output').hidden=false;
 $('#job-title').textContent=download?'NASA cFS download':action==='probe'?'SSH connection':'cFS service preparation';
 $('#job-log').textContent=download?'Cloning NASA cFS and its submodules…':'Connecting…';
 $('#job-state').textContent='running';$('#board-report').textContent='';
 while(job){
  const current=(await api('jobs')).find(j=>j.id===job);
  if(!current)throw Error('This operation has ended. Run it again to retry.');
  const log=$('#job-log');
  log.textContent=current.lines.join('\n');log.scrollTop=log.scrollHeight;$('#job-state').textContent=current.status;
  if(current.status==='running'){await new Promise(r=>setTimeout(r,700));continue;}
  job=null;
  const refreshed=await api('infrastructure');
  if(download){settings.source=refreshed.source;settings.sources_ready=refreshed.sources_ready;checks=null;renderChecks();}
  else settings=refreshed;
  renderCommands();
  if(current.status!=='succeeded')throw Error(current.error||'Operation failed. See the output for details.');
  if(download){feedback('NASA cFS is ready.');return;}
  const p=current.result;
  $('#board-report').textContent=p?`${p.model} · ${p.os} · ${p.ready?'cFS service ready':'cFS service needs preparation'} · ${p.i2c?.length?p.i2c.join(', '):'No I²C interfaces detected'}`:'';
  feedback(action==='probe'?'SSH verified.':'Board preparation checked.');
 }
}
async function startJob(action){
 const download=action==='clone-cfs';
 if(!download){await save();if(!settings.connection?.host)throw Error('Enter the SSH host before testing the board.');}
 const options=download?{}:{target:'physical',connection:settings.connection};
 const result=await api('job',{action,options});await followJob(action,result.id);
}
$('#clone-source').addEventListener('click',()=>perform(()=>startJob('clone-cfs')));

$('#close-terminal').addEventListener('click',async()=>{if(shell){await api('terminal/close',{id:shell.id});shells.dispose(shell.id);shell=null;}$('#setup-terminal').hidden=true;});
$('#targets').addEventListener('click',event=>{
 const choice=event.target.closest('[data-target]');if(!choice||busy)return;
 readForm();target=choice.dataset.target;checks=null;dirty=true;feedback();$('#job-output').hidden=true;render();
});
$('#configuration').addEventListener('input',()=>{dirty=true;checks=null;renderChecks();renderCommands();controls();});
$('#configuration').addEventListener('change',event=>{if(event.target.name==='board'){readForm();render();}});
document.addEventListener('click',event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.job)perform(()=>startJob(button.dataset.job));
 if(button.dataset.command)perform(async()=>{const key=button.dataset.command;if(settings.sources_ready)await save();const command=commands.get(key);if(!command)throw Error('Save a connection before running this command.');await terminal(command);});
});
$('#check').addEventListener('click',()=>{
 if(!$('#infrastructure-form').reportValidity())return;
 perform(async()=>{
  $('#check').textContent='Checking…';
  checks=null;renderChecks();
  try{await refreshSource();if(settings.sources_ready)await save();checks=await api('infrastructure/check',{target});renderChecks();renderCommands();}
  finally{$('#check').textContent='Run all checks';}
 });
});
$('#infrastructure-form').addEventListener('submit',event=>{event.preventDefault();perform(async()=>{if(!settings.sources_ready)throw Error('Clone NASA cFS before opening the workspace.');await save();location.href='/studio';});});
window.addEventListener('focus',()=>{if(settings&&!busy&&!settings.sources_ready)refreshSource().catch(e=>feedback(e.message,true));});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});

(async()=>{
 try{
  token=(await api('session')).token;settings=await api('infrastructure');
  const requested=new URLSearchParams(location.search).get('target');target=modes[requested]?requested:settings.target;
  feedback();render();
  const active=(await api('jobs')).find(j=>j.action==='clone-cfs'&&j.status==='running');
  if(active)await perform(()=>followJob('clone-cfs',active.id));
  else if(!settings.sources_ready)await refreshSource();
 }catch(error){feedback(error.message,true);controls();}
})();

$('#close-report').onclick=()=>$('#job-output').hidden=true;
