import {icon} from './ui.js';
import {mountShells} from './shell.js';

const $ = selector => document.querySelector(selector);
const form = $('#infrastructure-form');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const targets = ['native','qemu','physical'];
const checksByTarget = new Map();
const checkRequests = new Map();
const commands = new Map();
let token = '', settings = null, target = 'native', busy = false, dirty = false;
let activeGroup = '', advanced = false, shell = null, installation = null;

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

function controls() {
  for (const field of form.querySelectorAll('button,input,select')) field.disabled = busy || !settings;
  $('#enter').disabled = busy || !settings?.sources_ready;
  const checking = checkRequests.has(target);
  const installing = installation?.status === 'running';
  $('#check').disabled ||= checking || (installing && installation.target === target);
  $('#check').textContent = checking ? 'Checking…' : 'Run all checks';
  if (installing) {
    for (const button of form.querySelectorAll('[data-command]')) button.disabled = true;
  }
  const jobs = form.elements.build_jobs;
  if (jobs) {
    $('[data-step="-1"]').disabled ||= +jobs.value <= 1;
    $('[data-step="1"]').disabled ||= +jobs.value >= 64;
  }
  $('#save-state').textContent = busy ? 'Working…' : !settings ? '' : dirty ? 'Unsaved' : 'Saved';
  $('#save-state').dataset.state = dirty || busy ? 'dirty' : 'saved';
}

async function perform(action) {
  if (busy) return;
  busy = true;
  controls();
  feedback();
  try { await action(); }
  catch (error) { feedback(error.message, true); }
  finally { busy = false; controls(); }
}

function showTerminal(session) {
  $('#setup-terminal').hidden = false;
  $('#show-terminal').hidden = true;
  shells.select(session);
  shells.focus();
}

function finishInstallation(session, code) {
  if (session.status !== 'running') return;
  session.status = code === 0 ? 'succeeded' : 'failed';
  $('#terminal-state').textContent = code === 0 ? 'Completed' : 'Failed · exit ' + code;
  $('#terminal-state').dataset.status = session.status;
  $('#close-terminal').setAttribute('aria-label','Close terminal');
  renderChecks();
  controls();
}

const shells = mountShells({
  api, onError:error => feedback(error.message,true),
  onExit(id, code) {
    if (installation?.id !== id) return;
    finishInstallation(installation,code);
    return true;
  }
});

async function terminal(command) {
  if (installation?.status === 'running') return;
  if (installation) await closeTerminal();
  if (!shell) shell = await api('terminal/create', {});
  $('#terminal-title').textContent = 'Local terminal';
  $('#terminal-state').textContent = 'Project directory';
  delete $('#terminal-state').dataset.status;
  showTerminal(shell);
  await api('terminal/input',{id:shell.id, data:command + '\r'});
}

const installerTitles = {
  'native-tools':'Native tools', dependencies:'Toolchain', 'emulator-image':'Emulator image'
};

function attachInstaller(session) {
  // Installing tools changes what any previous check established.
  for (const mode of session.setup_action === 'emulator-image' ? [session.target] : targets) {
    invalidateChecks(mode);
  }
  installation = {...session,status:'running'};
  $('#terminal-title').textContent = installerTitles[session.setup_action];
  $('#terminal-state').textContent = 'Installing…';
  $('#terminal-state').dataset.status = 'running';
  $('#close-terminal').setAttribute('aria-label','Hide terminal');
  showTerminal(session);
  if (session.exit_code != null) {
    finishInstallation(installation,session.exit_code);
    return;
  }
  renderChecks();
  controls();
}

async function install(action) {
  if (installation?.status === 'running') return;
  if (installation) await closeTerminal();
  attachInstaller(await api('terminal/create',{setup_action:action,target}));
}

