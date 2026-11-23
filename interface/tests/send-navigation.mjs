import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source=await readFile(new URL('../static/app.js',import.meta.url),'utf8');
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert(a>=0&&b>a);return source.slice(a,b);}

test('Send uses the same Ground Station controller as Event, without the legacy lesson',()=>{
 const mountFirstContact=()=>{},mountCommandLesson=()=>{},mountSignalLesson=()=>{};
 const context=vm.createContext({mountFirstContact,mountCommandLesson,mountSignalLesson});
 vm.runInContext(section('const activities =','\nlet activity;')+'\nglobalThis.activities=activities;',context);
 assert.equal(context.activities.send,mountFirstContact);
 assert.equal(context.activities.event,mountFirstContact);
});

test('Send resolves the compiled authored command on reload and preserves an explicit selection',()=>{
 const state={workspace:{apps:[{name:'weather',managed:true,manifest:{commands:[{name:'set_rate'},{name:'calibrate'}]}},
  {name:'shipped',managed:false,manifest:{commands:[{name:'noop'}]}}]}};
 const context=vm.createContext({state});
 vm.runInContext(section('function authoredCommand(', '\nlet navigationRequest'),context);
 assert.deepEqual({...context.authoredCommand(null,{app:'weather',command:'WEATHER_SET_RATE_CC'})},{app:'weather',id:'WEATHER_SET_RATE_CC'});
 assert.equal(context.authoredCommand('WEATHER_CALIBRATE_CC',{app:'weather',command:'WEATHER_SET_RATE_CC'}).id,'WEATHER_CALIBRATE_CC');
 assert.equal(context.authoredCommand('SHIPPED_NOOP_CC').app,'weather');
});

test('an explicit Ground link remounts its selection and keeps the Send route',async()=>{
 const calls=[],state={target:'native'};
 const context=vm.createContext({state,activity:{close(){calls.push('closed');}},
  recordRoute(...args){calls.push(['record',...args]);},async selectView(...args){calls.push(['select',...args]);}});
 vm.runInContext(section('function openGroundRoute(', '\nlet guideTimer;'),context);
 await context.openGroundRoute('weather','WEATHER_SET_RATE_CC',true);
 assert.equal(state.commandLaunch,null);
 assert.equal(state.groundApp,'weather');assert.equal(state.groundSelection,'WEATHER_SET_RATE_CC');
 assert.deepEqual({...state.sendCommand},{app:'weather',command:'WEATHER_SET_RATE_CC'});
 assert.equal(context.activity,null);assert(calls.includes('closed'));
 assert.deepEqual(calls.find(item=>item[0]==='select'),['select','ground',undefined,undefined,null,'send']);
});


test('the toolbar prevents replacing Native binaries while cFS is running',()=>{
 const nodes=new Map();
 function node(){return {hidden:false,disabled:false,dataset:{},classList:{toggle(){}},setAttribute(){},querySelector(){return {textContent:''};},lastElementChild:{textContent:''}};}
 const $=selector=>{if(!nodes.has(selector))nodes.set(selector,node());return nodes.get(selector);};
 const state={target:'native',jobs:[],workspace:{project:{devices:[],board:null,os:null},catalog:{},builds:{native:{exists:true,current:false,stale:true}}},
  hardware:{native:{running:true,os:'Linux'},execution:{running_targets:['native'],target:'native',can_start:false}}};
 for(const name of ['build','run','stop'])$('.'+name+'-action').dataset.job=name;
 const context=vm.createContext({state,$,workspaceReady:true,operation:()=>null,simulationJob:()=>null,
  document:{querySelectorAll(selector){return selector==='.top-actions [data-job]'?['build','run','stop'].map(name=>$('.'+name+'-action')):[];}},
  boardSelector:{update(){}},osSelector:{update(){}},actionLabel:()=>'',syncBenchActions(){},renderProgress(){},renderSimulationPanel(){}});
 vm.runInContext(section('function renderToolbar()', '\nfunction architecture()'),context);
 context.renderToolbar();
 assert.equal($('.build-action').disabled,true);assert.equal($('.build-action').title,'Stop cFS before building');
 assert.equal($('.stop-action').hidden,false);assert.equal($('.stop-action').disabled,false);
 state.hardware.native.running=false;state.hardware.execution={running_targets:[],can_start:true};
 context.renderToolbar();assert.equal($('.build-action').disabled,false);
 assert.equal($('.build-action').title,'Mission sources changed');
});


test('command controls receive completed jobs and fresh hardware even when workspace refresh wins the race',async()=>{
 let resolveHardware;
 const updates=[],hardware=new Promise(resolve=>{resolveHardware=resolve;});
 const state={target:'native',view:'code',activity:'command',jobs:[{id:1,target:'native',action:'build',status:'running'}],
  history:new Map(),hardware:{launch:{native:{action:'build'}}}};
 const activity={update(){updates.push({job:state.jobs[0]?.status,action:state.hardware.launch.native?.action});}};
 const context=vm.createContext({state,activity,jobsPolling:false,loadedJobHistory:true,
  signalJobState:()=>null,selectTargetTerminal(){},isWorkbench:()=>false,
  terminal:{render(){}},renderToolbar(){},feedback(){},actionLabel:()=>'',
  api(endpoint){
   if(endpoint==='jobs?lines=0')return Promise.resolve([{id:1,target:'native',action:'build',status:'succeeded'}]);
   assert.equal(endpoint,'hardware');return hardware;
  },
  async refresh(){activity.update();},
 });
 vm.runInContext(section('async function pollJobs()', '\nfunction updateGround('),context);
 await context.pollJobs();
 assert(updates.some(update=>update.job==='succeeded'),'The lesson must stop showing Building without another event');
 assert.equal(updates.at(-1).action,'build','Workspace can arrive before the new hardware plan');
 resolveHardware({launch:{native:{action:'run'}}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(updates.at(-1),{job:'succeeded',action:'run'},'The Run action must render as soon as the hardware response arrives');
 assert.equal(state.view,'code');assert.equal(state.activity,'command','Refreshing evidence must not navigate');
});
