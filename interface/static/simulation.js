import {icon} from './ui.js';
import {pythonPanel,qemuPanel,scenarioPanel} from './signal-experiments.js';
import {orbitCard, orbitControls, orbitData, orbitIllumination, orbitTemperature, thermalCurve, orbitPoint, orbitSubtitle, orbitToolbar, orbitalTime} from './orbit-preview.js';

const seriesSelection=new Map();
const readings=new Map();
let currentRun;
const colors=['--fs-accent','--orbit-night','--fs-success','--fs-code','--fs-danger'];
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
const chartsPerPage=3;
function sessionCharts(session) {
  return (session?.available||[]).flatMap(device=>sensorCharts(
    session.settings.sensors.find(sensor=>sensor.device===device.id)||{...device.defaults,enabled:false},device));
}
export function chartPageForDevice(session,id) {
  const index=sessionCharts(session).findIndex(chart=>chart.device.id===id);
  return Math.floor(Math.max(0,index)/chartsPerPage);
}
function chartHtml({sensor,device,unit,keys},esc){
  const id=device.id+'|'+unit, chosen=seriesSelection.get(id)||'';
  return `<section class="signal-plot" data-series="${esc(id)}"><header><div class="series-title"><strong>${esc(device.name||device.id)}</strong><small>${identity(device,esc)}</small></div><small data-series-status></small>${keys.some(k=>['script','custom'].includes(sensor.signals[k]?.function))?`<button class="series-model-test" data-signal-preview-device="${esc(device.id)}" title="Run the Python model locally">Test Python</button>`:''}<div class="series-right">${keys.length>1?`<div class="series-channels" role="group" aria-label="Chart channels">${['',...keys].map(key=>`<button type="button" data-series-channel="${esc(key)}" data-series-id="${esc(id)}" aria-pressed="${chosen===key}" title="${esc(key||'All channels')}">${esc(key?key.replace(/.*[-_]/,''):'all')}</button>`).join('')}</div>`:''}<output></output></div></header><canvas class="wave-chart" data-device-id="${esc(sensor.device)}" data-unit="${esc(unit)}" role="img" aria-label="${esc(sensor.device+' waveform in '+unit)}"></canvas><div class="plot-empty" hidden></div></section>`;
}

export function sensorAvailability(state) {
  if (state.target === 'native') return state.hardware?.native?.running ? '' : 'Run cFS';
  if (state.target === 'physical') return state.ground?.connected && state.ground.target === 'physical' ? '' : 'Connect ground station';
  return state.hardware?.qemu?.running ? '' : 'Emulator stopped';
}

