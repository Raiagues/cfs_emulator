// Real explorer and command-lesson controllers, isolated from flight processes and project files.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const staticRoot = new URL('../../static/', import.meta.url);
const app = await readFile(new URL('app.js',staticRoot),'utf8');
function section(start,end) {
  const a=app.indexOf(start),b=app.indexOf(end,a);
  assert(a>=0&&b>a,'Missing explorer controller: '+start);
  return app.slice(a,b);
}
const explorer = [
  section('async function renderTree()', '\nfunction gitBadge('),
  section('function gitBadge(', '\nasync function loadTree('),
  section('async function loadTree(', '\nlet fileOpenRequest='),
  section('async function revealFile(', '\nfunction markFiles('),
  section('function markFiles(', '\nlet sourceActivityRequest='),
].join('\n');
const directory = path=>({type:'directory',path,name:path.split('/').at(-1)});
const file = path=>({type:'file',path,name:path.split('/').at(-1)});
const root = 'cFS/apps/orbit_demo';
const dispatch = root+'/fsw/src/orbit_demo_dispatch.c';
const header = root+'/config/default_orbit_demo_msgdefs.h';
const nasa = 'cFS/cfe/README.md';
const tree = {
  flight:[directory('cFS')], cFS:['apps','cfe','osal','psp','libs'].map(name=>directory('cFS/'+name)),
  'cFS/apps':[directory(root),directory('cFS/apps/sample_app')],
  [root]:[directory(root+'/fsw'),directory(root+'/config'),file(root+'/CMakeLists.txt')],
  [root+'/fsw']:[directory(root+'/fsw/src')], [root+'/fsw/src']:[file(dispatch)],
  [root+'/config']:[file(header)], 'cFS/cfe':[file(nasa)],
};
const content = {
  [dispatch]:'void ORBIT_DEMO_Dispatch(void)\n{\n    /* Dispatch source */\n}\n',
  [header]:'#define ORBIT_DEMO_SIZE 32\n',
  [nasa]:'# Core Flight Executive\n\nComplete NASA source documentation.\nLast line stays visible.\n',
};
const lesson = {stage:3,view:3,app:'orbit_demo',symbol:'ORBIT_DEMO_SET_RATE_CC',path:dispatch,
  steps:['Code','Struct','Prototype','Dispatch','Events','Handler','Test'],completed:[true,true,true,false,false,false,false],
  files:[dispatch],content:content[dispatch],ranges:[[1,4]]};

async function launch() {
  return chromium.launch({headless:true,
    ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{}),
    ...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{}),
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
}