async function closeTerminal() {
  const session = installation || shell;
  if (installation?.status === 'running') {
    $('#show-terminal').hidden = false;
    $('#setup-terminal').hidden = true;
    return;
  }
  if (session) {
    await api('terminal/close',{id:session.id});
    shells.dispose(session.id);
    if (installation) {
      installation = null;
    }
    else shell = null;
  }
  $('#setup-terminal').hidden = true;
  $('#show-terminal').hidden = true;
  renderChecks();
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
  $('#advanced').innerHTML = details && details + '<div id="field-commands" class="actions"></div>';
  $('#advanced').hidden = !advanced || !details;
  $('#project-name').textContent = settings.project;
  renderChecks();
  controls();
}

const primaryGroup = mode => mode === 'native' ? 'Compiler' : 'Toolchain';
function idleChecks(mode) {
  return (settings.check_plan?.[mode] || []).map(stage => ({...stage,status:'idle',ready:null}));
}
function checkGroup(label) {
  if (label === 'NASA cFS source') return 'Source';
  if (target === 'native' && label === 'Ground Station Python packages') return 'Python';
  if (target === 'qemu' && /emulator|local ssh/i.test(label)) return 'Emulator';
  if (target === 'physical' && /^ssh$|^scp$|Board SSH/i.test(label)) return 'SSH';
  return primaryGroup(target);
}

function groupChecks() {
  const groups = target === 'native' ? [['Compiler','code'],['Python','terminal'],['Source','folder']] :
    [[primaryGroup(target),'cpu'], target === 'qemu' ? ['Emulator','cube'] : ['SSH','terminal'], ['Source','folder']];
  const results = checksByTarget.get(target)?.checks || idleChecks(target);
  return groups.map(([name,glyph]) => {
    const entries = results.filter(item => checkGroup(item.label) === name);
    let state = 'pending';
    if (entries.some(item => item.status === 'running')) state = 'running';
    else if (entries.some(item => item.status === 'failed')) state = 'missing';
    else if (entries.length && entries.every(item => item.status === 'passed')) state = 'ready';
    const installing = installation?.status === 'running' && installation.target === target;
    if (installing && name === (installation.setup_action === 'emulator-image' ? 'Emulator' : primaryGroup(target))) state = 'installing';
    return {name,glyph,entries,state};
  });
}

const groupStates = {ready:'Ready',missing:'Needs setup',pending:'Unchecked',running:'Checking',installing:'Installing'};
const rowStates = {idle:'Unchecked',pending:'Queued',running:'Checking…',passed:'Passed',failed:'Needs setup'};
const completed = entries => entries.filter(item => item.status === 'passed' || item.status === 'failed').length;

function renderGroupButtons(groups) {
  const container = $('#requirements');
  if (container.dataset.renderedTarget !== target) {
    container.innerHTML = groups.map(({name,glyph}) =>
      `<button type="button" class="requirement" data-group="${name}" aria-controls="verification"><span class="ring">${icon(glyph)}</span><span>${name}</span></button>`
    ).join('');
    container.dataset.renderedTarget = target;
  }
  groups.forEach(({name,state},index) => {
    const button = container.children[index];
    const label = name + ' · ' + groupStates[state];
    button.dataset.state = state;
    button.setAttribute('aria-label',label);
    button.setAttribute('aria-expanded',String(activeGroup === name));
    button.title = label;
  });
}

