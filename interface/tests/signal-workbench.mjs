import {test} from 'node:test';
import {orbitControls} from '../static/orbit-preview.js';
import assert from 'node:assert/strict';
import {changePattern,chartPageForDevice,previewValue,renderSimulationBoard,renderSimulationSettings} from '../static/simulation.js';

const esc=value=>String(value??'');
const sensor={device:'probe',enabled:true,signals:{temperature:{enabled:true,function:'constant'}}};
const probe={id:'probe',name:'Cabin',model:'tmp105',bus:'i2c-bus.1',address:72,defaults:sensor,
  qom_path:'/machine/peripheral/probe',device_argument:'tmp105,id=probe,bus=i2c-bus.1,address=0x48',
  properties:{temperature:{unit:'°C',raw_unit:'millidegrees Celsius',scale:1000,register:0}}};
const state={target:'qemu',jobs:[],workspace:{project:{buses:['i2c-bus.1']}},
  simulation:{available:[probe],settings:{sensors:[sensor]}}};

test('each instrument tab keeps the stream separate from local test jobs',()=>{
 const preview={id:'dry',action:'simulate-preview',device:'probe',status:'running',lines:['local value']};
 for(const tab of ['signals','python','test','qemu']){
  const page=renderSimulationBoard({...state,signalView:tab,jobs:[preview]},{esc});
  assert.match(page,/data-orbit-clock/);
  assert.match(page,/class="signal-session-state" data-active="false"/);
  assert.match(page,/Synthetic data is off/);
  assert.match(page,/Local test running/);
  assert.doesNotMatch(page,/data-board-stop="simulate-preview"/);
 }
 const qemu=renderSimulationBoard({...state,signalView:'qemu'},{esc});
 assert.match(qemu,/-device tmp105,id=probe,bus=i2c-bus.1,address=0x48/);
 assert.match(qemu,/Configured buses/);
 assert.doesNotMatch(qemu,/sent to QEMU/);
});

test('opening a device finds its chart page even with multiple units per device',()=>{
 const motion={...probe, id:'motion',properties:{a:{unit:'g'},b:{unit:'g'},t:{unit:'°C'},v:{unit:'V'}}};
 const end={...probe,id:'last'};
 assert.equal(chartPageForDevice({...state.simulation,available:[motion,end]},'last'),1);
 assert.equal(chartPageForDevice({...state.simulation,available:[motion,end]},'motion'),0);
});


test('the sensor form keeps the waveform, Python function and noise independent',()=>{
 const thermal=changePattern({initial:20,enabled:true,noise:'gaussian',noise_level:0.75},'orbit.thermal');
 const device={...probe,sample_line:8,functions:[{name:'probe_curve',line:12}]};
 function form(signal){
  const entry={...sensor,signals:{temperature:signal}};
  return renderSimulationSettings({...state,selectedDevice:device.id,
   simulation:{available:[device],settings:{sensors:[entry],interval:1}}},{esc});
 }
 const html=form(thermal);
 assert.match(html,/<option value="orbit.thermal" selected>/);
 assert.match(html,/<option value="gaussian" selected>/);
 assert.match(html,/name="noise_level" value="0.75"/);
 const custom=changePattern(thermal,'python:probe_curve');
 assert.equal(custom.function,'custom');
 assert.equal(custom.custom,'probe_curve');
 assert.equal(custom.noise,'gaussian');
 assert.match(form(custom),/<option value="python:probe_curve" selected>/);
 const limits={min:-30,max:60};
 assert.equal(previewValue(thermal,0,1,limits),null); // orbital curve has not arrived
 const sine=changePattern({...thermal,noise:'uniform'},'sine');
 const noisy=previewValue(sine,0,1,limits);
 assert.ok(noisy>=19.25 && noisy<=20.75);
 assert.notEqual(noisy,20);
 assert.equal(previewValue({...sine,noise:'none'},0,1,limits),20);
});


test('manual orbital elements show the session epoch in UTC with millisecond precision',()=>{
 const elements={model:'J2',perigee:500,apogee:550,inclination:50,node:30,argument:0,anomaly:14,epoch:'2026-02-22T11:00:00.123456Z'};
 const form=orbitControls(elements);
 assert.match(form,/Epoch \(UTC\)<input type="datetime-local" data-orbit-epoch/);
 assert.match(form,/value="2026-02-22T11:00:00.123"/);
});
