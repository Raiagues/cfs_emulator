'use strict';
// Real UI illustration only. Run after quantitative collection is complete.
// Does not start a server, build, boot, stop flight, or send any cFS command.
// Optional environment: PLAYWRIGHT_MODULE (module/path), CHROME_BIN (browser executable).
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {parseArgs} = require('node:util');
const options = parseArgs({options:{
  log:{type:'string'}, output:{type:'string'}, target:{type:'string',default:'qemu'},
  'after-measurements':{type:'boolean',default:false},
  'connect-receiver':{type:'boolean',default:false},
  help:{type:'boolean',default:false}
}}).values;
if(options.help){
  console.log('node /tmp/capture-evaluation-ground.cjs --after-measurements --log SERVER_LOG --output NEW_DIR --target qemu [--connect-receiver]');
  process.exit(0);
}
assert(options['after-measurements'],'Explicit --after-measurements acknowledgement required.');
assert(options.log && options.output,'--log and --output are required.');
assert(['native','qemu','physical'].includes(options.target),'Unknown target.');
assert(!fs.existsSync(options.output),'Output directory must not already exist.');
const urls=fs.readFileSync(options.log,'utf8').match(/http:\/\/127\.0\.0\.1:8766\/\?t=[A-Za-z0-9_-]+/g);
assert(urls?.length,'No isolated localhost:8766 launch URL found in server log.');
const launchURL=urls.at(-1), origin=new URL(launchURL).origin;
const output=path.resolve(options.output);
const privateValues=[new URL(launchURL).searchParams.get('t')];
const sanitize=value=>{
  let text=String(value).replace(/https?:\/\/[^\s"']+/g,'[URL omitted]');
  for(const secret of privateValues)if(secret)text=text.split(secret).join('[redacted]');
  return text;
};
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const pick=(value,keys)=>Object.fromEntries(keys.filter(k=>value[k]!==undefined).map(k=>[k,value[k]]));
const packetRecord=packet=>pick(packet,['mid','sequence','bytes','name','app','source','values','errors','hex','received_at','count','event_id']);
const apps=['eval_temp','eval_mag','eval_mpu'];
const telemetryOrder=['eval_mag','eval_mpu','eval_temp'];
const result={purpose:'Real Ground UI illustration after quantitative collection; not a quantitative measurement',
  target:options.target,started_at:new Date().toISOString(),server_port:8766,
  preferences:{theme:'dark'},mutating_requests:[],blocked_requests:[],screenshots:[],page_errors:[]};
let browser,page;
(async()=>{
  const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  fs.mkdirSync(output,{recursive:false});
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_BIN || '/usr/bin/google-chrome',
    args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  const context=await browser.newContext({viewport:{width:1920,height:1280},deviceScaleFactor:1});
  await context.addInitScript(()=>{
    localStorage.setItem('fs-theme','dark');
    localStorage.setItem('fs-welcome','seen');
  });
  // Exchange the launch key for its real cookie without loading the setup page.
  const authentication=await context.request.get(launchURL,{maxRedirects:0});
  assert.equal(authentication.status(),303,'Launch session could not be established.');
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url()),method=request.method();
    if(url.origin!==origin)return route.abort('blockedbyclient');
    if(['GET','HEAD'].includes(method))return route.continue();
    let body;try{body=request.postDataJSON();}catch{}
    const allowed=options['connect-receiver'] && method==='POST' &&
      url.pathname==='/api/ground/start' && body?.target===options.target;
    const record={method,path:url.pathname,target:body?.target??null};
    if(allowed){result.mutating_requests.push(record);return route.continue();}
    result.blocked_requests.push(record);
    return route.abort('blockedbyclient');
  });
  page=await context.newPage();
  page.setDefaultTimeout(25000);
  page.on('pageerror',error=>result.page_errors.push(sanitize(error.message)));
  await page.goto(origin+'/studio?target='+options.target+'#ground',{waitUntil:'domcontentloaded'});
  await page.locator('.contact-layout').waitFor();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  const read=endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint,{cache:'no-store'});
    if(!response.ok)throw Error(endpoint+' returned '+response.status);
    return response.json();
  },endpoint);
  const catalog=await read('/api/ground/catalog?target='+options.target);
  const sensors=apps.map(app=>{
    const packet=catalog.packets.find(p=>p.app===app && p.id.endsWith('_SAMPLE_TLM_MID'));
    assert(packet,app+' sensor packet missing from real build catalog');
    return packet;
  });
  const byApp=Object.fromEntries(sensors.map(packet=>[packet.app,packet]));
  // Only packets received during this capture session satisfy the populated check.
  const startedAt=Date.parse(result.started_at)/1000;
  await page.waitForFunction(async ({target,mids,since})=>{
    const response=await fetch('/api/ground',{cache:'no-store'});if(!response.ok)return false;
    const state=await response.json();
    return state.connected && state.target===target && mids.every(mid=>
      state.packets?.some(packet=>packet.mid===mid && packet.received_at>=since &&
        packet.values && Object.keys(packet.values).length && !packet.errors?.length));
  },{target:options.target,mids:sensors.map(p=>p.mid),since:startedAt},{timeout:45000,polling:700});
  let station=await read('/api/ground');
  assert.equal(station.build_fingerprint,catalog.build_fingerprint,'Live receiver and catalog build differ');
  result.build_fingerprint=station.build_fingerprint;
  result.catalog_packets=sensors.map(packet=>pick(packet,['id','app','name','mid','size','fields','source']));
  const terminal=page.locator('#toggle-terminal');
  if(await terminal.count() && await terminal.getAttribute('aria-expanded')==='true')await terminal.click();
  const setGroup=async(kind,app,expanded)=>{
    const group=page.locator(`[data-${kind}-group="${app}"]`);
    if(await group.getAttribute('aria-expanded')!==String(expanded))await group.click();
  };
  for(const name of await page.locator('[data-command-group]').evaluateAll(nodes=>nodes.map(n=>n.dataset.commandGroup)))
    await setGroup('command',name,apps.includes(name));
  for(const name of await page.locator('[data-telemetry-group]').evaluateAll(nodes=>nodes.map(n=>n.dataset.telemetryGroup)))
    await setGroup('telemetry',name,apps.includes(name));
  const noop=catalog.commands.find(command=>command.app==='eval_mpu'&&command.id.endsWith('_NOOP_CC'));
  assert(noop,'Real MPU NOOP absent');
  await page.locator(`[data-pick="${noop.id}"]`).click(); // select only, never Send
  for(const app of ['eval_temp','eval_mag','eval_mpu']){
    const button=page.locator(`[data-packet="${byApp[app].id}"]`);
    if(await button.getAttribute('aria-expanded')!=='true')await button.click();
  }
  const verifyRoute=async packet=>{
    await page.waitForFunction(id=>document.querySelector(`[data-packet="${id}"]`)?.getAttribute('aria-pressed')==='true',packet.id);
    const route=await page.evaluate(async ({catalog,packet})=>{
      const {contactRouteModel}=await import('/contact-view.js');
      const model=contactRouteModel(catalog,packet);
      return {mid:model.selectedMid,expected:model.nodes.map(node=>node.name).sort(),
        actual:[...document.querySelectorAll('[data-route-node="app"]')].map(node=>node.dataset.app).sort(),
        busCount:document.querySelectorAll('.software-bus').length,
        groundCount:document.querySelectorAll('[data-route-node="ground"]').length,
        publications:model.nodes.flatMap(node=>node.publications.map(row=>({app:node.name,...row}))),
        subscriptions:model.nodes.flatMap(node=>node.subscriptions.map(row=>({app:node.name,...row})))};
    },{catalog,packet});
    assert.deepEqual(route.actual,route.expected,'Displayed diagram differs from resolved source relationships');
    assert.equal(route.busCount,1);assert.equal(route.groundCount,1);
    assert(route.actual.includes(packet.app),'Selected telemetry publisher absent');
    return route;
  };
  const capture=async(name,packet,{telemetryCrop=false}={})=>{
    const route=await verifyRoute(packet);
    const fields=await page.locator(`[data-packet="${packet.id}"] + .contact-fields`).evaluate(el=>
      [...el.querySelectorAll('.contact-value')].map(row=>({
        name:row.querySelector('code').textContent,value:row.querySelector('output').textContent,
        name_elided:row.querySelector('code').scrollWidth>row.querySelector('code').clientWidth,
        value_elided:row.querySelector('output').scrollWidth>row.querySelector('output').clientWidth})));
    assert(fields.length===packet.fields.length&&fields.every(field=>field.value!=='—'),'Fields not populated by real packets');
    station=await read('/api/ground');
    const filename=name+'.png';
    await page.screenshot({path:path.join(output,filename)});
    const record={file:filename,sha256:sha(path.join(output,filename)),captured_at:new Date().toISOString(),
      viewport:page.viewportSize(),selected_packet:packet.id,route,displayed_fields:fields,
      // API sample is read immediately before screenshot, not claimed to be the exact paint frame.
      preceding_packets:station.packets.filter(row=>sensors.some(sensor=>sensor.mid===row.mid)).map(packetRecord)};
    result.screenshots.push(record);
    if(telemetryCrop){
      const region=page.locator('.contact-telemetry .contact-tree').filter({
        has:page.locator(`[data-telemetry-group="${packet.app}"]`)
      });
      assert.equal(await region.count(),1,'Telemetry app region must be unique');
      await region.scrollIntoViewIfNeeded();
      const bounds=await region.boundingBox();
      assert(bounds&&bounds.width>0&&bounds.height>0,'Telemetry app region is not visible');
      const cropName=name+'-telemetry.png';
      const preceding=await read('/api/ground');
      // Playwright captures this actual DOM element, including app/packet headings.
      // No image editing, CSS overrides, resized fonts or substituted data.
      await region.screenshot({path:path.join(output,cropName)});
      const cropFields=await region.locator('.contact-value').evaluateAll(rows=>rows.map(row=>({
        name:row.querySelector('code').textContent,value:row.querySelector('output').textContent,
        name_elided:row.querySelector('code').scrollWidth>row.querySelector('code').clientWidth,
        value_elided:row.querySelector('output').scrollWidth>row.querySelector('output').clientWidth})));
      result.screenshots.push({file:cropName,sha256:sha(path.join(output,cropName)),
        captured_at:new Date().toISOString(),kind:'actual_dom_element',context_file:filename,
        viewport:page.viewportSize(),dom_bounds_css_px:bounds,selected_packet:packet.id,
        selected_mid:packet.mid,app:packet.app,displayed_fields:cropFields,
        preceding_packets:preceding.packets.filter(row=>row.mid===packet.mid).map(packetRecord),
        caption_context:`Real Ground telemetry for ${packet.app}; ${packet.id}, MID 0x${packet.mid.toString(16).toUpperCase()}; target ${options.target}; post-collection illustration. Values are the decoded wire fields as rendered, without unit conversion. Names may be elided by the application; full names and values accompany this image in capture.json. The preceding API record is not asserted to be the exact screenshot paint frame.`});
    }
  };
  await page.locator('.contact-telemetry > nav').evaluate(el=>{el.scrollTop=0;});
  await capture('ground-'+options.target+'-overview',byApp.eval_mpu);
  // Individual panels expose all fields without inventing or replacing UI content.
  for(const app of telemetryOrder){
    for(const other of apps)await setGroup('telemetry',other,other===app);
    const button=page.locator(`[data-packet="${byApp[app].id}"]`);
    if(await button.getAttribute('aria-pressed')!=='true'){
      await button.click();
      if(await button.getAttribute('aria-expanded')!=='true')await button.click();
    }
    await page.locator('.contact-telemetry > nav').evaluate(el=>{el.scrollTop=0;});
    await capture('ground-'+options.target+'-'+app,byApp[app],{telemetryCrop:true});
  }
  assert.equal(result.page_errors.length,0,'Page errors occurred; inspect sanitized metadata');
  assert(!result.mutating_requests.some(row=>row.path!=='/api/ground/start'),'Unexpected mutation');
  result.passed=true;
})().catch(error=>{
  result.passed=false;result.error=sanitize(error.message);process.exitCode=1;
}).finally(async()=>{
  if(browser)await browser.close();
  result.finished_at=new Date().toISOString();
  if(fs.existsSync(output))fs.writeFileSync(path.join(output,'capture.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({passed:result.passed,output,screenshots:result.screenshots.map(s=>s.file),
    blocked_requests:result.blocked_requests,error:result.error}));
});
