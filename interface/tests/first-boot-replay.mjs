import test from 'node:test';
import assert from 'node:assert/strict';
import {bootFrame,bootLayers,bootStages,stageProgress} from '../static/first-boot.js';

test('replay clears measured compilation progress during installation and catalog extraction', () => {
  const snapshot={job:{},trace:[{ms:1,phase:'build',percent:80,activity:'Compiling'},
    {ms:2,percent:null,activity:'Installing'},{ms:3,activity:'Indexing catalog'},
    {ms:4,phase:'boot',guest_stage:4},{ms:5,phase:'run',fact:{state:'APPS_INIT'}}]};
  const read=ms=>{
    const {job,flight}=bootFrame(snapshot,ms);
    return stageProgress(job.phase,job,flight.states);
  };
  assert.deepEqual(read(1),{label:'Compiling',percent:80});
  assert.deepEqual(read(2),{label:'Installing',percent:null});
  assert.deepEqual(read(3),{label:'Indexing catalog',percent:null});
  assert.deepEqual(read(4),{label:'Booting Linux',percent:null});
  assert.deepEqual(read(5),{label:'Loading apps',percent:null});
  // Older receipts can contain a 100% compiler reading carried into installation.
  assert.deepEqual(stageProgress('build',{build_percent:100,build_activity:'Installing'},[]),
    {label:'Installing',percent:null});
});

test('boot playback reveals compiler, process and EVS observations at their recorded times', () => {
  const snapshot = {
    job:{id:'boot', action:'first-boot'}, running:true, stopped:false, unverified:false,
    trace:[
      {ms:0,phase:'build'}, {ms:100,percent:15,line:'[ 15%] example.o'},
      {ms:310,phase:'run'}, {ms:330,fact:{process_started:true},line:'CFE_PSP: startup'},
      {ms:400,fact:{app:'DEMO',spacecraft:49,eid:9},line:'EVS Port2 test 49/1/DEMO 9: Initialized'},
      {ms:500,fact:{state:'OPERATIONAL'},line:'CFE_ES_Main entering OPERATIONAL state'}
    ]
  };
  const building = bootFrame(snapshot,300);
  assert.equal(building.job.phase, 'build');
  assert.equal(building.job.build_percent, 15);
  assert.equal(building.flight.process_started,false);
  assert.deepEqual(building.lines,['[ 15%] example.o']);
  const started = bootFrame(snapshot,401);
  assert.equal(started.job.phase, 'run');
  assert.equal(started.flight.initialized.DEMO.spacecraft,49);
  assert.deepEqual(started.flight.states,[]);
  const finished = bootFrame(snapshot,500);
  assert.deepEqual(finished.flight.states,['OPERATIONAL']);
  assert.equal(finished.running,false);
});

test('each startup card requires its own observation; a batched record can be inspected exactly', () => {
  const states=['EARLY_INIT','CORE_STARTUP','CORE_READY','APPS_INIT','OPERATIONAL'];
  const snap={target:'qemu', job:{id:'flight',action:'first-boot'}, hardware:'Pi',os:'Linux',
    apps:[{name:'demo',task:'DEMO'}],services:['ES','EVS'],es_states:states,trace:[
      {ms:1,phase:'build'},{ms:2,phase:'boot',guest_stage:3},{ms:3,guest_stage:4},
      {ms:6,phase:'run'},{ms:6,fact:{layer:'psp'}},{ms:6,fact:{layer:'osal'}},
      {ms:6,fact:{state:'EARLY_INIT'}},{ms:6,fact:{state:'CORE_STARTUP'}},
      {ms:6,fact:{app:'DEMO'}},{ms:6,fact:{state:'APPS_INIT'}},{ms:6,fact:{state:'OPERATIONAL'}}
    ]};
  const at=index=>bootFrame(snap,snap.trace[index].ms,index);
  assert.deepEqual([0,1,2,4,5,6,8].map(i=>bootLayers(at(i)).auto), ['build','hw','os','psp','osal','cfe','apps']);
  assert.deepEqual(bootStages(at(7)).startup.map(c=>c.state),['done','active','waiting','waiting','waiting']);
  assert.deepEqual(bootStages(at(10)).startup.map(c=>c.state),['done','done','waiting','done','done']);
  assert.deepEqual(bootStages(at(10)).preparation.map(c=>c.state),['done','done']);
  assert.equal(bootLayers(at(7)).layers[0][3][0][1],false);
  assert.equal(bootLayers(at(8)).layers[0][3][0][1],true);
  const runOnly=at(10);
  runOnly.job.action='run';
  runOnly.trace=runOnly.trace.filter(e=>!['build','boot'].includes(e.phase));
  assert.deepEqual(bootStages(runOnly).preparation.map(c=>c.state),['waiting','waiting']);
  const osalFirst = at(3);
  osalFirst.flight.platform_layers = ['osal'];
  osalFirst.flight.process_started = true;
  const platform = bootLayers(osalFirst).layers;
  assert.equal(platform.find(([id])=>id==='osal')[4],true);
  assert.equal(platform.find(([id])=>id==='psp')[4],false);
});

test('a build preparing the catalog is active while the previous deployment is stopped',()=>{
  const data={target:'native',starting:true,stopped:true,flight:{},job:{id:'new',phase:'build',status:'running',build_activity:'Indexing catalog'},
    apps:[],services:[],es_states:[],trace:[{ms:0,phase:'build'}]};
  const building=bootStages(data).preparation[0];
  assert.equal(building.state,'active');
  assert.equal(building.caption,'Indexing catalog');
  assert.equal(building.percent,null);
  data.starting=false;data.job.status='failed';
  assert.equal(bootStages(data).preparation[0].caption,'Failed');
});
