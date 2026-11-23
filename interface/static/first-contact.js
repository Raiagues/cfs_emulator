import {api} from './api.js';
import {escapeHtml as esc, paint} from './dom.js';
import {navigate, stepUrl} from './router.js';
import {icon} from './ui.js';
import {onUpdate} from './updates.js';

const hex = value => Number.isInteger(value) ? '0x'+value.toString(16).toUpperCase() : '';
const title = id => id?.endsWith('_OUTPUT_ENABLE_CC') ? 'ENABLE_OUTPUT' : id?.replace(/^SAMPLE_APP_|_CC$/g,'') || '';
const stages = ['Telemetry on', 'First command', 'Answer'];
const targets = {native:'Native', qemu:'Emulator', physical:'Board'};

function node(x,y,label,note,glyph,lit=false) {
  return `<g class="contact-node ${lit?'lit':''}" transform="translate(${x} ${y})"><rect width="130" height="49" rx="5"/>
    <g transform="translate(12 14)"><svg width="18" height="18" viewBox="0 0 24 24">${icon(glyph).replace(/^<svg[^>]*>|<\/svg>$/g,'')}</svg></g>
    <text x="39" y="20">${esc(label)}</text><text class="node-note" x="39" y="36">${esc(note)}</text></g>`;
}

function diagram(catalog, command, mid, target, progress) {
  const routes=catalog.first_contact_routes||{}, ingress=routes.ingress, egress=routes.egress;
  const recipient=routes.commands?.[command?.id]?.[0], packet=routes.returns?.[mid];
  const apps=new Set((catalog.apps||[]).map(app=>app.name)), port=catalog.transport||{};
  const sample=recipient && recipient.app!==egress?.app ? recipient.app : (apps.has('sample_app')?'sample_app':'');
  const down=Boolean(egress && packet?.publishers?.length), up=Boolean(ingress && recipient);
  const toSender=recipient?.app===egress?.app;
  const upPath='M147 137 H199 V72 H295 V133 '+(toSender?'V188':'H637 V97');
  const producerStart={ci_lab:'M305 97',to_lab:'M305 188',sample_app:'M647 97',cfe_evs:'M647 188'};
  const returnPath=down && producerStart[packet.app]
    ? producerStart[packet.app]+' V145 H305 V212 H199 V163 H147' : '';
  const caption=progress || (mid ? 'Telemetry received · MID '+hex(mid) : 'Telemetry off');
  const reference=ref=>ref ? esc(ref.path)+':'+esc(ref.line) : '';
  const routeInfo=recipient ? `<span>${esc(ingress?.app)} → Software Bus → ${esc(recipient.app)} · ${hex(recipient.mid)} · ${esc(recipient.pipe)}</span>
    <code>${reference(ingress?.publish)} · ${reference(recipient.source)}${(recipient.via||[]).map(ref=>' · '+reference(ref)).join('')}</code>` : '<span>Command subscription unavailable in this build.</span>';
  return `<section class="contact-trip"><header><strong>Round trip</strong><span><i></i> command <i></i> telemetry</span></header>
    <svg class="contact-svg" viewBox="0 0 810 266" role="img" aria-label="Command and telemetry path derived from the deployed flight catalog">
    <text class="area-label" x="14" y="23">GROUND</text><rect class="flight-area" x="176" y="11" width="624" height="240" rx="6"/>
    <text class="area-label" x="189" y="16">cFS · ${esc(targets[target])}</text>
    <rect class="software-bus" x="220" y="127" width="525" height="14" rx="3"/><text class="port-label" x="230" y="158">Software Bus</text>
    ${up?`<path class="command-route" data-up d="${upPath}"/>`:''}
    ${returnPath?`<path class="return-route" data-down d="${returnPath}"/>`:''}
    <text class="port-label" x="145" y="124">UDP ${esc(port.command_port)}</text><text class="port-label" x="145" y="180">UDP ${esc(port.telemetry_port)}</text>
    ${node(17,121,'Ground','This computer','antenna')}
    ${ingress?node(230,48,ingress.app,'commands in','inbox'):''}
    ${sample?node(572,48,sample,'example app','cube'):''}
    ${egress?node(230,188,egress.app,mid?'telemetry out':'output off','inbox'):''}
    ${apps.has('sch_lab')?'<text class="passive" x="455" y="215">sch_lab</text>':''}
    ${apps.has('cfe_evs')?node(572,188,'cfe_evs','event messages','layers'):''}
    ${down?`<text class="producer" x="454" y="176">${esc(packet.app)} · ${hex(mid)}</text>`:''}
    <circle class="contact-dot" r="5" style="display:none"/></svg>
    <div class="contact-playback"><span class="play-bars">${'<i></i>'.repeat(5)}</span><span data-caption>${esc(caption)}</span>
      <button data-play title="Pause or resume replay" aria-label="Pause or resume replay" hidden>Ⅱ</button><button data-step title="Next hop" aria-label="Next hop" hidden>›</button></div>
    <details class="contact-sources"><summary>Route in cFS</summary>${routeInfo}
    ${egress?`<span>${down?esc(packet.packet)+' → ':''}${esc(egress.pipe)} → ${esc(egress.app)} → Ground</span><code>${reference(egress.subscribe)} · ${reference(egress.send)} · ${esc(egress.table||'')}</code>`:''}
    ${(packet?.publishers||[]).map(p=>'<code>'+reference(p)+'</code>').join('')}</details></section>`;
}

