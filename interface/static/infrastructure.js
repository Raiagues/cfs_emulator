import {icon} from './ui.js';
import {mountShells} from './shell.js';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modes = {native:['monitor','Native','This computer'],qemu:['cube','Emulator','QEMU + Linux'],physical:['circuit','Physical board','Connect over SSH']};
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
 $('#save-state').textContent=busy?'Working…':dirty?'Unsaved configuration':'Connections and emulator settings stay local.';
}
async function perform(action){
 if(busy)return;busy=true;controls();feedback();
 try{await action();}catch(error){feedback(error.message,true);}
 finally{busy=false;controls();}
}
const shells=mountShells({api,onError:error=>feedback(error.message,true)});
async function terminal(command){
 $('#setup-terminal').hidden=false;
 if(!shell)shell=await api('terminal/create',{});
 shells.select(shell);shells.focus();$('#setup-terminal').scrollIntoView({behavior:'smooth',block:'nearest'});
 if(command)await api('terminal/input',{id:shell.id,data:command+'\r'});
}
function readForm(){
 if(!settings)return;
 const field=name=>$('#configuration [name="'+name+'"]');
 if(target!=='native'){
  settings.board=field('board').value;settings.os=field('os').value;
 }
 if(target==='qemu')settings.emulator={ssh_port:Number(field('ssh_port').value),image:field('image').value.trim()};
 if(target==='physical')settings.connection={host:field('host').value.trim(),user:field('user').value.trim(),port:Number(field('port').value),identity_file:field('identity_file').value.trim(),directory:field('directory').value.trim()};
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
 $('#project-name').textContent=settings.project;
 $('#targets').innerHTML=Object.entries(modes).map(([key,[glyph,name,description]])=>`<button type="button" class="target-option" data-target="${key}" aria-pressed="${key===target}">${icon(glyph)}<span><strong>${name}</strong><small>${description}</small></span></button>`).join('');
 $('#target-route').innerHTML=icon('monitor')+(target==='native'?'Local compiler → cFS':target==='qemu'?'Docker → QEMU → Linux':'SSH → Linux → cFS');
 let fields='';
 if(target==='native'){
  fields=`<div class="host-preview">${icon('monitor')}<div><strong>This computer</strong><span>${esc(settings.host.os)} · ${esc(settings.host.architecture)}</span></div></div><p class="field-note">Uses the local C compiler. Your saved board configuration stays available in the other modes.</p>`;
 }else{
  fields=profileFields();
  if(target==='qemu'){
   fields+=`<label>Local SSH port<input name="ssh_port" type="number" required min="1024" max="65535" value="${settings.emulator.ssh_port}"></label><label>SSH address<input value="127.0.0.1" readonly aria-label="Emulator SSH address"></label><label class="full">Emulator image<input name="image" required value="${esc(settings.emulator.image)}" spellcheck="false"></label><p class="field-note">The selected board and OS configure the cross compiler. The emulator keeps its disk between sessions.</p>`;
  }else{
   const c=settings.connection||{};
   fields+=`<label class="full">SSH host or alias<input name="host" placeholder="hostname or IP address" value="${esc(c.host)}" list="ssh-hosts" autocomplete="off"></label><datalist id="ssh-hosts">${settings.ssh_hosts.map(h=>`<option value="${esc(h.host)}">`).join('')}</datalist><label>SSH user<input name="user" placeholder="From SSH config" value="${esc(c.user)}" autocomplete="off"></label><label>SSH port<input name="port" type="number" required min="1" max="65535" value="${c.port||22}"></label><label class="full">SSH private key path <span class="optional">Optional · uses SSH config / agent when empty</span><input name="identity_file" value="${esc(c.identity_file)}" placeholder="~/.ssh/id_ed25519" list="ssh-keys" spellcheck="false"></label><datalist id="ssh-keys">${settings.ssh_keys.map(k=>`<option value="${esc(k)}">`).join('')}</datalist><label class="full">Installation folder on the board<input name="directory" required value="${esc(c.directory||'cfs-arm64')}" spellcheck="false"></label><p class="field-note">Relative to the SSH user's home. Keys stay on this computer.</p>`;
  }
  fields=`<div class="fields">${fields}</div>`;
  if(target==='physical')fields+=`<div class="field-actions"><button type="button" data-job="probe">Test SSH</button><button type="button" data-job="connect">Prepare cFS service</button></div>`;
 }
 $('#configuration').innerHTML=fields;
 renderChecks();renderCommands();controls();
}
function renderChecks(){
 $('#checks').innerHTML=checks?checks.checks.map(c=>`<div class="check-row ${c.ready?'ready':''}"><span class="check-mark" aria-label="${c.ready?'Ready':'Needs setup'}">${c.ready?'✓':'○'}</span><div><strong>${esc(c.label)}</strong><small>${esc(c.detail)}</small></div></div>`).join('')+`<p class="check-summary ${checks.ready?'ready':''}">${checks.ready?'Local requirements ready':'Complete the missing requirements below.'}</p>`:'<p class="empty">Check the tools for the selected target.</p>';
}
function commandRow(label, command){
 commands.set(label,command);
 return `<div class="command-row"><span>${esc(label)}</span><code>${esc(command)}</code><button type="button" data-command="${esc(label)}">Run in terminal</button></div>`;
}
function renderCommands(){
 commands.clear();
 let description=target==='physical'?`Enable SSH and key authentication in <a href="https://www.raspberrypi.com/documentation/computers/remote-access.html#enable-the-ssh-server" target="_blank" rel="noreferrer">Raspberry Pi OS</a>, then connect the board to your network.`:'Commands run in the local terminal below.';
 let rows='';
 if(target==='native'){
  if(settings.host.package_manager==='apt')rows+=commandRow('Build tools','sudo apt-get update && sudo apt-get install -y build-essential cmake git');
 }else rows+=commandRow(target==='qemu'?'Prepare emulator':'Build tools','./scripts/setup.sh'+(target==='physical'?' --build-only':''));
 if(target==='physical'){
  for(const [key,label] of [['create_key','Create SSH key'],['authorize_key','Authorize SSH key'],['ssh','SSH terminal'],['authorize_service','Authorize cFS service']]){
   if(settings.commands[key])rows+=commandRow(label,settings.commands[key]);
  }
 }
 for(const c of checks?.checks||[])if(c.command&&!c.ready)rows+=commandRow(c.label,c.command);
 $('#preparation').innerHTML=`<header><h3>Preparation</h3><p>${description}</p></header>${rows}`;
}
async function save(){
 readForm();
 const updated=await api('infrastructure',{target,board:settings.board,os:settings.os,connection:settings.connection||{},emulator:settings.emulator});
 settings=updated;dirty=false;
 renderCommands();
}
async function startJob(action){
 await save();
 if(!settings.connection?.host)throw Error('Enter the SSH host before testing the board.');
 const result=await api('job',{action,options:{target:'physical',connection:settings.connection}});
 job=result.id;$('#job-output').hidden=false;$('#job-title').textContent=action==='probe'?'SSH connection':'cFS service preparation';$('#job-log').textContent='Connecting…';$('#board-report').textContent='';
 while(job){
  await new Promise(r=>setTimeout(r,700));
  const current=(await api('jobs')).find(j=>j.id===job);
  if(!current)throw Error('Connection check no longer exists. Run it again.');
  $('#job-log').textContent=current.lines.join('\n');$('#job-state').textContent=current.status;
  if(current.status==='running')continue;
  job=null;
  settings=await api('infrastructure');renderCommands();
  if(current.status!=='succeeded')throw Error(current.error||'Connection failed.');
  const p=current.result;
  $('#board-report').textContent=p?`${p.model} · ${p.os} · ${p.ready?'cFS service ready':'cFS service needs preparation'} · ${p.i2c?.length?p.i2c.join(', '):'No I²C interfaces detected'}`:'';
  feedback(action==='probe'?'SSH verified.':'Board preparation checked.');
 }
}

