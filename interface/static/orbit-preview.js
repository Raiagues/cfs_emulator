import {coastlines} from './coastline.js';
import {icon} from './ui.js';

const rad = Math.PI / 180;
const earth = 6378.137;
const presets = {
  iss: {label:'ISS-like', perigee:405, apogee:420, inclination:51.64, argument:0},
  sso: {label:'SSO 550', perigee:548, apogee:552, inclination:97.59, argument:90},
  molniya: {label:'Molniya', perigee:600, apogee:39700, inclination:63.435, argument:270},
};
const clock = {time:0, anchor:0, speed:60, playing:true};
const viewport = {lon:18, lat:20, zoom:1};
let context, track, signature, pendingKey, requestNumber=0, timer;
let firstVisit=true, failedKey='', retryAt=0;
let source='elements', tleText='', tleError='';
const color = name => getComputedStyle(document.body).getPropertyValue(name).trim();
const numeric = (v, digits=1) => Number(v).toFixed(digits);
const wrap = v => ((v+180)%360+360)%360-180;
const currentJob = () => context?.state.jobs.find(job=>['simulate','simulate-preview'].includes(job.action) && job.status==='running');

export function orbitalTime() {
  const job=currentJob();
  return job ? job.samples?.elapsed || 0 : clock.time + (clock.playing?(performance.now()-clock.anchor)/1000*clock.speed:0);
}
function setClock(time) { clock.time=time; clock.anchor=performance.now(); }
const stateElements = () => context?.state.simulation?.settings.orbit;
export function orbitData() { return track; }
export function orbitPoint(t) {
  if(!track) return null;
  const u=Math.max(0,Math.min(1,t/track.period-track.cycle))*(track.points.length-1);
  const left=track.points[Math.floor(u)],right=track.points[Math.ceil(u)], mix=u%1;
  return left.map((v,i)=>i===3?(mix<.5?v:right[i]):(i===0 || i===4)?wrap(v+wrap(right[i]-v)*mix):v+(right[i]-v)*mix);
}
export function orbitIllumination(time, responseTime=0) {
  if(!responseTime) return orbitPoint(time)?.[3] ?? null;
  const curve=track?.responses?.get(responseTime);
  if(!curve) return null;
  const u=Math.max(0,Math.min(1,time/track.period-track.cycle))*(curve.length-1);
  const left=curve[Math.floor(u)],right=curve[Math.ceil(u)];
  return left+(u%1)*(right-left);
}
export const materialKey = m => JSON.stringify([m.size,m.mass,m.alpha,m.emissivity,m.power]);
export function thermalCurve(material) { return material && track?.thermal?.get(materialKey(material)); }
export function orbitTemperature(time,material) {
  const curve=thermalCurve(material)?.values;
  if(!curve)return null;
  const u=Math.max(0,Math.min(1,time/track.period-track.cycle))*(curve.length-1);
  const left=curve[Math.floor(u)], right=curve[Math.ceil(u)];
  return left+(u%1)*(right-left);
}
function setText(selector,text) { const el=document.querySelector(selector); if(el && el.textContent!==text)el.textContent=text; }
function presetName(el) {
  return Object.values(presets).find(p=>['perigee','apogee','inclination','argument'].every(k=>Math.abs(p[k]-el[k])<.001))?.label || 'Custom';
}
export function orbitSubtitle(el) {
  if (!el) return '';
  const period=2*Math.PI*Math.sqrt((earth+(el.apogee+el.perigee)/2)**3/398600.4418);
  return presetName(el)+' · '+numeric(el.inclination)+'° · '+Math.round(period/60)+' min';
}
export function orbitToolbar() {
  return `<div class="orbit-clock"><time data-orbit-clock></time><div class="orbit-rate" role="group" aria-label="Preview speed">${[1,60,600].map(speed=>`<button type="button" data-orbit-rate="${speed}" aria-pressed="${clock.speed===speed}">${speed}×</button>`).join('')}</div><button data-orbit-play aria-label="Pause orbit preview" class="orbit-pause"></button></div>`;
}
export function orbitCard() {
  const facts=[['model','propagator'],['period','period'],['alt','altitude now'],['beta','β'],['eclipse','eclipse'],['drift','node drift']];
  return `<section class="orbit-card" aria-label="Orbit preview"><div class="orbit-views"><div class="orbit-globe"><canvas data-orbit-globe aria-label="Earth and orbital plane" title="Drag to rotate · double-click to reset"></canvas></div><div class="orbit-map"><canvas data-orbit-map role="slider" tabindex="0" aria-label="Orbit time along the ground track" aria-valuemin="0" aria-valuemax="100"></canvas><div class="orbit-key"><span>sunlit</span><span>eclipse</span></div><output data-orbit-position></output></div></div><footer>${facts.map(([id,title])=>`<span>${title} <b data-orbit-fact="${id}">—</b></span>`).join('')}</footer></section>`;
}
export function orbitControls(el,locked=false) {
  if(!el)return '';
  const slider=(id,label,unit,min,max,step)=>`<div class="orbit-slider"><span><label for="orbit-${id}">${label}</label><small><input aria-label="${label} in ${unit}" data-orbit-number="${id}" type="number" min="${min}" max="${unit==='km'?100000:max}" step="${step}" value="${Number(el[id].toFixed(step<1?2:0))}"> ${unit}</small></span><input id="orbit-${id}" type="range" data-orbit-element="${id}" min="${min}" max="${max}" step="${step}" value="${el[id]}"></div>`;
  const seg=(items,attribute,selected)=>`<div class="orbit-segments">${items.map(([id,label])=>`<button type="button" data-orbit-${attribute}="${id}" aria-pressed="${id===selected}">${label}</button>`).join('')}</div>`;
  const rangeMax=el.apogee>3200?Math.max(45000,Math.ceil(el.apogee/1000)*1000):3200;
  const tleHtml=tleText.replaceAll('&','&amp;').replaceAll('<','&lt;');
  return `<fieldset class="orbit-inspector" ${locked?'disabled':''}><div class="orbit-presets">${Object.entries(presets).map(([id,p])=>`<button data-orbit-preset="${id}" aria-pressed="${presetName(el)===p.label}">${p.label}</button>`).join('')}</div><div class="orbit-defined">Defined by</div>${seg([['elements','Elements'],['tle','TLE']],'source',source)}
  ${source==='tle'?`<label class="orbit-tle">Two-line elements<textarea rows="4" data-orbit-tle spellcheck="false">${tleHtml}</textarea></label><span class="orbit-error" data-orbit-error role="status"></span><button type="button" data-orbit-import>Apply elements</button><div class="orbit-import-epoch">Epoch · ${el.epoch.slice(0,19).replace('T',' ')} UTC</div>`:
  `<h3>Shape</h3>${slider('perigee','Perigee altitude','km',100,Math.max(2500,el.perigee),1)}${slider('apogee','Apogee altitude','km',100,rangeMax,1)}<h3>Orientation</h3>${slider('inclination','Inclination','°',0,180,.01)}${slider('node','RAAN','°',0,360,.1)}${slider('argument','Argument of perigee','°',0,360,.1)}${slider('anomaly','Mean anomaly at epoch','°',0,360,.1)}`}
  <h3>Propagator</h3>${seg([['Two-body','Two-body'],['J2','J2']],'model',el.model)}<div class="orbit-readouts"><span>period <b data-orbit-summary="period">—</b></span><span>eccentricity <b data-orbit-summary="ecc">—</b></span></div></fieldset>`;
}

