import {icon} from './ui.js';
import {mountShells} from './shell.js';

const $ = selector => document.querySelector(selector);
const form = $('#infrastructure-form');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const targets = ['native','qemu','physical'];
const checksByTarget = new Map();
const checkRequests = new Map();
let token = '', settings = null, target = 'native', busy = false, dirty = false;
let activeGroup = '', advanced = false, installation = null, selectedVersion = 0;
let saving = Promise.resolve();
function feedback(message = '', error = false) {
  $('#feedback').textContent = message;
  $('#feedback').classList.toggle('error', error);
}

async function request(path, body, options = {}, retry = true) {
  const init = {...options, headers:{...options.headers}};
  if (body !== undefined) {
    init.method = 'POST';
    Object.assign(init.headers, {'Content-Type':'application/json','X-Studio-Token':token});
    init.body = JSON.stringify(body);
  }
  const response = await fetch('/api/' + path, init);
  if (response.status === 403 && retry && path !== 'session') {
    token = (await api('session')).token;
    return request(path, body, options, false);
  }
  if (!response.ok) {
    const error = await response.json();
    throw Error(error.error || response.statusText);
  }
  return response;
}

async function api(path, body) {
  return (await request(path, body)).json();
}

function readForm() {
  const fields = form.elements;
  if (target === 'native') {
    settings.build_jobs = Number(fields.build_jobs.value);
    return;
  }
  settings.board = fields.board.value;
  settings.os = fields.os.value;
  if (target === 'qemu') {
    settings.emulator = {ssh_port:Number(fields.ssh_port.value),image:fields.image.value.trim()};
  } else {
    settings.connection = {
      host:fields.host.value.trim(), user:fields.user.value.trim(), port:Number(fields.port.value),
      identity_file:fields.identity_file.value.trim(), directory:settings.connection?.directory || 'cfs-arm64'
    };
  }
}
function selectField(name, label, options, selected) {
  const choices = options.map(([value,text]) =>
    `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(text)}</option>`
  ).join('');
  return `<select name="${name}" aria-label="${label}" required>${choices}</select>`;
}
function profileFields() {
  const profiles = settings.profiles.filter(p => p.targets.includes(target));
  if (!profiles.some(p => p.board === settings.board)) settings.board = profiles[0]?.board || '';
  const systems = profiles.filter(p => p.board === settings.board);
  if (!systems.some(p => p.os === settings.os)) settings.os = systems[0]?.os || '';
  const boards = [...new Map(profiles.map(p => [p.board,p.board_label]))];
  return selectField('board','Board',boards,settings.board) +
    selectField('os','Operating system',systems.map(p => [p.os,p.os_label]),settings.os);
}

function renderFields() {
  const data = settings.connection || {};
  const more = `<button type="button" class="settings-button" id="advanced-toggle" aria-label="Target settings" title="Target settings" aria-controls="advanced" aria-expanded="${advanced}">${icon('settings')}</button>`;
  let fields, details = '';
  if (target === 'native') {
    fields = `<div class="stepper-field"><label for="build-jobs">Jobs</label><div class="stepper">
      <button type="button" data-step="-1" aria-label="Fewer build jobs">−</button>
      <input id="build-jobs" title="Parallel build jobs" aria-label="Parallel build jobs" name="build_jobs" type="number" value="${settings.build_jobs}" min="1" max="64" required>
      <button type="button" data-step="1" aria-label="More build jobs">+</button></div></div>`;
  } else if (target === 'qemu') {
    fields = profileFields() + more;
    details = `<div class="fields"><label>Local SSH port<input name="ssh_port" type="number" required min="1024" max="65535" value="${settings.emulator.ssh_port}"></label>
      <label class="wide">Emulator image<input name="image" required value="${escapeHtml(settings.emulator.image)}" spellcheck="false"></label></div>`;
  } else {
    fields = `<label class="input-wrap">${icon('antenna')}<input aria-label="SSH host or alias" name="host" placeholder="Host or SSH alias" value="${escapeHtml(data.host)}" list="ssh-hosts" autocomplete="off"></label>
      <datalist id="ssh-hosts">${settings.ssh_hosts.map(h => `<option value="${escapeHtml(h.host)}">`).join('')}</datalist>
      <label class="input-wrap">${icon('terminal')}<input name="user" aria-label="SSH user" placeholder="SSH user" value="${escapeHtml(data.user)}" autocomplete="off"></label>` + more;
    details = `<div class="fields">${profileFields()}<label>SSH port<input name="port" type="number" required min="1" max="65535" value="${data.port || 22}"></label>
      <label class="wide">SSH private key<input name="identity_file" value="${escapeHtml(data.identity_file)}" placeholder="From SSH config or agent" list="ssh-keys" spellcheck="false"></label>
      <datalist id="ssh-keys">${settings.ssh_keys.map(k => `<option value="${escapeHtml(k)}">`).join('')}</datalist></div>`;
  }
  $('#configuration').innerHTML = fields;
  $('#advanced').innerHTML = details;
  $('#advanced').hidden = !advanced || !details;
  $('#project-name').textContent = settings.project;
  renderChecks();
  controls();
}

