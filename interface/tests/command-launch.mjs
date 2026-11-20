import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {commandLaunchStep as presentStep} from '../static/command-launch.js';

// Exercise the CLI/HTTP decision and its browser presentation with the same snapshots.
function commandLaunchStep(state, intent, busy) {
 const snapshot = {...state.hardware,builds:state.workspace.builds};
 const script = "import json,sys; from hardware.deployment import next_action; print(json.dumps(next_action(json.load(sys.stdin),sys.argv[1])))";
 const plan = spawnSync('python3',['-c',script,intent.target],{input:JSON.stringify(snapshot),encoding:'utf8'});
 assert.equal(plan.status,0,plan.stderr);
 state.hardware.launch = {[intent.target]:JSON.parse(plan.stdout)};
 return presentStep(state,intent,busy);
}

const intent={target:'native',app:'orbit_demo',id:'ORBIT_DEMO_STAMP_CC'};
function session(){
 return {workspace:{builds:{native:{exists:true,current:false,fingerprint:'new'}}},
  hardware:{execution:{running_targets:['native'],can_start:false},deployed:{native:{fingerprint:'old'}}},
  catalogTarget:'native',catalog:{build_fingerprint:'old',commands:[{app:'sample_app',id:'SAMPLE_APP_NOOP_CC'}]}};
}
test('launching an authored command follows the actual deployment and compiled catalog',()=>{
 const s=session(),step=()=>commandLaunchStep(s,intent)?.action;
 assert.equal(step(),'stop');
 s.hardware.execution={running_targets:[],can_start:true};
 assert.equal(step(),'build');
 assert.equal(commandLaunchStep(s,intent,{action:'build'}).action,undefined);
 s.workspace.builds.native.current=true;
 assert.equal(step(),'run');
 s.hardware.execution.running_targets=['native'];s.hardware.deployed.native.fingerprint='new';
 assert.equal(step(),'catalog');
 s.catalog.build_fingerprint='new';
 assert.equal(step(),'source');
 s.catalog.commands.push({app:'another_app',id:intent.id});
 assert.equal(step(),'source');
 s.catalog.commands.push({app:intent.app,id:intent.id});
 assert.equal(commandLaunchStep(s,intent),null);
});
test('a run on another target is never selected for an authored command',()=>{
 const s=session();s.hardware.execution.running_targets=['physical'];
 assert.equal(commandLaunchStep(s,intent).action,'active');
});
test('an emulator needs its own Linux process before flight can start',()=>{
 const s=session(),qemu={...intent,target:'qemu'};
 s.workspace.builds.qemu={exists:true,current:true,fingerprint:'new'};
 Object.assign(s.hardware,{execution:{can_start:true,running_targets:[]},docker:{available:true},qemu:{linux_ready:false,ssh_configured:true,image_ready:false}});
 assert.equal(commandLaunchStep(s,qemu).action,'setup');
 s.hardware.qemu.image_ready=true;
 assert.equal(commandLaunchStep(s,qemu).action,'boot');
 s.hardware.qemu.linux_ready=true;
 assert.equal(commandLaunchStep(s,qemu).action,'run');
});
