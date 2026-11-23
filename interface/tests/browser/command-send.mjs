// Exercise the real lesson controller with target snapshots, without writing flight sources.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const staticRoot=new URL('../../static/',import.meta.url);
const lesson={stage:6,view:6,app:'weather',symbol:'WEATHER_SET_RATE_CC',
 path:'cFS/apps/weather/fsw/src/commands/weather_set_rate_cmd.c',
 content:'CFE_Status_t WEATHER_SetRateCmd(void) { return CFE_SUCCESS; }\n',ranges:[],
 steps:['Code','Struct','Prototype','Dispatch','Events','Handler','Test'],completed:[true,true,true,true,true,true,false]};

test('the final command step stops, builds, runs, then waits for an explicit Ground Station click',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
 const page=await browser.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());assert.equal(u.origin,'http://send.test');
   const reply=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
   if(u.pathname==='/api/session')return reply({token:'fixture'});
   if(u.pathname==='/api/command/lesson')return reply(lesson);
   if(u.pathname==='/api/workspace')return reply({apps:[],builds:{native:{current:true,fingerprint:'built'}}});
   if(u.pathname==='/api/ground')return reply({target:'native',commands:[],runs:[]});
   if(u.pathname==='/updates.js')return route.fulfill({contentType:'text/javascript',body:'export const onUpdate=()=>()=>{};'});
   if(u.pathname==='/studio')return route.fulfill({contentType:'text/html',body:`<!doctype html><body><main id="lesson"></main><script type="module">
    import {mountCommandLesson} from '/command-lesson.js';
    window.calls=[];window.opened=[];
    const state={target:'native',jobs:[],files:new Map(),hardware:{launch:{native:{action:'stop',label:'Stop cFS'}}}};
    window.controller=mountCommandLesson(document.querySelector('#lesson'),{state,
     async advanceDeployment(plan){
      window.calls.push(plan.action);
      if(plan.action==='stop')state.hardware.launch.native={action:'build',label:'Build cFS'};
      if(plan.action==='build')state.jobs=[{target:'native',action:'build',status:'running'}];
      if(plan.action==='run'){state.jobs=[{target:'native',action:'run',status:'running',operation_complete:false}];}
     },openGround(app,command){window.opened.push({app,command});}});
    window.finishBuild=()=>{state.jobs=[];state.hardware.launch.native={action:'run',label:'Run cFS'};window.controller.update();};
    window.finishRun=()=>{state.jobs[0].operation_complete=true;state.hardware.launch.native=null;window.controller.update();};
   </script></body>`});
   const path=new URL(u.pathname.slice(1),staticRoot);assert(fileURLToPath(path).startsWith(fileURLToPath(staticRoot)));
   return route.fulfill({contentType:'text/javascript',body:await readFile(path)});
  });
  await page.goto('http://send.test/studio?target=native#command');
  await page.getByRole('button',{name:'Stop cFS',exact:true}).click();
  await page.getByRole('button',{name:'Build cFS',exact:true}).click();
  await page.waitForSelector('[data-command-action="deploy"]:disabled');
  assert.match(await page.locator('[data-command-action]').textContent(),/Building cFS/);
  assert.deepEqual(await page.evaluate(()=>window.opened),[]);
  await page.evaluate(()=>window.finishBuild());
  await page.getByRole('button',{name:'Run cFS',exact:true}).click();
  assert.deepEqual(await page.evaluate(()=>window.opened),[]);
  await page.evaluate(()=>window.finishRun());
  const link=page.getByRole('link',{name:'Open Ground Station'});
  await link.waitFor();assert.match(await link.getAttribute('href'),/#send$/);
  assert.equal(new URL(page.url()).hash,'#command');
  assert.deepEqual(await page.evaluate(()=>window.calls),['stop','build','run']);
  assert.deepEqual(await page.evaluate(()=>window.opened),[]);
  await link.click();
  assert.deepEqual(await page.evaluate(()=>window.opened),[{app:'weather',command:'WEATHER_SET_RATE_CC'}]);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
