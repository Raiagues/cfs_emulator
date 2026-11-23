// Isolated browser regression: no flight server, subprocesses or hardware are used.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const {chromium} = createRequire(import.meta.url)('playwright');
const staticRoot = new URL('../../static/', import.meta.url);

const enable = {id:'TO_LAB_OUTPUT_ENABLE_CC',app:'to_lab',code:6,mid:0x1880,size:24,header_size:8,
  fields:[{name:'dest_IP',type:'char',format:'s',count:16,size:16,offset:8}]};
const param = {id:'SAMPLE_APP_DISPLAY_PARAM_CC',app:'sample_app',code:3,mid:0x1882,size:24,header_size:8,
  fields:[{name:'ValU32',type:'uint32',format:'I',count:1,size:4,offset:8},
    {name:'ValI16',type:'int16',format:'h',count:1,size:2,offset:12},
    {name:'ValStr',type:'char',format:'s',count:10,size:10,offset:14}]};
const catalog = {build_fingerprint:'fixture',commands:[enable,param],packets:[],apps:[{name:'to_lab'},{name:'sample_app'}],transport:{},first_contact_routes:{}};

test('switching commands restores their own drafts; polling preserves focus; a new session resets them', async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {}),
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  try {
    const page = await browser.newPage();
    const errors = [], previews = [];
    const station = {target:'native',connected:true,build_fingerprint:'fixture',communication:{since:1},packets:[],commands:[],
      first_flight:{enable_command:enable.id,return_host:'127.0.0.1',baseline_apps:['sample_app']}};
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      assert.equal(url.origin, 'http://contact.test');
      const reply = body => route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
      if (url.pathname === '/api/session') return reply({token:'test-only'});
      if (url.pathname === '/api/ground') return reply(station);
      if (url.pathname === '/api/ground/catalog') return reply(catalog);
      if (url.pathname === '/api/ground/preview') {
        previews.push(request.postDataJSON());
        return reply({size:24,segments:[]});
      }
      assert(!url.pathname.startsWith('/api/'), 'Unexpected API: '+url.pathname);
      if (url.pathname === '/updates.js') return route.fulfill({contentType:'text/javascript',
        body:'export const onUpdate=(_,callback)=>{window.refreshContact=callback;return ()=>{}};'});
      if (url.pathname === '/fixture') return route.fulfill({contentType:'text/html',body:`
        <!doctype html><div id="contact"></div><script type="module">
        import {mountFirstContact} from '/first-contact.js';
        mountFirstContact(document.querySelector('#contact'), {
          state:{target:'native',hardware:{native:{running:true}},jobs:[]},guided:false,
          startJob:()=>{throw Error('Unexpected flight action')}
        });</script>`});
      const file = new URL(url.pathname.slice(1), staticRoot);
      assert(fileURLToPath(file).startsWith(fileURLToPath(staticRoot)));
      return route.fulfill({contentType:'text/javascript',body:await readFile(file)});
    });
    await page.goto('http://contact.test/fixture');
    const destination = page.locator('[data-field=dest_IP]');
    await destination.fill('192.0.2.1');
    await page.locator('[data-pick='+param.id+']').click();
    assert.equal(await page.locator('[data-field=ValU32]').inputValue(), '');
    await page.locator('[data-field=ValU32]').fill('123');
    await page.locator('[data-field=ValI16]').fill('-4');
    await page.locator('[data-field=ValStr]').fill('alpha');
    await page.locator('[data-pick='+enable.id+']').click();
    assert.equal(await destination.inputValue(), '192.0.2.1');
    await destination.focus();
    await destination.evaluate(el => el.setSelectionRange(2, 5));
    await page.evaluate(() => window.refreshContact());
    assert.deepEqual(await destination.evaluate(el => ({focused:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd})),
      {focused:true,start:2,end:5});
    await page.locator('[data-bytes]').click();
    await page.locator('dialog[open]').waitFor();
    assert.deepEqual(previews.at(-1).values, {dest_IP:'192.0.2.1'});
    await page.keyboard.press('Escape');
    await page.locator('[data-pick='+param.id+']').click();
    assert.equal(await page.locator('[data-field=ValU32]').inputValue(), '123');
    assert.equal(await page.locator('[data-field=ValI16]').inputValue(), '-4');
    assert.equal(await page.locator('[data-field=ValStr]').inputValue(), 'alpha');
    await page.locator('[data-bytes]').click();
    await page.locator('dialog[open]').waitFor();
    assert.deepEqual(previews.at(-1).values, {ValU32:'123',ValI16:'-4',ValStr:'alpha'});
    await page.keyboard.press('Escape');
    station.communication.since = 2;
    await page.evaluate(() => window.refreshContact());
    assert.equal(await destination.inputValue(), '127.0.0.1');
    await page.locator('[data-pick='+param.id+']').click();
    assert.equal(await page.locator('[data-field=ValU32]').inputValue(), '');
    assert.deepEqual(errors, []);
  } finally {await browser.close();}
});