test('command tutorial browses the full cFS tree without losing its selected step',async()=>{
  const browser=await launch(),page=await browser.newPage();
  const errors=[],requests=[];
  page.on('pageerror',error=>{errors.push(error.message);console.error(error.message);});
  try {
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      assert.equal(url.origin,'http://explorer.test');
      const reply=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
      if(url.pathname==='/api/session')return reply({token:'fixture'});
      if(url.pathname.startsWith('/api/')) {
        requests.push([route.request().method(),url.pathname]);
        assert.equal(route.request().method(),'GET','Browsing must not mutate flight sources');
        if(url.pathname==='/api/tree')return reply({entries:tree[url.searchParams.get('path')]||[]});
        if(url.pathname==='/api/command/lesson')return reply(lesson);
        if(url.pathname==='/api/file')return reply({content:content[url.searchParams.get('path')],editable:true});
        throw Error('Unexpected API '+url.pathname);
      }
      if(url.pathname==='/updates.js')return route.fulfill({contentType:'text/javascript',body:'export const onUpdate=()=>()=>{};'});
      if(url.pathname==='/studio')return route.fulfill({contentType:'text/html',body:`<!doctype html>
        <body data-activity="command"><span id="explorer-title"></span><aside id="tree"></aside><main id="view"></main>
        <script type="module">
          import {api} from '/api.js'; import {icon} from '/ui.js'; import {escapeHtml as esc} from '/dom.js';
          import {mountCommandLesson} from '/command-lesson.js';
          const $=selector=>document.querySelector(selector),treeStates=new Map(),fileRoot=()=> 'flight';
          const guarded=fn=>(...args)=>Promise.resolve(fn(...args)).catch(error=>{throw error;});
          const state={target:'native',view:'code',files:new Map(),jobs:[],hardware:{execution:{running_targets:[]}}};
          let treeRequest=0,fileOpenRequest=0;
          ${explorer}
          await renderTree();
          window.edited=[];
          window.controller=mountCommandLesson(document.querySelector('#view'),{state,startJob:()=>{throw Error('Unexpected flight action');},
            sourceOpened:path=>{state.path=path;window.revealing=revealFile(path);},openEditor:path=>window.edited.push(path)});
          document.querySelector('#tree').addEventListener('click',event=>{
            const button=event.target.closest('[data-file]');if(button)window.controller.openFile(button.dataset.file);
          });
        </script></body>`});
      const path=new URL(url.pathname.slice(1),staticRoot);
      assert(fileURLToPath(path).startsWith(fileURLToPath(staticRoot)));
      return route.fulfill({contentType:'text/javascript',body:await readFile(path)});
    });
    await page.goto('http://explorer.test/studio#command');
    await page.waitForSelector(`[data-file="${dispatch}"].selected`);
    assert.equal(await page.locator('.command-tree').count(),0,'The tutorial must not create a filtered duplicate tree');
    for(const path of ['cFS','cFS/apps',root,'cFS/apps/sample_app','cFS/cfe','cFS/osal','cFS/psp','cFS/libs'])
      assert.equal(await page.locator(`details[data-path="${path}"]`).count(),1,path);
    await page.locator('details[data-path="cFS/cfe"]>summary').click();
    await page.locator(`[data-file="${nasa}"]`).click();
    await page.waitForSelector(`[data-file="${nasa}"].selected`);
    assert.match(await page.locator('.command-source').innerText(),/Last line stays visible/);
    assert.equal(await page.locator('[data-command-view="3"]').getAttribute('aria-current'),'step');
    assert.equal(new URL(page.url()).hash,'#command');
    await page.locator('[data-command-action="return"]').click();
    await page.waitForSelector(`[data-file="${dispatch}"].selected`);
    await page.locator(`details[data-path="${root}/config"]>summary`).click();
    await page.locator(`[data-file="${header}"]`).click();
    await page.waitForSelector(`[data-file="${header}"].selected`);
    await page.locator('[data-command-edit]').click();
    assert.deepEqual(await page.evaluate(()=>window.edited),[header]);
    assert.equal(await page.locator('[data-command-view="3"]').getAttribute('aria-current'),'step');
    assert.deepEqual(errors,[]);assert(requests.length>5);
  } finally {await browser.close();}
});