const stageTools = {
  git:['Git','git-branch'], cmake:['CMake','cmake'], make:['Make','build'],
  cc:['C compiler','code'], docker:['Docker CLI','container'], ssh:['SSH','terminal'], scp:['SCP','transfer'],
  'Ground Station Python packages':['Python packages','packages'], 'NASA cFS source':['NASA cFS','folder'],
  'Docker engine ≥ 23':['Docker Engine','settings'], 'Docker Buildx ≥ 0.10':['Buildx','layers'],
  'Emulator image':['Emulator image','cube'], 'Emulator SSH identity':['SSH key','key'],
  'Board SSH identity':['SSH key','key'], 'Local SSH port':['SSH port','network-port'],
  Installer:['Installer','arrow-down']
};
let openStage = '';
function showStageDetail() {
  const list = $('#checks');
  const stages = Array.from(list.children);
  const node = stages.find(n => n.dataset.label === openStage) ||
               stages.find(n => n.dataset.label === list.dataset.activeStage);
  const output = $('#pipeline-detail');
  output.hidden = !node;
  for (const sibling of stages) sibling.setAttribute('aria-expanded',String(sibling === node));
  if (!node) return;
  const {probe,detail,outcome} = node.dataset;
  const key = JSON.stringify([probe,detail,outcome]);
  if (key === output.dataset.content) return;
  output.dataset.content = key;
  output.innerHTML = '<code></code><span class="probe-detail"></span><small></small>';
  const command = output.querySelector('code');
  command.textContent = probe ? '$ ' + probe : '';
  command.hidden = !probe;
  output.querySelector('.probe-detail').textContent = detail;
  output.querySelector('small').textContent = outcome;
}
$('#checks').addEventListener('click',event=>{
  const label = event.target.closest('.check-row')?.dataset.label;
  if (!label) return;
  openStage = openStage === label ? '' : label;
  showStageDetail();
});
function renderRows(entries) {
  const list = $('#checks');
  const nodes = new Map(Array.from(list.children, row => [row.dataset.label,row]));
  for (let index = 0; index < entries.length; index++) {
    const item = entries[index];
    let row = nodes.get(item.label);
    if (!row) {
      row = document.createElement('button');
      row.type = 'button';
      row.className = 'requirement check-row';
      row.dataset.label = item.label;
      row.setAttribute('aria-controls','pipeline-detail');
      const [name,glyph] = stageTools[item.label] || [item.label,'terminal'];
      row.innerHTML = '<span class="ring check-mark" aria-hidden="true">'+icon(glyph)+'</span><strong></strong>';
      row.querySelector('strong').textContent = name;
    }
    if (list.children[index] !== row) list.insertBefore(row,list.children[index] || null);
    nodes.delete(item.label);
    row.dataset.status = item.status;
    row.dataset.state = {passed:'ready', failed:'missing', running:'running'}[item.status] || 'pending';
    const status = item.label === 'Installer' && item.status === 'running' ? 'Installing' : rowStates[item.status] || 'Not checked';
    row.dataset.probe = item.probe || '';
    row.dataset.detail = item.detail || status;
    row.dataset.outcome = [
      item.exit_code != null ? 'Exit ' + item.exit_code : '',
      item.duration_ms != null ? item.duration_ms + ' ms' : ''
    ].filter(Boolean).join(' · ');
    row.title = item.label + ' · ' + status;
    row.setAttribute('aria-label', row.title);
    if (item.status === 'running') row.setAttribute('aria-current','step');
    else row.removeAttribute('aria-current');
  }
  for (const row of nodes.values()) row.remove();
  showStageDetail();
}

