// The real Ground controller against deterministic HTTP fixtures; no flight process is started.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const staticRoot=new URL('../../static/',import.meta.url);
const enable={id:'TO_LAB_OUTPUT_ENABLE_CC',app:'to_lab',code:6,mid:0x1880,size:24,fields:[{name:'dest_IP',format:'s',type:'char',count:16,size:16}]};
const authored={id:'CUSTOM_APP_SET_WINDOW_CC',app:'custom_app',code:5,mid:0x1911,size:14,fields:[
  {name:'Duration_ms',format:'I',type:'uint32',count:1,size:4},{name:'Mode',format:'H',type:'uint16',count:1,size:2}]};
const catalog={build_fingerprint:'new-build',commands:[enable,authored],packets:[],transport:{command_port:1234,telemetry_port:2234},
 apps:[...Array.from({length:30},(_,i)=>'aaa_'+i),'ci_lab','to_lab','custom_app','unrelated'].map(name=>({name})),first_contact_routes:{
 ingress:{app:'ci_lab'},egress:{app:'to_lab',pipe:'TO_PIPE'},commands:{[authored.id]:[{app:authored.app,mid:authored.mid,pipe:'CUSTOM_PIPE'}]},
 returns:{2056:{app:'custom_app',publishers:[{app:'custom_app'}]}}}};
const station=()=>({target:'native',connected:true,build_fingerprint:'new-build',communication:{since:1},commands:[],packets:[],
 first_flight:{enable_command:enable.id,noop_command:'SAMPLE_APP_NOOP_CC',return_host:'127.0.0.1',downlink_receipt:{send_id:1,mid:2056}},
 authored_reply:{baseline_apps:[authored.app],answer:false,receipt:null}});
async function fixture({current=station(),initialPlan=null}={}){
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
 const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[],sends=[];
 let catalogReads=0;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()),reply=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  assert.equal(url.origin,'http://authored.test');
  if(url.pathname==='/api/session')return reply({token:'fixture'});
  if(url.pathname==='/api/ground')return reply(current);
  if(url.pathname==='/api/ground/catalog'){catalogReads++;return reply(catalog);}
  if(url.pathname==='/api/ground/send'){
   const body=req.postDataJSON();sends.push(body);const id=40+sends.length;
   current.commands.push({...authored,values:body.values,event_id:id,sent_at:100+sends.length});
   return reply({event_id:id});
  }
  assert(!url.pathname.startsWith('/api/'),'Unexpected API '+url.pathname);
  if(url.pathname==='/updates.js')return route.fulfill({contentType:'text/javascript',body:'export const onUpdate=(_,callback)=>{window.refreshContact=callback;return ()=>{}};'});
  if(url.pathname==='/studio')return route.fulfill({contentType:'text/html',body:`<!doctype html><html data-page="studio"><head><link rel="stylesheet" href="/first-contact.css"></head><body data-view="ground"><div class="visual" id="view"></div><script type="module">
   import {mountFirstContact} from '/first-contact.js';
   window.state={target:'native',jobs:[],hardware:{native:{running:true},launch:{native:${JSON.stringify(initialPlan)}}}};
   window.actions=[];
   mountFirstContact(document.querySelector('#view'),{state:window.state,guided:false,
    authoredCommand:${JSON.stringify({app:authored.app,command:authored.id})},
    advanceDeployment:async plan=>window.actions.push(plan.action),startJob:()=>{throw Error('Unexpected fallback job')}});
   </script></body></html>`});
  const file=new URL(url.pathname.slice(1),staticRoot);assert(fileURLToPath(file).startsWith(fileURLToPath(staticRoot)));
  return route.fulfill({contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript',body:await readFile(file)});
 });
 await page.goto('http://authored.test/studio#send');
 await page.locator('[data-field=Duration_ms]').waitFor();
 return {page,browser,current,errors,sends,catalogReads:()=>catalogReads};
}

test('Send uses catalog fields and replays only its confirmed event plus housekeeping',async()=>{
 const f=await fixture();
 try{
  const {page,current,errors,sends}=f,entryUrl=page.url();
  assert.equal(await page.locator('.contact-command').getAttribute('data-command'),authored.id);
  assert(await page.locator('[data-command-group=custom_app]').getAttribute('aria-expanded'));
  assert.equal(await page.locator('[data-route-node][data-app=unrelated]').count(),0);
  assert.equal(await page.locator('.contact-layout aside').count(),2);
  const commandNav=page.locator('.contact-browser>nav');
  assert(await commandNav.evaluate(nav=>{const selected=nav.querySelector('[aria-pressed=true]'),a=nav.getBoundingClientRect(),b=selected.getBoundingClientRect();return b.top>=a.top&&b.bottom<=a.bottom;}),'The authored command must be revealed inside the scrolling command list');
  await commandNav.evaluate(nav=>nav.scrollTop=0);
  await page.evaluate(()=>window.refreshContact());
  assert.equal(await commandNav.evaluate(nav=>nav.scrollTop),0,"Telemetry refresh must preserve the operator's scroll position");
  assert.equal(await page.locator('.contact-stages').getAttribute('aria-label'),'Your command');
  assert.equal(await page.locator('.lesson-track').count(),0);
  await page.locator('[data-field=Duration_ms]').fill('1250');
  await page.locator('[data-field=Mode]').fill('2');
  const uplink=page.waitForResponse(r=>r.url().endsWith('/api/ground/send'));
  await page.locator('.contact-send').click();
  await uplink;
  await page.waitForFunction(()=>document.querySelector('.contact-send')?.textContent.includes('Awaiting'));
  assert.deepEqual(sends,[{target:'native',command_id:authored.id,values:{Duration_ms:'1250',Mode:'2'}}]);
  assert.equal(await page.locator('.contact-playback').count(),0,'UDP send alone is not proof');
  current.authored_reply.receipt={command:authored.id,app:authored.app,send_id:41,reply:42,event_mid:2056,message:'Window configured',baseline:0};
  await page.evaluate(()=>window.refreshContact());
  assert.equal(await page.locator('.contact-playback').count(),0,'INFO alone must wait for matching HK');
  Object.assign(current.authored_reply.receipt,{increase:43,count:1});current.authored_reply.answer=true;
  await page.evaluate(()=>window.refreshContact());
  await page.locator('.contact-playback').waitFor();
  assert.equal(await page.locator('[data-down][data-producer=custom_app]').count(),1);
  assert.equal(await page.locator('[data-route-node][data-app=unrelated]').count(),0);
  await page.locator('[data-play]').click();
  for(let n=0;n<8;n++)if(await page.locator('[data-step]').count())await page.locator('[data-step]').click();
  await page.locator('.contact-confirmed').waitFor();
  assert.equal(page.url(),entryUrl,'Receiving and replaying must not navigate');
  assert.equal(await page.locator('.contact-next').count(),0,'Send must not link back to app creation');
  assert.match(await page.locator('.contact-history').innerText(),/CommandCounter 0 → 1/);
  assert.deepEqual(errors,[]);
 }finally{await f.browser.close();}
});