function canvasContext(canvas){
  const {width,height}=canvas.getBoundingClientRect();
  if(!width||!height)return;
  const dpr=window.devicePixelRatio||1,w=Math.round(width*dpr),h=Math.round(height*dpr);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
  return {ctx,width,height};
}
function line(ctx,path,project,limit,fill=false){
  ctx.beginPath();let prev=null;
  for(const p of path){
    const xy=project(p);
    if(xy){
      if(!prev||Math.abs(prev[0]-xy[0])>limit)ctx.moveTo(...xy);
      else ctx.lineTo(...xy);
    }
    prev=xy;
  }
  if(fill){ctx.closePath();ctx.fill();}else ctx.stroke();
}
const grid=[];
for(let lon=-150;lon<180;lon+=30) grid.push(Array.from({length:91},(_,i)=>[lon,i*2-90]));
for(let lat=-60;lat<=60;lat+=30) grid.push(Array.from({length:181},(_,i)=>[i*2-180,lat]));
function globeProjection(width,height){
  const tilt=viewport.lat*rad, outer=earth+(track?.elements.apogee||550), r=Math.min(width,height)*.47*viewport.zoom*earth/outer,center=[width*.5,height*.5];
  return {r,center,project(lon,lat,scale=1){
    const angle=(lon-viewport.lon)*rad,phi=lat*rad;
    const y=Math.sin(phi)*Math.cos(tilt)-Math.cos(phi)*Math.cos(angle)*Math.sin(tilt);
    const z=Math.sin(phi)*Math.sin(tilt)+Math.cos(phi)*Math.cos(angle)*Math.cos(tilt);
    const x=Math.cos(phi)*Math.sin(angle);
    if(z<0 && scale*scale*(x*x+y*y)<1)return null;
    return [center[0]+r*scale*x,center[1]-r*scale*y];
  }};
}
function drawScene(canvas,isMap,now,time){
  const context=canvasContext(canvas);if(!context)return;
  const {ctx,width,height}=context;
  const g=globeProjection(width,height),map=(lon,lat)=>[(lon+180)*width/360,(90-lat)*height/180];
  const project=coords=>isMap?map(...coords):g.project(...coords);
  ctx.save();
  if(!isMap){ctx.beginPath();ctx.arc(...g.center,g.r,0,2*Math.PI);ctx.clip();}
  ctx.fillStyle=color('--orbit-water');ctx.fillRect(0,0,width,height);
  ctx.lineWidth=.55;ctx.strokeStyle=color('--orbit-grid');for(const path of grid)line(ctx,path,project,width);
  ctx.strokeStyle=color('--orbit-land');ctx.fillStyle=color('--orbit-land');ctx.lineWidth=1;
  for(const path of coastlines)line(ctx,path,project,width,isMap);
  if(isMap){
    const dec=now[5]*rad, darkPole=dec>0?-90:90;
    const night=Array.from({length:241},(_,i)=>{
      const lon=i*1.5-180;
      const lat=Math.atan(-Math.cos(dec)*Math.cos((lon-now[4])*rad)/(Math.sin(dec)||1e-12))/rad;
      return [lon,lat];
    });
    ctx.fillStyle='rgba(4,9,18,.45)';line(ctx,[...night,[180,darkPole],[-180,darkPole]],project,width,true);
  }else{
    const source=g.project(now[4],now[5]) || [g.center[0]+g.r*.8,g.center[1]-g.r*.6];
    const shade=ctx.createRadialGradient(...source,0,...source,2*g.r);
    shade.addColorStop(0,'rgba(0,0,0,0)');shade.addColorStop(.6,'rgba(2,7,15,.12)');shade.addColorStop(.82,'rgba(2,7,15,.68)');ctx.fillStyle=shade;ctx.fillRect(0,0,width,height);
  }
  ctx.restore();
  if(!isMap){
    const lambda=(now[4]-viewport.lon)*rad,delta=now[5]*rad,tilt=viewport.lat*rad;
    const dx=Math.cos(delta)*Math.sin(lambda),dy=-Math.sin(delta)*Math.cos(tilt)+Math.cos(delta)*Math.cos(lambda)*Math.sin(tilt);
    const len=Math.hypot(dx,dy)||1, reach=Math.min(width,height)*.45;
    const x=Math.max(9,Math.min(width-9,g.center[0]+dx*reach/len)),y=Math.max(9,Math.min(height-9,g.center[1]+dy*reach/len));
    ctx.fillStyle=color('--fs-accent');ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=1;
    ctx.beginPath();ctx.arc(x,y,3.3,0,2*Math.PI);ctx.fill();
    for(let i=0;i<8;i++){const a=i*Math.PI/4;ctx.beginPath();ctx.moveTo(x+Math.cos(a)*5,y+Math.sin(a)*5);ctx.lineTo(x+Math.cos(a)*7,y+Math.sin(a)*7);ctx.stroke();}
  }
  const points=track.points;
  const pos=(p,i)=>isMap?map(p[0],p[1]):g.project(p[0]+((track.cycle+i/(points.length-1))*track.period-time)*360/86164.0905,p[1],(earth+p[2])/earth);
  const sun=color('--fs-accent'),night=color('--orbit-night');
  ctx.lineWidth=1.8;ctx.lineCap='round';let prev=null, visible=null;
  for(let i=0;i<points.length;i++){
    const p=points[i],xy=pos(p,i);
    if(xy&&prev&&Math.abs(xy[0]-prev[0])<width*.5){
      if(visible!==p[3]){if(visible!==null)ctx.stroke();ctx.beginPath();ctx.strokeStyle=p[3]?sun:night;visible=p[3];}
      ctx.moveTo(...prev);ctx.lineTo(...xy);
    }
    prev=xy;
  }
  if(visible!==null)ctx.stroke();
  const marker=isMap?map(now[0],now[1]):g.project(now[0],now[1],(earth+now[2])/earth);
  if(marker){ctx.fillStyle=now[3]?sun:night;ctx.strokeStyle=color('--fs-bg');ctx.lineWidth=2.5;ctx.beginPath();ctx.arc(...marker,4.6,0,2*Math.PI);ctx.fill();ctx.stroke();}
}

