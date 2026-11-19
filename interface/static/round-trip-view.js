import {renderCommunication,stationState} from './communication.js';

export function planFor(state, command) {
  const choices=(state.testPlans?.plans||[]).filter(test=>test.command===command?.id);
  const id=state.selectedTests?.[command?.id];
  if (!id && !stationState(state).first_flight?.event) return null;
  return id==='' ? null : choices.find(test=>test.id===id)||choices[0];
}

export function testSelector(state, command, esc, icon) {
  const tests=(state.testPlans?.plans||[]).filter(test=>test.command===command.id);
  const selected=planFor(state,command);
  const controls='<div class="trip-test-picker"><label>Test <select id="trip-test"><option value="">Send only</option>'+
    tests.map(test=>'<option value="'+esc(test.id)+'" '+(selected?.id===test.id?'selected':'')+'>'+esc(test.name)+'</option>').join('')+
    '</select></label>'+(selected?'<button data-edit-trip="'+esc(command.id)+'" data-test-id="'+esc(selected.id)+'">'+icon('edit')+' Edit</button>':'')+
    '<button data-edit-trip="'+esc(command.id)+'">'+icon('plus')+' New test</button></div>';
  return stationState(state).first_flight?.event?controls:
    '<details class="first-test-menu" data-detail-key="ground-tests"><summary aria-label="Tests" title="Tests">···</summary>'+controls+'</details>';
}

export function describeStep(step) {
  if (step.kind==='event') return [step.app,step.event_id!=null?'EVS #'+step.event_id:'EVS',step.message].filter(Boolean).join(' · ');
  return [step.packet,step.field,step.op==='equals'?'= '+String(step.value):step.op==='received'?'received':step.op].filter(Boolean).join(' · ');
}

const time=value=>new Date(value*1000).toLocaleTimeString('en-GB',{hour12:false});
const names={waiting:'Waiting',passed:'Passed',timed_out:'Timed out',disconnected:'Disconnected',cancelled:'Stopped'};
const clip=(text,n)=>text.length<=n?text:text.slice(0,n-1)+'…';

function outputOff(state) {
  if(stationState(state).first_flight?.telemetry)return false;
  const run=(state.jobs||[]).findLast(job=>job.target===state.target && ['run','first-boot','stop'].includes(job.action) && job.status!=='failed');
  if(!run || run.action==='stop')return false;
  const stateLine=run.lines.findLast(line=>/Tlm output suppressed|Awaiting enable command|TO telemetry output enabled/i.test(line));
  return Boolean(stateLine && !/TO telemetry output enabled/i.test(stateLine));
}

