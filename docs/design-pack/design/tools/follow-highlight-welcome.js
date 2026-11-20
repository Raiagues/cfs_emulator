const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 760 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const chs = (process.argv[2] || '0,1,2,3,7,4,11,5,12,8,9,10').split(',').map(Number);
  for (const ch of chs) {
    await page.goto('about:blank'); await page.goto('file://' + require('path').resolve(__dirname, '../preview/Welcome.html') + '?c=' + ch + '#' + encodeURIComponent(JSON.stringify({ state: { ch } })));
    await page.waitForTimeout(300);
    const log = []; let idle = 0, clicks = 0, done = false;
    for (let it = 0; it < 900; it++) {
      const res = await page.evaluate(() => {
        const sec = document.querySelector('section'); if (!sec) return { err: 'no section' };
        const next = [...document.querySelectorAll('[data-act]')].find(b => /(^next|^start)$/.test(b.getAttribute('data-act')) && /ready/.test(b.className));
        const vis = (el) => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; let e = el; while (e) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.15) return false; e = e.parentElement; } return true; };
        const co = [...sec.querySelectorAll('.fs-coach')].filter(vis);
        const acts = co.map(el => el.closest('[data-act]') || el.querySelector('[data-act]')).filter(Boolean);
        return { ready: !!next, n: co.length, acts: acts.map(a => a.getAttribute('data-act')), task: (document.body.innerText.match(/\b\d+\/\d+\b/) || [''])[0] };
      });
      if (res.err) { log.push(res.err); break; }
      if (res.ready) { log.push(`READY after ${clicks} clicks`); done = true; break; }
      if (res.acts.length === 0) { idle++; await page.waitForTimeout(100); if (idle === 300) { log.push(`STUCK 30s with no highlighted action (coach elements without action: ${res.n})`); break; } continue; }
      idle = 0;
      if (res.acts.length > 1) log.push('  several highlighted: ' + [...new Set(res.acts)].join(' | '));
      let act = res.acts[0];
      if (res.acts.includes('fw2.pickAll') && res.acts.includes('fw2.pickOne')) { const q0 = await page.evaluate(() => window.__c.state.fwQ); await page.evaluate(() => document.querySelector('[data-act="fw2.pickAll"]').click()); await page.waitForTimeout(150); const q1 = await page.evaluate(() => window.__c.state.fwQ); act = q1 > q0 ? null : 'fw2.pickOne'; if (!act) { clicks++; log.push('click fw2.pickAll'); await page.waitForTimeout(250); continue; } }
      await page.evaluate((act) => { const sec = document.querySelector('section'); const el = [...sec.querySelectorAll('[data-act]')].find(e => e.getAttribute('data-act') === act && (e.classList.contains('fs-coach') || e.closest('.fs-coach') || e.querySelector('.fs-coach'))) || sec.querySelector(`[data-act="${act}"]`); el && el.click(); }, act);
      clicks++; log.push(`click ${act}`);
      await page.waitForTimeout(350);
      if (clicks > 40) { log.push('TOO MANY CLICKS'); break; }
    }
    const title = await page.evaluate(() => (document.querySelector('h1') || {}).innerText || '');
    console.log(`=== ch${ch} ${title}\n  ` + log.join('\n  '));
  }
  if (errors.length) console.log('PAGE ERRORS:', [...new Set(errors)].slice(0, 5).join('\n'));
  await browser.close();
})();