async function loadTrack(el,cycle,key,responses,materials){
  if(pendingKey===key || (failedKey===key && performance.now()<retryAt))return;
  const request=++requestNumber;pendingKey=key;
  try{
    const batches=[];
    for(let i=0;i<Math.max(1,responses.length,materials.length);i+=32)
      batches.push({elements:el,cycle,responses:responses.slice(i,i+32),materials:materials.slice(i,i+32)});
    const parts=await Promise.all(batches.map(batch=>context.api('simulation/orbit',batch)));
    const thermal=new Map(parts.flatMap((part,i)=>(part.thermal||[]).map((curve,j)=>[materialKey(batches[i].materials[j]),curve])));
    const data=parts[0];
    data.thermal=thermal;
    data.responses=new Map(parts.flatMap(part=>Object.entries(part.responses||{})).map(([tau,curve])=>[Number(tau),curve]));
    if(request!==requestNumber)return;
    track=data;signature=key;failedKey='';drawOrbit();
  }catch(error){if(request===requestNumber){if(failedKey!==key)context.error(error.message);failedKey=key;retryAt=performance.now()+5000;}}
  finally{if(request===requestNumber)pendingKey=null;}
}
export function drawOrbit(){
  const globe=document.querySelector('[data-orbit-globe]'),el=stateElements();
  if(!document.querySelector('[data-orbit-clock]')||!el||!context)return;
  if(firstVisit){setClock(0);firstVisit=false;}
  const time=orbitalTime(), period=track?.period||2*Math.PI*Math.sqrt((earth+(el.apogee+el.perigee)/2)**3/398600.4418);
  const sensors=context.state.simulation.settings.sensors;
  const responses=[...new Set(sensors.flatMap(sensor=>Object.values(sensor.signals).filter(s=>s.function==='orbit.sunlight'&&s.response_time>0).map(s=>s.response_time)))].sort((a,b)=>a-b);
  const thermal=sensors.flatMap(sensor=>Object.values(sensor.signals).filter(s=>s.function==='orbit.thermal').map(s=>s.material));
  const materials=[...new Map(thermal.map(m=>[materialKey(m),m])).values()];
  const cycle=Math.floor(time/period),key=JSON.stringify([el,cycle,responses,materials]);
  if(signature!==key){if(!timer)loadTrack(el,cycle,key,responses,materials);if(!track)return;}
  const now=orbitPoint(time);
  const map=document.querySelector('[data-orbit-map]');
  if(globe && map){drawScene(globe,false,now,time);drawScene(map,true,now,time);}
  const utc=new Date(Date.parse(el.epoch)+time*1000);
  setText('[data-orbit-clock]',utc.toISOString().slice(0,19).replace('T',' ')+' UTC · orbit '+(cycle+1));
  setText('[data-orbit-position]',Math.abs(now[1]).toFixed(1)+'°'+(now[1]<0?'S':'N')+'  '+Math.abs(now[0]).toFixed(1)+'°'+(now[0]<0?'W':'E')+' · '+Math.round(now[2])+' km');
  const facts={model:el.model,period:numeric(track.period/60)+' min',alt:Math.round(now[2])+' km',beta:numeric(now[6])+'°',eclipse:numeric(track.eclipse*track.period/60)+' min · '+Math.round(track.eclipse*100)+'%',drift:(track.drift>=0?'+':'')+numeric(track.drift,3)+'°/day'};
  for(const [id,val] of Object.entries(facts))setText('[data-orbit-fact="'+id+'"]',val);
  setText('[data-orbit-summary="period"]',facts.period);setText('[data-orbit-summary="ecc"]',numeric(track.eccentricity,4));
  setText('[data-orbit-subtitle]',orbitSubtitle(el));
  const active=Boolean(currentJob());
  if(map){
    map.setAttribute('aria-valuenow',Math.round((time/track.period%1)*100));
    map.setAttribute('aria-valuetext',utc.toISOString().slice(11,19)+' UTC');
    map.setAttribute('aria-disabled',String(active));
  }
  for(const btn of document.querySelectorAll('[data-orbit-rate]')){btn.disabled=active;btn.setAttribute('aria-pressed',+btn.dataset.orbitRate===(active?1:clock.speed));}
  const btn=document.querySelector('[data-orbit-play]');
  if(btn){btn.disabled=active;btn.textContent=clock.playing?'Ⅱ':'▶';btn.setAttribute('aria-label',clock.playing?'Pause orbit preview':'Play orbit preview');}
}

