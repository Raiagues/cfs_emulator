import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sourceCommandTestEvidence,commandContext,renderCommandTrail,renderSourceGuide,renderSourceTools,renderInspectorDialog,renderCommandTest,syncCommandToFile} from '../static/source-guide.js';

const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const ref=(path,line,symbol)=>({path,line,symbol,end_line:line});
function state() {
  const root='mission/apps/reader';
  const mid={symbol:'READER_CMD_MID',value:6144,source:ref('mission/sample_defs/reader_ids.h',8,'READER_CMD_MID')};
  const handlers=['READ','CALIBRATE'].map((name,i)=>({
    cc:{symbol:name+'_CC',value:i,source:ref(root+'/ids.h',10+i,name+'_CC')},
    packet_type:name+'_Cmd_t',packet_source:ref(root+'/msg.h',11+i,name+'_Cmd_t'),
    handler:ref(root+'/cmds.c',20+i*5,name+'_Cmd'),source:ref(root+'/dispatch.c',4+i*8,name+'_CC'),
    fields:[{name:'samples',type:'uint16',source:ref(root+'/msg.h',5,'samples'),annotations:[{tag:'range',value:'1…16'}]}],
    prototypes:[ref(root+'/cmds.h',2+i,name+'_Cmd')], events:i?[]:[
      {id:{symbol:'READ_EID',value:9,source:ref(root+'/events.h',3,'READ_EID')},severity:'INFO',source:ref(root+'/cmds.c',21,'CFE_EVS_SendEvent')}],
    annotations:[{tag:'brief',value:'Collect samples',path:root+'/ids.h',line:9}]}));
  const app={name:'reader',path:root,managed:true,behavior:{details:{commands:[{mid,handlers}]}}};
  return {path:root+'/ids.h',files:new Map(),workspace:{apps:[app],libraries:[],builds:{native:{current:true,fingerprint:'build123'}}},
    target:'native',catalogTarget:'native',catalog:{build_fingerprint:'build123',commands:[{app:'reader',id:'READ_CC',mid:6144,code:0,size:10,
      fields:[{name:'samples',format:'uint16',offset:8,size:2}]}]},ground:{target:'native',build_fingerprint:'build123',runs:[]}};
}

test('source trail distinguishes indexed source, unavailable EVS and observed ground results',()=>{
  const s=state();
  assert.match(renderCommandTrail(s,esc),/data-guide-step/);
  s.commandTask={app:'reader',id:'READ_CC',reviewed:[]};
  assert.doesNotMatch(renderCommandTrail(s,esc),/data-state="done"/);
  s.commandTask.reviewed=[0,1,2,3,4,5];
  assert.doesNotMatch(renderCommandTrail(s,esc),/data-state="done"/); // navigation memory is not evidence
  s.sourceActivity={target:'native',app:'reader',command:'READ_CC',steps:Array.from({length:7},(_,i)=>({done:i<6,available:i<6}))};
  assert.equal((renderCommandTrail(s,esc).match(/data-guide-step=/g)||[]).length,7);
  assert.equal((renderCommandTrail(s,esc).match(/data-state="done"/g)||[]).length,6);
  assert.doesNotMatch(renderCommandTrail(s,esc),/<strong>New command/);
  assert.match(renderCommandTrail(s,esc),/data-review-source/);
  assert.match(renderSourceGuide(s,esc),/Collect samples/);
  assert.match(renderSourceGuide(s,esc),/FC 0/);
  assert.match(renderSourceGuide(s,esc),/byte 8 · 2 B/);
  assert.match(renderInspectorDialog(s,'packet',esc).body,/10 B/);
  assert.match(renderInspectorDialog(s,'dispatch',esc).body,/READER_CMD_MID/);
  assert.match(renderSourceTools(s,esc),/Tags[\s\S]*Packet[\s\S]*Dispatch/);
  s.ground.runs=[{command:'READ_CC',sent:{app:'reader',mid:6144},status:'passed'}];
  assert.equal((renderCommandTrail(s,esc).match(/data-state="done"/g)||[]).length,7);
  s.ground.runs.push({command:'READ_CC',sent:{app:'reader',mid:6144},status:'timed_out'});
  assert.equal((renderCommandTrail(s,esc).match(/data-state="done"/g)||[]).length,6);
  s.ground.runs.pop();s.ground.build_fingerprint='prior';
  assert.equal(commandContext(s).test,false);
  s.workspace.builds.native.current=false;
  assert.doesNotMatch(renderInspectorDialog(s,'packet',esc).body,/10 B/);
  s.sourceCommand='CALIBRATE_CC/6144';s.commandTask.id='CALIBRATE_CC';
  assert.match(renderCommandTrail(s,esc),/data-guide-step="4" data-state="pending"/);
});