const sets = {
  native:[['Compiler','code'],['Python','terminal'],['Source','folder']],
  qemu:[['Docker','container'],['Image','cube'],['Toolchain','cpu']],
  physical:[['Network','antenna'],['SSH key','key'],['Service','power']]
};
function groupFor(mode,label) {
  if (mode === 'native') return label === 'NASA cFS source' ? 'Source' : label.includes('Python') ? 'Python' : 'Compiler';
  if (mode === 'qemu') {
    if (/docker/i.test(label)) return 'Docker';
    return /Emulator|Local SSH/.test(label) ? 'Image' : 'Toolchain';
  }
  if (label === 'Board network') return 'Network';
  return /SSH identity|Board login|^ssh$|^scp$/.test(label) ? 'SSH key' : 'Service';
}
function repairFor(mode,item) {
  if (item.label === 'NASA cFS source') return 'clone-cfs';
  if (item.label === 'Board network' || item.label === 'Local SSH port') return 'settings';
  if (item.label === 'Board login' || item.label === 'Board SSH identity') return 'board-key';
  if (item.label === 'cFS service') return 'board-service';
  if (item.label.startsWith('Emulator')) return 'emulator-image';
  return mode === 'native' ? 'native-tools' : 'dependencies';
}
function reportFor(mode) {
  if (!checksByTarget.has(mode)) {
    checksByTarget.set(mode,(settings.check_plan[mode]||[]).map(entry => ({...entry,status:'pending'})));
  }
  return checksByTarget.get(mode);
}
function groups(mode) {
  const rows = reportFor(mode);
  return sets[mode].map(([name,glyph]) => {
    const entries = rows.filter(x=>groupFor(mode,x.label) === name);
    const failed = entries.find(x=>x.status === 'failed');
    const action = failed && repairFor(mode,failed);
    let state = 'pending';
    if (installation?.target === mode && installation.group === name && installation.status === 'running') state = 'installing';
    else if (entries.some(x=>x.status==='running')) state = 'running';
    else if (failed) state = 'missing';
    else if (entries.length && entries.every(x=>x.status==='passed')) state = 'ready';
    return {name,glyph,entries,state,action};
  });
}
const tick = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4 10-10" pathLength="1"/></svg>';
function renderChecks() {
  if (!settings) return;
  const plans = groups(target);
  const checking = checkRequests.has(target);
  const missing = plans.filter(x=>x.state==='missing').length;
  const fixing = installation?.target === target && installation.status==='running';
  const ready = !dirty && !checking && !fixing && plans.every(x=>x.state==='ready');
  for (const card of document.querySelectorAll('.target-option[data-target]')) {
    const mode = card.dataset.target;
    card.setAttribute('aria-pressed',String(mode === target));
    const statuses = groups(mode).map(group=>group.state);
    const count = statuses.filter(status=>status==='missing').length;
    const status = checkRequests.has(mode) ? 'checking' : statuses.includes('installing') ? 'installing' :
      count ? 'missing' : statuses.every(s=>s==='ready') ? 'ready' : 'unchecked';
    const caption = card.querySelector('small');
    caption.dataset.status = status;
    caption.textContent = status === 'missing' ? count+' missing' : status;
  }
  $('#group-summary').textContent = fixing ? 'Installing' : checking ? 'Checking target' : missing ? missing+' to fix' : ready ? 'Everything is ready' : '';
  const parent = $('#requirements');
  if (parent.dataset.target !== target) {
    parent.dataset.target = target;
    parent.innerHTML = plans.map(group=>`<button type="button" class="requirement" data-group="${group.name}" aria-controls="verification"><span class="ring"><span class="tool-glyph">${icon(group.glyph)}</span><span class="check-badge">${tick}</span><span class="repair-badge">+</span></span><span>${group.name}</span></button>`).join('');
  }
  plans.forEach((group,index)=>{
    const button = parent.children[index];
    button.dataset.state = group.state;
    button.setAttribute('aria-expanded',String(activeGroup===group.name));
    const repair = group.state === 'missing';
    button.title = (repair ? 'Fix ' : 'Inspect ')+group.name;
    button.setAttribute('aria-label',button.title);
    const percent = fixing && group.state==='installing' ? installation.progress : null;
    const glyph = button.querySelector('.tool-glyph');
    const text = percent==null ? icon(group.glyph) : Math.min(100,percent)+'%';
    if (glyph.dataset.content!==text) { glyph.dataset.content=text; glyph.innerHTML=text; }
    button.style.setProperty('--progress',(percent??0)+'%');
  });
  const group = plans.find(x=>x.name===activeGroup);
  $('#verification').hidden = !group;
  if (group) {
    $('#check-status').textContent = group.name;
    $('#check').disabled = checking || fixing || busy;
    const list=$('#checks');
    const details=group.entries.map(row=>`<div data-outcome="${row.status}"><code title="${escapeHtml(row.probe)}">${escapeHtml(row.probe)}</code><span>${escapeHtml(row.detail||row.status)}</span><small>${row.exit_code!=null?'Exit '+row.exit_code:''}${row.duration_ms!=null?' · '+row.duration_ms+' ms':''}</small></div>`).join('');
    if(list.dataset.content!==details){list.innerHTML=details;list.dataset.content=details;}
  }
  $('#enter').hidden = !ready;
  $('#enter').disabled = !ready || busy;
  $('#waiting').hidden = ready;
  $('#waiting').textContent = fixing?'Installing…':checking?'Checking…':missing?'Fix '+missing+' to continue':'Select to check';
}
function controls() {
  $('#save-state').textContent = busy ? 'Saving…' : !settings ? '' : dirty ? 'Unsaved' : 'Saved';
  $('#save-state').dataset.state = dirty || busy ? 'dirty' : 'saved';
  for(const card of document.querySelectorAll('.target-option')) card.disabled = !settings;
  renderChecks();
}
async function saveForm() {
  readForm();
  const {build_jobs,board,os,connection,emulator} = settings;
  const mode=target,version=selectedVersion;
  // Serialize saves from rapid selections so the last click is the saved target.
  const values={target:mode,build_jobs,board,os,connection:connection||{},emulator};
  const result = saving.then(()=>api('infrastructure',values));
  saving=result.catch(()=>{});
  const next=await result;
  if(version===selectedVersion){settings=next;dirty=false;}
}
function abortChecks(mode) {
  checkRequests.get(mode)?.abort();
  checkRequests.delete(mode);
}
async function verify(groupName) {
  if (!settings || !form.reportValidity()) return;
  const mode=target,version=selectedVersion;
  abortChecks(mode);
  const controller=new AbortController();
  checkRequests.set(mode,controller);
  feedback();
  try {
    // Persist connection values before SSH checks. Mission profile changes wait for the NASA checkout.
    if(dirty || !settings.target_saved || mode!==settings.target) await saveForm();
    if(controller.signal.aborted || version!==selectedVersion)return;
    if (mode!=='native') { settings.board=form.elements.board.value; settings.os=form.elements.os.value; }
    const report=reportFor(mode);
    const batch=sets[mode].filter(([name])=>!groupName || name===groupName)
      .flatMap(([name])=>report.filter(row=>groupFor(mode,row.label)===name));
    for(const stage of batch) Object.assign(stage,{status:'pending',detail:'',duration_ms:null,exit_code:null});
    for(const stage of batch){
      if(controller.signal.aborted)return;
      stage.status='running';renderChecks();
      const response=await request('infrastructure/check',{target:mode,label:stage.label},{signal:controller.signal});
      const result=await response.json();
      if(controller.signal.aborted)return;
      if(result.label!==stage.label || !['passed','failed'].includes(result.status)) throw Error('Invalid check result');
      Object.assign(stage,result);
      if(result.source){settings.source=result.source;settings.sources_ready=result.source.state==='ready';}
      renderChecks();
    }
    window.dispatchEvent(new Event('flight:updated'));
  }catch(error){if(!controller.signal.aborted)feedback(error.message,true);}
  finally{if(checkRequests.get(mode)===controller){checkRequests.delete(mode);controls();}}
}
const installerLabels={'clone-cfs':'NASA cFS','native-tools':'Native tools','dependencies':'Toolchain','emulator-image':'Emulator image','board-service':'cFS service','board-key':'SSH key'};
const shells=mountShells({api,onError:e=>feedback(e.message,true),onExit:()=>true});
function showTerminal(session) {
  $('#setup-terminal').hidden=false;$('#show-terminal').hidden=true;
  shells.select(session);shells.focus();
}
async function followInstaller(session,groupName) {
  installation={...session,group:groupName};
  $('#terminal-title').textContent=installerLabels[session.setup_action];
  $('#terminal-state').textContent='Installing…';
  showTerminal(session);
  do{
    controls();
    const jobs=await api('jobs'), current=jobs.find(j=>j.id===session.id);
    if(!current)throw Error('Installer exited');
    Object.assign(installation,current);
    if(current.status==='running')await new Promise(resolve=>setTimeout(resolve,400));
  }while(installation.status==='running');
  $('#terminal-state').textContent=installation.status==='succeeded'?'Completed':'Exit '+installation.exit_code;
  if(session.target===target){
    const preferred={board:settings.board,os:settings.os};
    settings=await api('infrastructure');
    if(session.setup_action==='clone-cfs' && target!=='native'){Object.assign(settings,preferred);dirty=true;}
    // Repairs may install shared prerequisites. Reuse other completed groups.
    await verify(session.setup_action==='clone-cfs' || reportFor(target).some(row=>row.status==='pending')?null:groupName);
  }
  controls();
}
async function repair(group) {
  activeGroup=group.name;renderChecks();
  if(checkRequests.has(target) || installation?.status==='running')return;
  if(group.action==='settings'){
    advanced=true;renderFields();
    (form.elements.host||form.elements.ssh_port)?.focus();
    return;
  }
  if(installation){await api('terminal/close',{id:installation.id});shells.dispose(installation.id);installation=null;}
  const session=await api('terminal/create',{target,setup_action:group.action});
  await followInstaller(session,group.name);
}
function showError(err){feedback(err.message,true);controls();}
$('#targets').addEventListener('click',event=>{
  const mode=event.target.closest('[data-target]')?.dataset.target;if(!mode || !settings)return;
  abortChecks(target);selectedVersion++;dirty=dirty || mode!==settings.target;target=mode;advanced=false;activeGroup='';
  checksByTarget.delete(target);renderFields();
  verify().catch(showError);
});
$('#requirements').addEventListener('click',event=>{
  const name=event.target.closest('[data-group]')?.dataset.group,group=groups(target).find(g=>g.name===name);
  if(!group)return;
  if(group.state==='missing')repair(group).catch(showError);
  else {activeGroup=activeGroup===name?'':name;renderChecks();}
});
$('#check').addEventListener('click',()=>verify(activeGroup).catch(showError));
$('#close-checks').addEventListener('click',()=>{activeGroup='';renderChecks();});
$('#close-terminal').addEventListener('click',()=>{$('#setup-terminal').hidden=true;$('#show-terminal').hidden=false;});
$('#show-terminal').addEventListener('click',()=>{if(installation)showTerminal(installation);});
form.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.id==='advanced-toggle'){advanced=!advanced;$('#advanced').hidden=!advanced;button.setAttribute('aria-expanded',String(advanced));}
  if(button.dataset.step){const input=form.elements.build_jobs;button.dataset.step==='-1'?input.stepDown():input.stepUp();input.dispatchEvent(new Event('change',{bubbles:true}));}
});
form.addEventListener('input',()=>{abortChecks(target);selectedVersion++;dirty=true;checksByTarget.delete(target);controls();});
form.addEventListener('change',e=>{
  dirty=true;
  if(e.target.name==='board'){readForm();renderFields();}
  verify().catch(showError);
});
form.addEventListener('submit',event=>{
  event.preventDefault();
  if(!$('#enter').disabled && !$('#enter').hidden)location.href='/studio#boot';
});
(async()=>{
  token=(await api('session')).token;settings=await api('infrastructure');
  const requested=new URLSearchParams(location.search).get('target');
  const explicitSelection=targets.includes(requested);
  target=explicitSelection?requested:settings.target;
  renderFields();
  const jobs=await api('jobs');
  const running=jobs.find(j=>j.setup_action && j.status==='running');
  if(running){
    const group=sets[running.target].find(([name])=>reportFor(running.target).some(row=>groupFor(running.target,row.label)===name && repairFor(running.target,row)===running.setup_action));
    await followInstaller(running,group?.[0]);
    if(explicitSelection && running.target!==target)await verify();
  }else if(explicitSelection)await verify();
})().catch(showError);
