import {targetDrawing} from './target-drawing.js';
import {icon} from './ui.js';
import {mountShells} from './shell.js';
import {groupsByTarget, groupFor, repairFor, nextRepair} from './setup-plan.js';

for (const art of document.querySelectorAll('[data-art]')) art.innerHTML = targetDrawing(art.dataset.art);
const $ = selector => document.querySelector(selector);
const form = $('#infrastructure-form');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const targets = ['native','qemu','physical'];
const checksByTarget = new Map();
const checkRequests = new Map();
let token = '', settings = null, target = 'native', busy = false, dirty = false;
let activeGroup = '', installation = null, selectedVersion = 0;
let verification = null;
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
  const more = `<button type="button" class="settings-button" id="advanced-toggle" aria-label="Target settings" title="Target settings" aria-haspopup="dialog" aria-controls="settings-sheet">${icon('settings')}</button>`;
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
  $('#project-name').textContent = settings.project;
  renderChecks();
  controls();
}

function reportFor(mode) {
  if (!checksByTarget.has(mode)) {
    checksByTarget.set(mode,(settings.check_plan[mode]||[]).map(entry => ({...entry,status:'pending'})));
  }
  return checksByTarget.get(mode);
}
function groups(mode) {
  const rows = reportFor(mode);
  return groupsByTarget[mode].map(([name,glyph]) => {
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
const spin = '<svg class="spin-arc" viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="22" pathLength="100"/></svg>';
const download = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/></svg>';
const installerLabels = {
  'clone-cfs':'NASA cFS', 'native-tools':'Native tools', dependencies:'Toolchain',
  'emulator-image':'Emulator image', 'board-service':'cFS service', 'board-key':'SSH key'
};

function updateDetails(plans) {
  const dialog = $('#verification');
  if (!dialog.open) return;
  const group = plans.find(item => item.name === activeGroup) || plans[0];
  const tabs = $('#check-groups');
  if (tabs.dataset.target !== target) {
    tabs.dataset.target = target;
    tabs.replaceChildren(...plans.map(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = button.dataset.group = item.name;
      return button;
    }));
  }
  for (const button of tabs.children) button.setAttribute('aria-pressed', String(button.dataset.group === group.name));
  const locked = busy || checkRequests.has(target);
  $('#check').disabled = locked;
  $('#fix-group').hidden = group.state !== 'missing';
  $('#fix-group').disabled = locked;
  $('#fix-group').textContent = group.action === 'settings' ? 'Target settings' : 'Install';
  const list = $('#checks');
  const openRows = new Set([...list.querySelectorAll('details[open]')].map(row => row.dataset.label));
  const statusIcon = {passed:'✓', failed:'!', pending:'○', running:'◌'};
  const content = group.entries.map(row => {
    const label = escapeHtml(row.label);
    const duration = row.duration_ms == null ? '' : row.duration_ms + ' ms';
    const outcome = row.exit_code == null ? row.status : 'Exit ' + row.exit_code;
    return '<details data-outcome="' + row.status + '" data-label="' + label + '"><summary><span aria-label="' + row.status + '">' + statusIcon[row.status] + '</span><span>' + label + '</span><small>' + duration + '</small></summary><pre>' + escapeHtml([row.probe,row.detail,outcome].filter(Boolean).join('\n')) + '</pre></details>';
  }).join('');
  if (list.dataset.content !== content) {
    list.innerHTML = content;
    list.dataset.content = content;
    for (const row of list.children) row.open = openRows.has(row.dataset.label);
  }
}

function renderChecks() {
  if (!settings) return;
  const plans = groups(target);
  const checking = checkRequests.has(target);
  const missing = plans.filter(x => x.state === 'missing').length;
  const fixing = installation?.target === target && installation.status === 'running';
  const ready = !dirty && !checking && !busy && plans.every(x => x.state === 'ready');
  const probe = reportFor(target).find(row => row.status === 'running');
  const note = fixing ? 'Installing ' + installerLabels[installation.setup_action] :
    probe ? 'Checking ' + probe.label : missing ? missing + ' to fix' : '';
  $('#group-summary').textContent = note;
  const parent = $('#requirements');
  if (parent.dataset.target !== target) {
    parent.dataset.target = target;
    parent.innerHTML = plans.map(group => '<button type="button" class="requirement" data-group="' + group.name + '"><span class="ring">' + spin + '<span class="tool-glyph"></span><span class="badge check-badge">' + tick + '</span><span class="badge repair-badge">+</span></span><span>' + group.name + '</span></button>').join('');
  }
  plans.forEach((group, index) => {
    const button = parent.children[index];
    if (button.dataset.state !== group.state) {
      button.dataset.state = group.state;
      button.querySelector('.tool-glyph').innerHTML = group.state === 'missing' ? download : icon(group.glyph);
    }
    const repair = group.state === 'missing' && !checking && !busy;
    button.title = repair ? (group.action === 'settings' ? 'Configure ' : 'Install ') + group.name : 'Inspect ' + group.name;
    button.setAttribute('aria-label', button.title);
  });
  updateDetails(plans);
  $('#enter').hidden = !ready;
  $('#enter').disabled = !ready;
  const install = $('#install');
  install.hidden = ready;
  install.disabled = busy;
  install.textContent = busy ? (fixing ? 'Installing' : 'Checking') : 'Install requirements';
  const terminal = $('#show-terminal');
  terminal.hidden = !installation || installation.target !== target;
  const details = $('#inspect');
  details.dataset.input = String(fixing && Boolean(installation.input_required));
  details.textContent = details.dataset.input === 'true' ? 'Input required' : 'Details';
}

function controls() {
  for (const card of document.querySelectorAll('.target-option')) {
    card.disabled = !settings || busy;
    card.setAttribute('aria-pressed', String(card.dataset.target === target));
  }
  for (const field of form.querySelectorAll('#configuration :is(input,select,button), #advanced :is(input,select)')) {
    field.disabled = busy;
  }
  $('#inspect').disabled = !settings;
  $('#save-state').textContent = dirty ? 'Unsaved' : '';
  $('#save-state').dataset.state = dirty ? 'dirty' : '';
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
async function runChecks(groupName) {
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
    const batch=groupsByTarget[mode].filter(([name])=>!groupName || name===groupName)
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
    return true;
  }catch(error){if(!controller.signal.aborted)feedback(error.message,true);}
  finally{if(checkRequests.get(mode)===controller){checkRequests.delete(mode);controls();}}
}
function verify(groupName) {
  verification = runChecks(groupName);
  return verification;
}

const shells = mountShells({api, onError: showError, onExit: () => true});
function showDialog(id) {
  const dialog = $(id);
  if (!dialog.open) dialog.showModal();
}
function inspect(name) {
  activeGroup = name || groups(target)[0].name;
  showDialog('#verification');
  renderChecks();
}

async function followInstaller(session, groupName) {
  installation = {...session, group: groupName};
  $('#terminal-title').textContent = installerLabels[session.setup_action];
  if ($('#setup-terminal').open) shells.select(session);
  while (installation.status === 'running') {
    $('#terminal-state').textContent = installation.input_required ? 'Input required' : 'Installing';
    controls();
    await new Promise(resolve => setTimeout(resolve,400));
    const jobs = await api('jobs');
    const current = jobs.find(job => job.id === session.id);
    if (!current) throw Error('Installer unavailable');
    Object.assign(installation,current);
  }
  const success = installation.status === 'succeeded';
  $('#terminal-state').textContent = success ? 'Completed' : 'Exit ' + installation.exit_code;
  // Cloning can change the active mission profile. Keep the user's selected board.
  const preferred = {board:settings.board, os:settings.os};
  settings = await api('infrastructure');
  if (session.setup_action === 'clone-cfs' && target !== 'native') {
    Object.assign(settings,preferred);
    dirty = true;
  }
  // A missing dependency can affect several groups. Keep already verified rings steady.
  const pending = groups(target).filter(group => group.state !== 'ready');
  let checked = true;
  if (dirty || !pending.length) checked = await verify();
  else for (const group of pending) {
    checked = await verify(group.name);
    if (!checked) break;
  }
  if (!success) feedback(installerLabels[session.setup_action] + ' · exit ' + installation.exit_code, true);
  return success && checked;
}

function openSettings() {
  if ($('#verification').open) $('#verification').close();
  if (target === 'physical') form.elements.host.focus();
  else {
    showDialog('#settings-sheet');
    form.elements.ssh_port?.focus();
  }
}

async function installRequirements(groupName) {
  if (!settings || busy || !form.reportValidity()) return;
  busy = true;
  const mode = target;
  try {
    controls();
    if (checkRequests.has(mode)) {
      if (!await verification) return;
    }
    if (dirty || reportFor(mode).some(row => row.status === 'pending')) {
      if (!await verify()) return;
    }
    const attempted = new Set();
    for (;;) {
      const repair = nextRepair(mode,reportFor(mode),groupName);
      if (!repair) break;
      const {action,group,label} = repair;
      if (action === 'settings') {
        busy = false;
        controls();
        openSettings();
        break;
      }
      if (attempted.has(action)) {
        feedback('Check ' + label, true);
        break;
      }
      attempted.add(action);
      const session = await api('terminal/create',{target:mode,setup_action:action});
      if (!await followInstaller(session,group)) break;
    }
  } finally {
    busy = false;
    controls();
  }
}

function showError(error) { feedback(error.message,true); controls(); }
$('#targets').addEventListener('click', event => {
  const mode = event.target.closest('[data-target]')?.dataset.target;
  if (!mode || !settings || busy) return;
  abortChecks(target);
  selectedVersion++;
  dirty = dirty || mode !== settings.target;
  target = mode;
  checksByTarget.delete(mode);
  renderFields();
  verify().catch(showError);
});
$('#install').addEventListener('click', () => installRequirements().catch(showError));
$('#inspect').addEventListener('click', () => {
  if (installation?.target === target && installation.status === 'running') showTerminal();
  else inspect(groups(target).find(group => group.state === 'missing')?.name);
});
$('#requirements').addEventListener('click', event => {
  const name = event.target.closest('[data-group]')?.dataset.group;
  const group = groups(target).find(item => item.name === name);
  if (!group) return;
  if (group.state === 'missing' && !checkRequests.has(target) && !busy) installRequirements(name).catch(showError);
  else inspect(name);
});
$('#check-groups').addEventListener('click', event => {
  const name = event.target.closest('[data-group]')?.dataset.group;
  if (name) inspect(name);
});
$('#fix-group').addEventListener('click', () => installRequirements(activeGroup).catch(showError));
$('#check').addEventListener('click', () => verify(activeGroup).catch(showError));
for (const dialog of document.querySelectorAll('dialog')) {
  dialog.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
}
function showTerminal() {
  if (!installation) return;
  showDialog('#setup-terminal');
  shells.select(installation);
  shells.focus();
}
$('#show-terminal').addEventListener('click', showTerminal);
$('#setup-terminal').addEventListener('close', () => { if (!$('#setup-terminal').open) shells.select(null); });
form.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.id === 'advanced-toggle') showDialog('#settings-sheet');
  if (button.dataset.step) {
    const input = form.elements.build_jobs;
    if (button.dataset.step === '-1') input.stepDown(); else input.stepUp();
    input.dispatchEvent(new Event('change',{bubbles:true}));
  }
});
form.addEventListener('input', () => {
  abortChecks(target);
  selectedVersion++;
  dirty = true;
  checksByTarget.delete(target);
  controls();
});
form.addEventListener('change', event => {
  dirty = true;
  if (event.target.name === 'board') { readForm(); renderFields(); }
  verify().catch(showError);
});
form.addEventListener('submit', event => {
  event.preventDefault();
  if (!$('#enter').disabled && !$('#enter').hidden) location.href = '/studio#boot';
});
(async () => {
  token = (await api('session')).token;
  settings = await api('infrastructure');
  const requested = new URLSearchParams(location.search).get('target');
  const explicitSelection = targets.includes(requested);
  target = explicitSelection ? requested : settings.target;
  const jobs = await api('jobs');
  const running = jobs.find(job => job.setup_action && job.status === 'running');
  if (running) {
    target = running.target;
    busy = true;
    renderFields();
    const row = reportFor(target).find(item => repairFor(target,item) === running.setup_action);
    try { await followInstaller(running, row && groupFor(target,row.label)); }
    finally { busy = false; controls(); }
  } else {
    renderFields();
    if (explicitSelection) await verify();
  }
})().catch(showError);