test('source line and mission overrides keep command identity across real file jumps',()=>{
  const s=state();
  assert.equal(syncCommandToFile(s,11),true);
  assert.equal(commandContext(s).selected.id,'CALIBRATE_CC');
  const ctx=commandContext(s);
  const override=ctx.selected.route.mid.source;
  ctx.selected.handler.cc.source=override;
  s.path=override.path;
  assert.equal(commandContext(s).selected.id,'CALIBRATE_CC');
  s.path='mission/unrelated.h';
  assert.equal(commandContext(s),null);
  assert.equal(renderCommandTrail(s,esc),'');
  assert.match(renderSourceTools(s,esc),/data-source-tab="packet"[^>]*disabled/);
});

test('the Code action selects only mission apps and receipts belong to the current build',()=>{
  const s=state(),app=s.workspace.apps[0];
  app.managed=false;
  assert.match(renderCommandTrail(s,esc),/data-guide-step/);
  assert.doesNotMatch(renderCommandTrail(s,esc),/data-state="done"/);
  s.workspace.apps.push({name:'mine',path:'mission/apps/mine',managed:true});
  assert.match(renderSourceTools(s,esc),/data-code-command="mine"/);
  s.sourceCommand='READ_CC/6144';s.sourceStep={app:'reader',command:s.sourceCommand,index:6};
  s.ground.commands=[{id:'READ_CC',mid:6144,app:'reader',hex:'1800c001000300ff0007'}];
  s.catalog.transport={command_header_size:8};
  assert.match(renderInspectorDialog(s,'packet',esc).body,/18 00/);
  assert.match(renderCommandTest(s,esc),/No test recorded/);
  s.ground.runs=[{command:'READ_CC',status:'passed',sent:{app:'reader',mid:6144},steps:[{observation:{name:'HK',sequence:12}}]}];
  assert.match(renderCommandTest(s,esc),/HK[\s\S]*seq 12/);
  s.ground.build_fingerprint='prior';
  assert.doesNotMatch(renderCommandTest(s,esc),/seq 12/);
  assert.doesNotMatch(renderInspectorDialog(s,'packet',esc).body,/18 00/);
  s.catalog.build_fingerprint='prior';
  assert.doesNotMatch(renderInspectorDialog(s,'packet',esc).body,/10 B/);
});

test('looking up another function code preserves the current author activity',()=>{
  const s=state();
  s.commandTask={app:'reader',id:'CALIBRATE_CC',reviewed:[]};
  s.sourceCommand='READ_CC/6144';
  assert.equal(commandContext(s).selected.id,'CALIBRATE_CC');
  assert.equal(syncCommandToFile(s,10),false);
  const guide=renderSourceGuide(s,esc);
  assert.match(guide,/data-source-jump="mission\/apps\/reader\/ids.h" data-line="10"/);
  assert.doesNotMatch(guide,/data-select-source-command/);
  assert.doesNotMatch(renderCommandTrail(s,esc),/data-state="done"/);
  s.sourceStep={app:'reader',command:'CALIBRATE_CC/6144',index:4};
  assert.match(renderSourceGuide(s,esc),/data-edit-handler/);
  assert.match(renderSourceGuide(s,esc),/READ_EID/);
  assert.match(renderSourceGuide(s,esc),/data-source-jump="mission\/apps\/reader\/cmds.c" data-line="21"/);
});


