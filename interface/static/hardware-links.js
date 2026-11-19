// The board advertises buses. Only the project's selected buses and device bindings are drawn.
import {icon} from './ui.js';

export function deviceReaders(workspace, deviceId) {
  return workspace.project.apps.flatMap(app => Object.entries(app.sensors)
    .filter(([, id]) => id === deviceId).map(([name]) => ({app:app.name, name})));
}

function readerSource(workspace, reader) {
  return workspace.apps.find(app => app.name===reader.app)?.locations?.find(item => item.id==='sensor.'+reader.name+'.read');
}

export function assemblyProgress(state, esc) {
  const w=state.workspace, devices=w.project.devices, buses=Object.values(w.catalog.buses);
  const chosen=devices.find(d=>d.id===state.inspected) || devices.find(d=>d.id===state.selectedDevice);
  const unlinked=devices.filter(d=>!deviceReaders(w,d.id).length);
  const device=unlinked.find(d=>d.id===chosen?.id) || unlinked[0] || chosen || devices[0];
  const stage=!buses.length?0:!devices.length?1:unlinked.length?2:3;
  const progress=['Bus','Sensor','HAL reader','Flight test'].map((label,i)=>{
    const status=i<stage?'done':i===stage?'current':'pending';
    return `<li class="${status}" ${i===stage?'aria-current="step"':''}><i>${i<stage?icon('check'):i+1}</i><span>${label}</span></li>`;
  }).join('');
  let action, caption='', glyph, attrs, sourceAction='';
  if(stage===0) { action='Add bus'; glyph='plus'; attrs='data-add-bus'; }
  else if(stage===1) {
    action='Connect sensor'; glyph='plus'; attrs='data-create="device"'; caption=buses.map(bus=>bus.label||bus.device).join(' · ');
  } else if(stage===2) {
    const compatible=w.catalog.models[device.model]?.cfs_driver;
    action=compatible?'Link HAL':'Inspect sensor';
    glyph=compatible?'link':'circuit';
    attrs=compatible?`data-link-hal="${esc(device.id)}"`:`data-inspect="${esc(device.id)}"`;
    caption=device.name+' · 0x'+device.address.toString(16);
  } else {
    const reader=deviceReaders(w,device.id)[0], path=readerSource(w,reader);
    caption=reader.app+' / '+reader.name;
    if(path)sourceAction=`<button class="assembly-source" data-hardware-source="${esc(path.path)}" data-line="${path.line}">${icon('code')} Open reader</button>`;
    const physical=state.target==='physical';
    const qemu=state.hardware?.qemu;
    const running=physical?state.hardware?.physical?.last_probe?.flight_running:qemu?.flight_running;
    const online=physical?state.hardware?.physical?.last_probe?.connected:qemu?.linux_ready;
    if(!w.builds?.[state.target]?.current) {action='Build cFS';glyph='build';attrs='data-workbench-job="build"';}
    else if(!online) {
      const needsSetup=!physical&&state.hardware&&(!state.hardware.docker?.available||!qemu?.ssh_configured||qemu.image_ready===false);
      action=physical?'Connect board':needsSetup?'Set up emulator':qemu?.can_retry_boot?'Retry emulator connection':'Start emulator';
      glyph=physical?'antenna':'power';attrs='data-workbench-job="boot"';
    }
    else if(!running) {action='Run cFS';glyph='play';attrs='data-workbench-job="run"';}
    else {action='Test in Ground Station';glyph='antenna';attrs=`data-workbench-ground="${esc(reader.app)}"`;}
  }
  return `<section class="assembly-progress" aria-label="Hardware setup" data-assembly-stage="${stage}"><ol aria-label="Assembly steps">${progress}</ol>
    <div class="assembly-next">${caption?`<code title="${esc(caption)}">${esc(caption)}</code>`:''}${sourceAction}<button class="assembly-primary" ${attrs}>${icon(glyph)} ${action}</button></div></section>`;
}

