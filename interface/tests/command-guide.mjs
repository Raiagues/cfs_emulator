import {test} from 'node:test';
import assert from 'node:assert/strict';
import {commandContext,renderCommandTrail,renderSourceGuide,renderSourceTools,renderInspectorDialog,renderCommandTest,syncCommandToFile} from '../static/source-guide.js';

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
  assert.equal((renderCommandTrail(s,esc).match(/data-guide-step=/g)||[]).length,7);
  assert.match(renderCommandTrail(s,esc),/6\/7/);
  assert.doesNotMatch(renderCommandTrail(s,esc),/<strong>New command/);
  assert.match(renderCommandTrail(s,esc),/data-code-command="reader"/);
  assert.match(renderSourceGuide(s,esc),/Collect samples/);
  assert.match(renderSourceGuide(s,esc),/FC 0/);
  assert.match(renderSourceGuide(s,esc),/byte 8 · 2 B/);
  assert.match(renderInspectorDialog(s,'packet',esc).body,/10 B/);
  assert.match(renderInspectorDialog(s,'dispatch',esc).body,/READER_CMD_MID/);
  assert.match(renderSourceTools(s,esc),/Tags[\s\S]*Packet[\s\S]*Dispatch/);
  s.ground.runs=[{command:'READ_CC',sent:{app:'reader',mid:6144},status:'passed'}];
  assert.match(renderCommandTrail(s,esc),/7\/7/);
  s.ground.runs.push({command:'READ_CC',sent:{app:'reader',mid:6144},status:'timed_out'});
  assert.doesNotMatch(renderCommandTrail(s,esc),/7\/7/);
  s.ground.runs.pop();s.ground.build_fingerprint='prior';
  assert.equal(commandContext(s).test,false);
  s.workspace.builds.native.current=false;
  assert.doesNotMatch(renderInspectorDialog(s,'packet',esc).body,/10 B/);
  s.sourceCommand='CALIBRATE_CC/6144';
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
  assert.match(renderCommandTrail(s,esc),/data-create="app"/);
  s.workspace.apps.push({name:'mine',path:'mission/apps/mine',managed:true});
  assert.match(renderCommandTrail(s,esc),/data-code-command="mine"/);
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
