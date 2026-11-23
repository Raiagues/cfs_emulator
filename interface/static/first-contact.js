import {api} from './api.js';
import {paint} from './dom.js';
import {stepUrl} from './router.js';
import {onUpdate} from './updates.js';
import {renderContact,renderPacketPreview,fieldValues,userFields,layoutContactRoute,contactRouteModel} from './contact-view.js';

export function mountFirstContact(root,{state,startJob,guided=true}){
  const target=state.target;
  let catalog=null,station={},selected=guided?'':state.groundSelection||'',error='',busy=false,closed=false,refreshBusy=false,refreshAgain=false;
  let attempted=false,wasRunning=null,sent=null,replay=null,frame=0,clock=0,paused=false,timer;
  let lastDeployment=null,lastSession=null,revealedSelection='',routePacket=null;
  const defaulted=new Set(),drafts=new Map(),receipts=new Map(),commandGroups=new Set(['to_lab','sample_app',state.groundApp].filter(Boolean)),telemetryGroups=new Set(['to_lab','sample_app',state.groundApp].filter(Boolean)),packetGroups=new Set();
  const nextUrl=stepUrl('app',location,target);
  let dialog;
  function command(){return catalog?.commands.find(c=>c.id===(replay?.command||selected));}
  function values(c=command()){
    if(!c)return {};
    if(!drafts.has(c.id))drafts.set(c.id,Object.fromEntries(userFields(c).map(f=>[f.name,f.format==='?'?false:''])));
    const draft=drafts.get(c.id);
    if(c.id===station.first_flight?.enable_command){const f=userFields(c).find(f=>f.format==='s');if(f&&!defaulted.has(c.id+f.name)&&station.first_flight.return_host){draft[f.name]=station.first_flight.return_host;defaulted.add(c.id+f.name);}}
    return draft;
  }
  function flightRunning(){return target==='qemu'?state.hardware?.qemu?.flight_running:target==='physical'?state.hardware?.physical?.last_probe?.flight_running:state.hardware?.native?.running;}
  function cancelMotion(){cancelAnimationFrame(frame);frame=0;replay=null;paused=false;}
  function acceptStation(next){
    const session=next.connected&&next.target===target?next.communication?.since:null;
    if(lastSession!==null&&session!==lastSession){selected=guided?'':state.groundSelection||selected;drafts.clear();defaulted.clear();receipts.clear();sent=null;clearTimeout(timer);cancelMotion();}
    lastSession=session;station=next.target===target?next:{};
    if(routePacket&&!catalog?.packets?.some(packet=>packet.id===routePacket))routePacket=null;
    if(!selected)selected=station.first_flight?.enable_command||catalog?.commands.find(c=>c.app==='to_lab'&&c.id.endsWith('_OUTPUT_ENABLE_CC'))?.id||catalog?.commands[0]?.id||'';
    if(!guided){state.groundSelection=selected;const app=catalog?.commands.find(c=>c.id===selected)?.app;if(app){state.groundApp=app;if(revealedSelection!==selected){commandGroups.add(app);telemetryGroups.add(app);revealedSelection=selected;}}}
  }
  function finish(complete){
    if(!complete&&guided)selected=station.first_flight?.noop_command||selected;
    routePacket=null;
    draw();
    // Keep the confirmed response visible until the operator follows Next.
  }
  function tick(now){
    frame=0;if(closed||!replay)return;
    if(!paused)replay.elapsed+=Math.min(120,now-clock);clock=now;
    const t=Math.min(1,replay.elapsed/replay.duration),down=t>=.58,svg=root.querySelector('.contact-svg'),dot=svg?.querySelector('.contact-dot'),path=[...(svg?.querySelectorAll(down?'[data-down]':'[data-up]')||[])].find(p=>(down?p.dataset.producer:p.dataset.recipient)===(down?replay.producer:replay.app));
    if(dot){dot.style.display=path?'':'none';if(path){const p=path.getPointAtLength(path.getTotalLength()*(down?(t-.58)/.42:t/.58));dot.setAttribute('cx',p.x);dot.setAttribute('cy',p.y);dot.classList.toggle('down',down);}}
    const label=t<.2?'Ground → '+replay.ingress:t<.4?replay.ingress+' → Software Bus':t<.58?'Software Bus → '+replay.app:t<.8?replay.producer+' → Software Bus → '+replay.egress:replay.egress+' → Ground';
    const caption=root.querySelector('[data-caption]');if(caption)caption.textContent='Confirmed response · '+label;
    root.querySelectorAll('.play-bars i').forEach((el,i)=>el.classList.toggle('on',i<=Math.floor(t*7)));
    const activeName=t<.2?'Ground':t<.4?replay.ingress:t<.58?replay.app:t<.75?replay.producer:t<.9?replay.egress:'Ground';
    root.querySelectorAll('[data-route-node]').forEach(el=>el.classList.toggle('lit',el.querySelector('strong')?.textContent===activeName));
    const play=root.querySelector('[data-play]');if(play)play.textContent=paused?'▶':'Ⅱ';
    if(t>=1){const complete=replay.complete;cancelMotion();finish(complete);return;}
    if(!paused)frame=requestAnimationFrame(tick);
  }
  function observe(){
    const f=station.first_flight||{};
    if(f.downlink_receipt)receipts.set(f.downlink_receipt.send_id,f.downlink_receipt);
    if(f.receipt?.reply&&f.receipt?.increase)receipts.set(f.receipt.send_id,f.receipt);
    const authored=station.authored_reply?.receipt;
    if(authored?.reply&&authored?.increase)receipts.set(authored.send_id,authored);
    if(!sent||sent.session!==station.communication?.since)return;
    const r=receipts.get(sent.eventId);if(!r)return;
    routePacket=null;
    const id=sent.command,mid=r.event_mid??r.mid,complete=id===f.noop_command&&!!r.increase;
    sent=null;clearTimeout(timer);cancelMotion();
    const route=contactRouteModel(catalog,catalog.commands.find(c=>c.id===id),mid);
    if(!route.recipients.length||!route.ingress||!route.egress||!route.producers.length){finish(complete);return;}
    replay={command:id,mid,elapsed:0,duration:matchMedia('(prefers-reduced-motion: reduce)').matches?1:3000,app:route.recipients[0],ingress:route.ingress,egress:route.egress,producer:route.producers[0],complete};
    clock=performance.now();frame=requestAnimationFrame(tick);
  }
  function draw(){
    if(closed)return;
    const c=command(),f=station.first_flight||{},linked=station.connected&&station.target===target;
    const missingCommand=catalog&&selected&&!c?selected:'';
    const baseline=guided&&c?.id===f.noop_command&&!f.baseline_apps?.includes('sample_app');
    const needsEnable=guided&&c?.id===f.noop_command&&!f.downlink_receipt;
    paint(root,renderContact({catalog,station,command:c,missingCommand,values:values(c),target,guided,nextUrl,routePacket:!replay&&catalog?.packets?.find(packet=>packet.id===routePacket),commandGroups,telemetryGroups,packetGroups,receipts,replay,
      disabled:busy||!!replay||!!sent||!c||linked&&(baseline||needsEnable),sendLabel:!linked?(busy?'Connecting…':wasRunning===false?'Run cFS':'Connect'):sent?'Sent':'Send',
      error:error||(missingCommand?missingCommand+' is not available in this build. Build the app or choose an available command.':'')||((baseline||needsEnable)&&linked?'Complete Telemetry on and wait for sample_app housekeeping.':'')}));
    layoutContactRoute(root);
    if(replay){cancelAnimationFrame(frame);tick(performance.now());}
  }
  async function connect(){busy=true;attempted=true;error='';draw();try{const next=await api('ground/start',{target});if(!closed)acceptStation(next);}catch(e){if(!closed)error=e.message;}finally{busy=false;draw();}}
  async function refresh(){
    if(closed)return;if(refreshBusy){refreshAgain=true;return;}refreshBusy=true;
    try{
      const current=await api('ground');if(closed)return;
      const deployment=state.jobs.filter(j=>j.target===target&&['run','first-boot','stop','shutdown'].includes(j.action)&&!['failed','cancelled'].includes(j.status)).at(-1);
      const changed=deployment&&lastDeployment!==deployment.id;
      if(changed){lastDeployment=deployment.id;attempted=false;error='';if(!current.connected||current.target!==target){selected=guided?'':state.groundSelection||selected;sent=null;cancelMotion();}}
      wasRunning=flightRunning();if(deployment&&['stop','shutdown'].includes(deployment.action))wasRunning=false;
      const launching=deployment&&['run','first-boot'].includes(deployment.action)&&deployment.status==='running'&&!deployment.operation_complete;
      if(!catalog||changed||current.connected&&current.target===target&&current.build_fingerprint!==catalog.build_fingerprint){
        catalog=await api('ground/catalog?target='+target);
        catalog.commands=(catalog.commands||[]).map(c=>({...c,header_size:c.header_size??catalog.transport?.command_header_size??8}));
      }
      if(closed)return;acceptStation(current);
      if(station.connected)error=station.error||error;
      else if(!busy&&!attempted&&!launching&&wasRunning!==false&&catalog?.commands.length)await connect();
      if(!catalog?.commands.length&&!error)error=(catalog?.errors||[]).join(' ');
      if(!closed){observe();draw();}
    }catch(e){if(!closed){error=e.message;draw();}}finally{refreshBusy=false;if(refreshAgain&&!closed){refreshAgain=false;void refresh();}}
  }
  async function submit(e){
    if(!e.target.matches('.contact-command'))return;e.preventDefault();if(closed||busy||sent||replay)return;
    if(!station.connected||station.target!==target){if(wasRunning===false){busy=true;error='';draw();try{await startJob('run',{target},false);attempted=false;}catch(e){error=e.message;}finally{busy=false;draw();}}else await connect();return;}
    const c=command(),f=station.first_flight||{};if(!c)return;
    let args;try{args=fieldValues(c,values(c));}catch(e){error=e.message;draw();return;}
    const watched=c.id===f.enable_command&&!f.downlink_receipt||c.id===f.noop_command&&!f.answer;
    routePacket=null;busy=true;error='';if(watched)sent={command:c.id,eventId:null,session:station.communication?.since};draw();
    try{const result=await api('ground/send',{target,command_id:c.id,values:args});if(sent?.command===c.id)sent.eventId=result.event_id;}
    catch(e){sent=null;error=e.message;}
    finally{busy=false;clearTimeout(timer);if(sent)timer=setTimeout(()=>{if(sent?.command===c.id){sent=null;error='No matching response yet. Check flight output or send again.';draw();}},30000);await refresh();}
  }
  async function preview(){
    try{
      const c=command();if(!c)return;const data=await api('ground/preview',{target,command_id:c.id,values:fieldValues(c,values(c))});if(closed)return;
      if(!dialog){dialog=document.createElement('dialog');dialog.className='contact-dialog';root.append(dialog);dialog.addEventListener('click',e=>{if(e.target===dialog||e.target.closest('[data-close-packet]'))dialog.close();});}
      dialog.innerHTML=renderPacketPreview(data,c);if(!dialog.open)dialog.showModal();
    }catch(e){error=e.message;draw();}
  }
  const toggle=(set,key)=>set.has(key)?set.delete(key):set.add(key);
  function click(e){
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.pick&&!sent&&!replay){selected=b.dataset.pick;routePacket=null;state.groundSelection=selected;state.groundApp=command()?.app||'';error='';draw();}
    for(const [attribute,set] of [['commandGroup',commandGroups],['telemetryGroup',telemetryGroups],['packet',packetGroups]])if(b.dataset[attribute]){toggle(set,b.dataset[attribute]);if(attribute==='packet'&&!sent&&!replay)routePacket=b.dataset.packet;draw();}
    if(b.hasAttribute('data-stage')&&!sent&&!replay){routePacket=null;const f=station.first_flight||{};selected=b.dataset.stage==='0'?f.enable_command:f.noop_command;draw();}
    if(b.hasAttribute('data-play')&&replay){paused=!paused;clock=performance.now();cancelAnimationFrame(frame);tick(clock);}
    if(b.hasAttribute('data-step')&&replay){replay.elapsed=Math.min(replay.duration,(Math.floor(replay.elapsed/(replay.duration/7))+1)*replay.duration/7);clock=performance.now();cancelAnimationFrame(frame);tick(clock);}
    if(b.hasAttribute('data-bytes'))void preview();
  }
  function input(e){const name=e.target.dataset.field;if(!name)return;const c=command(),f=c?.fields.find(f=>f.name===name);if(!f)return;defaulted.add(c.id+name);values(c)[name]=f.format==='?'&&f.count===1?e.target.value==='true':e.target.value;error='';}
  root.addEventListener('click',click);root.addEventListener('submit',submit);root.addEventListener('input',input);root.addEventListener('change',input);
  const resize=new ResizeObserver(()=>{layoutContactRoute(root);if(replay){cancelAnimationFrame(frame);tick(performance.now());}});resize.observe(root);
  const off=onUpdate(['ground','hardware','jobs'],refresh),poll=setInterval(refresh,1600);draw();void refresh();
  return {close(){closed=true;off();resize.disconnect();cancelMotion();clearInterval(poll);clearTimeout(timer);dialog?.remove();root.removeEventListener('click',click);root.removeEventListener('submit',submit);root.removeEventListener('input',input);root.removeEventListener('change',input);}};
}
