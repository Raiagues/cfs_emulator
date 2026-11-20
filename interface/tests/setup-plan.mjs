import assert from 'node:assert/strict';
import test from 'node:test';
import {nextRepair} from '../static/setup-plan.js';

const failure = label => ({label, status:'failed'});

test('setup repairs shared prerequisites before the emulator image and re-evaluates current checks', () => {
  const rows = ['Emulator image','NASA cFS source','Docker engine ≥ 23','docker'].map(failure);
  assert.equal(nextRepair('qemu',rows).action,'dependencies');
  rows[2].status = rows[3].status = 'passed';
  assert.equal(nextRepair('qemu',rows).action,'clone-cfs');
  rows[1].status = 'passed';
  assert.deepEqual(nextRepair('qemu',rows),{action:'emulator-image',group:'Image',label:'Emulator image'});
  rows[0].status = 'passed';
  assert.equal(nextRepair('qemu',rows),null);
});

test('clicking an individual group scopes installation to observed failures in that group', () => {
  const rows = [failure('NASA cFS source'),failure('Python'),{label:'git',status:'pending'}];
  assert.equal(nextRepair('native',rows,'Source').action,'clone-cfs');
  assert.equal(nextRepair('native',rows,'Compiler'),null);
  assert.equal(nextRepair('native',rows,'Python').action,'native-tools');
});

test('network configuration precedes any remote board setup', () => {
  const rows = ['cFS service','Board login','Board network'].map(failure);
  assert.equal(nextRepair('physical',rows).action,'settings');
  rows[2].status = 'passed';
  assert.equal(nextRepair('physical',rows).action,'board-key');
});
