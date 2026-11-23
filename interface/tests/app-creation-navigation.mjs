import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

// Exercise the actual workspace callbacks without starting a server or changing a mission.
const app = await readFile(new URL('../static/app.js', import.meta.url), 'utf8');
function section(start, end) {
  const a = app.indexOf(start), b = app.indexOf(end, a);
  assert(a >= 0 && b > a, 'Missing controller boundary: ' + start);
  assert.equal(app.indexOf(start, a + start.length), -1);
  return app.slice(a, b);
}
const creation = section('function newMissionApp(', '\nfunction newCodeCommand(');
const selectView = section('async function selectView(', '\nfunction openGroundRoute(');

test('creating an app opens its refreshed source in the complete code workspace', async () => {
  for (const root of ['cFS/apps', 'mission/apps']) {
    let wizard, refreshed = false, journey = false, invalidated = false;
    const opened = [], entry = root + '/orbit_demo/fsw/src/orbit_demo.c';
    const state = {workspace:{apps:[]}, commandTask:{app:'old',id:'OLD_CC'},
      sourceCommand:'OLD_CC', sourceStep:{app:'old',index:3}};
    const context = vm.createContext({state, api(){}, esc:String, editorPath:path=>path,
      requireSavedMission(){}, openAppWizard:options=>{wizard=options;return options;},
      async reloadMissionFiles(changed, deleted) {
        assert.deepEqual(changed,[entry]);assert.deepEqual(deleted,[]);
        state.workspace={apps:[{name:'orbit_demo',managed:true,entry}]};refreshed=true;
      },
      async refreshJourney(){journey=true;},
      invalidateSourceActivity(){invalidated=true;},
      async selectView(...args){assert(refreshed && journey);opened.push(args);}, feedback(){},
    });
    vm.runInContext(creation, context);
    context.newMissionApp();
    assert.deepEqual(opened, [], 'Opening the wizard must not leave the current page');
    await wizard.refresh([entry], []);
    assert.deepEqual(opened, [], 'Refreshing must not navigate while save animations are running');
    await wizard.onCreated('orbit_demo');
    assert.deepEqual(opened, [['code',entry]]);
    assert.equal(state.commandTask,null);assert.equal(state.sourceStep,null);
    assert.equal(state.sourceCommand,null);assert(invalidated);
  }
});

test('guided command and free code routes both load the complete explorer', async () => {
  const classes = new Set(['no-tree','no-editor']), calls = [];
  const body = {dataset:{},classList:{
    toggle(name,on){if(on)classes.add(name);else classes.delete(name);},
    remove(name){classes.delete(name);},
  }};
  const entry = 'cFS/apps/orbit_demo/fsw/src/orbit_demo.c';
  const state = {view:'architecture',groundError:'',workspace:{apps:[{managed:true,entry}]}};
  const context = vm.createContext({state,document:{body},activities:{command:()=>{}},
    viewRequest:0,fileOpenRequest:0,treeRequest:0,lastFiles:new Map(),
    recordRoute(...args){calls.push(['route',...args]);},renderToolbar(){},renderView(){},
    terminal:{selectContext(){},show(){}},
    async renderTree(){calls.push(['tree']);},async openFile(path){calls.push(['file',path]);},
    isWorkbench:()=>false,
  });
  vm.runInContext(selectView, context);
  assert.equal(await context.selectView('code',undefined,undefined,null,'command'),true);
  assert.equal(state.activity,'command');assert.equal(body.dataset.activity,'command');
  assert(!classes.has('no-tree'));assert(classes.has('no-editor'));
  assert.deepEqual(calls.filter(call=>call[0]==='tree'),[['tree']]);
  assert.equal(await context.selectView('code',entry),true);
  assert.equal(state.activity,null);assert.equal(body.dataset.activity,undefined);
  assert(!classes.has('no-tree'));assert(!classes.has('no-editor'));assert(classes.has('code-only'));
  assert.deepEqual(calls.filter(call=>call[0]==='file'),[['file',entry]]);
});