function renderChecks() {
  const groups = groupChecks();
  const subtitles = {native:settings.host.os, qemu:'QEMU',physical:'SSH'};
  for (const button of $('#targets').querySelectorAll('button[data-target]')) {
    const key = button.dataset.target;
    button.setAttribute('aria-pressed', String(key === target));
    const caption = button.querySelector('small'), report = checksByTarget.get(key);
    if (installation?.status === 'running' && installation.target === key) {
      caption.dataset.status = 'running';
      caption.textContent = 'Installing…';
    } else if (report?.status === 'running') {
      caption.dataset.status = 'running';
      caption.textContent = report.checks.length ? completed(report.checks) + '/' + report.checks.length : 'Checking…';
    } else if (report?.status === 'complete') {
      caption.dataset.status = report.ready ? 'ready' : 'missing';
      const missing = report.checks.filter(check => !check.ready).length;
      caption.textContent = report.ready ? 'Ready' : missing + ' missing';
    } else {
      delete caption.dataset.status;
      caption.textContent = subtitles[key];
    }
  }
  renderGroupButtons(groups);
  const report = checksByTarget.get(target);
  const entries = (report?.checks || idleChecks(target)).filter(item => activeGroup === 'all' || checkGroup(item.label) === activeGroup);
  $('#verification').hidden = !activeGroup;
  const count = completed(entries);
  const checking = checkRequests.has(target);
  const title = activeGroup === 'all' ? 'Setup checks' : activeGroup;
  $('#check-status').textContent = checking && entries.length ? title + ' · ' + count + '/' + entries.length : title;
  const progress = $('#check-progress');
  progress.hidden = !activeGroup || !checking;
  progress.max = Math.max(1,entries.length);
  progress.value = count;
  if (!entries.length) {
    progress.removeAttribute('value');
    progress.removeAttribute('aria-valuetext');
  }
  else progress.setAttribute('aria-valuetext',count + ' of ' + entries.length + ' checked');
  if (report && report.status === 'complete') $('#check-status').title = (report.duration_ms / 1000).toFixed(1) + ' s';
  else $('#check-status').removeAttribute('title');
  $('#checks').dataset.activeStage = checking ? report?.activeStage || '' : '';
  renderRows(entries);
  const source = settings.source;
  $('.source-setup').hidden = settings.sources_ready && activeGroup !== 'Source';
  $('#source-state').textContent = ({installed:'Installed',ready:source.revision,missing:'Not installed',incomplete:'Submodules missing',occupied:'Move the existing cFS directory to install the official source.'})[source.state] || '';
  const clone = $('#clone-source');
  clone.hidden = !['missing','incomplete'].includes(source.state);
  clone.textContent = source.state === 'incomplete' ? 'Complete download' : 'Clone NASA cFS';
  renderCommands();
}

function commandButton(label, command, setupAction = '') {
  commands.set(label,{command, setupAction});
  return `<button type="button" data-command="${escapeHtml(label)}">${escapeHtml(label)}</button>`;
}
function renderCommands() {
  commands.clear();
  const rows = [], inline = [];
  const showing = name => activeGroup === name || activeGroup === 'all';
  if (target === 'native' && (showing('Compiler') || showing('Python')))
    rows.push(commandButton('Install native tools',null,'native-tools'));
  if (target !== 'native' && showing('Toolchain'))
    rows.push(commandButton('Install dependencies',null,'dependencies'));
  if (target === 'qemu') {
    inline.push(commandButton('Install emulator image',null,'emulator-image'),
      '<a class="command-link" href="/emulator-guide.html" target="_blank" rel="noopener">Image setup guide</a>');
  }
  if (target === 'physical') {
    for (const [key,label] of [['create_key','Create SSH key'],['authorize_key','Authorize SSH key'],['ssh','SSH terminal'],['authorize_service','Authorize cFS service']]) {
      if (settings.commands[key]) inline.push(commandButton(label,settings.commands[key]));
    }
    inline.push('<button type="button" data-job="probe">Test SSH</button>','<button type="button" data-job="connect">Prepare cFS service</button>',
      '<a class="command-link" href="https://www.raspberrypi.com/documentation/computers/getting-started.html#install-an-operating-system" target="_blank" rel="noopener">Install Raspberry Pi OS</a>',
      '<a class="command-link" href="https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh" target="_blank" rel="noopener">Enable SSH</a>');
  }
  for (const [selector,buttons] of [['#field-commands',inline],['#preparation',rows]]) {
    const area = $(selector);
    const html = buttons.join('');
    if (area && area.dataset.content !== html) {
      area.innerHTML = html;
      area.dataset.content = html;
    }
  }
}

async function save() {
  readForm();
  settings = await api('infrastructure', {
    target,build_jobs:settings.build_jobs,board:settings.board,os:settings.os,
    connection:settings.connection || {},emulator:settings.emulator
  });
  dirty = false;
  renderChecks();
}

function applySource(source, verifiedTarget) {
  if (settings.source.state !== source.state || settings.source.revision !== source.revision) {
    for (const mode of targets) {
      if (mode !== verifiedTarget && checksByTarget.get(mode)?.status === 'complete') checksByTarget.delete(mode);
    }
  }
  settings.source = source;
  settings.sources_ready = source.state === 'ready' || source.state === 'installed';
}
async function refreshSource() {
  const snapshot = await api('infrastructure?verify_source=1');
  applySource(snapshot.source);
  renderChecks();
  controls();
}