export function renderSimulationBoard(state,{esc}){
  const active=state.jobs.find(job=>['simulate','simulate-preview'].includes(job.action)&&job.status==='running');
  const tab=state.signalView||'signals', session=state.simulation, available=session?.available||[], sensors=session?.settings.sensors||[];
  const selected=sensors.filter(item=>item.enabled), device=available.find(item=>item.id===state.selectedDevice);
  const sensorList=available.map(item=>{
    const sensor=sensors.find(s=>s.device===item.id);
    return `<div class="signal-entry" data-selected="${item.id===state.selectedDevice}"><input type="checkbox" data-simulation-enable="${esc(item.id)}" aria-label="Include ${esc(item.id)} in session" ${sensor?.enabled?'checked':''} ${active||state.simulationSaving?'disabled':''}><button class="signal-pick" data-signal-device="${esc(item.id)}" aria-pressed="${item.id===state.selectedDevice}"><span>${esc(item.name||item.id)}<small>${identity(item,esc)}</small></span><output data-sensor-reading="${esc(item.id)}"></output></button></div>`;
  }).join('');
  const reason=sensorAvailability(state) || (!selected.length?'No sensors selected':'');
  const stream=active?.action==='simulate' && active;
  const count=selected.length+' sensor'+(selected.length===1?'':'s')+' enabled';
  const action=stream?'<button data-board-stop="simulate">Stop</button>':`<button data-signal-begin ${reason||active?'disabled':''} title="${esc(reason||(active?'Local test running':'Start sensor data'))}">Start</button>`;
  const streamStatus=`<div class="signal-session-state" data-active="${Boolean(stream)}"><i></i><strong>${stream?(stream.samples?.devices?.length?'Sensor data is on':'Starting sensor data'):'Synthetic data is off'}</strong><small>${esc([count,stream?'':active?'Local test running':reason].filter(Boolean).join(' · '))}</small>${action}</div>`;
  let content;
  if(tab==='signals'){
    const charts=sessionCharts(session);
    const page=Math.min(state.signalPage||0,Math.max(0,Math.ceil(charts.length/chartsPerPage)-1));
    const pagination=charts.length>chartsPerPage?`<nav class="series-pages" aria-label="Signal charts"><button data-signal-page="${page-1}" aria-label="Previous charts" ${page?'':'disabled'}>‹</button><span>${page+1} / ${Math.ceil(charts.length/chartsPerPage)}</span><button data-signal-page="${page+1}" aria-label="Next charts" ${(page+1)*chartsPerPage>=charts.length?'disabled':''}>›</button></nav>`:'';
    content=`${orbitCard()}${charts.length?`<div class="series-grid">${charts.slice(page*chartsPerPage,(page+1)*chartsPerPage).map(chart=>chartHtml(chart,esc)).join('')}</div>`:''}${pagination}`;
  }else if(tab==='python')content=pythonPanel(state,esc,active,reason);
  else if(tab==='qemu')content=qemuPanel(state,esc);
  else content=scenarioPanel(state,esc,active);
  return `<div class="signals-bench"><aside class="signal-catalog"><h2>Synthetic data</h2><button class="signal-pick signal-orbit-pick" data-signal-orbit aria-pressed="${!device}"><i>${icon('compass')}</i><span>Orbit<small data-orbit-subtitle>${esc(orbitSubtitle(session?.settings.orbit))}</small></span></button><h3>Sensors <small>${selected.length} enabled</small></h3><div class="signal-entries">${sensorList}</div><button class="signal-add" data-signal-hardware>${icon(state.target==='native'?'circuit':'plus')}${state.target==='native'?'Hardware':'Add sensor'}</button></aside><section class="signal-main"><header class="signal-tabs"><nav aria-label="Synthetic data views">${[['signals','Signals'],['python','Python'],['qemu','QEMU'],['test','Test']].map(([id,title])=>`<button data-signal-view="${id}" aria-pressed="${tab===id}">${title}</button>`).join('')}</nav>${orbitToolbar()}<button class="signal-settings-toggle" data-signal-sidebar aria-label="Signal settings" aria-controls="simulation-fields" aria-expanded="${state.signalSidebar!==false}">${icon('settings')}</button></header>${streamStatus}<div class="signal-content" data-tab="${tab}">${content}</div></section></div>`;
}
const patterns=[['constant','Constant'],['sine','Sine wave'],['ramp','Linear ramp'],['orbit.sunlight','Orbit · sunlight']];

function patternOf(signal){
 return signal.function==='custom' ? 'python:'+signal.custom : signal.function;
}

