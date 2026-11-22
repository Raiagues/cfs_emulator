import {api, readJourney} from './api.js';
import {guide} from './coach.js';
import {deploymentControls} from './deployment-controls.js';
import {escapeHtml as esc, paint} from './dom.js';
import {drawPath, packetFlight} from './lesson-path.js';
import {onUpdate} from './updates.js';
import {icon} from './ui.js';

const ENABLE = {app:'to_lab', name:'ENABLE_OUTPUT', field:'dest_IP'};
const NOOP = {app:'sample_app', name:'NOOP'};
const check = '<svg class="fs-draw" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
function row(command, selected) {
  return `<button type="button" class="lesson-row" data-pick="${esc(command.name)}" aria-pressed="${command===selected}">
    ${icon('send')}<span><small>${esc(command.app)}</small><strong>${esc(command.name)}</strong>${command.authored?'<small>NEW</small>':''}</span></button>`;
}

function telemetry(station, contact, app) {
  if (!station?.connected || !contact.downlink_receipt) return '';
  const count = contact.counters?.[app];
  const receipt = contact.receipt;
  const own = receipt?.reply ? receipt.message : null;
  const other = station.packets.filter(packet => packet.app !== app && packet.app !== 'cfe_evs');
  return `<aside class="lesson-right fs-in"><h2>Telemetry</h2>
    ${count == null ? '' : `<article class="fs-panel fs-pop"><h3>${esc(app)}</h3><span>CommandCounter</span>
       <strong data-counter="${esc(app)}" data-scene="count-${count}" class="fs-pop">${count}</strong>
       ${receipt?.increase?`<b class="lesson-delta fs-pop">+1</b>`:''}</article>`}
    ${own?`<article class="fs-panel fs-in"><h3>Flight event</h3><p data-reply>${esc(own)}</p></article>`:''}
    ${other.length?`<details><summary>Housekeeping · ${other.length} packets</summary>${other.map(p=>`<div class="packet-card"><strong>${esc(p.app)}</strong> ${esc(p.name)}</div>`).join('')}</details>`:''}
  </aside>`;
}

