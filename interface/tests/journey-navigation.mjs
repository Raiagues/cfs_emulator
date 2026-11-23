import {test} from 'node:test';
import assert from 'node:assert/strict';
import {journeyNavigation} from '../static/journey.js';
import {redirectForStep, stepUrl, landingRoute} from '../static/router.js';

const page = path => new URL(path, 'http://studio.test');
const state = {
  target:'native', current:'event', next_route:'/studio?target=native#event',
  steps:{target:{done:true, reachable:true}, boot:{done:true, reachable:true}, event:{done:false, reachable:true},
    app:{done:false, reachable:false}}
};
state.steps.event.route = state.next_route;

test('the server current step survives reload, stopping cFS, and free workspace routes', () => {
  for (const hash of ['target', 'boot', 'event', 'app', 'send', 'ground', 'simulation', 'architecture', 'bench', 'code']) {
    const view = journeyNavigation(page('/studio#' + hash), state);
    assert.equal(view.current, 'event');
    assert.equal(view.completed, 2);
  }
});

test('Next on a completed guided view points to the server route', () => {
  assert.equal(journeyNavigation(page('/studio#boot'), state).next, state.next_route);
  for (const path of ['/studio#event', '/studio#ground','/#target']) {
    assert.equal(journeyNavigation(page(path), state).next, null);
  }
  assert.equal(journeyNavigation(page('/studio#boot'), {...state, optional_board:true}).next, null);
});

test('a locked step redirects to the server current step and a rail view remains reachable', () => {
  assert.equal(redirectForStep('app', state), state.next_route);
  for (const id of ['boot','event','ground','simulation','architecture','code','bench']) {
    assert.equal(redirectForStep(id, state), null);
  }
});

test('Board has its own view and target selection stays explicit', () => {
  const from = page('/studio?target=qemu#boot');
  assert.equal(stepUrl('board', from, 'qemu'), '/?target=physical#board');
  assert.equal(stepUrl('target', from), '/#target');
  assert.equal(stepUrl('event', from, 'qemu'), '/studio?target=qemu#event');
});

test('the connector turns green when its next step is reachable and red only on failure',async()=>{
  const {journeyLine}=await import('../static/journey.js');
  assert.deepEqual(journeyLine(state.steps.boot,state.steps.event),{complete:true,failed:false});
  assert.deepEqual(journeyLine(state.steps.event,state.steps.app),{complete:false,failed:false});
  assert.deepEqual(journeyLine(state.steps.target,{done:false,reachable:true},true),{complete:false,failed:true});
});


test('the entry URL resumes server progress even when browser welcome storage was cleared',()=>{
 for(const welcomeSeen of [true,false])assert.equal(landingRoute(page('/'),state,{welcomeSeen}),state.next_route);
 assert.equal(landingRoute(page('/'),{...state,current:null},{welcomeSeen:true}),'/studio?target=native#ground');
});

test('explicit target and board links keep setup available instead of resuming',()=>{
 for(const path of ['/#target','/?target=native','/?target=qemu#target','/?target=physical#board','/welcome','/studio#ground'])
  assert.equal(landingRoute(page(path),state,{welcomeSeen:false}),null);
});

test('a fresh or reset journey stays in setup, and missing NASA sources cannot redirect into a loop',()=>{
 const fresh={target:null,current:'target',steps:{target:{done:false,reachable:true}}};
 assert.equal(landingRoute(page('/'),fresh,{welcomeSeen:false}),'/welcome');
 assert.equal(landingRoute(page('/'),fresh,{welcomeSeen:true}),null);
 assert.equal(landingRoute(page('/'),state,{welcomeSeen:true,sourcesReady:false}),null);
 assert.equal(landingRoute(page('/'),state,{welcomeSeen:false,sourcesReady:false}),null);
});
