// The architecture describes source and wiring relationships. A reader binds one
// app to one physical instance, even when several devices use the same driver.
export function missionBuses(workspace) {
  const {project,catalog}=workspace;
  const ids = project.buses ?? new Set((project.devices || []).map(device => device.bus));
  return Object.fromEntries([...ids].filter(id => catalog.buses?.[id]).map(id => [id,catalog.buses[id]]));
}

export function missionGraph(state, groups, services, os, board) {
  const {workspace} = state;
  const native = state.target === 'native';
  const nodes = new Map(), edges = [];
  const byApp = new Map((workspace.project.apps || []).map(app => [app.name, app]));
  const key = (kind, name) => kind + ':' + name;
  function add(id, name, kind, section, properties = {}) {
    nodes.set(id,{id,name,kind,section,...properties});
  }
  function link(from,to,kind,detail) {
    if (nodes.has(from) && nodes.has(to) && !edges.some(edge => edge.from === from && edge.to === to && edge.kind === kind)) {
      edges.push({from,to,kind,detail});
    }
  }
  for (const [section,group] of Object.entries(groups)) {
    for (const item of group.modules.filter(item => item.included)) {
      const id = key(group.kind,item.name);
      add(id,item.name,group.kind,section,{item, tone: section === 'mission' ? 'own' : section === 'library' ? 'library' : 'upstream',
        source:item.entry || item.exports?.[0]?.path});
    }
  }
  for (const [id,title,path] of services) add('service:'+id,id.toUpperCase(),'service','core',{subtitle:title,source:path,tone:'core'});
  for (const id of ['OSAL','PSP']) add(id,id,'platform','platform',{tone:'platform',source:'cFS/'+id.toLowerCase()+'/README.md'});
  add('os',os,'os','platform',{tone:'system'});
  add('board',board,'board','hardware',{tone:'board',subtitle:os});
  if (!native) {
    for (const [id,bus] of Object.entries(missionBuses(workspace))) {
      add('bus:'+id,id,'bus','hardware',{item:bus,tone:'pin',subtitle:bus.device});
      link('bus:'+id,'board','header',bus.device);
    }
    for (const device of workspace.project.devices || []) {
      add('device:'+device.id,device.id,'device','hardware',{item:device,tone:'device',subtitle:device.model});
      link('device:'+device.id,'bus:'+device.bus,'wiring',device.bus);
    }
  }
  for (const node of nodes.values()) {
    for (const dep of node.item?.libraries || []) link(node.id,'library:'+dep.name,'dependency',dep.declared ? 'Build dependency' : 'API calls');
    for (const user of node.item?.used_by || []) link(key(user.kind,user.name),node.id,'dependency',user.declared ? 'Build dependency' : 'API calls');
    if (node.kind === 'app') {
      for (const [reader,device] of Object.entries(byApp.get(node.name)?.sensors || {})) link(node.id,'device:'+device,'reader',reader);
      for (const step of node.item.behavior?.nodes || []) {
        for (const api of step.apis || []) {
          const id = /^CFE_(SB|ES|EVS|FS|TIME|TBL)_/.exec(api)?.[1];
          if (id) link(node.id,'service:'+id.toLowerCase(),'service',api);
        }
      }
    }
    if (node.kind === 'device') {
      const driver = workspace.catalog.models?.[node.item.model]?.library;
      // A compatible model alone does not mean an app is using this sensor.
      if (driver && [...byApp.values()].some(app => Object.values(app.sensors || {}).includes(node.name))) {
        link('library:'+driver,node.id,'driver',node.item.model);
      }
    }
    if (node.kind === 'bus') link('library:'+node.item.library,node.id,'transport',node.item.device);
  }
  return {nodes,edges};
}

export function sensorPins(graph,node) {
  const bus=graph.nodes.get('bus:'+node.item.bus);
  return Object.entries(bus?.item.sensor_pins || {}).map(([signal,choices])=>({
    signal,pin:node.item.pins?.[signal] ?? choices[0]
  })).filter(({pin})=>Number.isInteger(pin) && pin>0);
}

export function connectedNodes(graph, selected) {
  const node = graph.nodes.get(selected), active = new Set();
  if (!node) return active;
  active.add(selected);
  function walk(seeds, kinds, reverse = false) {
    const seen = new Set(seeds), queue = [...seen];
    for (let index = 0; index < queue.length; index++) {
      for (const edge of graph.edges) {
        const [from,to] = reverse ? [edge.to,edge.from] : [edge.from,edge.to];
        if (from !== queue[index] || !kinds.includes(edge.kind) || seen.has(to)) continue;
        seen.add(to); active.add(to); queue.push(to);
      }
    }
    return seen;
  }
  if (node.kind === 'app') {
    walk([selected],['dependency','service']);
    walk([selected],['reader','wiring']);
  } else if (node.kind === 'library') {
    walk([selected],['dependency'],true);
    walk([selected],['dependency','driver','transport','wiring']);
  } else if (node.kind === 'device') {
    walk([selected],['reader','driver'],true);
    walk([selected],['wiring']);
  } else if (node.kind === 'bus' || node.kind === 'board') {
    const devices = walk([selected],['header','wiring'],true);
    walk(devices,['driver','reader','transport'],true);
  } else if (node.kind === 'service') walk([selected],['service'],true);
  return active;
}
