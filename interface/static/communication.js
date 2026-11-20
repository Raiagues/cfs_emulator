// Traffic comes from the UDP receiver's thirty one-second counters.
const services={cfe_sb:'Software Bus',cfe_es:'Executive Services',cfe_evs:'Event Services',cfe_tbl:'Table Services',cfe_time:'Time Services',cfe_fs:'File Services'};
export function stationState(state) {
  const ground=state.ground;
  if(ground?.target!==state.target)return {};
  if(ground.connected)return ground;
  return {connected:false,target:ground.target,error:ground.error,commands:[],packets:[],events:[],history:[]};
}
function spark(bins) {
  const max=Math.max(1,...bins);
  const points=bins.map((n,i)=>i+','+(16-15*n/max)).join(' ');
  return '<svg class="traffic-spark" viewBox="0 0 29 17" preserveAspectRatio="none" aria-hidden="true"><polyline vector-effect="non-scaling-stroke" points="'+points+'"/></svg>';
}
export function renderCommunication(state,{esc}) {
  const ground=stationState(state), commands=state.systemTraffic==='commands';
  const rows=(ground.communication?.recent || []).filter(r=>r.kind===(commands?'command':'telemetry') && r.app).sort((a,b)=>b.rate-a.rate || a.app.localeCompare(b.app));
  const mission=state.workspace.mission;
  const quiet=[...new Set([...(mission.included||mission.enabled||[]),...Object.keys(services)])].filter(app=>!rows.some(r=>r.app===app)).sort();
  const records=commands?ground.commands||[]:ground.history||[];
  const defs=(commands?state.catalog?.commands:state.catalog?.packets)||[];
  function row(r) {
    const packet=records.findLast(p=>p.app===r.app)||defs.find(p=>p.app===r.app);
    const action=packet?(commands?'data-open-trip-command="'+esc(packet.id)+'"':'data-system-packet="'+esc(packet.mid)+'"'):'disabled title="Packet details unavailable"';
    return `<li><button ${action}><span>${esc(services[r.app]||r.app)}</span>${spark(r.bins)}<output>${r.rate.toFixed(2)} pkt/s</output></button></li>`;
  }
  const apps=rows.filter(r=>!services[r.app]),core=rows.filter(r=>services[r.app]);
  return `<section class="system-traffic"><header class="system-title"><strong>Bus traffic · 30 s</strong><div role="group" aria-label="Traffic direction">
    ${['commands','telemetry'].map(mode=>`<button data-system-traffic="${mode}" aria-pressed="${(commands?'commands':'telemetry')===mode}">${mode==='commands'?'Commands':'Telemetry'}</button>`).join('')}</div></header>
    <ul class="traffic-list">${apps.map(row).join('')}</ul>${core.length?`<h3>cFE services</h3><ul class="traffic-list core">${core.map(row).join('')}</ul>`:''}
    ${quiet.length?`<details><summary>${quiet.length} quiet apps and services</summary>${quiet.map(app=>`<span class="quiet-app">${esc(services[app]||app)}</span>`).join('')}</details>`:''}</section>`;
}