test('app wizard previews cFS files and identifies the created app for the editor callback',async()=>{
  const browser=await launch(),page=await browser.newPage(),errors=[];
  const name='orbit_demo',entry=`cFS/apps/${name}/fsw/src/${name}.c`;
  const files={
    [`cFS/apps/${name}/CMakeLists.txt`]:'add_cfe_app(orbit_demo source.c)',
    [entry]:'void ORBIT_DEMO_AppMain(void) {}',
    [`cFS/apps/${name}/config/default_${name}_msgstruct.h`]:'struct Message {};',
  };
  page.on('pageerror',error=>{errors.push(error.message);console.error(error.message);});
  try {
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      assert.equal(url.origin,'http://wizard.test');
      if(url.pathname==='/studio')return route.fulfill({contentType:'text/html',body:`<!doctype html><body>
        <script type="module">
          import {openAppWizard} from '/app-wizard.js';import {escapeHtml as esc} from '/dom.js';
          window.created=[];window.wizardClosed=0;window.refreshed=[];
          const settings={priority:50,stack_size:16384,wakeup_hz:1,hk_hz:1};
          openAppWizard({workspace:{mission:{source:{hash:'revision'}}},initialName:'${name}',esc,
            sourcePath:path=>path.replace(/^mission\\/apps\\//,'cFS/apps/'),requireSaved(){},
            async api(route,body){
              if(route==='mission/draft')return {files:${JSON.stringify(files)},draft:{kind:'app',name:body.name,settings},
                expected_hash:'revision',plan_hash:'plan',preview:{build:{module:body.name},entry_point:'ORBIT_DEMO_AppMain'}};
              if(route==='mission/save')return {changed:${JSON.stringify(Object.keys(files))},deleted:[]};
              throw Error('Unexpected API '+route);
            },
            async refresh(changed,deleted){window.refreshed.push({changed,deleted});},
            async onCreated(createdName){if(document.querySelector('dialog[open]')||window.wizardClosed!==1)throw Error('Wizard close has not completed');window.created.push({name:createdName});},
            onClose(){window.wizardClosed++;}});
        </script></body>`});
      const path=new URL(url.pathname.slice(1),staticRoot);
      assert(fileURLToPath(path).startsWith(fileURLToPath(staticRoot)));
      return route.fulfill({contentType:'text/javascript',body:await readFile(path)});
    });
    await page.goto('http://wizard.test/studio#app');
    await page.getByRole('button',{name:'See its files'}).click();
    assert.equal(await page.locator('.wizard-file').count(),3);
    assert.match(await page.locator('.wizard-files').innerText(),/Main flight loop/);
    await page.getByRole('button',{name:'Create orbit_demo',exact:true}).click();
    await page.waitForFunction(()=>window.wizardClosed===1);
    assert.deepEqual(await page.evaluate(()=>window.refreshed),[{changed:Object.keys(files),deleted:[]}]);
    assert.deepEqual(await page.evaluate(()=>window.created),[{name}]);
    assert.deepEqual(errors,[]);
  } finally {await browser.close();}
});

