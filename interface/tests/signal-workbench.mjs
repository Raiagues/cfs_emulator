import {test} from 'node:test';
import assert from 'node:assert/strict';
import {chartPageForDevice,renderSimulationBoard} from '../static/simulation.js';

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
