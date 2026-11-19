import {icon} from './ui.js';
import {orbitCard, orbitControls, orbitData, orbitIllumination, orbitPoint, orbitSubtitle, orbitToolbar, orbitalTime} from './orbit-preview.js';

const seriesSelection=new Map();
const readings=new Map();
let currentRun;
const colors=['#d4b48a','#7cb4f0','#68d4b1','#c3a6ff','#df947d'];
const identity=(item,esc)=>esc(item.model)+' · 0x'+Number(item.address).toString(16);
const formatted=n=>Number.isFinite(n)?Number(n.toFixed(2)).toString():'—';

function sensorCharts(sensor,device) {
  const byUnit=new Map();
  for(const [key,property] of Object.entries(device.properties)){
    const channels=byUnit.get(property.unit) || [];
    channels.push(key);byUnit.set(property.unit,channels);
  }
  return Array.from(byUnit,([unit,keys])=>({sensor,device,unit,keys}));
}
function chartHtml({sensor,device,unit,keys},esc){
  const id=device.id+'|'+unit, chosen=seriesSelection.get(id)||'';
  return `<section class="signal-plot" data-series="${esc(id)}"><header><div class="series-title"><strong>${esc(device.name||device.id)}</strong><small>${identity(device,esc)}</small></div><small data-series-status></small>${keys.some(k=>['script','custom'].includes(sensor.signals[k]?.function))?`<button class="series-model-test" data-signal-preview-device="${esc(device.id)}" title="Run the Python model locally">Test Python</button>`:''}<div class="series-right">${keys.length>1?`<div class="series-channels" role="group" aria-label="Chart channels">${['',...keys].map(key=>`<button type="button" data-series-channel="${esc(key)}" data-series-id="${esc(id)}" aria-pressed="${chosen===key}" title="${esc(key||'All channels')}">${esc(key?key.replace(/.*[-_]/,''):'all')}</button>`).join('')}</div>`:''}<output></output></div></header><canvas class="wave-chart" data-device-id="${esc(sensor.device)}" data-unit="${esc(unit)}" role="img" aria-label="${esc(sensor.device+' waveform in '+unit)}"></canvas><div class="plot-empty" hidden></div></section>`;
}