test('reviewed steps keep their completion while selected and unsaved edits revoke it',()=>{
 const s=state();
 s.sourceActivity={target:'native',app:'reader',command:'READ_CC',steps:Array.from({length:7},(_,i)=>({done:i<6,available:i<6}))};
 const before=JSON.stringify(s.sourceActivity);
 s.sourceStep={app:'reader',command:'READ_CC/6144',index:0};
 assert.match(renderCommandTrail(s,esc),/data-guide-step="0" data-state="done" aria-current="step"/);
 s.sourceStep.index=3;
 assert.match(renderCommandTrail(s,esc),/data-guide-step="3" data-state="done" aria-current="step"/);
 assert.equal(JSON.stringify(s.sourceActivity),before);
 s.files.set(s.path,{content:'changed',saved:'original'});
 assert.match(renderCommandTrail(s,esc),/data-guide-step="0" data-state="pending"/);
});


test('a matching first-contact or authored receipt confirms only the current command and build',()=>{
 for(const tracker of ['first_flight','authored_reply']){
  const s=state();
  s.sourceCommand='READ_CC/6144';s.sourceStep={app:'reader',command:s.sourceCommand,index:6};
  s.ground.commands=[{id:'READ_CC',app:'reader',mid:6144,event_id:5}];
  s.ground[tracker]={receipt:{command:'READ_CC',app:'reader',send_id:5,reply:6,increase:7,baseline:0,count:1,message:'Read confirmed'}};
  assert.equal(commandContext(s).test,true);
  assert.match(renderCommandTest(s,esc),/Read confirmed/);
  assert.match(renderCommandTest(s,esc),/CommandCounter 0 → 1/);
  s.files.set('cFS/libs/shared/dependency.c',{content:'changed',saved:'original',editable:true});
  assert.equal(commandContext(s).test,false);
  assert.doesNotMatch(renderCommandTrail(s,esc),/data-guide-step="6" data-state="done"/);
 }
});

test('unrelated, stale, incomplete and uncorrelated receipts never complete Test',()=>{
 const changes=[
  s=>s.ground.target='qemu',
  s=>s.ground.build_fingerprint='old',
  s=>s.workspace.builds.native.current=false,
  s=>s.ground.first_flight.receipt.command='OTHER_CC',
  s=>s.ground.first_flight.receipt.app='other',
  s=>s.ground.commands[0].mid=6145,
  s=>s.ground.first_flight.receipt.send_id=4,
  s=>s.ground.first_flight.receipt.reply=null,
  s=>s.ground.first_flight.receipt.increase=null,
  s=>s.ground.first_flight.receipt.reply=3,
  s=>s.ground.first_flight.receipt.count=2,
  s=>s.ground.commands.push({...s.ground.commands[0],event_id:9}),
  s=>s.ground.commands=[],
  s=>s.ground.first_flight={answer:true,telemetry:true,downlink_receipt:{send_id:5,mid:6144}},
  s=>s.files.set('mission/sample_defs/platform.h',{content:'changed',saved:'original'})
 ];
 for(const change of changes){
  const s=state();s.ground.commands=[{id:'READ_CC',app:'reader',mid:6144,event_id:5}];
  s.ground.first_flight={receipt:{command:'READ_CC',app:'reader',send_id:5,reply:6,increase:7,baseline:0,count:1}};
  change(s);assert.equal(commandContext(s).test,false,String(change));
 }
 assert.equal(sourceCommandTestEvidence(state(),'reader','READ_CC',undefined).test,false);
});

test('a passed round-trip is also invalid while flight dependency buffers are dirty',()=>{
 const s=state();s.ground.runs=[{command:'READ_CC',sent:{app:'reader',mid:6144},status:'passed'}];
 assert.equal(commandContext(s).test,true);
 s.files.set('cFS/apps/reader/fsw/src/reader.c',{content:'changed',saved:'original'});
 assert.equal(commandContext(s).test,false);
});