export function changePattern(settings,pattern){
 const base={initial:settings.initial,enabled:settings.enabled,noise:settings.noise??'none',noise_level:settings.noise_level??0};
 if(pattern.startsWith('python:'))return {...base,function:'custom',custom:pattern.slice(7)};
 if(pattern==='sine')return {...base,function:pattern,amplitude:settings.amplitude??1,period:settings.period??30};
 if(pattern==='orbit.thermal')return {...base,function:pattern,material:settings.material||{size:'1U',mass:1.3,alpha:.7,emissivity:.7,power:1}};
 if(pattern==='orbit.sunlight')return {...base,function:pattern,amplitude:settings.amplitude??1,response_time:settings.response_time??0};
 if(pattern==='ramp')return {...base,function:pattern,slope:settings.slope??1};
 return {...base,function:pattern};
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
 if(unit==='°C')options.push(['orbit.thermal','Orbit physics']);
 if(device.sample_line)options.push(['script','Python · sample']);
 for(const fn of device.functions||[])options.push(['python:'+fn.name,'Python · '+fn.name]);
 const noiseOptions=[['none','None'],['uniform','Uniform'],['gaussian','Gaussian']];
 const numeric=(name,label,extra='')=>`<label>${esc(label)}<input type="number" step="any" required ${extra} data-signal-property="${prop}" name="${name}" value="${esc(signal[name]??0)}"></label>`;
 const thermal=signal.function==='orbit.thermal',m=signal.material;
 const materialField=(id,title,min,max,step,unit='')=>`<label class="thermal-range"><span>${title}<output>${m[id]} ${unit}</output></span><input type="range" min="${min}" max="${max}" step="${step}" value="${m[id]}" name="${id}" data-material-field data-signal-property="${prop}"></label>`;
 const massLimits=thermal?{'1U':[.8,2],'3U':[2,6],'6U':[6,14]}[m.size]:[];
 const thermalFields=thermal?`<div class="thermal-material"><label>Size<select data-material-field data-signal-property="${prop}" name="size">${['1U','3U','6U'].map(s=>`<option ${s===m.size?'selected':''}>${s}</option>`).join('')}</select></label>
 ${materialField('mass','Mass',...massLimits,.1,'kg')}${materialField('alpha','Absorptivity α',.1,.95,.01)}${materialField('emissivity','Emissivity ε',.05,.95,.01)}${materialField('power','Internal heat',0,5,.1,'W')}
 <div class="thermal-facts">${[['orbit','This orbit'],['steady_sun','Steady sun'],['steady_shadow','Steady shadow']].map(([key,title])=>`<span>${title}<output data-material-result="${key}">—</output></span>`).join('')}</div></div>`:'';
 return title+`<form id="simulation-form"><div class="signal-output-tabs" ${outputs.length===1?'hidden':''} role="group" aria-label="Sensor outputs">${outputs.map(name=>`<button type="button" data-signal-tab="${esc(name)}" aria-pressed="${name===key}">${esc(name)}</button>`).join('')}</div>
 <fieldset ${busy?'disabled':''}><legend>Signal settings</legend><label class="signal-check"><input type="checkbox" name="enabled" data-signal-property="${prop}" ${signal.enabled!==false?'checked':''}>Generate this output</label>
 <div class="signal-inputs">${thermal?'':numeric('initial','Baseline ('+unit+')',`min="${meta.min}" max="${meta.max}"`)}<label>Waveform<select name="variation" data-signal-property="${prop}">${options.map(([id,label])=>`<option value="${id}" ${id===patternOf(signal)?'selected':''}>${esc(label)}</option>`).join('')}</select></label>
 ${thermalFields}
 ${signal.function==='sine'?numeric('amplitude','Amplitude ('+unit+')')+numeric('period','Period (s)','min="0.001"'):signal.function==='ramp'?numeric('slope','Rate ('+unit+'/s)'):signal.function==='orbit.sunlight'?numeric('amplitude','Sunlit offset ('+unit+')')+numeric('response_time','Response time (s)','min="0" max="7200"'):''}
 <label>Noise<select name="noise" data-signal-property="${prop}">${noiseOptions.map(([id,label])=>`<option value="${id}" ${id===(signal.noise??'none')?'selected':''}>${label}</option>`).join('')}</select></label>
 ${signal.noise&&signal.noise!=='none'?numeric('noise_level',(signal.noise==='uniform'?'Peak deviation':'Standard deviation')+' ('+unit+')','min="0"'):''}</div></fieldset>
 <fieldset class="signal-session" ${busy?'disabled':''}><legend>Simulation session</legend><label class="signal-check"><input type="checkbox" data-simulation-enable="${esc(device.id)}" ${sensor.enabled?'checked':''}>Include sensor</label><label>Sample interval (s)<input type="number" name="interval" step="any" min="0.001" value="${esc(session.settings.interval)}" required></label></fieldset></form>`;
}


export function selectSeries(id,channel){seriesSelection.set(id,channel);}

