import {targetDrawing} from './target-drawing.js';
import {api, checkFrames, readJourney} from './api.js';
import {navigate, pageStep, redirectForStep, stepUrl} from './router.js';
import {icon} from './ui.js';
import {mountShells} from './shell.js';
import {groupsByTarget, groupFor, repairFor, nextRepair} from './setup-plan.js';

for (const art of document.querySelectorAll('[data-art]')) art.innerHTML = targetDrawing(art.dataset.art);
const $ = selector => document.querySelector(selector);
const form = $('#infrastructure-form');
const settingsForm = $('#target-settings-form');
const settingsDialog = $('#settings-sheet');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const boardVisit = pageStep() === 'board';
const checksByTarget = new Map();
const checkRequests = new Map();
let settings = null, target = null, busy = false, dirty = false;
let activeGroup = '', installation = null, selectedVersion = 0;
let verification = null;
function feedback(message = '', error = false) {
  $('#feedback').textContent = message;
  $('#feedback').classList.toggle('error', error);
}

function selectField(name, label, options, selected) {
  const choices = options.map(([value,text]) =>
    `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(text)}</option>`
  ).join('');
  return `<select name="${name}" aria-label="${label}" required>${choices}</select>`;
}
function profileOptions(board = settings.board, os = settings.os) {
  const profiles = settings.profiles.filter(p => p.targets.includes(target));
  const boards = [...new Map(profiles.map(p => [p.board,p.board_label]))];
  const selectedBoard = boards.some(([id]) => id === board) ? board : boards[0]?.[0];
  const systems = profiles.filter(p => p.board === selectedBoard).map(p => [p.os,p.os_label]);
  const selectedOS = systems.some(([id]) => id === os) ? os : systems[0]?.[0];
  return {boards,systems,board:selectedBoard,os:selectedOS};
}

function profileFields(labeled = false) {
  const {boards, systems, board, os} = profileOptions();
  const boardField = selectField('board','Board',boards,board);
  const osField = selectField('os','Operating system',systems,os);
  return labeled ? '<label>Board' + boardField + '</label><label>Operating system' + osField + '</label>' : boardField + osField;
}

function connectionButton(field, glyph, label, value) {
  return `<button type="button" class="connection-value" data-setting="${field}" aria-haspopup="dialog" aria-controls="settings-sheet" aria-label="Edit ${label}: ${escapeHtml(value || 'Not set')}">${icon(glyph)}<span><small>${label}</small><strong>${escapeHtml(value || 'Not set')}</strong></span></button>`;
}

function renderFields() {
  if (target) document.body.dataset.flightTarget = target;
  else delete document.body.dataset.flightTarget;
  $('.setup-panel').hidden = !target;
  $('.setup-footer').hidden = !target;
  if (!target) {
    $('#configuration').replaceChildren();
    controls();
    return;
  }
  const configure = `<button type="button" class="settings-button" id="advanced-toggle" aria-haspopup="dialog" aria-controls="settings-sheet">${icon('sliders')}Configure</button>`;
  let fields;
  if (target === 'native') {
    fields = `<div class="stepper-field"><label for="build-jobs">Jobs</label><div class="stepper">
      <button type="button" data-step="-1" aria-label="Fewer build jobs">−</button>
      <input id="build-jobs" title="Parallel build jobs" aria-label="Parallel build jobs" name="build_jobs" type="number" value="${settings.build_jobs}" min="1" max="64" required>
      <button type="button" data-step="1" aria-label="More build jobs">+</button></div></div>`;
  } else if (target === 'qemu') {
    fields = profileFields() + configure;
  } else {
    const connection = settings.connection || {};
    fields = connectionButton('host','antenna','Host',connection.host) +
      connectionButton('user','terminal','SSH user',connection.user || (connection.host ? 'SSH config' : '')) + configure;
  }
  $('#configuration').innerHTML = fields;
  $('#project-name').textContent = settings.project;
  controls();
}

function updateOperatingSystems(fields) {
  const {systems, os} = profileOptions(fields.board.value,fields.os.value);
  fields.os.replaceChildren(...systems.map(([value,label]) => new Option(label,value,false,value === os)));
}

