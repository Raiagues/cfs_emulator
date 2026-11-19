import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderGround,renderGroundRoute,renderTelemetry} from '../static/panels.js';

const esc=value=>String(value??'');
const helpers={esc,icon:()=>'',hex:value=>'0x'+value.toString(16)};
const sample={id:'SAMPLE_APP_NOOP_CC',app:'sample_app',mid:0x1882,code:0,size:8};
const enable={id:'TO_LAB_OUTPUT_ENABLE_CC',app:'to_lab',mid:0x1880,code:6,size:24,fields:[{name:'dest_IP',format:'s',count:16}]};
const state={target:'native',workspace:{project:{apps:[]},mission:{core_services:[{name:'SB'}]}},
 catalog:{commands:[sample,enable,{...sample,id:'FM_NOOP_CC',app:'fm'}],packets:[],apps:[],transport:{}},
 ground:{target:'native',connected:true,first_flight:{telemetry:false,event:false,enable_command:enable.id,noop_command:sample.id,return_host:'127.0.0.1'}}};

test('first contact selects the real output destination and limits the command list',()=>{
 const before=renderGround(state,helpers);
 assert.match(before,/data-command-id="TO_LAB_OUTPUT_ENABLE_CC"/);
 assert.match(before,/name="dest_IP" value="127.0.0.1"/);
 assert.doesNotMatch(before,/data-gs-select="FM_NOOP_CC"/);
 assert.match(renderGround({...state,allGroundApps:true},helpers),/data-gs-select="FM_NOOP_CC"/);
 assert.match(renderTelemetry(state,helpers),/Select ENABLE_OUTPUT/);
 const next={...state,ground:{...state.ground,first_flight:{...state.ground.first_flight,telemetry:true}}};
 assert.match(renderGround(next,helpers),/data-command-id="SAMPLE_APP_NOOP_CC"/);
 assert.match(renderGroundRoute(next,helpers),/first-test-menu/);
 assert.match(renderGroundRoute(next,helpers),/trip-empty-track/);
});

test('the return path is marked off only when flight reports it',()=>{
 const sent={id:sample.id,mid:sample.mid,event_id:2,sent_at:8,bytes:8};
 const active={...state,groundSelection:sample.id,ground:{...state.ground,commands:[sent]}};
 assert.doesNotMatch(renderGroundRoute(active,helpers),/to_lab output off/);
 active.jobs=[{target:'native',action:'run',status:'running',lines:['EVS Port1 66/1/TO_LAB 1: Awaiting enable command.']}];
 assert.match(renderGroundRoute(active,helpers),/to_lab output off/);
 active.jobs[0].lines.push('EVS Port1 66/1/TO_LAB 5: TO telemetry output enabled for IP 127.0.0.1');
 assert.doesNotMatch(renderGroundRoute(active,helpers),/to_lab output off/);
});