test('Ground disables stale commands while building and refreshes the catalog on completion',async()=>{
 const f=await fixture({initialPlan:{action:'build',label:'Build cFS'}});
 try{
  const {page,sends,errors}=f;
  assert(await page.locator('.contact-send').isDisabled());
  await page.locator('[data-contact-deploy]').click();
  assert.deepEqual(await page.evaluate(()=>window.actions),['build']);
  await page.evaluate(()=>{window.state.jobs=[{id:'build-1',target:'native',action:'build',status:'running'}];return window.refreshContact();});
  assert(await page.locator('[data-contact-deploy]').isDisabled());
  const count=f.catalogReads();
  await page.evaluate(()=>{window.state.jobs[0].status='succeeded';window.state.jobs[0].operation_complete=true;window.state.hardware.launch.native=null;return window.refreshContact();});
  assert(f.catalogReads()>count,'The successful build must reload its compiled catalog');
  assert.equal(await page.locator('[data-contact-deploy]').count(),0);
  assert(await page.locator('.contact-send').isEnabled());
  assert.equal(sends.length,0);
  assert.deepEqual(errors,[]);
 }finally{await f.browser.close();}
});

test('an authored command waits for ENABLE_OUTPUT and its own housekeeping after a new run',async()=>{
 const current=station();current.first_flight.downlink_receipt=null;current.authored_reply.baseline_apps=[];
 const f=await fixture({current});
 try{
  const {page,sends,errors}=f;
  assert(await page.locator('.contact-send').isDisabled());
  assert.match(await page.locator('.contact-notice').innerText(),/custom_app housekeeping/);
  await page.locator('[data-stage="0"]').click();
  assert.equal(await page.locator('[data-field=dest_IP]').inputValue(),'127.0.0.1');
  const uplink=page.waitForResponse(r=>r.url().endsWith('/api/ground/send'));
  await page.locator('.contact-send').click();await uplink;
  await page.waitForFunction(()=>document.querySelector('.contact-send')?.textContent.includes('Awaiting'));
  assert.equal(sends[0].command_id,enable.id);
  current.first_flight.downlink_receipt={send_id:41,mid:2056};
  await page.evaluate(()=>window.refreshContact());
  assert.equal(await page.locator('.contact-command').getAttribute('data-command'),authored.id);
  assert(await page.locator('.contact-send').isDisabled(),'Other telemetry does not provide the authored app baseline');
  current.authored_reply.baseline_apps=[authored.app];
  await page.evaluate(()=>window.refreshContact());
  assert(await page.locator('.contact-send').isEnabled());
  assert.deepEqual(errors,[]);
 }finally{await f.browser.close();}
});


test('reloading Ground preserves each confirmed send without borrowing a newer receipt',async()=>{
 const current=station();
 const proof=(id,before,after)=>({command:authored.id,app:authored.app,send_id:id,reply:id+1,increase:id+2,event_mid:2056,baseline:before,count:after,message:'Window '+after});
 current.commands=[
  {...authored,event_id:10,sent_at:100,values:{Duration_ms:17},receipt:proof(10,0,1)},
  {...authored,event_id:20,sent_at:101,values:{Duration_ms:23},receipt:proof(20,1,2)},
  {...authored,event_id:30,sent_at:102,values:{Duration_ms:51},receipt:proof(20,1,2)}
 ];
 current.authored_reply={baseline_apps:[authored.app],answer:true,receipt:current.commands[1].receipt};
 const f=await fixture({current});
 try{
  const {page,errors}=f;
  await page.waitForFunction(()=>document.querySelector('.contact-history')?.textContent.includes('CommandCounter 0 → 1'));
  const rows=page.locator('.contact-history-row');
  assert.equal(await rows.count(),3);
  assert.match(await rows.nth(2).innerText(),/Duration_ms = 17[\s\S]*CommandCounter 0 → 1/);
  assert.match(await rows.nth(1).innerText(),/Duration_ms = 23[\s\S]*CommandCounter 1 → 2/);
  assert.match(await rows.nth(0).innerText(),/awaiting a confirmed reply/);
  assert.doesNotMatch(await rows.nth(0).innerText(),/CommandCounter/);
  assert.deepEqual(errors,[]);
 }finally{await f.browser.close();}
});
