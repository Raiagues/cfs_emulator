const { chromium } = require('playwright');
const PLAN0 = { Main: [[], 'target'], Boot: [['target'], 'boot'], Lesson: [['target', 'boot'], 'event'], Mission: [['target', 'boot', 'event'], 'app'], AddCommand: [['target', 'boot', 'event', 'app'], 'command'], Lesson2: [['target', 'boot', 'event', 'app', 'command'], 'send'], Ground: [['target', 'boot', 'event', 'app', 'command', 'send'], 'sensor'], Ground2: [['target', 'boot', 'event', 'app', 'command', 'send', 'sensor'], 'test'] };
const ONLY = process.argv[2] ? process.argv[2].split(',') : null; const PLAN = ONLY ? Object.fromEntries(Object.entries(PLAN0).filter(([k]) => ONLY.includes(k))) : PLAN0;
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  for (const [name, [pre, goal]] of Object.entries(PLAN)) {
    const file = name.replace(/2$/, '');
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    await ctx.addInitScript((pre) => { if (!sessionStorage.getItem('init')) { localStorage.setItem('fs-journey', JSON.stringify(pre)); localStorage.setItem('fs-target', 'emu'); sessionStorage.setItem('init', '1'); } }, pre);
    const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto('file://' + require('path').resolve(__dirname, '../preview/' + file + '.html'));
    await page.waitForTimeout(400);
    const log = []; let idle = 0, clicks = 0;
    for (let it = 0; it < 1500; it++) {
      if (!page.url().includes('/preview/')) { log.push('NAVIGATED to ' + page.url().split('/').pop()); break; }
      let res; try { res = await page.evaluate(() => {
        const vis = (el) => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; let e = el; while (e) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.15) return false; e = e.parentElement; } return true; };
        const guide = document.querySelector('[aria-label="First steps guide"]');
        const co = [...document.querySelectorAll('.fs-coach, .fs-ping, .fs-ring')].filter(el => vis(el) && !(guide && guide.contains(el)));
        const acts = co.map(el => el.closest('[data-act]') || el.querySelector('[data-act]')).filter(Boolean);
        return { j: JSON.parse(localStorage.getItem('fs-journey') || '[]'), acts: acts.map(a => a.getAttribute('data-act')), n: co.length, guideNext: guide ? (guide.innerText.match(/Next\s*\n?\s*(\w+)/) || [])[1] : null, count: guide ? (guide.innerText.match(/(\d+)\/(\d+)/) || [''])[0] : '' };
      }); } catch (e) { log.push('NAVIGATED to ' + page.url().split('/').pop()); break; }
      if (it === 0) log.push(`start: guide ${res.count} next=${res.guideNext || '-'}`);
      if (res.j.includes(goal)) { log.push(`GOAL '${goal}' reached after ${clicks} clicks; guide now ${res.count} next=${res.guideNext || '-'}`); break; }
      if (!res.acts.length) { idle++; await page.waitForTimeout(100); if (idle === 300) { log.push(`STUCK 30s: no highlighted action (highlighted w/o action: ${res.n}); journey=${res.j.join(',')}`); break; } continue; }
      idle = 0; const act = res.acts[0]; if (res.acts.length > 1) log.push('  several: ' + [...new Set(res.acts)].join(' | '));
      try { await page.evaluate((act) => { const el = [...document.querySelectorAll('[data-act]')].find(e => e.getAttribute('data-act') === act && (e.classList.contains('fs-coach') || e.closest('.fs-coach') || e.querySelector('.fs-coach,.fs-ping,.fs-ring') || e.classList.contains('fs-ping') || e.classList.contains('fs-ring'))) || document.querySelector(`[data-act="${act}"]`); el && el.click(); }, act); } catch (e) {}
      clicks++; log.push('click ' + act); await page.waitForTimeout(400); if (clicks > 40) { log.push('TOO MANY CLICKS'); break; }
    }
    console.log(`=== ${name} (goal ${goal})\n  ` + log.join('\n  ') + (errors.length ? '\n  ERRORS: ' + [...new Set(errors)].slice(0, 3).join(' / ') : ''));
    await ctx.close();
  }
  await browser.close();
})();