function reportFor(mode) {
  if (!checksByTarget.has(mode)) {
    checksByTarget.set(mode,(settings.check_plan[mode]||[]).map(entry => {
      const result = settings.check_results[mode]?.[entry.label];
      return {...entry, status:result == null ? 'pending' : result ? 'passed' : 'failed'};
    }));
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
  if (!settings || !target) return;
  const plans = groups(target);
  const checking = checkRequests.has(target);
  const missing = plans.filter(x => x.state === 'missing').length;
  const fixing = installation?.target === target && installation.status === 'running';
  const ready = !dirty && !checking && !busy && plans.every(x => x.state === 'ready');
  const probe = reportFor(target).find(row => row.status === 'running');
  const note = fixing ? 'Installing ' + installerLabels[installation.setup_action] :
    probe ? 'Checking ' + probe.label : missing ? 'Click + to fix' : '';
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
      button.querySelector('.tool-glyph').innerHTML = icon(group.glyph);
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
  if (boardVisit) {
    $('#enter').textContent = settings.target === 'physical' ? 'Build cFS' : 'Use this board';
    if (!ready && !checking && !missing) {
      install.hidden = false;
      install.textContent = 'Check connection';
    }
  }
  details.textContent = details.dataset.input === 'true' ? 'Input required' : 'Details';
}

function controls() {
  for (const card of document.querySelectorAll('.target-option')) {
    card.disabled = !settings || busy || boardVisit && card.dataset.target !== 'physical';
    card.setAttribute('aria-pressed', String(card.dataset.target === target));
  }
  for (const field of form.querySelectorAll('#configuration :is(input,select,button)')) {
    field.disabled = busy;
  }
  $('#inspect').disabled = !settings;
  $('#save-state').textContent = dirty ? 'Unsaved' : '';
  $('#save-state').dataset.state = dirty ? 'dirty' : '';
  renderChecks();
}
async function saveForm(changes = {}) {
  const mode = target, version = selectedVersion;
  const {board, os, ...values} = changes;
  if (board !== undefined && (board !== settings.board || os !== settings.os)) {
    await api('mission/profile', {board, os});
  }
  if (mode === 'native') values.build_jobs = Number(form.elements.build_jobs.value);
  if (mode === 'qemu' && !values.emulator) values.emulator = settings.emulator;
  if (mode === 'physical' && !values.connection) values.connection = settings.connection || {};
  const next = await api('infrastructure', {target:mode, ...values});
  if (version === selectedVersion) {
    settings = next;
    dirty = false;
  }
}

function abortChecks(mode) {
  checkRequests.get(mode)?.abort();
  checkRequests.delete(mode);
}
async function runChecks() {
  if (!target || !settings || !form.reportValidity()) return;
  const mode = target, version = selectedVersion;
  abortChecks(mode);
  const controller = new AbortController();
  checkRequests.set(mode, controller);
  controls();
  feedback();
  let complete = false;
  try {
    for await (const frame of checkFrames(mode, controller.signal)) {
      if (controller.signal.aborted || version !== selectedVersion) return;
      checksByTarget.set(mode, frame.checks);
      const source = frame.checks.find(row => row.source)?.source;
      if (source) Object.assign(settings, {source, sources_ready:source.state === 'ready'});
      complete = frame.status === 'complete';
      renderChecks();
    }
    if (!complete) throw Error('Setup checks interrupted');
    window.dispatchEvent(new Event('flight:updated'));
    return true;
  } catch (error) {
    if (!controller.signal.aborted) feedback(error.message, true);
  } finally {
    if (checkRequests.get(mode) === controller) {
      checkRequests.delete(mode);
      controls();
    }
  }
}
function verify() {
  verification = runChecks();
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

async function followInstaller(session, groupName, recheck = true) {
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
  settings = await api('infrastructure');
  if (!recheck) {
    checksByTarget.delete(target);
    controls();
    return success;
  }
  const checked = await verify();
  if (!success) feedback(installerLabels[session.setup_action] + ' · exit ' + installation.exit_code, true);
  return success && checked;
}

function openSettings(field) {
  if ($('#verification').open) $('#verification').close();
  const connection = settings.connection || {};
  $('#settings-title').textContent = target === 'physical' ? 'Board settings' : 'Emulator settings';
  $('#settings-error').textContent = '';
  $('#advanced').innerHTML = target === 'physical' ? `
    <div class="fields">
      ${profileFields(true)}
      <label>Host or SSH alias<input name="host" required value="${escapeHtml(connection.host)}" list="ssh-hosts" autocomplete="off" spellcheck="false"></label>
      <label>SSH user<input name="user" value="${escapeHtml(connection.user)}" placeholder="From SSH config" autocomplete="off" spellcheck="false"></label>
      <label>SSH port<input name="port" type="number" min="1" max="65535" required value="${connection.port || 22}"></label>
      <label>SSH private key<input name="identity_file" value="${escapeHtml(connection.identity_file)}" placeholder="From SSH config" list="ssh-keys" spellcheck="false"></label>
    </div>
    <datalist id="ssh-hosts">${settings.ssh_hosts.map(h => `<option value="${escapeHtml(h.host)}">`).join('')}</datalist>
    <datalist id="ssh-keys">${settings.ssh_keys.map(k => `<option value="${escapeHtml(k)}">`).join('')}</datalist>` : `
    <div class="fields emulator-fields">
      <label>Local SSH port<input name="ssh_port" type="number" required min="1024" max="65535" value="${settings.emulator.ssh_port}"></label>
      <label>Emulator image<input name="image" required value="${escapeHtml(settings.emulator.image)}" spellcheck="false"></label>
    </div>`;
  showDialog('#settings-sheet');
  settingsForm.elements[field || (target === 'physical' ? 'host' : 'ssh_port')].focus();
}

settingsForm.addEventListener('change', event => {
  if (event.target.name === 'board') updateOperatingSystems(settingsForm.elements);
});
$('#settings-cancel').addEventListener('click', () => settingsDialog.close());
settingsDialog.addEventListener('cancel', event => {
  if (settingsDialog.getAttribute('aria-busy') === 'true') event.preventDefault();
});
settingsForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const f = settingsForm.elements;
  const changes = target === 'physical' ? {board:f.board.value, os:f.os.value,
    connection:{host:f.host.value.trim(), user:f.user.value.trim(), port:Number(f.port.value),
      identity_file:f.identity_file.value.trim(), directory:settings.connection?.directory || 'cfs-arm64'}} :
    {emulator:{ssh_port:Number(f.ssh_port.value),image:f.image.value.trim()}};
  abortChecks(target);
  selectedVersion++;
  busy = true;
  controls();
  settingsDialog.setAttribute('aria-busy','true');
  for (const control of settingsDialog.querySelectorAll('button,select,input')) control.disabled = true;
  let saved = false;
  try {
    await saveForm(changes);
    checksByTarget.delete(target);
    settingsDialog.close();
    renderFields();
    saved = true;
  } catch (error) {
    $('#settings-error').textContent = error.message;
  } finally {
    busy = false;
    settingsDialog.removeAttribute('aria-busy');
    for (const control of settingsDialog.querySelectorAll('button,select,input')) control.disabled = false;
    controls();
  }
  if (saved) {
    $('#advanced-toggle').focus({preventScroll:true});
    await verify();
  }
});

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
      if (action === 'settings' || (!settings.connection?.host && ['board-key','board-service'].includes(action))) {
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
$('#targets').addEventListener('click', async event => {
  const mode = event.target.closest('[data-target]')?.dataset.target;
  if (!mode || !settings || busy || boardVisit && mode !== 'physical') return;
  abortChecks(target);
  selectedVersion++;
  busy = true;
  controls();
  try {
    if (!boardVisit) {
      const choice = await api('hardware/target', {target:mode});
      settings.target = choice.target;
      settings.target_saved = true;
    }
    dirty = false;
    target = mode;
    checksByTarget.delete(mode);
    renderFields();
  } catch (error) {
    showError(error);
    return;
  } finally {
    busy = false;
    controls();
  }
  await verify();
});
$('#install').addEventListener('click', () => {
  if (boardVisit && $('#install').textContent === 'Check connection') verify().catch(showError);
  else installRequirements().catch(showError);
});
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
    if (event.target !== dialog || dialog.getAttribute('aria-busy') === 'true') return;
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
  if (button.id === 'advanced-toggle' || button.dataset.setting) openSettings(button.dataset.setting);
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
form.addEventListener('change', async event => {
  if (!form.reportValidity()) return;
  dirty = true;
  if (event.target.name === 'board') updateOperatingSystems(form.elements);
  const fields = form.elements;
  const profile = target === 'qemu' ? {board:fields.board.value, os:fields.os.value} : {};
  busy = true;
  controls();
  try {
    await saveForm(profile);
  } catch (error) {
    showError(error);
    return;
  } finally {
    busy = false;
    controls();
  }
  await verify();
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  if ($('#enter').disabled || $('#enter').hidden) return;
  if (!boardVisit) {
    navigate(stepUrl('boot', location, target));
    return;
  }
  try {
    if (settings.target !== 'physical') {
      await api('hardware/target', {target:'physical', use_board:true});
      settings.target = 'physical';
      controls();
    } else {
      await api('job', {action:'build', options:{target:'physical'}});
    }
  } catch (error) {showError(error);}
});
(async () => {
  settings = await api('infrastructure');
  if (boardVisit) {
    const state = await readJourney(null, true);
    const redirect = redirectForStep('board', state);
    if (redirect) {navigate(redirect, true); return;}
  }
  target = boardVisit ? 'physical' : settings.target;
  const jobs = await api('jobs');
  const running = jobs.find(job => job.setup_action && job.status === 'running');
  if (running) {
    target = running.target;
    busy = true;
    renderFields();
    const row = reportFor(target).find(item => repairFor(target,item) === running.setup_action);
    try { await followInstaller(running, row && groupFor(target,row.label), false); }
    finally { busy = false; controls(); }
  } else {
    renderFields();
  }
})().catch(showError);