export function renderSimulationBoard(state,{esc}){
  const active=state.jobs.find(job=>['simulate','simulate-preview'].includes(job.action)&&job.status==='running');
  const tab=state.signalView||'signals', session=state.simulation, available=session?.available||[], sensors=session?.settings.sensors||[];
  const selected=sensors.filter(item=>item.enabled), device=available.find(item=>item.id===state.selectedDevice);
  const sensorList=available.map(item=>{
    const sensor=sensors.find(s=>s.device===item.id);
    return `<div class="signal-entry" data-selected="${item.id===state.selectedDevice}"><input type="checkbox" data-simulation-enable="${esc(item.id)}" aria-label="Include ${esc(item.id)} in session" ${sensor?.enabled?'checked':''} ${active||state.simulationSaving?'disabled':''}><button class="signal-pick" data-signal-device="${esc(item.id)}" aria-pressed="${item.id===state.selectedDevice}"><span>${esc(item.name||item.id)}<small>${identity(item,esc)}</small></span><output data-sensor-reading="${esc(item.id)}"></output></button></div>`;
  }).join('');
  const reason=state.target!=='qemu'?'Emulator required':!state.hardware?.qemu?.running?'Emulator stopped':!selected.length?'No sensors selected':'';
  const action=active?`<button data-board-stop="${active.action}">Stop</button>`:`<button data-signal-begin ${reason?'disabled':''} title="${reason||'Send samples to QEMU'}">Start</button>`;
  let content;
  if(tab==='signals'){
    const charts=available.flatMap(item=>sensorCharts(sensors.find(s=>s.device===item.id)||{...item.defaults,enabled:false},item));
    const page=Math.min(state.signalPage||0,Math.max(0,Math.ceil(charts.length/2)-1));
    const pagination=charts.length>2?`<nav class="series-pages" aria-label="Signal charts"><button data-signal-page="${page-1}" aria-label="Previous charts" ${page?'':'disabled'}>‹</button><span>${page+1} / ${Math.ceil(charts.length/2)}</span><button data-signal-page="${page+1}" aria-label="Next charts" ${(page+1)*2>=charts.length?'disabled':''}>›</button></nav>`:'';
    const count=active?.device?'sensor · '+active.device:selected.length+' sensor'+(selected.length===1?'':'s')+' enabled';
    content=`<div class="signal-session-state" data-active="${Boolean(active)}"><i></i><strong>${active?.action==='simulate'?(active.samples?.devices?.length?'Sending to QEMU':'Starting QEMU session'):active?'Local test running':'Synthetic data is off'}</strong><small>${esc(active?count:[count,reason].filter(Boolean).join(' · '))}</small>${action}</div>${orbitCard()}${charts.length?`<div class="series-grid">${charts.slice(page*2,page*2+2).map(chart=>chartHtml(chart,esc)).join('')}</div>`:''}${pagination}`;
  }else if(tab==='python'){
    content=`<section class="signal-summary"><h3>Signal sources</h3>${(session?.sources||[]).map(path=>`<button class="signal-file" data-signal-source="${esc(path)}">${icon('code')}<code>${esc(path)}</code>${icon('arrow-up-right')}</button>`).join('')}</section>`;
  }else if(tab==='qemu'){
    content=`<section class="signal-summary"><h3>QEMU devices</h3>${available.map(item=>`<div class="qemu-device"><strong>${esc(item.id)}</strong><code>${esc(item.qom_path)}</code><small>${esc(item.bus)} · ${Object.keys(item.properties).map(esc).join(', ')}</small></div>`).join('')||'<p>No devices configured.</p>'}</section>`;
  }else{
    const tests=state.jobs.filter(job=>job.action==='simulate-preview').slice().reverse();
    content=`<section class="signal-summary"><h3>Local signal test</h3><button data-run-signal-test ${(active || !(device||selected.length))?'disabled':''}>${icon('play')}Test ${device?esc(device.id):'enabled sensors'}</button>${tests.map(job=>`<div><strong>${esc(job.device||'Signal test')}</strong><span>${esc(job.status)}</span></div>`).join('')}</section>`;
  }
  return `<div class="signals-bench"><aside class="signal-catalog"><h2>Synthetic data</h2><button class="signal-pick signal-orbit-pick" data-signal-orbit aria-pressed="${!device}"><i>${icon('compass')}</i><span>Orbit<small data-orbit-subtitle>${esc(orbitSubtitle(session?.settings.orbit))}</small></span></button><h3>Sensors <small>${selected.length} enabled</small></h3><div class="signal-entries">${sensorList}</div><button class="signal-add" data-signal-hardware>${icon(state.target==='native'?'circuit':'plus')}${state.target==='native'?'Hardware':'Add sensor'}</button></aside><section class="signal-main"><header class="signal-tabs"><nav aria-label="Synthetic data views">${[['signals','Signals'],['python','Python'],['qemu','QEMU'],['test','Test']].map(([id,title])=>`<button data-signal-view="${id}" aria-pressed="${tab===id}">${title}</button>`).join('')}</nav>${tab==='signals'?orbitToolbar():''}<button class="signal-settings-toggle" data-signal-sidebar aria-label="Signal settings" aria-controls="simulation-fields" aria-expanded="${state.signalSidebar!==false}">${icon('settings')}</button></header><div class="signal-content" data-tab="${tab}">${content}</div></section></div>`;
}
const patterns=[['constant','Constant'],['sine','Sine wave'],['ramp','Linear ramp'],['orbit.sunlight','Orbit · sunlight'],['uniform','Uniform noise'],['gaussian','Gaussian noise']];

function patternOf(signal){
 if(signal.noise && signal.noise!=='none')return signal.function==='constant'?signal.noise:'model';
 return patterns.some(([key])=>key===signal.function)?signal.function:'model';
}

