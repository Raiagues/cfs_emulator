import test from 'node:test';
import assert from 'node:assert/strict';
import {bootFrame} from '../static/first-boot.js';

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