export function busInventory(workspace, esc) {
  const {buses, available_buses:available} = workspace.catalog;
  const canAdd = Object.keys(available).some(id => !Object.hasOwn(buses,id));
  const rows = Object.entries(buses).map(([id,spec]) => {
    const devices = workspace.project.devices.filter(device => device.bus === id);
    const connector = Object.entries(spec.sensor_pins || {}).filter(([role]) => !['VCC','GND'].includes(role))
      .map(([role,pins]) => role + ' ' + pins.join('/')).join(' · ');
    return `<div class="hardware-port"><div>${icon('link')}<div><strong>${esc(spec.label || id)}</strong><small>${esc(spec.device)} · ${esc(connector)}</small></div>
      <button type="button" class="icon-button" data-remove-bus="${esc(id)}" aria-label="Remove ${esc(spec.label || id)}" title="${devices.length?'Disconnect sensors first':'Remove bus'}" ${devices.length?'disabled':''}>${icon('trash')}</button></div>
      <button class="port-add" data-create="device" data-preferred-bus="${esc(id)}">${icon('plus')} Connect sensor</button>
      ${devices.map(device => `<button data-view="bench" data-inspect="${esc(device.id)}" data-device="${esc(device.id)}">${icon('circuit')}${esc(device.name)}<small>${deviceReaders(workspace,device.id).length?'HAL linked':'No HAL'}</small></button>`).join('')}</div>`;
  }).join('');
  return `<section class="hardware-connectors"><div class="wire-heading"><b>Buses</b><small>${Object.keys(buses).length}</small>${canAdd?'<button data-add-bus>'+icon('plus')+' Add bus</button>':''}</div>${rows}</section>`;
}

export function halDetails(workspace, device, esc) {
  const readers = deviceReaders(workspace,device.id);
  const canLink = workspace.catalog.models[device.model].cfs_driver;
  const rows = readers.map(reader => {
    const source = readerSource(workspace,reader);
    const name = esc(reader.app) + ' / ' + esc(reader.name);
    return source ? `<button data-hardware-source="${esc(source.path)}" data-line="${source.line}">${icon('code')}${name}</button>` : `<code>${name}</code>`;
  }).join('');
  return `<section class="sensor-hal" data-linked="${Boolean(readers.length)}"><div class="wire-heading">
    <i></i><b>${readers.length?'HAL linked':'No HAL linked'}</b>
    ${canLink && !readers.length?`<button data-link-hal="${esc(device.id)}">${icon('link')} Link HAL</button>`:''}</div>${rows}</section>`;
}

export function busDialog(workspace, {dialog, esc, save}) {
  const options = Object.entries(workspace.catalog.available_buses)
    .filter(([id]) => !Object.hasOwn(workspace.catalog.buses,id));
  if (!options.length) return;
  const list = options.map(([id,spec],index) => {
    const pins = Object.entries(spec.sensor_pins || {}).filter(([key]) => !['VCC','GND'].includes(key))
      .map(([role,choices]) => `<span>${esc(role)} <b>${esc(choices.join('/'))}</b></span>`).join('');
    return `<label class="bus-choice"><input required type="radio" name="bus" value="${esc(id)}" ${index?'':'checked'}>
      <span><strong>${esc(spec.label || id)}</strong><code>${esc(spec.device)}</code></span><span class="bus-pins">${pins}</span></label>`;
  }).join('');
  dialog('Add bus', list, values => save('add-bus', {bus:values.bus}), 'Add bus');
}

export function halDialog(workspace, deviceId, {dialog, esc, save}) {
  const device = workspace.project.devices.find(item => item.id===deviceId);
  if (!device || !workspace.catalog.models[device.model]?.cfs_driver) return;
  const apps = workspace.project.apps.filter(app => !Object.values(app.sensors).includes(deviceId));
  let base = deviceId.slice(0,15).replace(/_$/,'') + '_app', candidate = base, suffix = 2;
  const reserved = new Set([...workspace.apps, ...workspace.libraries].map(module => module.name));
  while (reserved.has(candidate)) {
    const end = String(suffix++); candidate = base.slice(0,19-end.length) + end;
  }
  const names = apps.map(app => `<option value="${esc(app.name)}">${esc(app.name)}</option>`).join('');
  const inputs = 'required maxlength="19" pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*" autocomplete="off"';
  dialog('Link sensor HAL',`<div class="hal-device">${icon('circuit')} <strong>${esc(device.name)}</strong><code>${esc(device.bus)} · 0x${device.address.toString(16)}</code></div>
     <label>Mission app<select name="target">${names}<option value="">Create mission app…</option></select></label>
     <label class="hal-app-name">App name<input name="app" value="${esc(candidate)}" ${inputs}></label>
     <label>Reader name<input name="reader" value="${esc(device.id)}" ${inputs}></label>`, values =>
       save('link-hal',{app:values.target || values.app, new_app:!values.target, name:values.reader, device:deviceId}), 'Link HAL');
  const target = document.querySelector('#dialog-body [name=target]');
  const newApp = document.querySelector('#dialog-body .hal-app-name');
  const update = () => {
    newApp.hidden = Boolean(target.value);
    newApp.querySelector('input').disabled = newApp.hidden;
  };
  target.addEventListener('change',update);
  update();
}