export function changePattern(settings,pattern,saved){
 const base={initial:settings.initial,enabled:settings.enabled,noise:'none',function:'constant'};
 if(pattern==='model')return {...saved,initial:base.initial,enabled:base.enabled};
 if(pattern==='sine')return {...base,function:'sine',amplitude:settings.amplitude??1,period:settings.period??30};
 if(pattern==='orbit.sunlight')return {...base,function:'orbit.sunlight',amplitude:settings.amplitude??1,response_time:settings.response_time??0};
 if(pattern==='ramp')return {...base,function:'ramp',slope:settings.slope??1};
 if(pattern==='gaussian'||pattern==='uniform')return {...base,noise:pattern,noise_level:settings.noise_level||1};
 return base;
}

export function renderSimulationSettings(state,{esc}){
 const session=state.simulation, device=session?.available.find(d=>d.id===state.selectedDevice);
 if(!device)return `<header class="signal-heading"><h2>Orbit</h2><button class="icon-button" data-signal-sidebar aria-label="Close settings">${icon('close')}</button></header>${orbitControls(session?.settings.orbit,state.simulationSaving||state.jobs.some(j=>['simulate','simulate-preview'].includes(j.action)&&j.status==='running'))}
 ${session?`<form id="simulation-form"><fieldset class="signal-session" ${state.simulationSaving||state.jobs.some(j=>j.action==='simulate'&&j.status==='running')?'disabled':''}><legend>Sensor sampling</legend><label>Interval (s)<input name="interval" type="number" step="any" min="0.001" required value="${esc(session.settings.interval)}"></label><button data-simulation-save type="button" ${!state.simulationDirty||state.simulationSaving?'disabled':''}>Save settings</button></fieldset></form>`:''}`;
 const sensor=session.settings.sensors.find(s=>s.device===device.id);
 const title=`<header class="signal-heading"><div><h2>${esc(device.id)}</h2><small>${esc(device.bus)} · 0x${Number(device.address).toString(16)}</small></div><button data-back-sensors class="icon-button" aria-label="Close sensor settings">${icon('close')}</button></header>`;
 if(!sensor)return title+`<button data-simulation-add="${esc(device.id)}">Include sensor in session</button>`;
 const busy=state.jobs.some(j=>['simulate','simulate-preview'].includes(j.action)&&j.status==='running')||state.simulationSaving;
 const outputs=Object.keys(sensor.signals);
 const key=outputs.includes(state.signalOutput)?state.signalOutput:outputs[0];
 const signal=sensor.signals[key],meta=device.properties[key],unit=meta.unit,prop=esc(key);
 const options=[...patterns];
 if(patternOf(device.defaults.signals[key])==='model')options.push(['model','Sensor model']);
 const numeric=(name,label,extra='')=>`<label>${esc(label)}<input type="number" step="any" required ${extra} data-signal-property="${prop}" name="${name}" value="${esc(signal[name]??0)}"></label>`;
 return title+`<form id="simulation-form"><div class="signal-output-tabs" ${outputs.length===1?'hidden':''} role="group" aria-label="Sensor outputs">${outputs.map(name=>`<button type="button" data-signal-tab="${esc(name)}" aria-pressed="${name===key}">${esc(name)}</button>`).join('')}</div>
 <fieldset ${busy?'disabled':''}><legend>Signal settings</legend><label class="signal-check"><input type="checkbox" name="enabled" data-signal-property="${prop}" ${signal.enabled!==false?'checked':''}>Generate this output</label>
 <div class="signal-inputs">${numeric('initial','Baseline ('+unit+')',`min="${meta.min}" max="${meta.max}"`)}<label>Variation<select name="variation" data-signal-property="${prop}">${options.map(([id,label])=>`<option value="${id}" ${id===patternOf(signal)?'selected':''}>${label}</option>`).join('')}</select></label>
 ${signal.function==='sine'?numeric('amplitude','Amplitude ('+unit+')')+numeric('period','Period (s)','min="0.001"'):signal.function==='ramp'?numeric('slope','Rate ('+unit+'/s)'):signal.function==='orbit.sunlight'?numeric('amplitude','Sunlit offset ('+unit+')')+numeric('response_time','Response time (s)','min="0" max="7200"'):''}
 ${signal.noise&&signal.noise!=='none'?numeric('noise_level',(signal.noise==='uniform'?'Peak deviation':'Standard deviation')+' ('+unit+')','min="0"'):''}</div></fieldset>
 <fieldset class="signal-session" ${busy?'disabled':''}><legend>Simulation session</legend><label class="signal-check"><input type="checkbox" data-simulation-enable="${esc(device.id)}" ${sensor.enabled?'checked':''}>Include sensor</label><label>Sample interval (s)<input type="number" name="interval" step="any" min="0.001" value="${esc(session.settings.interval)}" required></label></fieldset></form>`;
}


