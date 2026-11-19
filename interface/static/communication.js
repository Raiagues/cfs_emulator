/* Traffic and packet definitions for the selected target. */
const serviceLabels = {
  SB: ['Software Bus', 'Routes messages between applications.'],
  ES: ['Executive Services', 'Starts and manages flight applications.'],
  EVS: ['Event Services', 'Reports events from the flight software.'],
  TBL: ['Table Services', 'Loads and manages application tables.'],
  TIME: ['Time Services', 'Maintains spacecraft time.'],
  FS: ['File Services', 'Provides common flight file operations.'],
};

export function renderCommunication(state,{esc,icon}){
 const ground=state.ground?.target===state.target?state.ground:{};
 const catalog=state.catalogTarget===state.target?state.catalog||{}:{};
 const observed=new Map((ground.communication?.apps||[]).map(item=>[item.app,item]));
 const mission=state.workspace.mission;
 const names=[...(mission.included||mission.enabled||[])].sort();
 const target={native:'Native',physical:'Physical board',qemu:'Emulator'}[state.target];
 const appName=names.includes(state.commApp)?state.commApp:null;
 const blocks=names.map(name=>{
   const latest=(ground.packets||[]).filter(packet=>packet.app===name).reduce((time,p)=>Math.max(time,p.received_at||0),0);
   const live=ground.connected&&latest&&Date.now()/1000-latest<10;
   const received=observed.get(name)?.telemetry_received||0;
   const status=live?'Live telemetry':received?received+' received':ground.connected?'Awaiting telemetry':'Offline';
   const commands=(catalog.commands||[]).filter(command=>command.app===name).length;
   return `<button class="comm-app-block" data-comm-app="${esc(name)}" aria-expanded="${name===appName}" data-live="${!!live}"><strong>${esc(name.replaceAll('_',' ').toUpperCase())}</strong><small>${catalog.commands?commands+' commands · ':''}${status}</small></button>`;
 }).join('');
 const services=(mission.core_services||[]).map(item=>item.name);
 const core=Object.entries(serviceLabels).filter(([key])=>services.includes(key)).map(([key,[title,description]])=>
   `<div class="comm-service ${key==='SB'?'comm-bus':''}"><strong>${key}</strong><b>${title}</b><small>${description}</small></div>`).join('');

 function appDetails(name){
   const counts=observed.get(name)||{};
   const app=state.workspace.apps.find(item=>item.name===name);
   const entry=app?.entry||[...(catalog.commands||[]),...(catalog.packets||[])].find(item=>item.app===name&&item.source)?.source;
   const definitions=(items,kind,count)=>`<details data-detail-key="${esc(name)}-${kind}"><summary>${kind==='command'?'Commands sent':'Telemetry received'} <b>${count}</b></summary><div class="comm-source-links">${items.filter(item=>item.app===name).map(item=>`<button data-gs-source="${esc(item.id)}" data-source-kind="${kind}" aria-current="${state.sourcePreview?.definitionId===item.id&&state.sourcePreview?.definitionKind===kind}" data-source-section="${kind==='command'&&item.locations?.dispatch?'dispatch':'packet'}">${icon('code')}${esc(item.id||item.name)}</button>`).join('')||'<small>No definitions in this catalog</small>'}</div></details>`;
   return `<article class="communication-app"><header><strong>${esc(name)}</strong>${entry?`<button data-file="${esc(entry)}">${icon('code')}Open source</button>`:''}</header>${definitions(catalog.packets||[],'telemetry',counts.telemetry_received||0)}${definitions(catalog.commands||[],'command',counts.commands_sent||0)}</article>`;
 }

 return `<section class="communication-view"><header class="communication-link"><div>${icon('antenna')}<strong>Ground Station ⇄ ${esc(target)}</strong><span class="${ground.connected?'is-connected':''}"><i></i>${ground.connected?'Connected':'Disconnected'}</span></div>
 <button data-ground="${ground.connected?'stop':'start'}" ${state.groundBusy?'disabled':''}>${state.groundBusy?'Connecting…':ground.connected?'Disconnect':'Connect'}</button></header>
 ${state.groundError||ground.error?`<p class="communication-error" role="alert">${esc(state.groundError||ground.error)}</p>`:''}
 <div class="comm-source-links"><button data-file="ground_station/station.py">${icon('code')} Ground receiver</button><button data-file="ground_station/catalog.py">${icon('code')} Packet catalog</button></div>
 <section class="comm-stack"><h2>NASA cFS</h2><section><h3>cFS Apps</h3><div class="communication-app-grid">${blocks}</div>${appName?appDetails(appName):''}</section>
 <section><h3>Core Flight Executive (cFE)</h3><div class="comm-services">${core}</div></section></section></section>`;
}
