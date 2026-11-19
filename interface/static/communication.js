// Traffic totals are recorded by the UDP sender and decoder in this session.
const services={SB:'Software Bus',ES:'Executive Services',EVS:'Event Services',TBL:'Table Services',TIME:'Time Services',FS:'File Services'};
export function stationState(state) {
  return state.ground?.target === state.target ? state.ground : {};
}
export function renderCommunication(state,{esc,icon}){
  const ground=stationState(state);
  const catalog=state.catalog||{}, mission=state.workspace.mission;
  const traffic=new Map((ground.communication?.apps||[]).map(row=>[row.app,row]));
  const apps=[...(mission.included||mission.enabled||[])].sort();
  const commands=state.systemTraffic==='commands';
  const unit=commands?'sent':'received', key=commands?'commands_sent':'telemetry_received';
  function block(app,title=app,desc=''){
    const total=traffic.get(app)?.[key]||0;
    return '<button class="comm-app-block '+(app==='cfe_sb'?'comm-bus':'')+'" data-comm-app="'+esc(app)+'" aria-expanded="'+(state.commApp===app)+'" data-live="'+Boolean(total)+'"><strong>'+esc(title)+'</strong><small>'+esc(desc?desc+' · ':'')+total+' '+unit+'</small></button>';
  }
  const selected=state.commApp;
  const source=commands?ground.commands||[]:ground.history||[];
  const recent=source.filter(record=>record.app===selected).slice(-12).reverse();
  const defs=(commands?catalog.commands:catalog.packets)||[];
  const relevant=defs.filter(d=>d.app===selected);
  const browser=selected?'<article class="system-detail"><header><strong>'+esc(selected)+'</strong><button data-comm-app="'+esc(selected)+'" aria-label="Close application">×</button></header>'+
    (recent.length?'<ol>'+recent.map(r=>'<li><time>'+new Date((r.received_at||r.sent_at)*1000).toLocaleTimeString()+'</time> '+esc(r.name||r.id)+' · '+r.bytes+' B</li>').join('')+'</ol>':'<p>No session traffic</p>')+
    '<div class="comm-source-links">'+relevant.map(d=>commands?'<button data-open-trip-command="'+esc(d.id)+'">'+icon('antenna')+esc(d.id)+'</button>':'<button data-system-packet="'+d.mid+'">'+icon('wave')+esc(d.id)+'</button>').join('')+'</div></article>':'';
  return '<section class="system-traffic"><header class="system-title"><strong>NASA cFS</strong><div role="group" aria-label="Traffic direction">'+
    ['commands','telemetry'].map(v=>'<button data-system-traffic="'+v+'" aria-pressed="'+((commands?'commands':'telemetry')===v)+'">'+(v==='commands'?'Commands':'Telemetry')+'</button>').join('')+'</div></header>'+
    '<section class="system-group"><h3>cFS apps</h3><div class="system-nodes">'+apps.map(app=>block(app)).join('')+'</div></section>'+
    '<section class="system-group"><h3>Core Flight Executive</h3><div class="system-nodes">'+(mission.core_services||[]).map(({name})=>block('cfe_'+name.toLowerCase(),name,services[name]||'')).join('')+'</div></section>'+browser+'</section>';
}