export function selectSeries(id,channel){seriesSelection.set(id,channel);}

// A deterministic noise realization keeps previous preview samples in place while scrubbing.
function variate(i){const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x);}
function previewValue(signal,t,interval,limits){
  let result=signal.initial;
  if(signal.function==='sine')result+=signal.amplitude*Math.sin(2*Math.PI*t/signal.period);
  else if(signal.function==='ramp')result+=signal.slope*t;
  else if(signal.function==='orbit.sunlight'){const amount=orbitIllumination(t,signal.response_time);if(amount==null)return null;result+=signal.amplitude*amount;}
  else if(signal.function!=='constant')return null;
  if(signal.noise && signal.noise!=='none'){
    const i=Math.floor(t/Math.max(.001,interval));
    const noise=signal.noise==='uniform'?2*variate(i)-1:Math.sqrt(-2*Math.log(1-variate(i*2)))*Math.cos(2*Math.PI*variate(i*2+1));
    result=Math.min(limits.max,Math.max(limits.min,result+noise*signal.noise_level));
  }
  return result;
}
function collectSamples(job){
  if(currentRun!==job?.id){readings.clear();currentRun=job?.id;}
  for(const sample of job?.samples?.devices||[]){
    const list=readings.get(sample.id)||[],t=job.samples.elapsed;
    if(!list.length||list.at(-1).t!==t){list.push({t,...sample.values});if(list.length>360)list.shift();}
    readings.set(sample.id,list);
  }
}
function chart(canvas,points,keys,lo,hi,now,orbital){
  const width=canvas.clientWidth,height=canvas.clientHeight;
  if(!width||!height||!points.length)return;
  const dpr=window.devicePixelRatio||1,w=Math.round(width*dpr),h=Math.round(height*dpr);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
  const theme=getComputedStyle(canvas),start=points[0].t,end=points.at(-1).t,delta=(hi-lo)*.13||Math.max(Math.abs(hi)*.04,.1);
  const left=38,right=width-6,top=6,bottom=height-15;
  const x=t=>left+(t-start)/Math.max(.001,end-start)*(right-left),y=v=>top+(hi+delta-v)/(hi-lo+2*delta)*(bottom-top);
  if(orbital){ctx.fillStyle=theme.getPropertyValue('--orbit-shadow');
    for(let i=1;i<points.length;i++){if(!points[i-1].lit){const x0=x(points[i-1].t);ctx.fillRect(x0,top,x(points[i].t)-x0+.3,bottom-top);}}
  }
  ctx.strokeStyle=theme.getPropertyValue('--fs-line');ctx.lineWidth=.65;
  ctx.beginPath();ctx.moveTo(left,bottom);ctx.lineTo(right,bottom);ctx.stroke();
  ctx.font='10px "JetBrains Mono",monospace';ctx.fillStyle=theme.getPropertyValue('--fs-muted');ctx.textAlign='left';ctx.fillText(formatted(hi),0,top+6,34);ctx.fillText(formatted(lo),0,bottom,34);
  const minutes=end-start>=180,unit=minutes?' min':' s',div=minutes?60:1;
  ctx.fillText(Math.round(start/div)+unit,left,height-1);ctx.textAlign='right';ctx.fillText(Math.round(end/div)+unit,right,height-1);
  keys.forEach((key,i)=>{ctx.strokeStyle=colors[i%colors.length];ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.6;ctx.beginPath();let connected=false;
    for(const point of points){const v=point[key];if(!Number.isFinite(v)){connected=false;continue;}ctx[connected?'lineTo':'moveTo'](x(point.t),y(v));connected=true;}
    ctx.stroke();if(points.length===1&&Number.isFinite(points[0][key])){ctx.beginPath();ctx.arc(left,y(points[0][key]),2.5,0,2*Math.PI);ctx.fill();}
  });
  if(now>=start&&now<=end){ctx.strokeStyle=theme.getPropertyValue('--fs-muted');ctx.beginPath();ctx.moveTo(x(now),top);ctx.lineTo(x(now),bottom);ctx.stroke();}
}
export function updateSignalValues(state){
  if(state.view!=='simulation'||!state.simulation)return;
  const session=state.simulation,job=state.jobs.find(j=>['simulate','simulate-preview'].includes(j.action)&&j.status==='running');
  collectSamples(job);
  const now=orbitalTime(),track=orbitData();
  const present=new Map();
  for(const sensor of session.settings.sensors){
    const last=readings.get(sensor.device)?.at(-1), properties=session.available.find(d=>d.id===sensor.device)?.properties||{};
    const values={};
    for(const [key,signal] of Object.entries(sensor.signals))values[key]=!signal.enabled?null:job?(last?.[key]??null):previewValue(signal,now,session.settings.interval,properties[key]);
    present.set(sensor.device,values);
  }
  for(const output of document.querySelectorAll('[data-sensor-reading]')){
    const device=session.available.find(d=>d.id===output.dataset.sensorReading);
    const sensor=session.settings.sensors.find(s=>s.device===device.id);
    const value=Object.entries(present.get(device.id)||{}).find(([,v])=>Number.isFinite(v));
    output.textContent=!sensor?.enabled?'off':value?formatted(value[1])+' '+device.properties[value[0]].unit:'—';
  }
  for(const canvas of document.querySelectorAll('.wave-chart[data-device-id]')){
    const device=session.available.find(item=>item.id===canvas.dataset.deviceId);if(!device)continue;
    const sensor=session.settings.sensors.find(s=>s.device===device.id)||{...device.defaults,enabled:false};
    const unit=canvas.dataset.unit,section=canvas.closest('.signal-plot'), filter=seriesSelection.get(section.dataset.series), values=present.get(device.id)||{};
    const keys=Object.keys(device.properties).filter(k=>device.properties[k].unit===unit&&sensor.signals[k]?.enabled&&(!filter||k===filter));
    const measured=readings.get(device.id), lasts=keys.map(k=>formatted(values[k]));
    section.querySelector('output').textContent=lasts.length?lasts.join('  ')+' '+unit:'—';
    const tag=section.querySelector('[data-series-status]');
    tag.textContent=!sensor.enabled?'off':job?.action==='simulate'&&measured?'sent to QEMU':job?.action==='simulate-preview'&&measured?'local test':job?(job.device&&job.device!==device.id?'not in test':'waiting'):'preview';
    const testButton=section.querySelector('[data-signal-preview-device]');if(testButton)testButton.hidden=Boolean(job);
    tag.classList.toggle('streaming',Boolean(job&&measured));section.classList.toggle('inactive',!sensor.enabled);
    const points=job?measured||[]:[], orbital=keys.some(k=>sensor.signals[k].function==='orbit.sunlight')&&track;
    if(!job&&sensor.enabled&&keys.length){
      const periods=keys.filter(k=>sensor.signals[k].function==='sine').map(k=>sensor.signals[k].period);
      const span=orbital?track.period:periods.length?Math.max(...periods):Math.max(60,session.settings.interval*40);
      const start=orbital?track.cycle*track.period:Math.floor(now/span)*span;
      for(let i=0;i<=240;i++){const t=start+span*i/240,point={t,lit:orbital?orbitPoint(t)?.[3]:true};
        for(const k of keys)point[k]=previewValue(sensor.signals[k],t,session.settings.interval,device.properties[k]);
        points.push(point);
      }
    }
    const numbers=points.flatMap(p=>keys.map(k=>p[k]).filter(Number.isFinite));
    const empty=section.querySelector('.plot-empty');
    canvas.hidden=!numbers.length;empty.hidden=Boolean(numbers.length);
    if(!numbers.length){empty.textContent=!sensor.enabled?'Excluded from session':!keys.length?'Outputs disabled':job?'Waiting for samples…':'Run a local test to sample the Python model.';continue;}
    chart(canvas,points,keys,Math.min(...numbers),Math.max(...numbers),now,Boolean(orbital&&!job));
  }
}