function routeDiagram(state, command, steps, sent, esc, hex, icon) {
  const transport=state.catalog?.transport||{}, apps=state.catalog?.apps||[];
  const has=name=>apps.some(app=>app.name===name);
  const ingress=transport.command_port && has('ci_lab') ? 'ci_lab' : '';
  const egress=apps.find(app=>app.name.toLowerCase()===transport.subscription_app?.toLowerCase())?.name;
  const target={native:'Native',qemu:'Emulator',physical:'Physical board'}[state.target];
  const addressed=command?.app;
  const contact=stationState(state).first_flight;
  const reply=sent && contact?.receipt?.send_id===sent.event_id && contact.receipt.reply;
  const downlink=sent && contact?.downlink_receipt?.send_id===sent.event_id;
  const returned=Boolean(reply||downlink||steps.some(step=>step.observation));
  const off=outputOff(state), app=addressed===egress||addressed===ingress ? '' : addressed;
  const passive=app||['sample_app','sch_lab'].find(has);
  const faint=['sample_app','sch_lab'].filter(name=>has(name)&&name!==passive);
  const bus=state.workspace?.mission?.core_services?.some(service=>service.name==='SB');
  const up='M100 127 H159 V58 H216', down='M216 210 H159 V148 H100';
  const toApp='M275 82 V132 H643 V82', toEgress='M275 82 V186';
  const fromApp='M650 82 V140 H283 V186';

  function node(x,y,name,detail,glyph,status='configured') {
    const text=String(name||'');
    return `<g transform="translate(${x} ${y})" class="trip-node ${status}"><title>${esc(text+' · '+detail)}</title>
      <rect x="-59" y="-22" width="118" height="44" rx="5"/>
      <g class="trip-node-glyph" transform="translate(-50 -13)"><rect width="26" height="26" rx="4"/>${icon(glyph).replace('<svg','<svg x="5" y="5" width="16" height="16"')}</g>
      <text x="-18" y="-1">${esc(clip(text,13))}</text><text x="-18" y="13" class="node-meta">${esc(clip(detail,15))}</text></g>`;
  }
  function packet(path,kind) {
    return `<circle r="3.5" aria-hidden="true" class="trip-packet ${kind}" style="offset-path:path('${path}')"/>`;
  }
  const wire=d=>'<path d="'+d+'"/>';
  const wires=[
    ingress && wire(up),egress && wire(down), bus&&ingress&&egress&&wire(toEgress),
    bus&&ingress&&passive&&wire(toApp),bus&&egress&&passive&&wire(fromApp)
  ].filter(Boolean).join('');
  const returnedFromApp=Boolean(app && (reply || steps.some(({observation})=>observation &&
    (observation.app===app || String(observation.values?.['PacketID.AppName']||'').toLowerCase()===app.toLowerCase()))));
  return `<svg viewBox="0 0 760 268" class="trip-drawing" role="img" aria-label="Configured routes and observed UDP traffic">
    <defs><marker id="uplink-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="4" markerHeight="4" orient="auto"><path fill="var(--fs-accent)" d="M0 0 8 4 0 8Z"/></marker>
    <marker id="downlink-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="4" markerHeight="4" orient="auto"><path fill="var(--fs-success)" d="M0 0 8 4 0 8Z"/></marker></defs>
    <rect class="trip-frame" x="184" y="10" width="568" height="250" rx="6"/>
    <text class="trip-caption" x="8" y="20">GROUND</text><text class="trip-caption" x="198" y="21">cFS · ${esc(target)}</text>
    ${bus?'<g class="trip-bus"><rect x="212" y="130" width="520" height="14" rx="4"/><text x="221" y="161">Software Bus</text></g>':''}
    <g class="trip-wires">${wires}</g>
    ${faint.map((name,i)=>`<g class="trip-idle-node" transform="translate(${454+i*135} 210)"><path d="M0 -66 V-15"/><rect x="-49" y="-14" width="98" height="28" rx="4"/><text y="4">${esc(name)}</text></g>`).join('')}
    ${sent&&ingress?`<path class="trip-send-line" d="${up}" marker-end="url(#uplink-arrow)"><title>${esc('Sent '+sent.id+' · '+hex(sent.mid))}</title></path>${packet(up,'sending')}`:''}
    ${returned && egress?`<path class="trip-proof-line" d="${down}" marker-end="url(#downlink-arrow)"/>${packet(down,'returning')}`:''}
    ${node(69,138,'Ground','This computer','antenna','ground')}
    ${ingress?node(275,58,ingress,'Commands in','arrow-down'):''}
    ${egress?node(275,210,egress,off?'Output off':'Telemetry out','send',off?'off':downlink?'seen':'configured'):''}
    ${passive?node(643,58,passive,app?'Destination':'Mission app','cube',returnedFromApp?'seen':'configured'):''}
    ${transport.command_port?`<text class="trip-caption" x="115" y="117">UDP ${Number(transport.command_port)}</text>`:''}
    ${transport.telemetry_port?`<text class="trip-caption" x="115" y="166">UDP ${Number(transport.telemetry_port)}</text>`:''}
    </svg>`;
}

function evidenceLine(step, esc, hex) {
  const observation=step.observation;
  if (!observation) return '';
  const header=[observation.name,hex(observation.mid),'seq '+observation.sequence,time(observation.received_at)].join(' · ');
  return ' <b>'+esc(header)+'</b><code>'+esc(JSON.stringify(observation.values))+'</code>';
}

