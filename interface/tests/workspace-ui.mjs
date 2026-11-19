// node --experimental-default-type=module --test interface/tests/workspace-ui.mjs
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderMissionDiagram} from '../static/mission-diagram.js';
import {assemblyProgress} from '../static/hardware-links.js';
import {renderGround, renderTelemetry} from '../static/panels.js';
import {renderCommunication} from '../static/communication.js';
import {orbitControls, orbitSubtitle} from '../static/orbit-preview.js';
import {renderSimulationBoard} from '../static/simulation.js';

const html = value => String(value || '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const helpers = {esc:html, icon:()=>'', hex:n=>'0x'+Number(n).toString(16)};
const missionApp={name:'science', included:true, enabled:true, editable:true, managed:true};
const nasaApp={name:'sample_app',included:true, enabled:true};
const library={name:'sample_lib', included:true, used_by:[], built:true};
const state={
  target:'qemu',mapMode:'3d',showLibraries:true,
  workspace:{apps:[missionApp,nasaApp],libraries:[library],
    project:{board:'raspi4b',os:'linux',apps:[missionApp],devices:[{id:'mag',model:'lsm303dlhc_mag',address:30,bus:'i2c-bus.1'}]},
    catalog:{name:'Raspberry Pi 4B',buses:{'i2c-bus.1':{device:'/dev/i2c-1'}}},
    mission:{included:['science','sample_app'],enabled:['science','sample_app'],available:[missionApp,nasaApp],
      available_libraries:[library],core_services:[{name:'SB'},{name:'EVS'}]}},
  ground:{target:'qemu',connected:true,packets:[],events:[]},
  catalogTarget:'qemu',catalog:{commands:[
    {id:'SAMPLE_APP_NOOP_CC',app:'sample_app',mid:6274,code:0,size:8},
    {id:'SCIENCE_RESET_CC',app:'science',mid:6280,code:1,size:8},
    {id:'SCIENCE_NOOP_CC',app:'science',mid:6280,code:0,size:8}],
    packets:[{id:'SCIENCE_HK',mid:2049,app:'science',fields:[]}],transport:{command_port:1234,telemetry_port:2234}}
};

test('CAD and flat maps navigate the same included sources and devices',()=>{
 for (const mode of ['3d','2d']) {
  const page=renderMissionDiagram({...state,mapMode:mode},helpers);
  for (const name of ['science','sample_app']) assert.match(page,new RegExp('data-arch-app="'+name+'"'));
  assert.match(page,/data-arch-library="sample_lib"/);
  assert.match(page,/data-view="bench" data-device="mag"/);
  assert.match(page,/data-arch-source="cFS\/cfe\/modules\/sb\/fsw\/src\/cfe_sb_task.c"/);
  assert.match(page,/data-module-group="mission" data-module-action="new"/);
  const hidden=renderMissionDiagram({...state,mapMode:mode,showLibraries:false},helpers);
  assert.doesNotMatch(hidden,/data-arch-library="sample_lib"/);
 }
 const native=renderMissionDiagram({...state,target:'native'},helpers);
 assert.doesNotMatch(native,/data-device="mag"|Raspberry Pi/);
 assert.match(native,/This computer/);
});

test('Ground opens a mission NOOP and respects explicit selection, packet filtering and real observations',()=>{
 assert.match(renderGround(state,helpers),/data-command-id="SCIENCE_NOOP_CC"/);
 assert.match(renderGround({...state, groundSelection:'SCIENCE_RESET_CC'},helpers),/data-command-id="SCIENCE_RESET_CC"/);
 const search=renderGround({...state, groundQuery:'SAMPLE_APP_NOOP'},helpers);
 assert.match(search,/data-command-id="SAMPLE_APP_NOOP_CC"/);
 assert.doesNotMatch(search,/data-gs-select="SCIENCE_RESET_CC"/);
 const initial=renderTelemetry(state,helpers);
 assert.match(initial,/No telemetry/);assert.doesNotMatch(initial,/SCIENCE_HK/);
 const comm=renderCommunication(state,helpers);
 assert.match(comm,/data-comm-app="sample_app"/);assert.match(comm,/Software Bus/);
 assert.doesNotMatch(comm,/data-module-action|data-create/);
});

test('Orbit controls use mission elements and the sensor catalog can start empty',()=>{
 const elements={perigee:548,apogee:552,inclination:97.59,node:0,argument:90,anomaly:0,model:'J2',epoch:'2026-01-01T00:00:00Z'};
 assert.match(orbitSubtitle(elements),/SSO 550/);
 assert.match(orbitControls(elements),/data-orbit-element="apogee"/);
 const view=renderSimulationBoard({target:'qemu',jobs:[],simulation:{available:[],settings:{orbit:elements,sensors:[]}}},{esc:html});
 assert.match(view,/0 sensors enabled/);assert.doesNotMatch(view,/data-series="/);
 assert.match(view,/data-signal-begin disabled/);
});

test('Hardware advances from empty board to the reader source and the live Ground Station',()=>{
 const workspace={project:{apps:[],devices:[]},catalog:{buses:{},models:{tmp105:{cfs_driver:'tmp105_lib'}}},apps:[],builds:{qemu:{current:false}}};
 const qemu={running:false,linux_ready:false,flight_running:false,ssh_configured:true,image_ready:true};
 const board={target:'qemu',inspected:'board',workspace,hardware:{docker:{available:true},qemu}};
 const view=()=>assemblyProgress(board,html);
 assert.match(view(),/class="assembly-primary" data-add-bus/);
 workspace.catalog.buses['i2c-bus.1']={label:'I²C 1'};
 assert.match(view(),/class="assembly-primary" data-create="device"/);
 workspace.project.devices.push({id:'probe',name:'Temperature',model:'tmp105',address:72});
 assert.match(view(),/class="assembly-primary" data-link-hal="probe"/);
 workspace.project.apps.push({name:'science',sensors:{temperature:'probe'}});
 workspace.apps.push({name:'science',locations:[{id:'sensor.temperature.read',path:'reader.c',line:42}]});
 assert.match(view(),/data-hardware-source="reader.c" data-line="42"/);
 assert.match(view(),/class="assembly-primary" data-workbench-job="build"/);
 workspace.builds.qemu.current=true;
 assert.match(view(),/Start emulator/);
 Object.assign(qemu,{running:true,can_retry_boot:true});
 assert.match(view(),/Retry emulator connection/);
 qemu.linux_ready=true;
 assert.match(view(),/data-workbench-job="run"/);
 qemu.flight_running=true;
 assert.match(view(),/data-workbench-ground="science"/);
});