export function mountOrbit(options){
  context=options;clock.playing=!matchMedia('(prefers-reduced-motion: reduce)').matches;setClock(0);
  const update=(patch,refresh=false)=>{
    Object.assign(stateElements(),patch);context.changed(refresh);
    clearTimeout(timer);requestNumber++;pendingKey=null;timer=setTimeout(()=>{timer=null;drawOrbit();},90);
  };
  document.addEventListener('input',event=>{
    const el=event.target;
    if(el.hasAttribute('data-orbit-tle')){tleText=el.value;return;}
    if(!el.dataset.orbitElement||currentJob())return;
    const id=el.dataset.orbitElement, value=Number(el.value), settings=stateElements();
    const patch={[id]:value};
    if(id==='perigee'&&value>settings.apogee)patch.apogee=value;
    if(id==='apogee'&&value<settings.perigee)patch.perigee=value;
    for(const [key,v] of Object.entries(patch)){
      const range=document.querySelector('[data-orbit-element="'+key+'"]');
      if(v>Number(range.max))range.max=v;
      range.value=v;
      document.querySelector('[data-orbit-number="'+key+'"]').value=v;
    }
    update(patch);
    document.querySelectorAll('[data-orbit-preset]').forEach(btn=>btn.setAttribute('aria-pressed','false'));
  });
  document.addEventListener('change',event=>{
    const field=event.target,id=field.dataset.orbitNumber;
    if(!id || currentJob())return;
    if(field.value==='' || !field.checkValidity()){field.value=stateElements()[id];return;}
    const range=document.querySelector('[data-orbit-element="'+id+'"]');
    if(Number(field.value)>Number(range.max))range.max=field.value;
    range.value=field.value;range.dispatchEvent(new Event('input',{bubbles:true}));
  });
  document.addEventListener('click',async event=>{
    const b=event.target.closest('button');if(!b||b.disabled)return;
    const d=b.dataset;
    if('orbitPlay'in d){setClock(orbitalTime());clock.playing=!clock.playing;drawOrbit();}
    if('orbitRate'in d){setClock(orbitalTime());clock.speed=Number(d.orbitRate);drawOrbit();}
    if(d.orbitSource){source=d.orbitSource;tleError='';context.refresh();}
    if(d.orbitModel)update({model:d.orbitModel},true);
    if(d.orbitPreset){const {label,...p}=presets[d.orbitPreset];source='elements';setClock(0);const elements=stateElements(),epochSun=sunNode(elements.epoch);update({...p,anomaly:0,node:d.orbitPreset==='sso'?epochSun:0},true);}
    if('orbitImport'in d){
      const input=document.querySelector('[data-orbit-tle]'),value=input.value,original=stateElements();b.disabled=true;
      try{
        const data=await context.api('simulation/orbit',{elements:original,tle:value});
        if(input.isConnected && value===input.value && stateElements()===original){tleError='';setClock(0);update(data.elements,true);}
      }catch(error){tleError=error.message;setText('[data-orbit-error]',tleError);}
      finally{b.disabled=false;}
    }
  });
  const seek=time=>{if(!track||currentJob())return;setClock(Math.max(0,time));clock.playing=false;drawOrbit();};
  document.addEventListener('click',event=>{
    if(!event.target.hasAttribute('data-orbit-map') || !track || currentJob())return;
    const box=event.target.getBoundingClientRect(),lon=(event.clientX-box.left)/box.width*360-180,lat=90-(event.clientY-box.top)/box.height*180;
    let best=Infinity,index=0;
    track.points.forEach((point,i)=>{const distance=(wrap(point[0]-lon)*Math.cos(lat*rad))**2+(point[1]-lat)**2;
      if(distance<best){best=distance;index=i;}});
    seek((track.cycle+index/(track.points.length-1))*track.period);
  });
  document.addEventListener('keydown',event=>{
    if(!event.target.hasAttribute('data-orbit-map') || !track || currentJob())return;
    const delta={ArrowLeft:-1,ArrowRight:1,PageUp:10,PageDown:-10}[event.key];
    if(delta){event.preventDefault();seek(orbitalTime()+delta*track.period/100);}
  });
  document.addEventListener('wheel',event=>{
    if(!event.target.hasAttribute('data-orbit-globe'))return;
    event.preventDefault();viewport.zoom=Math.max(.58,Math.min(3,viewport.zoom*Math.exp(-.001*event.deltaY)));drawOrbit();
  },{passive:false});
  let drag=null;
  document.addEventListener('pointerdown',e=>{if(e.target.hasAttribute('data-orbit-globe')){drag={x:e.clientX,y:e.clientY,lon:viewport.lon,lat:viewport.lat};e.target.setPointerCapture(e.pointerId);}});
  document.addEventListener('pointermove',e=>{if(drag){viewport.lon=drag.lon-(e.clientX-drag.x)*.7;viewport.lat=Math.max(-89,Math.min(89,drag.lat+(e.clientY-drag.y)*.7));drawOrbit();}});
  document.addEventListener('pointerup',()=>{drag=null;});document.addEventListener('pointercancel',()=>{drag=null;});
  document.addEventListener('dblclick',e=>{if(e.target.hasAttribute('data-orbit-globe')){Object.assign(viewport,{lon:18,lat:20,zoom:1});drawOrbit();}});
  window.addEventListener('resize',drawOrbit);
  setInterval(()=>{if(context.state.view==='simulation'&&!document.hidden)drawOrbit();},200);
}
function sunNode(epoch){
  const days=Date.parse(epoch)/86400000-10957.5, g=(357.528+.9856003*days)*rad;
  const lambda=(280.460+.9856474*days+1.915*Math.sin(g)+.020*Math.sin(2*g))*rad;
  const ra=Math.atan2(Math.cos((23.439-.0000004*days)*rad)*Math.sin(lambda),Math.cos(lambda))/rad;
  return Math.round(((ra-22.5+360)%360)*100)/100;
}
