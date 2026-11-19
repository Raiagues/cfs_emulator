import {icon} from './ui.js';
import {connectedNodes,sensorPins} from './mission-graph.js';

const WIDTH = 330, DEPTH = 210;
const LEVEL = {hardware:0, os:151, platform:198, core:331, software:486};
export const homeCamera = () => ({yaw:Math.PI/4, pitch:0.5, zoom:1, panX:0, panY:0});
const clamp = (n,min,max) => Math.min(max,Math.max(min,n));
const points = corners => corners.map(([x,y])=>x.toFixed(2)+','+y.toFixed(2)).join(' ');

export function stackScene(graph, showLibraries, native) {
  const planes = [], objects = [], anchors = new Map(), traces = [];
  function box(x,y,w,d,z,h,tone, label='', id='', attrs='') {
    const object = {x:x-WIDTH/2,y:y-DEPTH/2,w,d,z,h,tone,label,id,attrs};
    objects.push(object);
    if (id) anchors.set(id,[object.x+w/2,object.y+d/2,z+h]);
    return object;
  }
  function plate(z,tone,depth=DEPTH,id='') {
    planes.push(box(0,0,WIDTH,depth,z-7,7,tone,'',id));
  }
  const nodes = [...graph.nodes.values()];
  const rows = [];
  const software = nodes.filter(n=>['app','library'].includes(n.kind));
  const columns = Math.max(5, Math.ceil(Math.sqrt(software.length * 1.6)));
  for (const section of ['cfs','library','mission']) {
    if (section === 'library' && !showLibraries) continue;
    const items = software.filter(n=>n.section===section);
    if (section==='mission') items.push({name:'+ New',tone:'new',attrs:'data-module-group="mission" data-module-action="new"'});
    for (let i=0;i<items.length;i+=columns) rows.push(items.slice(i,i+columns));
  }
  const rowHeight = Math.min(42,(DEPTH-10)/rows.length);
  const cell = (WIDTH-8)/columns;
  const swDepth = 8 + rows.length*rowHeight;
  plate(LEVEL.software,'deck',swDepth);
  rows.forEach((row,r)=>row.forEach((n,c)=>box(5+c*cell,5+r*rowHeight,cell-4,rowHeight-4,LEVEL.software,8,n.tone,n.name,n.id,n.attrs)));

  plate(LEVEL.core,'core-deck');
  const services = nodes.filter(n=>n.kind==='service'), others = services.filter(n=>n.name!=='SB');
  if (services.some(n=>n.name==='SB')) box(9,16,WIDTH-18,72,LEVEL.core,9,'core','SB · Software Bus','service:sb');
  others.forEach((n,i)=>box(9+i*(WIDTH-14)/others.length,102,(WIDTH-14)/others.length-5,85,LEVEL.core,9,'core',n.name,n.id));
  plate(LEVEL.platform,'deck');
  box(5,5,WIDTH/2-7,DEPTH-10,LEVEL.platform,8,'osal','OSAL','OSAL');
  box(WIDTH/2+2,5,WIDTH/2-7,DEPTH-10,LEVEL.platform,8,'psp','PSP','PSP');
  plate(LEVEL.os,'system',DEPTH,'os');
  plate(LEVEL.hardware,native?'chassis':'board',DEPTH,'board');
  if (native) {
    box(52,18,220,139,1,7,'metal');
    box(63,26,198,119,8,1,'glass',graph.nodes.get('os').name);
    box(17,169,292,26,1,4,'metal');
    for (let i=0;i<15;i++) box(25+i*18,174,13,12,5,2,'glass');
  } else {
    box(172,88,55,47,1,8,'metal','CPU');
    box(216,44,27,23,1,5,'glass');
    for (let i=0;i<3;i++) box(WIDTH-35,38+i*56,44,42,1,19,'metal');
    const buses=nodes.filter(n=>n.kind==='bus'), devices=nodes.filter(n=>n.kind==='device');
    box(15,DEPTH-24,187,15,2,5,'glass');
    for (let pin=1;pin<=40;pin++) box(18+Math.floor((pin-1)/2)*9,DEPTH-(pin%2?21:15),3,3,7,4,'pin');
    buses.forEach((bus,i)=>box(16,DEPTH-42-i*15,180,9,2,5,'bus','',bus.id));
    const across=Math.min(3,Math.max(1, Math.ceil(Math.sqrt(devices.length))));
    const chipW=Math.min(72,143/across), chipD=Math.min(43,80/Math.max(1,Math.ceil(devices.length/across)));
    devices.forEach((n,i)=>{
      const x=28+(i%across)*chipW,y=DEPTH-106-Math.floor(i/across)*chipD;
      const board=box(x,y,chipW-5,chipD-5,2,6,'device',n.name,n.id);
      const end=anchors.get('bus:'+n.item.bus);
      const pins=sensorPins(graph,n);
      if (pins.length && end) {
        pins.forEach(({signal,pin},index)=>{
          const cx=board.x+board.w*(index+1)/(pins.length+1), cy=board.y+board.d;
          const px=19.5+Math.floor((pin-1)/2)*9-WIDTH/2, py=DEPTH/2-(pin%2?19.5:13.5);
          const channel=Math.max(cy+3,py-19-index*3);
          traces.push({from:n.id,to:'bus:'+n.item.bus,signal,pin,points:[[cx,cy,9],[cx,channel,9],[px,channel,9],[px,py,10]]});
        });
      } else if (end) {
        const cx=board.x+board.w/2, cy=board.y+board.d;
        traces.push({from:n.id,to:'bus:'+n.item.bus,points:[[cx,cy,7],[cx,end[1],7],[end[0],end[1],7]]});
      }
    });
  }
  return {objects,planes,anchors,traces, swDepth};
}

