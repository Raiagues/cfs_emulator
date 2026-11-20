import fs from 'node:fs';
import assert from 'node:assert/strict';
import path from 'node:path';
import {parse} from 'acorn';
import * as walk from 'acorn-walk';
import {chromium} from 'playwright';

const directory = 'interface/static';
const files = new Map();
const functions = new Map();
const handlers = [];
const markup = [];

function source(file, node) {
  return files.get(file).text.slice(node.start, node.end);
}

function keys(expression) {
  const result = new Set(expression.match(/#[a-z][\w-]*|data-[a-z][\w-]*/gi) || []);
  for (const match of expression.matchAll(/(?:\bd\.|dataset\??\.)(\w+)|['"](\w+)['"] in d\b/g)) {
    result.add('data-' + (match[1] || match[2]).replace(/[A-Z]/g, c => '-' + c.toLowerCase()));
  }
  for (const match of expression.matchAll(/\.id\s*===?\s*['"]([\w-]+)|\.key\s*===?\s*['"]([^'"]+)/g)) {
    result.add(match[1] ? '#' + match[1] : 'key ' + match[2]);
  }
  return [...result];
}

function nameOf(node) {
  return node?.name || node?.property?.name || '';
}

function outcomes(file, node, seen = new Set()) {
  const api = new Set(), state = new Set();
  function scan(file, node) {
    if (!node || seen.has(node)) return;
    seen.add(node);
    walk.simple(node, {
      AssignmentExpression(n) {
        const left = source(file, n.left);
        if (/^(state\.|location\.|.*\.location\.)/.test(left)) state.add(left);
      },
      CallExpression(n) {
        const name = nameOf(n.callee);
        const arg = n.arguments[0];
        if (['api', 'request', 'fetch'].includes(name) && arg) {
          const literal = arg.type === 'BinaryExpression' ? arg.left : arg;
          const endpoint = literal.value;
          if (typeof endpoint === 'string' && endpoint !== '/api/') {
            const method = n.arguments.length > 1 && name !== 'fetch' ? 'POST' : 'GET';
            api.add(method + ' /api/' + endpoint.replace(/^\/api\//, '').split('?')[0]);
          }
        } else if (['selectView', 'recordRoute', 'openFlightStep', 'navigate', 'stepUrl'].includes(name) && arg) {
          state.add(name + '(' + source(file, arg) + ')');
        } else if (['showModal', 'close', 'pushState', 'replaceState'].includes(name)) {
          state.add(name);
        } else if (n.callee.type === 'Identifier' && !/^(render|draw|poll|refreshJourney|feedback|icon|esc)/.test(name)) {
          const defs = functions.get(name) || [];
          const def = defs.find(d => d.file === file) || (defs.length === 1 && defs[0]);
          if (def) scan(def.file, def.node.body);
        }
      }
    });
  }
  scan(file, node);
  return {api: [...api].sort(), state: [...state].sort()};
}

function binding(file, entry, body, controls) {
  if (!controls.length || !body) return;
  const where = file + ':' + entry.loc.start.line;
  handlers.push({where, keys: controls, ...outcomes(file, body)});
}

function staticMap() {
  for (const file of fs.readdirSync(directory).filter(f => f.endsWith('.js')).sort()) {
    const text = fs.readFileSync(path.join(directory, file), 'utf8');
    const ast = parse(text, {ecmaVersion:'latest', sourceType:'module', locations:true});
    files.set(file, {text, ast});
    walk.simple(ast, {
      FunctionDeclaration(n) {functions.set(n.id.name, [...(functions.get(n.id.name) || []), {file, node:n}]);},
      Literal(n) {if (typeof n.value === 'string' && /<(button|a |input|select|summary|textarea|[^>]+role=)/.test(n.value))
        markup.push([file, n.loc.start.line, n.value]);},
      TemplateLiteral(n) {
        const fragment = n.quasis.map(q => q.value.cooked).join('{…}');
        if (fragment.includes('<')) markup.push([file, n.loc.start.line, fragment]);
      }
    });
  }
  for (const [file, {ast}] of files) {
    walk.simple(ast, {
      IfStatement(n) {binding(file, n, n.consequent, keys(source(file, n.test)));},
      CallExpression(n) {
        if (nameOf(n.callee) !== 'addEventListener') return;
        const receiver = source(file, n.callee.object);
        const controls = keys(receiver);
        const cb = n.arguments[1];
        const fn = cb?.type === 'Identifier' ? functions.get(cb.name)?.find(d => d.file === file)?.node : cb;
        binding(file, n, fn || cb, controls.length ? controls : [receiver + ' ' + (n.arguments[0]?.value || 'event')]);
      },
      AssignmentExpression(n) {
        if (/^on(click|change|input|submit|key)/.test(nameOf(n.left))) {
          const expr = source(file, n.left);
          const controls = keys(expr);
          binding(file, n, n.right, controls.length ? controls : [expr]);
        }
      }
    });
  }
  return {markup, handlers, differences:compare()};
}

function compare() {
  const checks = [
    ['app.js', 'railSteps', 'Rail views override the server’s current step.'],
    ['journey.js', 'railSteps', 'Free Architecture, Hardware, Code, Ground and Synthetic data visits change the current stop.'],
    ['journey.js', 'fs-journey-reset', 'Reset hides evidence in one browser and stays on the open route.'],
    ['journey.js', 'canAdvance ? stages[index + 1]', 'Next uses local ordering and a live-boot condition.'],
    ['journey.js', "link.setAttribute('href', stepUrl", 'Every stop receives a link before its prerequisites are observed.'],
    ['journey.js', "return '/?target=physical';", 'Board lacks the #board route and the originating journey context.'],
    ['infrastructure.js', 'if (explicitSelection) await verify()', 'Opening a target URL saves settings and verifies it.'],
    ['infrastructure.js', "api('infrastructure',values)", 'Target and profile selection share the settings mutation in Setup.'],
    ['infrastructure.js', "request('infrastructure/check',{target:mode,label:", 'Setup sends individual probes instead of one NDJSON batch.'],
    ['first-boot.js', 'if(next.verified&&!requested', 'Entering or refreshing Boot launches the build and run job.'],
    ['app.js', "if(await openFlightStep('app'))newMissionApp()", 'Entering Command can open an app or command dialog on Back.'],
    ['app.js', "location.href='/infrastructure", 'Setup actions and Add sensor use the duplicate setup URL.'],
    ['app.js', "openFlightStep('boot')", 'View active flight switches targets and opens Boot.'],
    ['app.js', "board-select\').click()", 'Select board dispatches a click on the toolbar selector.'],
    ['orbit-preview.js', "context.api('simulation/orbit',batch)", 'Viewing Sensor or Test posts the default orbit calculation.'],
    ['command-launch.js', 'Stop previous build', 'The label describes a build while the job stops the cFS process.'],
    ['command-launch.js', "'Start cFS'", 'The launch card and toolbar use different names for Run cFS.'],
    ['infrastructure.html', 'Continue to boot', 'Setup exposes the old Continue label.'],
    ['index.html', 'href="/infrastructure"', 'The brand goes directly to the legacy Setup URL and has no Welcome menu.'],
    ['panels.js', 'System overview', 'The guided ground screen exposes free-view traffic controls.'],
    ['round-trip-view.js', 'System overview', 'System overview shares the guided route with Round trip.'],
    ['interface/server.py', 'journal=app.follow_boot_journal', 'Reading first-boot status can start a log job.'],
    ['interface/server.py', "if action == 'simulate' and target != 'qemu'", 'Sensor start cannot operate on Native or Board.'],
    ['interface/backend/journey.py', 'registration.stat().st_mtime', 'Shipped apps and file mtimes can earn App or Command credit.'],
    ['interface/backend/journey.py', '"done": bool(when)', 'Each stop is credited independently of earlier steps.'],
    ['interface/backend/journey.py', 'ground.get("connected")', 'Disconnecting the ground station loses Event progress.'],
    ['ground_station/station.py', 'def _subscribe_catalog', 'Connect or Send can issue TO subscriptions on the operator’s behalf.']
  ];
  const results = [];
  for (const [file, text, difference] of checks) {
    const contents = files.get(file)?.text || fs.readFileSync(file.includes('/') ? file : path.join(directory, file), 'utf8');
    const at = contents.indexOf(text);
    if (at >= 0) results.push(difference + ' `' + file + ':' + contents.slice(0, at).split('\n').length + '`');
  }
  if (!fs.existsSync(path.join(directory,'welcome.html'))) results.unshift('Welcome, its chapter controls, Skip and Start are absent.');
  return results;
}

async function crawl(url, verifyRoutes) {
  const base = new URL(url);
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) throw Error('Use a local test instance');
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHANNEL ? {channel: process.env.PLAYWRIGHT_CHANNEL} : {});
  const rows = [];
  const faults = [];
  try {
    const context = await browser.newContext({viewport:{width:1440,height:900}});
    const page = await context.newPage();
    // Inventory visits never install software or deploy the lab being inspected.
    let visiting = '';
    page.on('pageerror', e => faults.push(visiting + ' ' + e.message));
    page.on('response', async response => {
      if (response.status() >= 400 && response.request().method() === 'GET') {
        faults.push(visiting + ' ' + response.status() + ' ' + new URL(response.url()).pathname);
      }
    });
    await context.route('**/api/**', route => {
      const request = route.request();
      if (request.method() === 'GET') return route.continue();
      rows.push([visiting, 'Route entry', request.method() + ' ' + new URL(request.url()).pathname]);
      return route.fulfill({status:409, contentType:'application/json',body:'{"error":"Inventory captured this action"}'});
    });
    const saved = async () => {
      const read = async endpoint => (await context.request.get(new URL('/api/' + endpoint, base).href)).json();
      const [setup, jobs] = await Promise.all([read('infrastructure'), read('jobs')]);
      return [setup.target_saved, setup.target, setup.board, setup.os, setup.check_results, jobs.map(job => job.id)];
    };
    const before = verifyRoutes && await saved();
    async function ready() {
      await page.waitForFunction(() => document.querySelector('#targets button:not(:disabled),body:not(.workspace-loading) #studio') ||
        document.querySelector('#feedback')?.innerText || document.querySelector('#workspace-opening button:not([hidden])'));
      assert.equal(await page.locator('dialog[open]').count(), 0, visiting);
    }
    for (const route of ['/#target','/?target=physical#board', ...['boot','event','app','command','send','sensor','test',
          'architecture','bench','code','ground','simulation'].map(id => '/studio?target=native#' + id)]) {
      visiting = route;
      await page.goto(new URL(route, base).href);
      await ready();
      const failure = await page.locator('body.workspace-loading #workspace-opening p, #feedback').allInnerTexts();
      if (failure.some(text => text.trim())) rows.push([route, 'Page feedback', failure.join(' ')]);
      const controls = await page.locator('button:visible,a:visible,summary:visible,input:visible,select:visible,[role=button]:visible')
        .evaluateAll(elements => elements.map(el => [
          el.getAttribute('aria-label') || el.title || el.textContent.trim().replace(/\s+/g,' ') || el.name || el.id || el.tagName,
          el.getAttribute('href') || Object.keys(el.dataset).map(k=>k + '=' + el.dataset[k]).join(' ') || el.id || el.tagName
        ]));
      for (const [label, destination] of controls) rows.push([route,label,destination]);
    }
    if (verifyRoutes) {
      visiting = 'Step bar and history';
      await page.locator('#flight-guide a[data-flight=target]').click();
      await ready();
      await page.goBack();
      await ready();
      await page.goForward();
      await ready();
      assert.deepEqual(rows.filter(([, label]) => label === 'Route entry' || label === 'Page feedback'), []);
      assert.deepEqual(await saved(), before, 'a passive view changed the target, checks, profile, or jobs');
      assert.deepEqual(faults, []);
    } else if (faults.length) {
      for (const fault of faults) rows.push(['Browser', 'Page error', fault]);
    }
  } finally {await browser.close();}
  return rows;
}

console.log(JSON.stringify(process.argv[2] ? await crawl(process.argv[2], process.argv.includes('--verify-routes')) : staticMap()));
