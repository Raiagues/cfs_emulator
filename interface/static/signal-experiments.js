import {icon} from './ui.js';

const scenarios = [['orbit','One orbit','compass'],['eclipse','Eclipse entry','moon'],['dropout','Sensor drops out','pulse']];
const number = n => Number.isFinite(n) ? Number(n.toFixed(3)).toString() : '—';

export function pythonPanel(state,esc,active,reason) {
  const session=state.simulation;
  const device=session?.available.find(d=>d.id===state.selectedDevice);
  const path=state.signalScript?.path||device?.script||session?.source||'';
  const lines=state.jobs.filter(j=>['simulate','simulate-preview'].includes(j.action)&&!j.scenario).at(-1)?.lines||[];
  return `<section class="signal-script-card"><header><select aria-label="Python source" data-signal-script>${(session?.sources||[]).map(file=>`<option ${file===path?'selected':''}>${esc(file)}</option>`).join('')}</select>
    <button data-signal-source="${esc(path)}" title="Open source" aria-label="Open source">${icon('code')}</button>
    <button data-run-signal-test ${active?.action==='simulate'||!session?.settings.sensors.some(s=>s.enabled)?'disabled':''}>${icon('play')}${active?.action==='simulate-preview'?'Stop dry run':'Dry run'}</button>
    <button ${active?.action==='simulate'?'data-board-stop="simulate"':'data-signal-begin'} ${reason||active?.action==='simulate-preview'?'disabled':''}>${icon('send')}${active?.action==='simulate'?'Stop sending':'Send to QEMU'}</button></header>
    <pre><code>${esc(state.signalScript?.content||'')}</code></pre></section>
    <section class="signal-console"><h3>Console</h3><pre data-signal-console>${esc(lines.slice(-24).join('\n'))}</pre></section>`;
}

function matchingReads(state,device,key,latestJob) {
  if(state.ground?.target!=='qemu'||!state.ground?.connected)return [];
  const current=state.workspace?.builds?.qemu;
  if(current && (!current.current||state.ground.build_fingerprint!==current.fingerprint))return [];
  const prop=device.properties[key], values=[];
  for(const app of state.workspace?.apps||[]){
    const registration=state.workspace.project.apps.find(a=>a.name===app.name);
    for(const reader of app.manifest?.sensors||[]){
      if(registration?.sensors?.[reader.name]!==device.id)continue;
      const packet=state.ground.packets?.find(p=>p.app===app.name && p.mid===reader.tlm_mid);
      if(!packet||packet.received_at<(latestJob?.started||0)||packet.values?.Valid!==1||packet.values.Status!==0)continue;
      const value=packet.values[prop.telemetry_field];
      if(Number.isFinite(value))values.push({app:app.name, value:value/prop.scale});
    }
  }
  return values;
}

export function qemuPanel(state,esc) {
  const devices=state.simulation?.available||[];
  const last=state.jobs.filter(j=>j.target==='qemu'&&j.action==='simulate'&&j.samples).at(-1);
  const rows=devices.map(device=>{
    const active=last?.samples.devices?.find(d=>d.id===device.id);
    const cell=(label,text)=>`<div><b>${esc(label)}</b><small>${esc(text)}</small></div>`;
    const props=Object.entries(device.properties);
    const python=[],qmp=[],registers=[],reads=[];
    for(const [key,prop] of props){
      const value=active?.values[key], register=prop.register;
      python.push(cell(Number.isFinite(value)?number(value)+' '+prop.unit:'—', key));
      qmp.push(cell(Number.isFinite(value)?String(Math.round(value*prop.scale)):'—',prop.raw_unit));
      registers.push(cell(register==null?'—':'0x'+register.toString(16).padStart(2,'0'), key));
      const observed=matchingReads(state,device,key,last);
      reads.push(observed.length?observed.map(x=>cell(number(x.value)+' '+prop.unit,x.app)).join(''):cell('—',prop.telemetry_field));
    }
    return `<section class="chain-device"><header><b>${esc(device.name||device.id)}</b><code>${esc(device.qom_path)}</code><small>${esc(device.bus)} · 0x${device.address.toString(16)}</small></header>
      <div class="value-chain">${[python,qmp,registers,reads].map(c=>'<div>'+c.join('')+'</div>').join('')}</div></section>`;
  });
  return `<div class="value-chain chain-head">${['Python','qom-set','Device register','cFS read'].map(s=>'<span>'+s+'</span>').join('')}</div>${rows.join('')||'<div class="signal-empty">No devices</div>'}`;
}

export function scenarioPanel(state,esc,active) {
  const name=state.signalScenario||'orbit';
  const enabled=state.simulation?.settings.sensors.filter(s=>s.enabled)||[];
  const device=state.selectedDevice||enabled[0]?.device;
  const job=state.jobs.filter(j=>j.action==='simulate-preview'&&j.device===device&&j.scenario===name).at(-1);
  const result=job?.scenario_result;
  const outputs=Object.keys(result?.units||{});
  const key=outputs.includes(state.signalTestOutput)?state.signalTestOutput:outputs[0];
  let chart='';
  if(result && key){
    const points=result.samples.map(s=>({t:s.time, sent:s.sent[key], read:s.read[key]}));
    const values=points.flatMap(p=>[p.sent,p.read].filter(Number.isFinite));
    if(values.length){
      const min=Math.min(...values),max=Math.max(...values),span=max-min||1;
      const makePath=field=>{
        let drawing=false, path='';
        for(const p of points){
          if(!Number.isFinite(p[field])){drawing=false;continue;}
          const x=(p.t-points[0].t)/(points.at(-1).t-points[0].t)*1000,y=137-(p[field]-min)/span*117;
          path+=(drawing?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)+' ';drawing=true;
        }
        return path;
      };
      chart=`<div class="signal-check-graph"><output>${number(max)}<br>${number(min)}</output><svg viewBox="0 0 1000 150" preserveAspectRatio="none" role="img" aria-label="Sent and local HAL read"><path class="sent-trace" d="${makePath('sent')}"/><path class="read-trace" d="${makePath('read')}"/></svg></div>`;
    }
  }
  return `<nav class="scenario-choices" aria-label="Scenario">${scenarios.map(([id,title,glyph])=>`<button data-signal-scenario="${id}" aria-pressed="${id===name}">${icon(glyph)}${title}</button>`).join('')}<button class="scenario-run" data-run-signal-scenario ${active||!device?'disabled':''}>${icon('play')}Run</button></nav>
    <section class="signal-scenario-card"><header><strong>${esc(device||'Sensor')}</strong><span>Python sent</span><span>Local HAL read</span>${outputs.length?`<select aria-label="Output" data-test-output>${outputs.map(k=>`<option ${k===key?'selected':''}>${esc(k)}</option>`).join('')}</select><small>${esc(result.units[key])}</small>`:''}</header>
    ${chart||`<div class="signal-empty">${job?.status==='running'?'Running':esc(job?.error||'Awaiting run')}</div>`}</section>
    <section class="signal-checks"><h3>Checks</h3>${Object.entries(result?.checks||{}).map(([label,passed])=>`<div><strong data-passed="${passed}">${passed?'✓':'×'}</strong>${esc(label)}</div>`).join('')}</section>`;
}
