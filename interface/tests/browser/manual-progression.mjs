// Exercise real page controllers with deterministic backend receipts, without a flight target.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const staticRoot = new URL('../../static/', import.meta.url);
const steps = ['target','boot','event','app','command','send','sensor','test','board'];
function journey(target, current) {
  const index = steps.indexOf(current);
  return {target, current, next_route:`/studio?target=${target}#${current}`,
    steps:Object.fromEntries(steps.map((id, i) => [id, {done:i<index, reachable:i<=index,
      route:`/studio?target=${target}#${id}`}]))};
}
async function browser() {
  return chromium.launch({headless:true,
    ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {}),
    ...(process.env.PLAYWRIGHT_CHANNEL ? {channel:process.env.PLAYWRIGHT_CHANNEL} : {}),
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
}
async function fixture(browser, {target='native', view, response, sent=()=>{throw Error('Unexpected command');}}) {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    assert.equal(url.origin, 'http://progression.test');
    const reply = body => route.fulfill({contentType:'application/json', body:JSON.stringify(body)});
    if (url.pathname === '/api/session') return reply({token:'fixture'});
    if (url.pathname === '/api/ground/send') return reply(sent(route.request().postDataJSON()));
    if (url.pathname.startsWith('/api/')) return reply(response(url.pathname));
    if (url.pathname === '/updates.js') return route.fulfill({contentType:'text/javascript', body:`
      const listeners = new Set();
      export const onUpdate = (topics, callback) => {
        const listener = {topics, callback}; listeners.add(listener);
        return () => listeners.delete(listener);
      };
      window.publishUpdates = changed => Promise.all([...listeners]
        .filter(listener => listener.topics.some(topic => changed.includes(topic)))
        .map(listener => listener.callback()));`});
    if (url.pathname === '/studio') return route.fulfill({contentType:'text/html',body:`
      <!doctype html><body data-flight-target="${target}"><nav id="flight-guide"></nav><div id="view"></div>
      <script type="module">
        import '/journey.js';
        import {api} from '/api.js';
        import {mountFirstBoot} from '/first-boot.js';
        import {mountFirstContact} from '/first-contact.js';
        sessionStorage.setItem('flight.boot.${target}', 'boot-job');
        const root = document.querySelector('#view');
        if (${JSON.stringify(view)} === 'boot') mountFirstBoot(root,{api,target:'${target}'});
        else mountFirstContact(root,{state:{target:'${target}',jobs:[],hardware:{native:{running:true}}},
          startJob:()=>{throw Error('Unexpected flight action')}});
      </script></body>`});
    const file = new URL(url.pathname.slice(1), staticRoot);
    assert(fileURLToPath(file).startsWith(fileURLToPath(staticRoot)));
    return route.fulfill({contentType:'text/javascript',body:await readFile(file)});
  });
  await page.goto(`http://progression.test/studio?target=${target}#${view}`);
  return {page, errors};
}

test('completed boot stays open on every target until Next is clicked', async () => {
  const instance = await browser();
  try {
    for (const target of ['native','qemu','physical']) {
      let completed = false;
      const boot = () => ({target, hardware:'Test target', os:'Linux', architecture:'fixture',
        apps:[], services:[], es_states:['OPERATIONAL'], lines:[], trace:[], verified:true,
        starting:!completed, running:completed, stopped:false, unverified:false,
        job:{id:'boot-job',action:'first-boot',phase:'run',status:completed?'succeeded':'running'},
        flight:{states:completed?['OPERATIONAL']:[],initialized:{},process_started:true}});
      const {page, errors} = await fixture(instance, {target, view:'boot', response:path => {
        if (path === '/api/first-boot') return boot();
        if (path === '/api/journey') return journey(target, completed?'event':'boot');
        throw Error('Unexpected API: '+path);
      }});
      await page.locator('.boot-console').waitFor();
      assert(await page.locator('.flight-next').isHidden());
      const before = page.url();
      completed = true;
      await page.evaluate(() => window.publishUpdates(['jobs','journey']));
      await page.locator('.boot-success').waitFor();
      await page.locator('.flight-next:not([hidden])').waitFor();
      await page.waitForTimeout(1200);
      assert.equal(page.url(), before, 'Completion must leave the boot page visible');
      assert.equal(await page.locator('.flight-next').textContent(), 'Next · Event');
      await page.locator('.flight-next').click();
      assert.equal(new URL(page.url()).hash, '#event');
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {await instance.close();}
});

const enable = {id:'TO_LAB_OUTPUT_ENABLE_CC',app:'to_lab',code:6,mid:0x1880,size:24,
  fields:[{name:'dest_IP',type:'char',format:'s',count:16,size:16,offset:8}]};
const noop = {id:'SAMPLE_APP_NOOP_CC',app:'sample_app',code:0,mid:0x1882,size:8,fields:[]};
const catalog = {build_fingerprint:'fixture',commands:[enable,noop],packets:[],transport:{},
  apps:['ci_lab','to_lab','sample_app'].map(name=>({name})),first_contact_routes:{
    ingress:{app:'ci_lab'},egress:{app:'to_lab',pipe:'TO_PIPE'},
    commands:{[noop.id]:[{app:'sample_app',mid:noop.mid,pipe:'SAMPLE_PIPE'}]},
    returns:{0x0808:{app:'sample_app',publishers:[{app:'sample_app'}]}}}};

test('a confirmed NOOP and its complete animation stay on Event until an explicit click', async () => {
  const instance = await browser();
  try {
    let complete = false;
    const station = () => ({target:'native',connected:true,build_fingerprint:'fixture',
      communication:{since:1},packets:[],commands:[],first_flight:{enable_command:enable.id,noop_command:noop.id,
        return_host:'127.0.0.1',baseline_apps:['sample_app'],downlink_receipt:{send_id:'enable',mid:0x0808},
        answer:complete,receipt:complete?{command:noop.id,send_id:'noop',event_mid:0x0808,reply:true,increase:true,baseline:0,count:1}:null}});
    const {page, errors} = await fixture(instance, {view:'event', response:path => {
      if (path === '/api/ground') return station();
      if (path === '/api/ground/catalog') return catalog;
      if (path === '/api/journey') return journey('native',complete?'app':'event');
      throw Error('Unexpected API: '+path);
    }, sent:body => {
      assert.equal(body.command_id, noop.id);
      complete = true;
      return {event_id:'noop'};
    }});
    await page.locator(`[data-pick=${noop.id}]`).click();
    const before = page.url();
    assert(await page.locator('.flight-next').isHidden());
    const uplink = page.waitForResponse(response => response.url().endsWith('/api/ground/send'));
    await page.locator('.contact-send').click();
    await uplink;
    await page.evaluate(() => window.publishUpdates(['ground','journey']));
    await page.locator('.contact-next').waitFor();
    await page.waitForTimeout(4500);
    assert.equal(page.url(), before, 'Animation completion must not open Architecture');
    assert.equal(await page.locator('.flight-next').textContent(), 'Next · App');
    assert.equal(await page.locator('.contact-stages [data-fact=done]').count(), 3);
    await page.locator('.contact-next').click();
    assert.equal(new URL(page.url()).hash, '#app');
    assert.deepEqual(errors, []);
  } finally {await instance.close();}
});
