import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const url = new URL(process.env.FLIGHT_TEST_URL);
const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || undefined});
try {
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const errors = [], installers = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/terminal/create') installers.push(request.postDataJSON().setup_action);
  });
  // An explicit launch link is needed if the test driver has a different local UID.
  await page.request.get(url.href);
  const start = performance.now();
  await page.goto(url.origin);
  await page.waitForURL('**/welcome');
  await page.getByRole('button', {name:'Skip', exact:true}).click();
  assert.equal(await page.locator('[data-target][aria-pressed=true]').count(), 0);
  await page.locator('#targets [data-target=native].fs-coach').click();
  for (;;) {
    const control = await page.waitForFunction(() => {
      const failure = document.querySelector('.install-failed');
      if (failure) throw Error(failure.textContent);
      return document.querySelector('#setup-terminal[open] .close-dialog.fs-coach, #requirements .fs-coach, #enter.fs-coach');
    }, null, {timeout:600000});
    const button = control.asElement();
    const next = await button.getAttribute('id') === 'enter';
    await button.click();
    if (next) break;
  }
  await page.locator('[data-start-boot].fs-coach').click();
  await page.waitForFunction(() => {
    const fail = document.querySelector('.boot-stage[data-state=failed]');
    if (fail) throw Error(fail.textContent);
    return document.querySelector('.boot-success') && document.querySelector('.flight-next.fs-coach');
  }, null, {timeout:600000});
  const observation = await (await page.request.get(url.origin+'/api/first-boot?target=native')).json();
  assert(observation.flight.initialized.SCH_LAB);
  assert(installers.includes('clone-cfs') && installers.includes('native-tools'), JSON.stringify(installers));
  assert.deepEqual(errors, []);
  console.log('Clean login · '+installers.join(' + ')+' · OPERATIONAL · '+Math.round((performance.now()-start)/1000)+' s');
} finally {
  await browser.close();
}