test('completed app creation navigates to its source in the real workspace shell',async()=>{
  const browser=await launch(),page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  const entry=root+'/fsw/src/orbit_demo.c';
  const files={
    [root+'/CMakeLists.txt']:'add_cfe_app(orbit_demo ${APP_SRC_FILES})\n',
    [entry]:'#include "orbit_demo.h"\n\nvoid ORBIT_DEMO_AppMain(void)\n{\n    ORBIT_DEMO_Init();\n}\n',
  };
  const shell=(await readFile(new URL('index.html',staticRoot),'utf8')).replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  const controllers=[
    section('function editorPath(', '\nasync function openFile('),
    section('async function openFile(', '\nfunction renderTabs('),
    section('function renderTabs(', '\nasync function revealFile('),
    section('function newMissionApp(', '\nfunction newCodeCommand('),
    section('async function selectView(', '\nfunction openGroundRoute('),
    section('async function reloadMissionFiles(', '\nasync function saveMissionDraft('),
  ].join('\n');
  const listing={...tree,[root+'/fsw/src']:[file(entry),file(dispatch)]};
  page.on('pageerror',error=>{errors.push(error.message);console.error(error.message);});
  try {
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      assert.equal(url.origin,'http://creation.test');
      if(url.pathname==='/studio') {
        const script=`<script type="module">
          import {openAppWizard} from '/app-wizard.js';import {icon,highlight} from '/ui.js';
          import {escapeHtml as esc} from '/dom.js';import {recordRoute} from '/router.js';
          import {syncCommandToFile} from '/source-guide.js';
          const $=selector=>document.querySelector(selector),treeStates=new Map(),lastFiles=new Map();
          const fileRoot=()=> 'flight',guarded=fn=>(...args)=>Promise.resolve(fn(...args));
          const fileType=path=>path.endsWith('.c')?'C':'CM';
          let viewRequest=0,fileOpenRequest=0,treeRequest=0,workspaceRequest=0,workspaceReady=true;
          const activities={},isWorkbench=()=>false,terminal={selectContext(){}};
          const state={target:'native',view:'architecture',files:new Map(),path:null,jobs:[],
            workspace:{apps:[],project:{devices:[]},module_roots:{apps:'cFS'},mission:{source:{hash:'before',path:'mission/targets.cmake'}}}};
          window.wizardClosed=0;
          const settings={priority:50,stack_size:16384,wakeup_hz:1,hk_hz:1};
          async function api(route,body) {
            if(route==='mission/draft')return {files:${JSON.stringify(files)},draft:{kind:'app',name:body.name,settings},expected_hash:'before',plan_hash:'plan',preview:{build:{module:body.name},entry_point:'ORBIT_DEMO_AppMain'}};
            if(route==='mission/save')return {changed:${JSON.stringify(Object.keys(files))},deleted:[]};
            if(route.startsWith('tree?'))return {entries:${JSON.stringify(listing)}[new URLSearchParams(route.slice(5)).get('path')]||[]};
            if(route.startsWith('file?'))return {path:'${entry}',content:${JSON.stringify(files[entry])},editable:true};
            throw Error('Unexpected API '+route);
          }
          async function refresh(){state.workspace.apps=[{name:'orbit_demo',managed:true,path:'${root}',entry:'${entry}'}];await renderTree();}
          async function refreshJourney(){}
          function invalidateSourceActivity(){state.sourceActivity=null;}
          function requireSavedMission(){}
          function feedback(text){$('#feedback').textContent=text;}
          function renderToolbar(){}
          function renderView(){
            document.body.dataset.view=state.view;
            if(state.view==='code' && window.wizardClosed!==1)throw Error('Editor opened before owner close callback');
          }
          function lineNumbers(){$('#line-numbers').textContent=$('#code').value.split('\\n').map((_,i)=>i+1).join('\\n');$('#highlight-code').innerHTML=highlight($('#code').value,state.path);}
          function syncScroll(){}
          ${explorer}
          ${controllers}
          $('#project-title').textContent='Isolated browser test';
          document.documentElement.dataset.theme='dark';
          document.body.classList.remove('workspace-loading');
          for(const node of document.querySelectorAll('[data-icon]'))node.innerHTML=icon(node.dataset.icon);
          newMissionApp('orbit_demo',()=>{window.wizardClosed++;});
        </script>`;
        return route.fulfill({contentType:'text/html',body:shell.replace('</body>',script+'</body>')});
      }
      const path=new URL(url.pathname.slice(1),staticRoot);
      assert(fileURLToPath(path).startsWith(fileURLToPath(staticRoot)));
      const contentType=url.pathname.endsWith('.css')?'text/css':url.pathname.endsWith('.woff2')?'font/woff2':url.pathname.endsWith('.svg')?'image/svg+xml':'text/javascript';
      return route.fulfill({contentType,body:await readFile(path)});
    });
    await page.goto('http://creation.test/studio#app');
    await page.getByRole('button',{name:'See its files'}).click();
    await page.getByRole('button',{name:'Create orbit_demo',exact:true}).click();
    await page.waitForSelector(`[data-file="${entry}"].selected`);
    assert.equal(new URL(page.url()).hash,'#code');
    assert.equal(await page.locator('#code').inputValue(),files[entry]);
    assert.equal(await page.locator('#code').isEditable(),true);
    assert.equal(await page.locator('.explorer').isVisible(),true);
    for(const path of ['cFS/apps/sample_app','cFS/cfe','cFS/osal','cFS/psp','cFS/libs'])
      assert.equal(await page.locator(`details[data-path="${path}"]`).count(),1,path);
    assert.equal(await page.locator('[data-job="build"]').isEnabled(),true);
    assert.equal(await page.locator('.command-lesson').count(),0);
    assert.equal(await page.evaluate(()=>window.wizardClosed),1);
    assert.deepEqual(errors,[]);
    if(process.env.EXPLORER_SCREENSHOT)await page.screenshot({path:process.env.EXPLORER_SCREENSHOT});
  } finally {await browser.close();}
});
