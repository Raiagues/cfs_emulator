import {test} from 'node:test';
import assert from 'node:assert/strict';
import {connectedNodes,missionGraph} from '../static/mission-graph.js';
import {moduleGroups,renderMissionDiagram} from '../static/mission-diagram.js';
import {drawStack,homeCamera,projectPoint,stackScene} from '../static/mission-stack.js';

const esc = s => String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
function fixture() {
  const science={name:'science',managed:true,included:true,enabled:true,entry:'project/apps/science/main.c',libraries:[{name:'therm_lib'}]};
  const spare={name:'standby',managed:true,included:true,enabled:true,libraries:[{name:'therm_lib'}]};
  const libs=['therm_lib','i2c_lib'].map((name,i)=>({name,included:true,used_by:[],libraries:i?[]:[{name:'i2c_lib'}]}));
  return {target:'physical',showLibraries:true,mapMode:'3d',workspace:{
    project:{board:'raspi4b',os:'raspios',apps:[{name:'science',sensors:{temperature:'probe'}},{name:'standby',sensors:{}}],devices:[
      {id:'probe',model:'therm',bus:'bus1',address:72},{id:'spare',model:'therm',bus:'bus1',address:73}]},
    catalog:{name:'Raspberry Pi 4B',buses:{bus1:{device:'/dev/i2c-1',library:'i2c_lib'}},models:{therm:{library:'therm_lib'}}},
    apps:[science,spare],libraries:libs,mission:{available:[science,spare],available_libraries:libs,included:['science','standby'],core_services:[{name:'SB'}]}
  }};
}

test('CAD uses actual readers, configured devices and transitive library dependencies',()=>{
  const s=fixture(),graph=missionGraph(s,moduleGroups(s.workspace),[], 'Raspberry Pi OS','Raspberry Pi 4B');
  assert.deepEqual([...connectedNodes(graph,'app:science')].sort(),['app:science','bus:bus1','device:probe','library:i2c_lib','library:therm_lib']);
  assert.equal(connectedNodes(graph,'device:spare').has('app:science'),false);
  assert.equal(connectedNodes(graph,'device:spare').has('library:therm_lib'),false);
  assert.equal(connectedNodes(graph,'device:probe').has('app:standby'),false);
  assert.equal(connectedNodes(graph,'library:i2c_lib').has('app:science'),true);
  assert.equal(connectedNodes(graph,'app:standby').has('device:probe'),false);
  s.mapSelected='device:spare';
  assert.match(renderMissionDiagram(s,{esc}),/data-link-hal="spare"/);
  s.mapSelected='device:probe';
  assert.doesNotMatch(renderMissionDiagram(s,{esc}),/data-link-hal="probe"/);
  assert.match(renderMissionDiagram(s,{esc}),/data-connection="reader"/);
  s.mapSelected='app:science';
  const view=renderMissionDiagram(s,{esc});
  assert.match(view,/data-map-code="project\/apps\/science\/main.c"/);
  assert.match(view,/data-map-ground="science"/);
  assert.match(view,/data-cad-neighbor/);
  assert.match(view,/cad-box tone-own stack-pick is-selected/);
});

test('CAD scene rotates in model space and the flat map uses the same inventory',()=>{
  const s=fixture(), graph=missionGraph(s,moduleGroups(s.workspace),[], 'Linux','Pi');
  const camera=homeCamera(), scene=stackScene(graph,false,false);
  assert.equal(scene.anchors.has('library:therm_lib'),false);
  assert.equal(scene.anchors.has('device:probe'),true);
  assert.equal(scene.traces.length,2);
  const before=projectPoint(camera,0,50,100);
  const after=projectPoint({...camera,yaw:camera.yaw+1},0,50,100);
  assert.notDeepEqual(before,after);
  assert.match(drawStack(scene,graph,camera,'app:science',false,esc),/class="cad-wire active wire-bus"/);
  s.mapMode='2d';
  assert.match(renderMissionDiagram(s,{esc}),/data-module-action="remove"[^>]*>[\s\S]*?M3 6h18/);
  s.workspace.project.apps=[];s.workspace.project.devices=[];s.workspace.catalog.buses={};
  for(const mode of ['3d','2d']) {
    const view=renderMissionDiagram({...s,mapMode:mode},{esc});
    assert.doesNotMatch(view,/\/dev\/i2c-1|bus:bus1|No devices/);
  }
  s.target='native';s.mapMode='3d';
  assert.doesNotMatch(renderMissionDiagram(s,{esc}),/BCM2711|Raspberry Pi 4B/);
});

test('PCB traces use the selected physical pin for each signal',()=>{
  const s=fixture();
  s.workspace.catalog.buses.bus1.sensor_pins={VCC:[1,17],GND:[6,14],SDA:[3],SCL:[5]};
  s.workspace.project.devices[0].pins={GND:14};
  s.mapSelected='device:probe';
  const view=renderMissionDiagram(s,{esc});
  assert.match(view,/GND 14/);
  assert.equal((view.match(/class="cad-wire active wire-(?!bus)/g)||[]).length,4);
  assert.doesNotMatch(view,/class="cad-wire active wire-bus"/);
});
