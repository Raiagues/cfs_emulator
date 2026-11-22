import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderGround,renderGroundRoute,renderTelemetry} from '../static/panels.js';

const esc=value=>String(value??'');
const helpers={esc,icon:()=>'',hex:value=>'0x'+value.toString(16)};
const sample={id:'SAMPLE_APP_NOOP_CC',app:'sample_app',mid:0x1882,code:0,size:8};
const enable={id:'TO_LAB_OUTPUT_ENABLE_CC',app:'to_lab',mid:0x1880,code:6,size:24,fields:[{name:'dest_IP',format:'s',count:16}]};
const state={target:'native',catalogTarget:'native',workspace:{project:{apps:[]},mission:{core_services:[{name:'SB'}]}},
 catalog:{commands:[sample,enable,{...sample,id:'FM_NOOP_CC',app:'fm'}],packets:[],apps:[],transport:{}},
 ground:{target:'native',connected:true,first_flight:{telemetry:false,event:false,enable_command:enable.id,noop_command:sample.id,return_host:'127.0.0.1'}}};

test('Event waits for its target catalog before displaying session state or connection controls',()=>{
 for(const pending of [{catalog:null,catalogLoading:false},{catalog:null,catalogLoading:true},{catalogTarget:'qemu'}]){
   const page=renderGround({...state,...pending},helpers);
   assert.match(page,/role="status"/);
   assert.match(page,/Reading catalog/);
   assert.doesNotMatch(page,/No commands|Disconnected|No telemetry|data-command-id=|data-ground="start"|id="ground-route"/);
 }
 const error=renderGround({...state,catalog:null,groundError:'Catalog request failed'},helpers);
 assert.match(error,/role="alert"/);
 assert.match(error,/Catalog request failed/);
 assert.match(error,/data-ground="catalog"/);
 assert.doesNotMatch(error,/Reading catalog/);
 const refreshed=renderGround({...state,catalogLoading:true},helpers);
 assert.match(refreshed,/data-command-id="TO_LAB_OUTPUT_ENABLE_CC"/);
});

test('an Event received on the previous target cannot select a test on the new target',()=>{
 const changing={...state,target:'qemu',catalogTarget:'qemu',groundSelection:sample.id,
   ground:{...state.ground,first_flight:{event:true}},
   testPlans:{plans:[{id:'sample-noop',name:'NOOP event',command:sample.id,steps:[]}]}};
 assert.match(renderGroundRoute(changing,helpers),/class="first-test-menu"/);
 assert.doesNotMatch(renderGround(changing,helpers),/>Run test</);
});

test('Event shows the action requested by the selected target even before the catalog loads',()=>{
 const hardware={launch:{native:{action:'build',label:'Build cFS'}}};
 for(const catalog of [null,state.catalog]){
   assert.match(renderGround({...state,catalog,hardware},helpers),/data-ground="prepare"[^>]*>[^<]*Build cFS/);
 }
 assert.doesNotMatch(renderGround(state,helpers),/data-ground="prepare"/);
});

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

test('the send journal retains other commands and scopes each return to its original send',()=>{
 const flight={...state.ground.first_flight,telemetry:true,event:true,answer:true,
   downlink_receipt:{send_id:1,mid:0x801},receipt:{send_id:9,reply:11,increase:12,baseline:2,count:3,message:'Sample NOOP confirmed'}};
 const commands=[{...enable,event_id:1,sent_at:1},{...sample,event_id:9,sent_at:2},{...enable,event_id:15,sent_at:3}];
 const after={...state,groundSelection:sample.id,ground:{...state.ground,first_flight:flight,commands}};
 const page=renderGroundRoute(after,helpers);
 assert.match(page,/data-inspect-send="1"/);
 assert.match(page,/data-inspect-send="15"/);
 assert.match(page,/Telemetry · MID 0x801/);
 assert.match(page,/EVS · Sample NOOP confirmed · CommandCounter 2 → 3/);
 const latest=renderGroundRoute({...after,groundSelection:enable.id},helpers);
 assert.doesNotMatch(latest,/<circle[^>]+class="trip-packet returning"/);
});
