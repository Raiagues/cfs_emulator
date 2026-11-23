// Opt-in live check: stops, builds and starts Native, then sends two SET_RATE commands.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
const app=process.argv[2];
assert(app&&/^[a-z][a-z0-9_]*$/.test(app),'Usage: node live-authored-native.mjs <completed-SET_RATE-app>');
const command=app.toUpperCase()+'_SET_RATE_CC';
const base=process.env.FLIGHT_STUDIO_URL||'http://127.0.0.1:8765';
assert(['127.0.0.1','localhost'].includes(new URL(base).hostname),'Use a local Studio URL');
const out=await fs.mkdtemp(join(tmpdir(),'studio-authored-native-'));
console.log('Evidence directory:',out);
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const b=await chromium.launch({...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{}),headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const p=await b.newPage({viewport:{width:1680,height:1050}});p.setDefaultTimeout(60000);
 const errors=[],jobs=[],sends=[];p.on('pageerror',e=>errors.push(e.message));
 p.on('response',async r=>{if(r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/job'){try{jobs.push(await r.json());}catch{}}});
 async function until(fn,timeout=60000){const start=Date.now();while(Date.now()-start<timeout){const v=await fn();if(v)return v;await p.waitForTimeout(250);}throw Error('Timed out waiting for live backend confirmation');}
 const api=path=>p.evaluate(async path=>{const r=await fetch('/api/'+path);if(!r.ok)throw Error(await r.text());return r.json()},path);
 try{
  await p.goto(base+'/studio?target=native#command');
  await p.locator('.command-lesson').waitFor();
  const h=await api('hardware');
  if(h.native.running){assert(await p.locator('.build-action').isDisabled());await p.locator('.stop-action').click();}
  await p.waitForFunction(()=>!document.querySelector('.build-action').disabled);
  console.log('STOP ready; initiating one-worker build');
  const builtResponse=p.waitForResponse(r=>new URL(r.url()).pathname==='/api/job'&&r.request().method()==='POST');
  await p.locator('.build-action').click();
  const buildJob=await (await builtResponse).json();
  await until(async()=>{const js=await api('jobs?lines=0');const j=js.find(x=>x.id===buildJob.id);if(j?.status==='failed')throw Error(j.error);return j?.status==='succeeded';},300000);
  assert.equal(new URL(p.url()).hash,'#command');console.log('BUILD succeeded, page unchanged');
  await p.locator('[data-command-action="deploy"]').click();
  await p.locator('[data-command-ground]').waitFor({timeout:120000});
  assert.equal(new URL(p.url()).hash,'#command');console.log('RUN ready, explicit Ground link visible');
  await p.screenshot({path:out+'/01-command-ready.png'});
  await p.locator('[data-command-ground]').click();
  await p.locator('.contact-layout').waitFor();
  assert.equal(new URL(p.url()).hash,'#send');
  await p.waitForFunction(id=>document.querySelector('.contact-command')?.dataset.command===id,command);
  assert.equal(await p.locator('[data-pick="'+command+'"]').getAttribute('aria-pressed'),'true');
  console.log('SEND uses real Ground; authored app/command selected');
  async function send(){const r=p.waitForResponse(r=>new URL(r.url()).pathname==='/api/ground/send'&&r.request().method()==='POST');await p.locator('.contact-send').click();const resp=await r;assert(resp.ok(),await resp.text());return resp.json();}
  await p.locator('[data-stage="0"]').click();
  await p.waitForFunction(()=>document.querySelector('.contact-command')?.dataset.command==='TO_LAB_OUTPUT_ENABLE_CC'&&!document.querySelector('.contact-send').disabled);
  const enabled=await send();
  await until(async()=>{const g=await api('ground');return g.first_flight?.downlink_receipt?.send_id===enabled.event_id;},40000);
  await p.waitForFunction(()=>!document.querySelector('.contact-playback'));
  for(const rate of [17,23]){
   await p.locator('[data-stage="1"]').click();
   await p.locator('[data-field="Rate_Hz"]').fill(String(rate));
   await p.waitForFunction(()=>!document.querySelector('.contact-send').disabled);
   const sent=await send();
   const receipt=await until(async()=>{const g=await api('ground');const r=g.authored_reply?.receipt;return r?.send_id===sent.event_id&&r.reply&&r.increase&&r;},40000);
   assert.match(receipt.message,new RegExp('Rate set to '+rate+' Hz'));
   assert.equal(receipt.count,receipt.baseline+1);
   assert.equal(new URL(p.url()).hash,'#send');
   await p.screenshot({path:out+'/02-replay-'+rate+'.png'});
   await p.waitForFunction(()=>!document.querySelector('.contact-playback'));
   sends.push({command:sent,receipt});console.log('CONFIRMED',rate,JSON.stringify(receipt));
  }
  assert.notEqual(sends[0].receipt.send_id,sends[1].receipt.send_id);
  const nodes=await p.locator('[data-route-node]').evaluateAll(es=>es.map(e=>e.dataset.app||e.dataset.routeNode));
  assert(nodes.includes(app));assert(!nodes.includes('sample_app'));assert(!nodes.includes('cs'));
  const widths=await p.evaluate(()=>[document.querySelector('.contact-browser').getBoundingClientRect().width,document.querySelector('.contact-telemetry').getBoundingClientRect().width]);assert(Math.abs(widths[0]-widths[1])<1);
  await p.screenshot({path:out+'/03-confirmed.png'});
  await p.reload();await p.waitForFunction(id=>document.querySelector('.contact-command')?.dataset.command===id,command);
  for(const {receipt} of sends){
   const row=p.locator('.contact-history-row').filter({hasText:receipt.message});
   await row.waitFor();
   assert.match(await row.innerText(),new RegExp('CommandCounter '+receipt.baseline+' → '+receipt.count));
  }
  await p.screenshot({path:out+'/04-reloaded.png'});
  assert.deepEqual(errors,[]);
  await fs.writeFile(out+'/result.json',JSON.stringify({checked_at:new Date().toISOString(),target:'native',app,jobs,sends,nodes,sidebar_widths:widths,errors},null,2));
  console.log('Evidence:',out);console.log('PASS: build/run, manual navigation, two real receipts, MID filtering, equal sidebars, reload, no JS errors');
 }catch(e){await p.screenshot({path:out+'/failure.png'}).catch(()=>{});await fs.writeFile(out+'/failure.json',JSON.stringify({error:e.message,errors,jobs,sends,body:await p.locator('body').innerText()},null,2));throw e;}
 finally{await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});