export function projectPoint(camera,x,y,z) {
  const s=Math.sin(camera.yaw), c=Math.cos(camera.yaw);
  return [x*c-y*s,(x*s+y*c)*Math.sin(camera.pitch)-(z-LEVEL.software/2)*Math.cos(camera.pitch)];
}

function boxSvg(o, camera, graph, selected, active, esc) {
  const {x,y,w,d,z,h,id}=o, top=z+h+(id && selected===id && o.label ? 4 : 0);
  const corners=[[x,y],[x+w,y],[x+w,y+d],[x,y+d]];
  const face=corners.map(([x,y])=>projectPoint(camera,x,y,top));
  const base=corners.map(([x,y])=>projectPoint(camera,x,y,z));
  const sides=face.map((p,i)=>{
    const j=(i+1)%4;
    return p[0]>face[j][0] ? '<polygon class="side side-'+(i%2)+'" points="'+points([p,base[i],base[j],face[j]])+'"/>' : '';
  }).join('');
  const node=graph.nodes.get(id);
  const actionable=Boolean(node || o.attrs);
  const attrs=node ? 'data-cad-node="'+esc(id)+'" '+navigation(node,esc) : o.attrs || '';
  const chosen=id && selected===id, related=id && active.has(id);
  const dim=selected && !related && !['board','os'].includes(id);
  const label=o.label;
  let text='';
  if (label) {
    const [cx,cy]=projectPoint(camera,x+w/2,y+d/2,top);
    const c=Math.cos(camera.yaw),s=Math.sin(camera.yaw),p=Math.sin(camera.pitch), sign=c<0?-1:1;
    const m=[c*sign,s*p*sign,-s*sign,c*p*sign,cx,cy].map(v=>v.toFixed(4)).join(' ');
    const fontSize=clamp(Math.min(w/Math.max(label.length*.62,3),d*.56),6,11);
    const limit=Math.max(4,Math.floor(w/(fontSize*.59)));
    text='<text class="cad-face-label" transform="matrix('+m+')" font-size="'+fontSize+'" text-anchor="middle" dominant-baseline="central">'+esc(label.length>limit?label.slice(0,limit-1)+'…':label)+'</text>';
  }
  const title=node?.name || o.label;
  return '<g class="cad-box tone-'+o.tone+(actionable?' stack-pick':'')+(chosen?' is-selected':related?' is-related':'')+(dim?' is-muted':'')+'" '+
    (actionable?'role="button" tabindex="0" aria-label="'+esc(title)+'" '+(node?'aria-pressed="'+Boolean(chosen)+'" ':'')+attrs:'aria-hidden="true"')+'>'+
    (actionable?'<title>'+esc(title)+'</title>':'')+sides+'<polygon class="cad-top" points="'+points(face)+'"/>'+text+'</g>';
}

export function navigation(node,esc) {
  if (node.kind==='app') return 'data-arch-app="'+esc(node.name)+'"';
  if (node.kind==='library') return 'data-arch-library="'+esc(node.name)+'"';
  if (node.kind==='device') return 'data-view="bench" data-device="'+esc(node.name)+'" data-inspect="'+esc(node.name)+'"';
  if (node.source) return 'data-arch-source="'+esc(node.source)+'" data-symbol="'+esc(node.subtitle||node.name)+'"';
  return 'data-view="bench" data-inspect="board"';
}

function stroke(coords, camera, cls) {
  return '<polyline class="'+cls+'" points="'+points(coords.map(p=>projectPoint(camera,...p)))+'"/>';
}

