import {renderCommunication} from './communication.js';

export function planFor(state, command) {
  const choices=(state.testPlans?.plans||[]).filter(test=>test.command===command?.id);
  const id=state.selectedTests?.[command?.id];
  if (!id && !state.ground?.first_flight?.event) return null;
  return id==='' ? null : choices.find(test=>test.id===id)||choices[0];
}

export function testSelector(state, command, esc, icon) {
  const tests=(state.testPlans?.plans||[]).filter(test=>test.command===command.id);
  const selected=planFor(state,command);
  const controls='<div class="trip-test-picker"><label>Test <select id="trip-test"><option value="">Send only</option>'+
    tests.map(test=>'<option value="'+esc(test.id)+'" '+(selected?.id===test.id?'selected':'')+'>'+esc(test.name)+'</option>').join('')+
    '</select></label>'+(selected?'<button data-edit-trip="'+esc(command.id)+'" data-test-id="'+esc(selected.id)+'">'+icon('edit')+' Edit</button>':'')+
    '<button data-edit-trip="'+esc(command.id)+'">'+icon('plus')+' New test</button></div>';
  return state.ground?.first_flight?.event?controls:
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
  if(state.ground?.target===state.target && state.ground?.first_flight?.telemetry)return false;
  const run=(state.jobs||[]).findLast(job=>job.target===state.target && ['run','first-boot','stop'].includes(job.action) && job.status!=='failed');
  if(!run || run.action==='stop')return false;
  const stateLine=run.lines.findLast(line=>/Tlm output suppressed|Awaiting enable command|TO telemetry output enabled/i.test(line));
  return Boolean(stateLine && !/TO telemetry output enabled/i.test(stateLine));
}

function routeDiagram(state, command, steps, sent, esc, hex) {
  const count=Math.max(1,steps.length), cols=Math.min(count,3), rows=Math.ceil(count/cols);
  const height=292+76*(rows-1), groundX=69, groundY=height/2;
  const target={native:'Native',qemu:'Emulator',physical:'Physical board'}[state.target];
  const transport=state.catalog?.transport||{};
  const apps=state.catalog?.apps||[];
  const ingress=transport.command_port && apps.find(app=>app.name==='ci_lab')?.name;
  const egress=apps.find(app=>app.name.toLowerCase()===transport.subscription_app?.toLowerCase())?.name;
  const bus=state.workspace?.mission?.core_services?.find(service=>service.name==='SB');
  function node(x,y,title,detail,status,tip,width=112) {
    const left=-width/2;
    return '<g class="trip-node '+status+'" transform="translate('+x+' '+y+')"><title>'+esc(tip)+'</title><rect x="'+left+'" y="-23" width="'+width+'" height="46" rx="5"/><text y="-3">'+esc(clip(title,17))+'</text><text class="node-meta" y="13">'+esc(clip(detail,20))+'</text><circle cx="'+(left+8)+'" cy="-15" r="2.5"/></g>';
  }
  const upY=83, returnY=height-62;
  const receipt=state.ground?.target===state.target && state.ground.first_flight?.receipt;
  const reply=sent && receipt?.send_id===sent.event_id && receipt.reply;
  let lines='',observations='';
  (steps.length?steps:[null]).forEach((step,i)=>{
    const x=351+(i%cols+.5)*(403/cols), y=upY+Math.floor(i/cols)*76;
    const observed=step?.observation;
    if(observed){
      const baseline=height-22-(i%3)*4, gutter=x-60, lead=y+29;
      lines+='<path class="trip-proof-line" d="M'+x+' '+(y+23)+' V'+lead+' H'+gutter+' V'+baseline+' H'+groundX+' V'+(groundY+29)+'" marker-end="url(#downlink-arrow)"><title>'+
        esc('Received '+observed.name+' · '+hex(observed.mid)+' · sequence '+observed.sequence+' · '+time(observed.received_at))+'</title></path>';
    }
    const standby=!step && command?.app===egress && apps.find(app=>app.name==='sample_app');
    const title=step?(step.kind==='event'?step.app:(state.catalog?.packets||[]).find(p=>p.id===step.packet)?.app||step.packet):standby?.name||command?.app||'cFS';
    const detail=step?(step.kind==='event'?(observed?'EVS #'+observed.values['PacketID.EventID']:'EVS '+(step.event_id??step.message)):step.field||'Telemetry packet'):standby?'Example app':'Command destination';
    observations+=node(x,y,title,detail,observed||reply?'seen':'pending',step?describeStep(step):'Addressed by MID');
  });
  const incoming=ingress?node(272,upY,ingress,'Commands in','configured','Command interface in the compiled mission'): '';
  const off=outputOff(state);
  const outgoing=egress?node(272,returnY,egress,off?'Output off':'Telemetry out',off?'off':'configured','Downlink configured in the compiled mission'): '';
  const busY=height-122;
  const backbone=bus?'<g class="trip-bus"><rect x="214" y="'+busY+'" width="525" height="17" rx="4"/><text x="220" y="'+(busY+31)+'">Software Bus</text></g>':'';
  const uplink=sent?'<path class="trip-send-line" d="M128 '+groundY+' H166 V'+upY+' H205" marker-end="url(#uplink-arrow)"><title>'+esc('Sent '+sent.id+' · '+hex(sent.mid)+' · '+time(sent.sent_at))+'</title></path>':'';
  // Configured segments stay muted. Only datagrams or a flight receipt illuminate a path.
  const center=351+.5*(403/cols);
  const ingressPath='M128 '+groundY+' H166 V'+upY+' H205';
  const returnPath=command?.app===egress?'M272 '+(upY+24)+' V'+(returnY-25):
    'M'+center+' '+(upY+24)+' V'+(busY+8)+' H272 V'+(returnY-25);
  const groundPath='M214 '+returnY+' H178 V'+(groundY+25)+' H126';
  const topology='<g class="trip-wires"><path d="'+ingressPath+'"/><path d="M272 '+(upY+24)+' V'+(busY+3)+' H'+center+' V'+(upY+24)+'"/><path d="'+returnPath+'"/><path d="'+groundPath+'"/></g>';
  const anyReturn=Boolean(reply || steps.some(step=>step.observation) ||
    (sent?.id===state.ground?.first_flight?.enable_command && state.ground?.first_flight?.telemetry && state.ground.history?.some(p=>p.event_id>sent.event_id)));
  const burst=(id,d)=>'<circle r="4" class="trip-packet '+id+'" style="offset-path:path(\''+d+'\')"/>';
  const confirmed=anyReturn?'<path class="trip-proof-line" d="'+returnPath+' '+groundPath+'"/>'+burst('returning',groundPath):
    off && sent?'<path class="trip-blocked" d="M272 '+(returnY-38)+' v12"/>':'';
  return '<svg viewBox="0 0 774 '+height+'" class="trip-drawing" role="img" aria-label="Configured flight interfaces and observed command traffic">'+
    '<defs><marker id="uplink-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="4" markerHeight="4" orient="auto"><path fill="var(--fs-accent)" d="M0 0 8 4 0 8Z"/></marker><marker id="downlink-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="4" markerHeight="4" orient="auto"><path fill="var(--fs-success)" d="M0 0 8 4 0 8Z"/></marker></defs>'+
    '<rect class="trip-frame" x="196" y="22" width="569" height="'+(height-30)+'" rx="8"/><text class="trip-caption" x="208" y="17">cFS · '+esc(target)+'</text>'+
    topology+backbone+confirmed+incoming+outgoing+lines+uplink+(sent?burst('sending',ingressPath):'')+node(groundX,groundY,'Ground','This computer','ground','Local UDP socket')+observations+
    (transport.command_port?'<text class="trip-caption" x="93" y="'+(upY-7)+'">UDP '+Number(transport.command_port)+'</text>':'')+
    (transport.telemetry_port?'<text class="trip-caption" x="85" y="'+(height-34)+'">UDP '+Number(transport.telemetry_port)+'</text>':'')+'</svg>';
}

