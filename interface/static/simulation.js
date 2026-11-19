import {icon} from './ui.js';

export function renderSimulationBoard(state){
 const active=state.jobs.find(job=>job.status==='running'&&['simulate','simulate-preview'].includes(job.action));
 const stop=active?`<button class="signal-stop" data-board-stop="${active.action}">Stop ${active.action==='simulate-preview'?'test':'simulation'}</button>`:'';
 return `<div class="signals-bench"><header><div>${icon('wave')}<strong>Synthetic data</strong></div><div>${stop}<button class="signal-settings-toggle" data-signal-sidebar aria-controls="simulation-fields" aria-expanded="${state.signalSidebar!==false}">${icon('settings')}Signal settings</button></div></header><div class="signals-board"><div id="board-stage"></div></div></div>`;
}

const patterns=[['constant','Constant'],['sine','Sine wave'],['ramp','Linear ramp'],['uniform','Uniform noise'],['gaussian','Gaussian noise']];

function patternOf(signal){
 if(signal.noise && signal.noise!=='none')return signal.function==='constant'?signal.noise:'model';
 return patterns.some(([key])=>key===signal.function)?signal.function:'model';
}

export function changePattern(settings,pattern,saved){
 const base={initial:settings.initial,enabled:settings.enabled,noise:'none',function:'constant'};
 if(pattern==='model')return {...saved,initial:base.initial,enabled:base.enabled};
 if(pattern==='sine')return {...base,function:'sine',amplitude:settings.amplitude??1,period:settings.period??30};
 if(pattern==='ramp')return {...base,function:'ramp',slope:settings.slope??1};
 if(pattern==='gaussian'||pattern==='uniform')return {...base,noise:pattern,noise_level:settings.noise_level||1};
 return base;
}

