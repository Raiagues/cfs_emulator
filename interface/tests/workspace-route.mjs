import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceRoute, workspaceTarget} from '../static/workspace-route.js';

test('a first-flight deep link opens its own screen during hydration', () => {
  for (const [id, view] of Object.entries({
    boot:'boot', event:'ground', send:'ground', command:'code', app:'architecture', sensor:'simulation', test:'simulation'
  })) {
    assert.deepEqual(workspaceRoute('#' + id), {id, view});
  }
  assert.deepEqual(workspaceRoute('#code'), {id:'code', view:'code'});
  assert.deepEqual(workspaceRoute(''), {id:'architecture', view:'architecture'});
  assert.deepEqual(workspaceRoute('#constructor'), workspaceRoute(''));
});

test('ground follows the live flight, or the target explicitly chosen in setup', () => {
  const execution = {target:'qemu', preferred_target:'physical'};
  assert.equal(workspaceTarget(null, execution), 'qemu');
  assert.equal(workspaceTarget('invalid', execution), 'qemu');
  assert.equal(workspaceTarget('native', execution), 'native');
  assert.equal(workspaceTarget(null, {preferred_target:'physical'}), 'physical');
  assert.equal(workspaceTarget(null, {}), undefined);
});