// A deterministic noise realization keeps previous preview samples in place while scrubbing.
function variate(i){const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x);}
export function previewValue(signal,t,interval,limits){
  let result=signal.initial;
  if(signal.function==='orbit.thermal'){
    result=orbitTemperature(t,signal.material);
    if(result==null)return null;
  }else if(signal.function==='sine')result+=signal.amplitude*Math.sin(2*Math.PI*t/signal.period);
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
  ctx.font=theme.getPropertyValue('--fs-small').trim()+' '+theme.getPropertyValue('--fs-mono');ctx.fillStyle=theme.getPropertyValue('--fs-muted');ctx.textAlign='left';ctx.fillText(formatted(hi),0,top+6,34);ctx.fillText(formatted(lo),0,bottom,34);
  const minutes=end-start>=180,unit=minutes?' min':' s',div=minutes?60:1;
  ctx.fillText(Math.round(start/div)+unit,left,height-1);ctx.textAlign='right';ctx.fillText(Math.round(end/div)+unit,right,height-1);
  keys.forEach((key,i)=>{ctx.strokeStyle=theme.getPropertyValue(colors[i%colors.length]);ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.6;ctx.beginPath();let connected=false;
    for(const point of points){const v=point[key];if(!Number.isFinite(v)){connected=false;continue;}ctx[connected?'lineTo':'moveTo'](x(point.t),y(v));connected=true;}
    ctx.stroke();if(points.length===1&&Number.isFinite(points[0][key])){ctx.beginPath();ctx.arc(left,y(points[0][key]),2.5,0,2*Math.PI);ctx.fill();}
  });
  if(now>=start&&now<=end){ctx.strokeStyle=theme.getPropertyValue('--fs-muted');ctx.beginPath();ctx.moveTo(x(now),top);ctx.lineTo(x(now),bottom);ctx.stroke();}
}
export function updateSignalValues(state){
  if(state.view!=='simulation'||!state.simulation)return;
  const session=state.simulation,job=state.jobs.find(j=>['simulate','simulate-preview'].includes(j.action)&&j.status==='running');
  collectSamples(job);
  const consoleBox=document.querySelector('[data-signal-console]');
  if(consoleBox){
    const last=state.jobs.filter(j=>['simulate','simulate-preview'].includes(j.action)&&!j.scenario).at(-1);
    const lines=last?.lines?.slice(-24).join('\n')||'';
    if(consoleBox.textContent!==lines){consoleBox.textContent=lines;consoleBox.scrollTop=consoleBox.scrollHeight;}
  }
  const now=orbitalTime(),track=orbitData();
  const focus=session.settings.sensors.find(sensor=>sensor.device===state.selectedDevice);
  const curve=focus&&thermalCurve((focus.signals[state.signalOutput]||Object.values(focus.signals)[0])?.material);
  for(const el of document.querySelectorAll('[data-material-result]')){
    const k=el.dataset.materialResult;
    el.textContent=!curve?'—':(k==='orbit'?formatted(curve.minimum)+' … '+formatted(curve.maximum):formatted(curve[k]))+' °C';
  }
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
    section.querySelector('output').textContent=!sensor.enabled?'—':lasts.length?lasts.join('  ')+' '+unit:'—';
    const tag=section.querySelector('[data-series-status]');
    tag.textContent=!sensor.enabled?'off':job?.action==='simulate'&&measured?'sent to QEMU':job?.action==='simulate-preview'&&measured?'local test':job?(job.device&&job.device!==device.id?'not in test':'waiting'):'preview';
    const testButton=section.querySelector('[data-signal-preview-device]');if(testButton)testButton.hidden=Boolean(job);
    tag.classList.toggle('streaming',Boolean(job&&measured));section.classList.toggle('inactive',!sensor.enabled);
    const points=job?measured||[]:[], orbital=keys.some(k=>sensor.signals[k].function.startsWith('orbit.'))&&track;
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
    if(!numbers.length){empty.textContent=!sensor.enabled?'':!keys.length?'Outputs disabled':job?'Waiting for samples…':'Awaiting Python samples';continue;}
    chart(canvas,points,keys,Math.min(...numbers),Math.max(...numbers),now,Boolean(orbital&&!job));
  }
}