function evidenceLine(step, esc, hex) {
  const observation=step.observation;
  if (!observation) return '';
  const header=[observation.name,hex(observation.mid),'seq '+observation.sequence,time(observation.received_at)].join(' · ');
  return ' <b>'+esc(header)+'</b><code>'+esc(JSON.stringify(observation.values))+'</code>';
}

function journal(sent, runs, selected, esc, hex){
  return '<section class="trip-journal"><header>Sent <span>Flight observations</span></header><div>'+sent.slice(0,32).map(item=>{
    const run=runs.find(r=>r.id===item.event_id);
    return '<details '+(selected?.id===item.event_id?'class="current"':'')+' data-detail-key="sent-'+item.event_id+'"><summary><strong>'+esc(item.id)+'</strong><span class="trip-result" data-status="'+(run?.status||'sent')+'">'+
      (run?names[run.status]+' · '+run.matched+'/'+run.steps.length:'Sent')+'</span><time>'+time(item.sent_at)+'</time></summary>'+
      '<button data-inspect-send="'+item.event_id+'">View observation</button><code>'+hex(item.mid)+' · '+esc(item.hex)+'</code>'+(run?'<ol>'+run.steps.map(step=>'<li>'+esc(describeStep(step))+evidenceLine(step,esc,hex)+'</li>').join('')+'</ol>':'')+'</details>';
  }).join('')+(sent.length?'':'<span class="trip-empty-track" aria-label="Empty send history"></span>')+'</div></section>';
}

export function tripPanel(state,command,helpers){
  const {esc,hex,icon}=helpers;
  const ground=state.ground?.target===state.target?state.ground:{};
  const system=state.groundMode==='system';
  const sent=(ground.commands||[]).filter(c=>!c.automatic&&c.id===command?.id).slice().reverse();
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
    outputOff(state)?'to_lab output off':
    last?'Ground → ci_lab · MID '+hex(last.mid):'';
  const header='<header class="trip-modes"><div role="group" aria-label="Ground view">'+
    ['trip','system'].map((mode,i)=>'<button data-ground-mode="'+mode+'" aria-pressed="'+((system?'system':'trip')===mode)+'">'+(i?'System overview':'Round trip')+'</button>').join('')+'</div></header>';
  if(system)return '<div class="trip-card system">'+header+renderCommunication(state,helpers)+'</div>';
  return '<div class="trip-card">'+header+(command?testSelector(state,command,esc,icon):'')+
    '<div class="trip-canvas">'+routeDiagram(state,command,steps,last,esc,hex)+'</div>'+
    '<div class="trip-observations">'+(showRun?'<strong data-status="'+run.status+'">'+names[run.status]+' · '+run.matched+'/'+steps.length+'</strong>':'')+
    (steps.length?'<ol>'+steps.map(step=>'<li class="'+(step.observation?'matched':'')+'">'+(step.observation?'✓ ':'')+esc(describeStep(step))+'</li>').join('')+'</ol>':
    '<span>'+esc(caption)+'</span>')+
    (showRun&&run.status==='waiting'?'<button data-stop-trip="'+run.id+'">Stop test</button>':'')+'</div></div>'+journal(sent,tests,showRun?run:null,esc,hex);
}