function counters(station, enable, catalog) {
  const packets=station.packets||[];
  const definitions=new Map((catalog?.packets||[]).map(p=>[p.mid,p]));
  const fields=packets.filter(p=>['ci_lab','sample_app'].includes(p.app) && definitions.get(p.mid)?.id.includes('HK'));
  if(!station.first_flight?.telemetry) return `<div class="contact-empty">${icon('antenna')}<strong>No telemetry yet</strong><button data-pick="${esc(enable||'')}">Select ENABLE_OUTPUT</button></div>`;
  const rows=fields.map(p=>{
    const values=Object.entries(p.values).filter(([key])=>/IngestPackets|IngestErrors|CommandCounter|CommandErrorCounter/.test(key));
    return values.length ? `<section><h3>${esc(p.app)} <small>${esc(definitions.get(p.mid).id)}</small></h3>${values.map(([key,val])=>`<div class="contact-metric"><code>${esc(key.split('.').at(-1))}</code><b>${esc(val)}</b></div>`).join('')}</section>`:'';
  }).join('');
  return rows || '<p>Receiving telemetry · waiting for housekeeping</p>';
}

export function mountFirstContact(root,{state,startJob}){
  const target=state.target;
  let catalog=null, station={}, selected='', address='', error='', busy=false, closed=false, refreshBusy=false;
  let attempted=false, wasRunning=null, sent=null, replay=null, lastReplay='', frame=0, clock=0, paused=false, timer, stepTimer;
  let autoNext=false, lastDeployment=null, lastSession=null, refreshAgain=false;
  function flightRunning(){
    if(target==='qemu')return state.hardware?.qemu?.flight_running;
    if(target==='physical')return state.hardware?.physical?.last_probe?.flight_running;
    return state.hardware?.native?.running;
  }
  function acceptStation(next){
    const session=next.connected && next.target===target ? next.communication?.since : null;
    if(lastSession!==null && session!==lastSession){
      selected='';address='';sent=null;autoNext=false;lastReplay='';
      clearTimeout(timer);cancelMotion();
    }
    lastSession=session;
    station=next.target===target?next:{};
    if(station.connected && !address)address=station.first_flight?.return_host||'';
  }
  function cancelMotion(){cancelAnimationFrame(frame);frame=0;clearTimeout(stepTimer);replay=null;paused=false;}
  function tick(now){
    frame=0;
    if(closed || !replay)return;
    if(!paused)replay.elapsed+=Math.min(120,now-clock);
    clock=now;
    const svg=root.querySelector('.contact-svg'), dot=svg?.querySelector('.contact-dot');
    const t=Math.min(1,replay.elapsed/replay.duration), down=t>=0.58;
    const path=svg?.querySelector(down?'[data-down]':'[data-up]');
    if(path && dot){
      const p=path.getPointAtLength(path.getTotalLength()*(down?(t-.58)/.42:t/.58));
      dot.style.display='';dot.setAttribute('cx',p.x);dot.setAttribute('cy',p.y);
      dot.classList.toggle('down',down);
    }
    const label=t<.2?'Ground → '+replay.ingress:t<.4?replay.ingress+' → Software Bus':t<.58?'Software Bus → '+replay.app:t<.8?replay.producer+' → Software Bus → '+replay.egress:replay.egress+' → Ground';
    const caption=root.querySelector('[data-caption]');
    if(caption)caption.textContent='Route replay · '+label;
    root.querySelectorAll('.play-bars i').forEach((el,i)=>el.classList.toggle('on',i<=Math.floor(t*5)));
    const play=root.querySelector('[data-play]'), step=root.querySelector('[data-step]');
    if(play){play.hidden=false;play.textContent=paused?'▶':'Ⅱ';step.hidden=false;}
    if(t>=1){const complete=replay.complete;cancelMotion();if(complete)finish();else {selected=station.first_flight.noop_command;draw();}return;}
    if(!paused)frame=requestAnimationFrame(tick);
  }
  function finish(){
    draw();
    if(autoNext){autoNext=false;stepTimer=setTimeout(()=>{if(!closed)navigate(stepUrl('app',location,target));},1000);}
  }
  function observe(){
    const f=station.first_flight||{}, answer=f.answer&&f.receipt?.increase&&f.receipt?.reply;
    const r=answer?f.receipt:f.downlink_receipt;
    if(!r)return;
    const id=station.communication?.since+'/'+r.send_id;
    if(lastReplay===id || (!sent && !replay))return;
    const command=answer?f.noop_command:f.enable_command, mid=answer?r.event_mid:r.mid;
    if(!sent || sent.command!==command || sent.eventId!==r.send_id || sent.session!==station.communication?.since)return;
    const routes=catalog?.first_contact_routes, sub=routes?.commands?.[command]?.[0], returned=routes?.returns?.[mid];
    lastReplay=id;cancelMotion();clearTimeout(timer);sent=null;
    if(!sub || !routes.ingress || !routes.egress || !returned?.publishers?.length){if(answer)finish();else selected=f.noop_command;return;}
    const duration=matchMedia('(prefers-reduced-motion: reduce)').matches?1:2600;
    replay={command,mid,elapsed:0,duration,app:sub.app,ingress:routes.ingress.app,egress:routes.egress.app,producer:returned.app,complete:!!answer};
    clock=performance.now();frame=requestAnimationFrame(tick);
  }
  function draw(){
    if(closed)return;
    const f=station.first_flight||{}, cmds=catalog?.commands||[];
    const enable=cmds.find(c=>c.app==='to_lab' && c.id.endsWith('_OUTPUT_ENABLE_CC'));
    const noop=cmds.find(c=>c.app==='sample_app' && c.id.endsWith('_NOOP_CC'));
    const enabled=!!f.downlink_receipt, answer=!!f.answer;
    const choice=replay?.command || selected || (enabled?noop?.id:enable?.id);
    const command=cmds.find(c=>c.id===choice), field=command?.fields?.find(f=>f.format==='s');
    const linked=station.connected && station.target===target;
    const baseline=command?.id===noop?.id && !f.baseline_apps?.includes('sample_app');
    const waiting=!!sent && !error;
    const completeCommand=linked && (field && enabled || command?.id===noop?.id && answer);
    const disabled=busy||!!replay||waiting||completeCommand||!command||linked && (field && !address || baseline || command.id===noop?.id && !enabled);
    const stage=answer?2:enabled?1:0;
    const names=[enable,noop].filter(Boolean);
    const entries=names.map(c=>`<div class="contact-tree"><strong>⌄ ${esc(c.app)} <small>${hex(c.mid)}</small></strong>
      <button data-pick="${esc(c.id)}" aria-pressed="${choice===c.id}">${icon('send')}<code>${esc(title(c.id))}</code><small>FC ${c.code}</small></button></div>`).join('');
    const last=(station.commands||[]).filter(c=>names.some(n=>n.id===c.id)&&!c.automatic).slice(-8).reverse();
    const mid=replay?.mid || (command?.id===noop?.id && answer?f.receipt?.event_mid:f.downlink_receipt?.mid);
    const note=error || (waiting?'Waiting for flight telemetry…':baseline && linked?'Waiting for sample_app housekeeping…':'');
    paint(root,`<div class="contact-layout"><aside class="contact-browser"><header>Commands <small>${catalog?.build_fingerprint?'↻ from build':''}</small></header>${entries}</aside>
      <main class="contact-main"><div class="contact-stages">${stages.map((s,i)=>`<div data-fact="${i<stage||answer?'done':i===stage?'current':'waiting'}"><i>${i<stage||answer?'✓':i+1}</i><span>${s}<code>${['to_lab · ENABLE_OUTPUT','sample_app · NOOP','INFO + CommandCounter ↑'][i]}</code></span></div>`).join('')}</div>
      <form class="contact-command"><div><small>${esc(command?.app||'')} ${command?'· FC '+command.code:''}</small><h2>${esc(title(command?.id)||'Loading commands…')}</h2><span>${command?(field?'telemetry → ground':'answers, changes nothing'):''}</span></div>
      ${field?`<label><span><strong>${esc(field.name)}</strong><small>char[${esc(field.count)}] · where to send</small></span><input name="destination" aria-label="Destination IP" value="${esc(address)}" maxlength="${field.count-1}" required></label>`:'<div class="no-parameters">No parameters</div>'}
      <div class="contact-size"><span>▪▪▪▪</span>${esc(command?.size??'–')} B</div>
      <button type="submit" class="contact-send" ${disabled?'disabled':''}>${icon('send')}${!linked?(busy?'Connecting…':wasRunning===false?'Run cFS':'Connect'):waiting?'Sent':completeCommand?'Received':'Send'}</button></form>
      ${note?`<p class="contact-note" role="status" data-error="${!!error}">${esc(note)}</p>`:''}
      ${catalog?diagram(catalog,command,mid,target,replay?'Route replay':enabled?'Telemetry received · MID '+hex(mid):'Telemetry off'):''}
      <section class="contact-history"><header>Sent <span>Ground　 ci_lab　 app　 to_lab　 Ground</span> Came back</header>
      ${last.map(c=>{const down=f.downlink_receipt?.send_id===c.event_id, nr=f.receipt?.send_id===c.event_id&&f.receipt.reply, got=down||nr;
        return `<div><strong>${esc(c.app)} ${esc(title(c.id))}</strong><span class="history-dots">${got?'● ─ ● ─ ●':'● · · · ○'}</span><span>${nr?esc(f.receipt.message)+(f.receipt.increase?' · '+f.receipt.baseline+' → '+f.receipt.count:''):down?'Telemetry received · MID '+hex(f.downlink_receipt.mid):'Awaiting response'}</span></div>`;}).join('')||'<div class="empty-history"></div>'}</section>
      ${answer?`<a class="contact-next" href="${stepUrl('app',location,target)}">Create app →</a>`:''}</main>
      <aside class="contact-telemetry"><header>Telemetry <small>${f.telemetry?'● on':'● off'}</small></header>${counters(station,enable?.id,catalog)}</aside></div>`);
    if(replay){cancelAnimationFrame(frame);frame=0;tick(performance.now());}
  }
  async function connect(){
    busy=true;attempted=true;error='';draw();
    try{const data=await api('ground/start',{target});if(closed)return;acceptStation(data);}
    catch(e){if(!closed)error=e.message;}
    finally{busy=false;draw();}
  }
  async function refresh(){
    if(closed)return;
    if(refreshBusy){refreshAgain=true;return;}
    refreshBusy=true;
    try{
      const current=await api('ground');if(closed)return;
      const deployment=state.jobs.filter(j=>j.target===target&&['run','first-boot','stop','shutdown'].includes(j.action)&&!['failed','cancelled'].includes(j.status)).at(-1);
      const changed=deployment && lastDeployment!==deployment.id;
      if(changed){lastDeployment=deployment.id;attempted=false;error='';if(!current.connected || current.target!==target){selected='';sent=null;autoNext=false;cancelMotion();}}
      wasRunning=flightRunning();
      if(deployment && ['stop','shutdown'].includes(deployment.action))wasRunning=false;
      const launching=deployment && ['run','first-boot'].includes(deployment.action) && deployment.status==='running' && !deployment.operation_complete;
      if(!catalog || changed || current.connected && current.target===target && current.build_fingerprint!==catalog.build_fingerprint)
        catalog=await api('ground/catalog?target='+target);
      if(closed)return;
      acceptStation(current);
      if(station.connected)error=station.error||error;
      else if(!busy && !attempted && !launching && wasRunning!==false && catalog?.commands?.length){await connect();}
      if(closed)return;observe();draw();
    }catch(e){if(!closed){error=e.message;draw();}}
    finally{refreshBusy=false;if(refreshAgain&&!closed){refreshAgain=false;void refresh();}}
  }
  async function submit(e){
    e.preventDefault();if(closed||busy||sent||replay)return;
    if(!station.connected || station.target!==target){
      if(wasRunning===false){
        busy=true;error='';draw();
        try{await startJob('run',{target},false);attempted=false;}
        catch(e){error=e.message;}
        finally{busy=false;draw();}
      }
      else await connect();
      return;
    }
    const f=station.first_flight, id=selected || (f.downlink_receipt?f.noop_command:f.enable_command);
    const field=catalog.commands.find(c=>c.id===id)?.fields?.find(f=>f.format==='s');
    if(id===f.noop_command && (!f.downlink_receipt || !f.baseline_apps?.includes('sample_app')))return;
    busy=true;sent={command:id,eventId:null,session:station.communication?.since};autoNext=id===f.noop_command;error='';draw();
    try{
      const result=await api('ground/send',{target,command_id:id,values:field?{[field.name]:address}:{}});
      if(sent?.command===id)sent.eventId=result.event_id;
    }
    catch(e){sent=null;autoNext=false;error=e.message;}
    finally{busy=false;clearTimeout(timer);if(sent)timer=setTimeout(()=>{if(sent?.command===id){sent=null;autoNext=false;error='No matching response yet. Check flight output or send again.';draw();}},30000);await refresh();}
  }
  function click(e){
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.pick && !sent && !replay){selected=b.dataset.pick;error='';draw();}
    if(b.hasAttribute('data-play')&&replay){paused=!paused;clock=performance.now();cancelAnimationFrame(frame);tick(clock);}
    if(b.hasAttribute('data-step')&&replay){replay.elapsed=Math.min(replay.duration,(Math.floor(replay.elapsed/(replay.duration/5))+1)*replay.duration/5);clock=performance.now();cancelAnimationFrame(frame);tick(clock);}
  }
  const input=e=>{if(e.target.name==='destination'){address=e.target.value;draw();}};
  root.addEventListener('click',click);root.addEventListener('submit',submit);root.addEventListener('input',input);
  const off=onUpdate(['ground','hardware','jobs'],refresh), poll=setInterval(refresh,1600);
  draw();void refresh();
  return {close(){closed=true;off();cancelMotion();clearInterval(poll);clearTimeout(timer);root.removeEventListener('click',click);root.removeEventListener('submit',submit);root.removeEventListener('input',input);}};
}