export function mountGroundLesson(root, {state, advanceDeployment}) {
  const target = state.target, sendMode = state.activity === 'send';
  let main = sendMode ? null : NOOP;
  const deploy = () => sendMode ? deploymentControls(state) : {};
  const choices = () => [ENABLE,main].filter(Boolean);
  let station, selected, draft = '', busy = false, disposed = false, error = '', waiting, timer;
  let version = 0, responseSeen = 0, lastSession;
  const flights = new Set();
  const local = () => station?.target === target && station.connected;
  const first = () => local() ? (sendMode ? station.authored_reply : station.first_flight) : {};
  function packet(nodes, label, returning) {
    const cancel = packetFlight(root.querySelector('.lesson-track'), nodes, label, returning);
    flights.add(cancel);
  }
  function valid() {
    if(selected?.field==='Rate_Hz')return /^\d+$/.test(draft) && Number(draft)>=1 && Number(draft)<=50;
    return selected && (!selected.field || /^\d{1,3}(\.\d{1,3}){3}$/.test(draft) && draft.split('.').every(part=>+part<=255));
  }
  function stopWait() {
    clearTimeout(timer);waiting=null;
  }
  function cue() {
    const flight = first();
    let action;
    const {plan, button, working}=deploy();
    if (!station || !main || busy || waiting || working) action = null;
    else if(plan) {guide(button || root.querySelector('[data-deploy]'));return;}
    else if (!local()) action = '[data-connect]';
    else if (!flight.downlink_receipt && selected !== ENABLE) action = '[data-pick="ENABLE_OUTPUT"]';
    else if (flight.downlink_receipt && selected !== main) action = '[data-pick="'+CSS.escape(main.name)+'"]';
    else if (!valid()) action = '[data-argument]';
    else if (selected !== main || flight.baseline_apps?.includes(main?.app)) action = '[data-send]';
    guide(action && root.querySelector(action));
  }
  function draw() {
    if (disposed) return;
    const flight = first(), connected = local();
    const {plan,working,failure}=deploy();
    const stage = [!!flight.downlink_receipt, !!flight.receipt?.send_id, !!flight.answer];
    const cards = ['Telemetry on', sendMode?'Your command':'First command', 'Answer'].map((label,i) =>
      `<li class="fs-panel" data-done="${stage[i]}" ${error && (i===0 && selected===ENABLE || i===2 && selected===main)?'data-failed':''}>
        <i>${stage[i]?check:i+1}</i><strong>${label}</strong></li>`).join('');
    const active = selected || (flight.downlink_receipt && main ? main : ENABLE);
    const destination = selected?.authored ? '1…50' : flight.return_host;
    const commands = connected ? station.commands : [];
    const sent = commands.at(-1);
    const ready = valid() && (selected !== main || flight.baseline_apps?.includes(main?.app) && flight.downlink_receipt);
    const field = selected?.field ? `<label class="lesson-field" data-scene="arg-${esc(selected.app)}-${esc(selected.field)}">${selected.field}<input data-argument autocomplete="off" spellcheck="false"
        value="${esc(draft)}" placeholder="${esc(destination || '')}" aria-label="${selected.field}"></label>` : '';
    const cli = plan && ['boot','stop','build','run'].includes(plan.action) ? './start --no-ui '+plan.action+' --target '+target :
      !connected ? './start --no-ui ground connect --target '+target :
      './start --no-ui ground send '+ active.app+' '+active.name+(active.field?' --arg '+active.field+'='+(draft || destination || '<value>'):'');
    paint(root, `<section class="ground-lesson fs-in">
      <aside class="lesson-list"><h2>Commands</h2>${choices().map(command=>row(command,selected)).join('')}</aside>
      <div class="lesson-body"><ol class="lesson-cards">${cards}</ol>
      <form class="lesson-form fs-panel" novalidate>
        ${selected?`<span><small>${esc(selected.app)}</small><strong>${esc(selected.name)}</strong></span>`:''}
        ${field}${plan ? `<button type="button" class="primary" data-deploy ${working?'disabled':''}>${esc(plan.label)}</button>` : !connected?`<button type="button" class="primary" data-connect ${!station||busy?'disabled':''}>Connect</button>`:
          selected?`<button type="submit" class="primary" data-send ${!ready||busy||waiting?'disabled':''}>Send</button>`:''}
        ${error||failure?`<output role="alert">${esc(error||failure)}</output>`:''}
      </form>
      ${drawPath(active.app, connected)}
      ${sent?`<details class="lesson-bytes fs-panel fs-in"><summary>See the bytes</summary><code>${esc(sent.hex.match(/../g).join(' '))}</code><small>${sent.bytes} B · CCSDS</small></details>`:''}
      <details class="terminal-twin"><summary>In the terminal</summary><pre>${esc(cli)}</pre></details></div>
      ${telemetry(station,flight,main?.app)}</section>`);
    cue();
  }
  async function read() {
    const id = ++version;
    const next = await api('ground');
    if (disposed || version !== id) return;
    if (lastSession && lastSession !== next.communication.since) {
      selected=null;draft='';stopWait();responseSeen=0;error='';
    }
    station=next;lastSession=next.communication.since;
    const flight=first();
    if (waiting===ENABLE && flight.downlink_receipt || waiting===main && flight.answer) {stopWait();error='';}
    draw();
    const reply = flight.receipt?.reply || flight.downlink_receipt?.send_id || 0;
    if (reply > responseSeen) {
      responseSeen = reply;
      packet(flight.receipt?.reply ? [main?.app,'to_lab','Ground'] : ['to_lab','Ground'],
        flight.receipt?.reply ? 'Flight event' : 'Housekeeping', true);
    }
  }
  function fail(e) {if (!disposed) {error=e.message;draw();}}
  async function operate(action) {
    if (busy) return;
    busy=true;error='';draw();
    try {
      if (action==='connect') await api('ground/start',{target});
      else {
        if (!local() || !valid()) return;
        const cmd=selected;
        await api('ground/send',{target, app:cmd.app, command:cmd.name,args:cmd.field?{[cmd.field]:draft}:{}});
        if (disposed) return;
        packet(cmd===ENABLE?['Ground','ci_lab','to_lab']:['Ground','ci_lab','Software Bus',cmd.app],cmd.name,false);
        waiting=cmd;
        timer=setTimeout(()=>{
          if (disposed || !waiting) return;
          error=cmd===ENABLE?'No telemetry. Check dest_IP and send again.':'No reply. Check the cFS console and send again.';
          stopWait();draw();
        }, station.reply_timeout*1000);
      }
      await read();
    } catch(e) {fail(e);}
    finally {busy=false;draw();}
  }
  function click(event) {
    const button=event.target.closest('button');
    if (!button || busy || waiting) return;
    if (button.hasAttribute('data-deploy'))advanceDeployment(deploy().plan).catch(fail);
    if (button.hasAttribute('data-connect')) operate('connect');
    if (button.dataset.pick) {
      selected=choices().find(command => command.name===button.dataset.pick);
      draft='';error='';draw();
      root.querySelector('[data-argument]')?.focus({preventScroll:true});
    }
  }
  function input(event) {
    if (!event.target.hasAttribute('data-argument')) return;
    draft=event.target.value;error='';draw();
  }
  function submit(event) {event.preventDefault();if(valid()&&!waiting) operate('send');}
  root.addEventListener('click',click);root.addEventListener('submit',submit);root.addEventListener('input',input);
  const unsubscribe=onUpdate(['ground','jobs'],()=>read().catch(fail));
  async function open() {
    if(sendMode) {
      const journey=await readJourney(target);
      const evidence=journey.steps.command.ref;
      if(!evidence?.command)throw Error('Build your command first.');
      const name=evidence.command.slice(evidence.app.length+1).replace(/_CC$/,'');
      main={app:evidence.app,name,field:name==='SET_RATE'?'Rate_Hz':null,authored:true};
    }
    await read();
  }
  draw();open().catch(fail);
  return {update:draw,close() {
    disposed=true;unsubscribe();stopWait();flights.forEach(cancel=>cancel());
    root.removeEventListener('click',click);root.removeEventListener('submit',submit);root.removeEventListener('input',input);
  }};
}
