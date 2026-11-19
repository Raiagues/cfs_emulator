import {test} from 'node:test';
import assert from 'node:assert/strict';
import {journeyNavigation, stepUrl} from '../static/journey.js';

const route = path => new URL(path, 'http://studio.test');
const passed = {done: true, observed_at: 5};

test('Boot selects Boot while checks are pending and advances only for its live target', () => {
  const page = route('/studio?target=qemu#boot');
  const state = {target: 'qemu', steps: {boot: passed}};
  const stopped = journeyNavigation(page, state);
  assert.equal(stopped.current, 'boot');
  assert.equal(stopped.next, null);
  assert.equal(stopped.done[0], false);
  assert.equal(stopped.done[1], true);
  assert.equal(journeyNavigation(page, {...state, bootReadyTarget: 'physical'}).next, null);
  assert.equal(journeyNavigation(page, {...state, bootReadyTarget: 'qemu'}).next, 'event');
});

test('Workspace Next advances from the open activity after its own evidence', () => {
  const pairs = [['event', 'app'], ['app', 'command'], ['command', 'send'], ['send', 'sensor'],
    ['sensor', 'test'], ['test', 'board']];
  for (const [current, next] of pairs) {
    const page = route('/studio#' + current);
    const state = {steps: {[current]: passed}};
    assert.equal(journeyNavigation(page).next, null);
    assert.equal(journeyNavigation(page, state).next, next);
    assert.equal(journeyNavigation(page, {...state, since: 5}).next, null);
  }
});

test('Direct links, rail views and shared activities retain their own selection', () => {
  const aliases = {bench:'sensor', ground:'event', event:'event', send:'send', simulation:'sensor',
    sensor:'sensor', test:'test', code:'command', command:'command', architecture:'app', app:'app'};
  for (const [hash, expected] of Object.entries(aliases)) {
    assert.equal(journeyNavigation(route('/studio#' + hash)).current, expected);
  }
  assert.equal(journeyNavigation(route('/studio')).current, 'app');
  assert.equal(journeyNavigation(route('/')).current, 'target');
  assert.equal(journeyNavigation(route('/infrastructure')).current, 'target');
  assert.equal(journeyNavigation(route('/studio#boot'), {setup:true}).current, 'target');
  assert.equal(journeyNavigation(route('/?target=physical')).current, 'board');
  assert.equal(journeyNavigation(route('/?target=physical#target')).current, 'target');
  assert.equal(journeyNavigation(route('/?target=physical'), {target:'native'}).current, 'target');
  assert.equal(journeyNavigation(route('/'), {steps:{target:passed}}).next, null);
});

test('Guide links keep workspace targets and do not reload the document', () => {
  const page = route('/studio/?target=qemu#boot');
  const next = new URL(stepUrl('event', page, 'qemu'), page);
  assert.equal(next.pathname, page.pathname);
  assert.equal(next.search, page.search);
  assert.equal(next.hash, '#event');
  assert.equal(stepUrl('boot', route('/'), 'physical'), '/studio?target=physical#boot');
  assert.equal(stepUrl('board', page, 'qemu'), '/?target=physical');
  assert.equal(stepUrl('target', page, 'qemu'), '/?target=qemu#target');
});