function invalidateChecks(mode) {
  checkRequests.get(mode)?.abort();
  checkRequests.delete(mode);
  checksByTarget.delete(mode);
}

async function runChecks(mode) {
  if (checkRequests.has(mode)) return;
  const checks = idleChecks(mode).map(stage => ({...stage,status:'pending'}));
  if (!checks.length) throw Error('Verification plan unavailable. Reload setup to retry.');
  const controller = new AbortController();
  const {signal} = controller;
  const report = {status:'running',checks,ready:null,activeStage:''};
  checksByTarget.set(mode,report);
  checkRequests.set(mode,controller);
  openStage = '';
  controls();
  try {
    for (const [index,stage] of checks.entries()) {
      if (signal.aborted) return;
      report.activeStage = stage.label;
      stage.status = 'running';
      renderChecks();
      const response = await request('infrastructure/check',{target:mode,label:stage.label},{signal});
      const result = await response.json();
      if (signal.aborted) return;
      if (result.label !== stage.label || !['passed','failed'].includes(result.status)) {
        throw Error('Unexpected verification result. Run the checks again.');
      }
      Object.assign(stage,result);
      if (result.source) applySource(result.source,mode);
      renderChecks();
      // Show the actual result immediately, then give the icon time to settle
      // before starting the next process. Probe durations come from the host.
      if (index < checks.length - 1 && !document.hidden) {
        await new Promise(resolve => setTimeout(resolve,350));
      }
    }
    report.status = 'complete';
    report.ready = checks.every(stage => stage.ready);
    report.duration_ms = checks.reduce((total,stage) => total + stage.duration_ms,0);
  } catch (error) {
    if (signal.aborted) return;
    report.status = 'interrupted';
    for (const stage of checks) {
      if (stage.status === 'running' || stage.status === 'pending') stage.status = 'idle';
    }
    throw error;
  } finally {
    if (checkRequests.get(mode) === controller) {
      report.activeStage = '';
      checkRequests.delete(mode);
      renderChecks();
      controls();
    }
  }
}

function verify() {
  if (!form.reportValidity()) return;
  const mode = target;
  perform(async () => {
    if (dirty) await save();
    runChecks(mode).catch(error => feedback(error.message,true));
  });
}

async function followJob(action, id) {
  const download = action === 'clone-cfs';
  $('#job-output').hidden = false;
  $('#job-title').textContent = download ? 'NASA cFS download' : action === 'probe' ? 'SSH connection' : 'cFS service preparation';
  $('#job-log').textContent = '';
  $('#job-state').textContent = 'Running';
  $('#board-report').textContent = '';
  while (true) {
    const current = (await api('jobs')).find(item => item.id === id);
    if (!current) throw Error('This operation has ended. Run it again to retry.');
    const log = $('#job-log');
    log.textContent = current.lines.join('\n');
    log.scrollTop = log.scrollHeight;
    $('#job-state').textContent = current.status;
    if (current.status === 'running') {
      await new Promise(resolve => setTimeout(resolve,700));
      continue;
    }
    if (download) await refreshSource();
    else settings = await api('infrastructure');
    if (current.status !== 'succeeded') throw Error(current.error || 'Operation failed. See the output for details.');
    const p = current.result;
    if (!download && p) {
      $('#board-report').textContent = [p.model,p.os,p.ready ? 'cFS service ready' : 'cFS service needs preparation',
        p.i2c?.length ? p.i2c.join(', ') : 'No I²C interfaces detected'].filter(Boolean).join(' · ');
    }
    return;
  }
}

async function startJob(action) {
  let options = {};
  if (action !== 'clone-cfs') {
    if (!form.elements.host.value.trim()) {
      form.elements.host.focus();
      throw Error('Enter the SSH host before testing the board.');
    }
    await save();
    options = {target:'physical',connection:settings.connection};
  }
  const result = await api('job',{action,options});
  await followJob(action,result.id);
}