function journal(sent, runs, selected, contact, esc, hex){
  return '<section class="trip-journal"><header>Sent <span>Flight observations</span></header><div>'+sent.slice(0,32).map(item=>{
    const run=runs.find(r=>r.id===item.event_id);
    const first=contact.receipt?.send_id===item.event_id && contact.receipt;
    const downlink=contact.downlink_receipt?.send_id===item.event_id && contact.downlink_receipt;
    const receipt=first?.reply ? 'EVS · '+first.message+(first.increase?' · CommandCounter '+first.baseline+' → '+first.count:'') : downlink?'Telemetry · MID '+hex(downlink.mid):'';
    return '<details '+(selected===item.event_id?'class="current"':'')+' data-detail-key="sent-'+item.event_id+'"><summary><strong>'+esc(item.id)+'</strong><span class="trip-result" data-status="'+(run?.status||(receipt?'passed':'sent'))+'">'+
      (run?names[run.status]+' · '+run.matched+'/'+run.steps.length:receipt?esc(receipt):'Sent')+'</span><time>'+time(item.sent_at)+'</time></summary>'+
      '<button data-inspect-send="'+item.event_id+'">View observation</button><code>'+hex(item.mid)+' · '+esc(item.hex)+'</code>'+(run?'<ol>'+run.steps.map(step=>'<li>'+esc(describeStep(step))+evidenceLine(step,esc,hex)+'</li>').join('')+'</ol>':'')+'</details>';
  }).join('')+(sent.length?'':'<span class="trip-empty-track" aria-label="Empty send history"></span>')+'</div></section>';
}

export function tripPanel(state,command,helpers){
  const {esc,hex,icon}=helpers;
  const ground=stationState(state);
  const system=state.groundMode==='system';
  const history=(ground.commands||[]).filter(c=>!c.automatic).slice().reverse();
  const sent=history.filter(c=>c.id===command?.id);
  const tests=ground.runs||[], plan=planFor(state,command);
  const inspected=sent.find(item=>item.event_id===state.inspectedSend);
  const last=inspected||sent[0], run=tests.find(r=>r.id===last?.event_id);
  const showRun=run && (inspected||run.status==='waiting'||run.test_id===plan?.id);
  const steps=(showRun?run.steps:plan?.steps)||[];
  const contact=ground.first_flight||{};
  const receipt=last && contact.receipt?.send_id===last.event_id ? contact.receipt : null;
  const observed=showRun && steps.filter(step=>step.observation).at(-1)?.observation;
  const caption=observed?observed.app+' → Ground · MID '+hex(observed.mid):
    receipt?.reply?command.app+' → Ground · EVS':
    last && contact.downlink_receipt?.send_id===last.event_id?'to_lab → Ground · MID '+hex(contact.downlink_receipt.mid):
    outputOff(state)?'to_lab output off':
    last?'Ground → ci_lab · MID '+hex(last.mid):'';
  const header='<header class="trip-modes"><div role="group" aria-label="Ground view">'+
    ['trip','system'].map((mode,i)=>'<button data-ground-mode="'+mode+'" aria-pressed="'+((system?'system':'trip')===mode)+'">'+(i?'System overview':'Round trip')+'</button>').join('')+'</div>'+(system?'':'<span class="trip-legend"><i></i> Command <i></i> Telemetry</span>')+'</header>';
  if(system)return '<div class="trip-card system">'+header+renderCommunication(state,helpers)+'</div>';
  return '<div class="trip-card">'+header+(command?testSelector(state,command,esc,icon):'')+
    '<div class="trip-canvas">'+routeDiagram(state,command,steps,last,esc,hex,icon)+'</div>'+
    '<div class="trip-observations">'+(showRun?'<strong data-status="'+run.status+'">'+names[run.status]+' · '+run.matched+'/'+steps.length+'</strong>':'')+
    (steps.length?'<ol>'+steps.map(step=>'<li class="'+(step.observation?'matched':'')+'">'+(step.observation?'✓ ':'')+esc(describeStep(step))+'</li>').join('')+'</ol>':
    '<span>'+esc(caption)+'</span>')+
    (showRun&&run.status==='waiting'?'<button data-stop-trip="'+run.id+'">Stop test</button>':'')+'</div></div>'+journal(history,tests,last?.event_id,contact,esc,hex);
}
