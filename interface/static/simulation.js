import {icon} from './ui.js';

export function renderSimulationBoard(state,{esc}){
 const session=state.simulation,job=state.jobs.find(job=>job.action==='simulate'&&job.status==='running');
 const sensors=session?.settings.sensors||[],available=session?.available||[];
 return `<div class="signals-bench"><header><div>${icon('wave')}<strong>Synthetic sources</strong></div><span class="signals-state ${job?'running':''}">${job?'Sending':'Stopped'}</span></header><div class="signals-board"><div id="board-stage"></div></div><div class="signals-sources">${available.map(device=>{const settings=sensors.find(sensor=>sensor.device===device.id),sample=job?.samples?.devices?.find(sample=>sample.id===device.id);return `<button class="signals-source ${state.selectedDevice===device.id?'selected':''}" data-simulation-device="${esc(device.id)}"><span>${icon('cpu')}<strong>${esc(device.model)}</strong><i>${settings?.enabled?(job?'Sending':'Ready'):'Not selected'}</i></span><small>${esc(device.id)}</small><div data-signal-values="${esc(device.id)}">${sample?Object.entries(sample.values).map(([name,value])=>`<span>${esc(name)} <b>${Number(value).toFixed(3)} ${esc(sample.units[name])}</b></span>`).join(''):'—'}</div></button>`;}).join('')||'<p>Add a sensor in Hardware</p>'}</div></div>`;
}

export function renderSimulationSettings(state,{esc}){
 const session=state.simulation,job=state.jobs.find(job=>job.action==='simulate'&&job.status==='running'),busy=!!job||state.simulationSaving;
 if(!session)return `<p class="signals-error">${esc(state.simulationError||'Loading signals…')}</p>`;
 const selected=session.available.find(device=>device.id===state.selectedDevice)||session.available[0];
 const sensor=session.settings.sensors.find(sensor=>sensor.device===selected?.id);
 const absent=session.available.filter(device=>!session.settings.sensors.some(sensor=>sensor.device===device.id));
 const number=(field,label,settings,property,extra='')=>`<label>${label}<input type="number" step="any" required name="${field}" data-signal-property="${esc(property)}" value="${esc(settings[field])}" ${extra}></label>`;
 const options=[['script','Python sample()'],['constant','Constant'],['sine','Sine'],['ramp','Ramp'],['custom','Custom Python function']];
 return `<form id="simulation-form"><fieldset ${busy?'disabled':''}><div class="signals-session-row"><label>Update interval · s<input type="number" step="any" min="0.001" name="interval" value="${esc(session.settings.interval)}"></label>${absent.length?`<label>Add sensor<select id="simulation-add"><option value="">Choose sensor…</option>${absent.map(device=>`<option value="${esc(device.id)}">${esc(device.id)}</option>`).join('')}</select></label>`:''}</div><div class="signals-selection">${session.settings.sensors.map(item=>`<div class="${item.device===selected?.id?'selected':''}"><input type="checkbox" data-simulation-enable="${esc(item.device)}" aria-label="Enable ${esc(item.device)}" ${item.enabled?'checked':''}><button type="button" data-simulation-device="${esc(item.device)}">${esc(item.device)}</button><button type="button" data-simulation-remove="${esc(item.device)}" aria-label="Remove ${esc(item.device)} from synthetic session" title="Remove from synthetic session">${icon('close')}</button></div>`).join('')}</div>${selected?`<div class="signals-device-heading"><strong>${esc(selected.model)}</strong><button type="button" class="signal-source-file" data-simulation-source="${esc(selected.script)}">${icon('code')}${esc(selected.script)}</button></div>${sensor?Object.entries(sensor.signals).map(([property,settings])=>{const prop=selected.properties[property];return `<section class="signal-fields"><header><strong>${esc(property)}</strong><span>${esc(prop.unit)}</span></header><div class="signal-inputs">${number('initial','Initial · '+esc(prop.unit),settings,property,`min="${prop.min}" max="${prop.max}"`)}<label>Function<select name="function" data-signal-property="${esc(property)}">${options.map(([value,label])=>`<option value="${value}" ${settings.function===value?'selected':''} ${value==='custom'&&!selected.functions.length?'disabled':''}>${label}</option>`).join('')}</select></label>${settings.function==='sine'?number('amplitude','Amplitude · '+esc(prop.unit),settings,property)+number('period','Period · s',settings,property,'min="0.001"'):settings.function==='ramp'?number('slope','Rate · '+esc(prop.unit)+'/s',settings,property):settings.function==='custom'?`<label>Python function<select name="custom" data-signal-property="${esc(property)}">${selected.functions.map(fn=>`<option value="${esc(fn.name)}" ${fn.name===settings.custom?'selected':''}>${esc(fn.name)}</option>`).join('')}</select></label>`:''}</div>${settings.function==='script'?`<button type="button" class="signal-code-link" data-simulation-source="${esc(selected.script)}" data-simulation-function="sample">${icon('code')}Edit sample()</button>`:settings.function==='custom'?`<button type="button" class="signal-code-link" data-simulation-source="${esc(selected.script)}" data-simulation-function="${esc(settings.custom)}">${icon('code')}Edit ${esc(settings.custom)}()</button>`:''}${['constant','sine','ramp'].includes(settings.function)?preview(settings,esc):''}</section>`;}).join(''):`<button class="signals-add-selected" type="button" data-simulation-add="${esc(selected.id)}">${icon('plus')}Use this sensor</button>`}`:`<div class="signals-empty"><p>No sensors configured.</p><button type="button" data-view="bench">${icon('plus')}Add hardware</button><p>Open a Python model to edit or test its waveform.</p>${Object.entries(state.workspace?.simulation?.scripts||{}).map(([model,path])=>`<button type="button" data-simulation-source="${esc(path)}">${icon('code')}${esc(model)}.py</button>`).join('')}</div>`}</fieldset>${state.simulationError?`<p class="signals-error" role="alert">${esc(state.simulationError)}</p>`:''}</form>`;
}

function preview(settings,esc){
 const duration=settings.function==='sine'?settings.period:10;
 const values=Array.from({length:81},(_,index)=>{const time=index/80*duration;return settings.initial+(settings.function==='sine'?settings.amplitude*Math.sin(2*Math.PI*time/settings.period):settings.function==='ramp'?settings.slope*time:0);});
 const low=Math.min(...values),high=Math.max(...values),range=high-low||1;
 const points=values.map((value,index)=>`${index*4},${56-(value-low)/range*40}`).join(' ');
 return `<div class="signal-preview"><svg viewBox="0 0 320 72" role="img" aria-label="Waveform preview"><path d="M0 56H320"/><polyline points="${points}"/></svg><span>0 s</span><span>${esc(duration)} s</span></div>`;
}

export function updateSignalValues(state){
 const job=state.jobs.find(job=>job.action==='simulate'&&job.status==='running');
 for(const element of document.querySelectorAll('[data-signal-values]')){
  const sample=job?.samples?.devices?.find(sample=>sample.id===element.dataset.signalValues);
  element.replaceChildren();
  if(!sample){element.textContent='—';continue;}
  for(const [name,value] of Object.entries(sample.values)){
   const row=document.createElement('span'),number=document.createElement('b');
   row.textContent=name+' ';number.textContent=Number(value).toFixed(3)+' '+sample.units[name];row.append(number);element.append(row);
  }
 }
}