export function renderSimulationSettings(state,{esc}){
 const session=state.simulation, device=session?.available.find(d=>d.id===state.selectedDevice);
 if(!device)return `<header class="signal-heading"><h2>Signal settings</h2><button class="icon-button" data-signal-sidebar aria-label="Close signal settings">${icon('close')}</button></header>
 ${session?.available.length?`<p>Select a sensor to configure its signals.</p><div class="signal-device-list">${session.available.map(d=>`<button data-signal-device="${esc(d.id)}">${icon('wave')}${esc(d.id)}</button>`).join('')}</div>`:`<p>No sensors configured.</p>${state.target==='native'?'<p>Sensor wiring belongs to the board profile. Local signal tests run on this computer.</p>':''}`}
 ${session?`<form id="simulation-form"><fieldset class="signal-session" ${state.simulationSaving||state.jobs.some(j=>j.action==='simulate'&&j.status==='running')?'disabled':''}><legend>Simulation session</legend><label>Sample interval (s)<input name="interval" type="number" step="any" min="0.001" required value="${esc(session.settings.interval)}"></label><button data-simulation-save type="button">Save interval</button></fieldset></form>`:''}
 <button class="signal-hardware" data-signal-hardware>${icon('plus')}Add a sensor in Hardware</button>`;
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
 <section class="signal-plot"><header><strong>${esc(key)}</strong><span>Amplitude · ${esc(unit)}</span></header><canvas class="wave-chart" data-wave="${prop}" aria-label="Amplitude in ${esc(unit)} over time"></canvas><output data-reading="${prop}"></output></section>
 <fieldset ${busy?'disabled':''}><legend>Signal settings</legend><label class="signal-check"><input type="checkbox" name="enabled" data-signal-property="${prop}" ${signal.enabled!==false?'checked':''}>Generate this output</label>
 <div class="signal-inputs">${numeric('initial','Baseline ('+unit+')',`min="${meta.min}" max="${meta.max}"`)}<label>Variation<select name="variation" data-signal-property="${prop}">${options.map(([id,label])=>`<option value="${id}" ${id===patternOf(signal)?'selected':''}>${label}</option>`).join('')}</select></label>
 ${signal.function==='sine'?numeric('amplitude','Amplitude ('+unit+')')+numeric('period','Period (s)','min="0.001"'):signal.function==='ramp'?numeric('slope','Rate ('+unit+'/s)'):''}
 ${signal.noise&&signal.noise!=='none'?numeric('noise_level',(signal.noise==='uniform'?'Peak deviation':'Standard deviation')+' ('+unit+')','min="0"'):''}</div></fieldset>
 <fieldset class="signal-session" ${busy?'disabled':''}><legend>Simulation session</legend><label class="signal-check"><input type="checkbox" data-simulation-enable="${esc(device.id)}" ${sensor.enabled?'checked':''}>Include sensor</label><label>Sample interval (s)<input type="number" name="interval" step="any" min="0.001" value="${esc(session.settings.interval)}" required></label></fieldset></form>`;
}

const readings=new Map();
let lastJob=null,previewKey='',previewStart=0;

// Use the sample time as the noise seed so previous points stay put as the plot moves.
function uniform(index){
 const n=Math.sin(index*127.1+311.7)*43758.5453;
 return n-Math.floor(n);
}
function previewValue(s,t,interval){
 let value=s.initial;
 if(s.function==='sine')value+=s.amplitude*Math.sin(2*Math.PI*t/s.period);
 if(s.function==='ramp')value+=s.slope*t;
 const i=Math.floor(t/interval);
 if(s.noise==='uniform')value+=(2*uniform(i)-1)*s.noise_level;
 if(s.noise==='gaussian')value+=Math.sqrt(-2*Math.log(1-uniform(2*i)))*Math.cos(2*Math.PI*uniform(2*i+1))*s.noise_level;
 return value;
}

function drawChart(canvas,points,baseline,marker=points.at(-1)){
 const width=canvas.clientWidth,height=canvas.clientHeight;
 if(!width||!height)return;
 const ratio=window.devicePixelRatio||1;
 canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
 const ctx=canvas.getContext('2d');
 ctx.scale(ratio,ratio);
 const values=points.map(p=>p.value),min=Math.min(...values,baseline),max=Math.max(...values,baseline);
 const margin=Math.max((max-min)*.12,.01,Math.abs(baseline)*.01),lo=min-margin,hi=max+margin;
 const left=45,right=width-8,top=9,bottom=height-23;
 const start=points[0].time,end=points.at(-1).time;
 const y=v=>bottom-(v-lo)/(hi-lo)*(bottom-top);
 const x=t=>left+(t-start)/Math.max(.001,end-start)*(right-left);
 ctx.font='10px monospace';ctx.fillStyle='#9cabb9';
 for(const value of [hi,(hi+lo)/2,lo]){
  const py=y(value);ctx.strokeStyle='#343e47';ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(right,py);ctx.stroke();
  ctx.fillText(Number(value.toPrecision(3)).toString(),1,py+3,40);
 }
 ctx.fillText(start.toFixed(1)+' s',left,height-4);ctx.textAlign='right';ctx.fillText(end.toFixed(1)+' s',right,height-4);
 ctx.setLineDash([3,4]);ctx.strokeStyle='#837568';ctx.beginPath();ctx.moveTo(left,y(baseline));ctx.lineTo(right,y(baseline));ctx.stroke();ctx.setLineDash([]);
 ctx.strokeStyle='#8ed9c9';ctx.lineWidth=1.8;ctx.beginPath();
 points.forEach(({time,value},i)=>ctx[i?'lineTo':'moveTo'](x(time),y(value)));ctx.stroke();
 ctx.fillStyle='#9ee4d1';ctx.beginPath();ctx.arc(x(marker.time),y(marker.value),2.5,0,2*Math.PI);ctx.fill();
}

export function updateSignalValues(state){
 if(state.view!=='simulation')return;
 const sensor=state.simulation?.settings.sensors.find(s=>s.device===state.selectedDevice);
 const job=state.jobs.find(j=>['simulate','simulate-preview'].includes(j.action)&&j.status==='running');
 if(lastJob!==job?.id){readings.clear();lastJob=job?.id;}
 for(const frame of job?.samples?.devices||[]){
  for(const [key,value] of Object.entries(frame.values)){
   const id=frame.id+'/'+key,points=readings.get(id)||[],time=job.samples.elapsed;
   if(points.at(-1)?.time!==time){points.push({time,value});if(points.length>120)points.shift();readings.set(id,points);}
  }
 }
 const canvas=document.querySelector('canvas[data-wave]'),key=canvas?.dataset.wave,s=sensor?.signals[key];
 if(!s)return;
 const measured=job&&readings.get(sensor.device+'/'+key),known=['constant','sine','ramp'].includes(s.function);
 const caption=canvas.nextElementSibling;
 canvas.hidden=!s.enabled||(!measured&&!known)||!!job&&!measured;
 if(canvas.hidden){caption.textContent=!s.enabled?'Output disabled':job?'Waiting for samples…':'Start a test to plot the sensor model.';return;}
 if(measured){const unit=state.simulation.available.find(d=>d.id===sensor.device).properties[key].unit;caption.textContent='Live sample · '+measured.at(-1).value+' '+unit;drawChart(canvas,measured,s.initial);return;}
 const interval=Math.max(.001,state.simulation.settings.interval||1);
 const duration=s.function==='sine'?Math.max(.001,s.period):Math.max(10,interval*24);
 const signature=JSON.stringify([sensor.device,key,s,interval]);
 if(previewKey!==signature){previewKey=signature;previewStart=performance.now();}
 const elapsed=(performance.now()-previewStart)/1000,start=Math.max(0,elapsed-duration);
 const limits=state.simulation.available.find(device=>device.id===sensor.device).properties[key];
 const point=time=>{
  const value=previewValue(s,time,interval);
  return {time,value:s.noise&&s.noise!=='none'?Math.max(limits.min,Math.min(limits.max,value)):value};
 };
 const points=Array.from({length:121},(_,i)=>point(start+duration*i/120));
 caption.textContent='Signal preview · Time (s)';
 drawChart(canvas,points,s.initial,point(elapsed));
}