export function drawStack(scene,graph,camera,selected,showLibraries,esc) {
  const active=connectedNodes(graph,selected);
  const s=Math.sin(camera.yaw), c=Math.cos(camera.yaw);
  const depth=o=>(o.x+o.w/2)*s+(o.y+o.d/2)*c;
  const order=[...scene.objects].sort((a,b)=>a.z-b.z || depth(a)-depth(b));
  const guides=[];
  for(const [x,y] of [[-WIDTH/2,-DEPTH/2],[WIDTH/2,-DEPTH/2],[WIDTH/2,DEPTH/2],[-WIDTH/2,DEPTH/2]]) {
    guides.push(stroke([[x,y,LEVEL.hardware],[x,y,LEVEL.software-7]],camera,'cad-guide'));
  }
  const wireColors={VCC:'power',GND:'ground',SDA:'data',SCL:'clock'};
  const wires=scene.traces.map(line=>{
    const cls='cad-wire'+(active.has(line.from)&&active.has(line.to)?' active':'')+' wire-'+(wireColors[line.signal]||'bus');
    return '<g>'+ (line.signal?'<title>'+esc(line.signal)+' · pin '+line.pin+'</title>':'')+stroke(line.points,camera,cls)+'</g>';
  }).join('');
  // Draw PCB traces above the substrate, beneath the component markings.
  const surface=order.map(o=>boxSvg(o,camera,graph,selected,active,esc)+(o.id==='board'?wires:'')).join('');
  const highlights=graph.edges.filter(e=>active.has(e.from)&&active.has(e.to)&&scene.anchors.has(e.from)&&scene.anchors.has(e.to)&&e.kind!=='wiring' && e.kind!=='header' &&
    (e.kind!=='service'||graph.nodes.get(selected)?.kind==='service') && (e.kind!=='dependency'||e.from===selected||e.to===selected));
  const links=highlights.map(edge=>{
    const start=projectPoint(camera,...scene.anchors.get(edge.from)),end=projectPoint(camera,...scene.anchors.get(edge.to));
    const y=(start[1]+end[1])/2;
    return '<path class="cad-connection" data-connection="'+esc(edge.kind)+'" d="M'+start+' C'+start[0]+','+y+' '+end[0]+','+y+' '+end+'"><title>'+esc(edge.detail)+'</title></path>';
  }).join('');
  const left=-Math.abs(WIDTH*c)/2-Math.abs(DEPTH*s)/2;
  const counts=section=>[...graph.nodes.values()].filter(n=>n.section===section).length;
  const swY=projectPoint(camera,0,0,LEVEL.software)[1];
  const sensorCount=[...graph.nodes.values()].filter(n=>n.kind==='device').length;
  const labels=[['cFS apps',String(counts('cfs')),'cfs',swY-28],
    ...(showLibraries?[['Libraries',String(counts('library')),'library',swY+1]]:[]),
    ['Your apps',String(counts('mission')),'mission',swY+30],
    ['cFE',counts('core')+' core services','core',projectPoint(camera,0,0,LEVEL.core)[1]],
    ['OSAL · PSP','Platform','platform',projectPoint(camera,0,0,LEVEL.platform)[1]-2],
    [graph.nodes.get('os').name,'Operating system','platform',projectPoint(camera,0,0,LEVEL.os)[1]+8],
    [graph.nodes.get('board').name,graph.nodes.get('board').name==='This computer'?'Native execution':sensorCount+(sensorCount===1?' sensor':' sensors'),'hardware',projectPoint(camera,0,0,0)[1]+9]];
  const captions=labels.map(([label,sub,section,y])=>'<g class="cad-caption stack-pick" role="button" tabindex="0" aria-label="Open '+esc(label)+' in 2D" data-map-section="'+section+'"><path d="M'+(left-32)+' '+y+'h30"/><circle cx="'+(left-2)+'" cy="'+y+'" r="1.8"/><text x="'+(left-39)+'" y="'+y+'">'+esc(label)+'</text><text class="caption-sub" x="'+(left-39)+'" y="'+(y+12)+'">'+esc(sub)+'</text></g>').join('');
  return '<g transform="translate('+camera.panX+' '+camera.panY+') scale('+camera.zoom+')">'+guides.join('')+surface+links+captions+'</g>';
}

export function renderStack(scene,graph,camera,selected,showLibraries,esc) {
  const tools=[['orbit','rotate','Orbit'],['pan','expand','Pan'],['out','minus','Zoom out'],['in','plus','Zoom in'],['fit','compass','Reset view']];
  return '<div class="cad-stage"><svg class="mission-cad" tabindex="0" viewBox="-384 -339 644 678" aria-label="Mission architecture, orbit with arrow keys, zoom with plus and minus">'+drawStack(scene,graph,camera,selected,showLibraries,esc)+'</svg>'+
    '<div class="cad-camera" role="group" aria-label="Camera controls">'+tools.map(([k,g,title])=>'<button type="button" data-camera="'+k+'" aria-label="'+title+'" title="'+title+'" '+(['orbit','pan'].includes(k)?'aria-pressed="'+(k===(camera.mode||'orbit'))+'"':'')+'>'+icon(g)+'</button>').join('')+'</div></div>';
}
