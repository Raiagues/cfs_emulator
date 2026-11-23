import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {commandContext, renderCommandTrail} from '../static/source-guide.js';
import {escapeHtml as esc} from '../static/dom.js';

// Exercise the actual unexported save/cache controller with mocked IO and the
// real progress renderer. No browser, flight server or project files are changed.
const app = await readFile(new URL('../static/app.js', import.meta.url), 'utf8');
// Explicit boundaries keep this test dependency-free. A renamed or duplicated
// boundary fails loudly instead of silently exercising the wrong controller.
function boundary(marker) {
  const at = app.indexOf(marker);
  assert(at >= 0, 'Missing controller boundary: ' + marker);
  assert.equal(app.indexOf(marker, at + marker.length), -1, 'Duplicate controller boundary: ' + marker);
  return at;
}
function section(start, end) {
  const first = boundary(start), last = boundary(end);
  assert(last > first, 'Controller boundaries are out of order: ' + start);
  return app.slice(first, last);
}
function declaration(marker) {
  const first = boundary(marker), last = app.indexOf('\n', first);
  assert(last > first && app.slice(first, last).endsWith(';'), 'Expected a complete declaration: ' + marker);
  return app.slice(first, last);
}
const reviewStart = " else if('reviewSource' in d)";
const review = section(reviewStart, "\n else if('guideStep' in d").slice(reviewStart.length);
const controller = [
  declaration('let sourceActivityRequest='),
  declaration('let workspaceRequest='),
  section('function invalidateSourceActivity(){', '\nasync function refreshSourceActivity('),
  section('async function refreshSourceActivity(ctx,force=false){', '\nfunction renderEditorActivity()'),
  section('function renderEditorActivity(){', '\n\nfunction syncScroll()'),
  section('async function saveFile(path) {', '\nasync function save(){'),
  section('async function saveAll(){', '\nasync function refreshSimulation()'),
  section('async function refresh(tree=false) {', '\nasync function renderTree()'),
  'async function reviewSource() ' + review,
].join('\n');
const path = 'cFS/apps/example/ids.h';
const command = 'EXAMPLE_NOOP_CC';
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  let disk = 'old source', revision = 'old', reads = 0, hold = false, held, heldReview;
  const nodes = new Map();
  const $ = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {hidden:false,innerHTML:'',textContent:'',replaceChildren(){}});
    return nodes.get(selector);
  };
  const workspace = {name:'fixture', apps:[{name:'example',path:'cFS/apps/example',behavior:{details:{commands:[{
    mid:{value:0x1882},handlers:[{cc:{symbol:command,source:{path,line:1}}}],
  }]}}}],builds:{native:{current:false}}};
  const state = {target:'native',view:'code',path,files:new Map([[path,{editable:true,content:disk,saved:disk,hash:revision}]]),workspace};
  const snapshot = () => ({target:'native',app:'example',command,
    steps:Array.from({length:7},(_,i)=>({available:i===0,done:i===0&&revision==='old',fingerprint:revision,sources:{[path]:revision}})),
    files:{[path]:revision==='old'}});
  const api = async (route, body) => {
    if (route.startsWith('source/activity?')) {
      reads++;
      const result = snapshot();
      if (hold) {hold = false; return new Promise(resolve => {held = () => resolve(result);});}
      return result;
    }
    if (route === 'source/activity') {
      const result = snapshot();
      return new Promise(resolve => {heldReview = () => resolve(result);});
    }
    if (route === 'file') {
      assert.equal(body.expected_hash, revision);
      disk = body.content; revision = 'new';
      return {hash:revision,annotations:[]};
    }
    if (route === 'workspace') return {...workspace, sourceRevision:revision};
    throw Error('Unexpected API '+route);
  };
  const context = vm.createContext({state,api,$,commandContext,renderCommandTrail,renderCommandTest:()=>'',esc,
    Date:{now:()=>1000},URLSearchParams,workspaceReady:true,
    document:{body:{classList:{contains:()=>true}}},renderTabs(){},renderToolbar(){},renderTree(){},backendState(){},markFiles(){},openFile(){},
    renderView(){context.renderEditorActivity();},
  });
  vm.runInContext(controller, context);
  return {context,state,nodes,
    reads:()=>reads,
    green:()=>/data-guide-step="0" data-state="done"/.test($('#command-trail').innerHTML),
    holdRead(){hold=true;},resolveHeld(){held();},resolveReview(){heldReview();},
    externalSave(){revision='new';},
  };
}

test('reviewed source loses completion immediately after edit/saveAll within the cache TTL', async () => {
  const f = fixture();
  await f.context.refreshSourceActivity(commandContext(f.state));
  assert(f.green(), 'server review initially appears complete');
  f.state.files.get(path).content = 'edited source';
  f.context.renderEditorActivity();
  assert(!f.green(), 'dirty source must not appear reviewed');
  assert.equal(f.reads(), 1, 'the original five-second cache is still active');
  await f.context.saveAll();
  await flush();
  assert.equal(f.state.files.get(path).content, f.state.files.get(path).saved);
  assert.equal(f.reads(), 2, 'saving forces a fresh review read without further interaction');
  assert(!f.green(), 'saved new content requires its own review');
});

test('a pre-save request completing later cannot restore old green progress', async () => {
  const f = fixture();
  await f.context.refreshSourceActivity(commandContext(f.state));
  f.holdRead();
  const oldRead = f.context.refreshSourceActivity(commandContext(f.state), true);
  f.state.files.get(path).content = 'new handler source';
  await f.context.saveFile(path);
  await flush();
  assert(!f.green());
  f.resolveHeld();
  await oldRead;
  assert(!f.green(), 'the superseded response must be ignored');
  assert.equal(f.state.sourceActivity.steps[0].fingerprint, 'new');
});

test('workspace refresh invalidates reviews after a command-lesson or external source save', async () => {
  const f = fixture();
  await f.context.refreshSourceActivity(commandContext(f.state));
  assert(f.green());
  f.externalSave();
  await f.context.refresh();
  await flush();
  assert.equal(f.reads(), 2);
  assert(!f.green(), 'a changed workspace cannot reuse a cached source review');
});


test('a review POST started before saving cannot restore completion after the save', async () => {
  const f = fixture();
  await f.context.refreshSourceActivity(commandContext(f.state));
  const oldReview = f.context.reviewSource();
  assert.equal(f.state.sourceReviewBusy, true);
  f.state.files.get(path).content = 'edited while the review request was pending';
  await f.context.saveFile(path);
  await flush();
  assert(!f.green());
  f.resolveReview();
  await oldReview;
  assert(!f.green(), 'the old review acknowledgement must not replace current evidence');
  assert.equal(f.state.sourceActivity.steps[0].fingerprint, 'new');
  assert.equal(f.state.sourceReviewBusy, false);
});