$('#open-terminal').innerHTML=icon('terminal')+'Open terminal';
$('#open-terminal').addEventListener('click',()=>terminal().catch(error=>feedback(error.message,true)));
$('#close-terminal').addEventListener('click',async()=>{if(shell){await api('terminal/close',{id:shell.id});shells.dispose(shell.id);shell=null;}$('#setup-terminal').hidden=true;});
$('#targets').addEventListener('click',event=>{
 const choice=event.target.closest('[data-target]');if(!choice||busy)return;
 readForm();target=choice.dataset.target;checks=null;dirty=true;feedback();render();
});
$('#configuration').addEventListener('input',()=>{dirty=true;checks=null;renderChecks();controls();});
$('#configuration').addEventListener('change',event=>{if(event.target.name==='board'){readForm();render();}});
document.addEventListener('click',event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.job)perform(()=>startJob(button.dataset.job));
 if(button.dataset.command)perform(async()=>{const key=button.dataset.command;await save();const command=commands.get(key);if(!command)throw Error('Save a connection before running this command.');await terminal(command);});
});
$('#save').addEventListener('click',()=>{if($('#infrastructure-form').reportValidity())perform(async()=>{await save();feedback('Configuration saved.');});});
$('#check').addEventListener('click',()=>{if($('#infrastructure-form').reportValidity())perform(async()=>{await save();checks=await api('infrastructure/check',{target});renderChecks();renderCommands();feedback(checks.ready?'Local requirements ready.':'Requirements checked.');});});
$('#infrastructure-form').addEventListener('submit',event=>{event.preventDefault();perform(async()=>{await save();location.href='/studio';});});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});

(async()=>{
 try{
  token=(await api('session')).token;settings=await api('infrastructure');
  const requested=new URLSearchParams(location.search).get('target');target=modes[requested]?requested:settings.target;
  feedback();render();
 }catch(error){feedback(error.message,true);controls();}
})();