$('#clone-source').addEventListener('click',() => perform(() => startJob('clone-cfs')));
$('#close-report').addEventListener('click',() => { $('#job-output').hidden = true; });
$('#close-terminal').addEventListener('click',() => perform(closeTerminal));
$('#show-terminal').addEventListener('click',() => {
  if (installation) showTerminal(installation);
});
$('#targets').addEventListener('click', event => {
  const key = event.target.closest('[data-target]')?.dataset.target;
  if (!key || key === target || busy) return;
  if (checkRequests.has(target)) invalidateChecks(target);
  readForm();
  target = key;
  dirty = true;
  activeGroup = primaryGroup(key);
  openStage = '';
  advanced = false;
  feedback();
  $('#job-output').hidden = true;
  renderFields();
});

function markDirty(event) {
  dirty = true;
  if (event.target.name !== 'build_jobs') {
    invalidateChecks(target);
    activeGroup = '';
    renderChecks();
  }
  controls();
}
form.addEventListener('input', markDirty);
form.addEventListener('change', event => {
  if (event.target.name === 'board') {
    readForm();
    renderFields();
    form.elements.board.focus();
  }
});
form.addEventListener('invalid', event => {
  if ($('#advanced').contains(event.target)) {
    advanced = true;
    $('#advanced').hidden = false;
    $('#advanced-toggle')?.setAttribute('aria-expanded','true');
  }
}, true);
form.addEventListener('click',event => {
  const button = event.target.closest('button');
  if (!button || busy) return;
  if (button.dataset.step) {
    const input = form.elements.build_jobs;
    if (Number(button.dataset.step) < 0) input.stepDown();
    else input.stepUp();
    input.dispatchEvent(new Event('input',{bubbles:true}));
  }
  if (button.id === 'advanced-toggle') {
    advanced = !advanced;
    $('#advanced').hidden = !advanced;
    button.setAttribute('aria-expanded', String(advanced));
  }
  if (button.dataset.group) {
    const name = button.dataset.group;
    activeGroup = activeGroup === name ? '' : name;
    openStage = '';
    renderChecks();
    document.querySelector(`[data-group="${name}"]`).focus();
  }
  if (button.id === 'close-checks') {
    const previous = activeGroup;
    activeGroup = '';
    renderChecks();
    (document.querySelector(`[data-group="${previous}"]`) || $('#check')).focus();
  }
  if (button.dataset.job && form.reportValidity()) perform(() => startJob(button.dataset.job));
  if (button.dataset.command && form.reportValidity()) perform(async () => {
    const label = button.dataset.command;
    if (dirty && settings.sources_ready) await save();
    const action = commands.get(label);
    if (!action) throw Error('Check the connection settings before running this command.');
    if (action.setupAction) await install(action.setupAction);
    else await terminal(action.command);
  });
});
$('#check').addEventListener('click',() => {
  if (!form.reportValidity()) return;
  activeGroup = 'all';
  renderChecks();
  verify();
});
form.addEventListener('submit',event => {
  event.preventDefault();
  perform(async () => {
    await refreshSource();
    if (!settings.sources_ready) throw Error('Complete the NASA cFS download before opening the workspace.');
    await save();
    location.href = '/studio';
  });
});

window.addEventListener('beforeunload', event => {
  if (dirty) { event.preventDefault(); event.returnValue = ''; }
});

(async () => {
  try {
    token = (await api('session')).token;
    settings = await api('infrastructure');
    const requested = new URLSearchParams(location.search).get('target');
    target = targets.includes(requested) ? requested : settings.target;
    dirty = target !== settings.target;
    activeGroup = primaryGroup(target);
    renderFields();
    const jobs = await api('jobs');
    const installer = jobs.find(j => j.setup_action && j.status === 'running');
    const download = jobs.find(j => j.action === 'clone-cfs' && j.status === 'running');
    if (installer) attachInstaller(installer);
    if (download) await perform(() => followJob('clone-cfs', download.id));
  } catch (error) {
    feedback(error.message,true);
    controls();
  }
})();
