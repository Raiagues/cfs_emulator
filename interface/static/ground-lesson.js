import {api} from './api.js';
import {guide} from './coach.js';
import {escapeHtml as esc, paint} from './dom.js';
import {drawPath, packetFlight} from './lesson-path.js';
import {onUpdate} from './updates.js';
import {icon} from './ui.js';

const ENABLE = {app:'to_lab', name:'ENABLE_OUTPUT', field:'dest_IP'};
const NOOP = {app:'sample_app', name:'NOOP'};
const check = '<svg class="fs-draw" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
function row(command, selected) {
  return `<button type="button" class="lesson-row" data-pick="${esc(command.name)}" aria-pressed="${command===selected}">
    ${icon('send')}<span><small>${esc(command.app)}</small><strong>${esc(command.name)}</strong></span></button>`;
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

export function mountGroundLesson(root, {state}) {
  const target = state.target;
  let station, selected, draft = '', busy = false, disposed = false, error = '', waiting, timer;
  let version = 0, responseSeen = 0, lastSession;
  const flights = new Set();
  const local = () => station?.target === target && station.connected;
  const first = () => local() ? station.first_flight : {};
  function packet(nodes, label, returning) {
    const cancel = packetFlight(root.querySelector('.lesson-track'), nodes, label, returning);
    flights.add(cancel);
  }
  function valid() {
    return selected && (!selected.field || /^\d{1,3}(\.\d{1,3}){3}$/.test(draft) && draft.split('.').every(part=>+part<=255));
  }
  function stopWait() {
    clearTimeout(timer);waiting=null;
  }
  function cue() {
    const flight = first();
    let action;
    if (!station || busy || waiting) action = null;
    else if (!local()) action = '[data-connect]';
    else if (!flight.downlink_receipt && selected !== ENABLE) action = '[data-pick="ENABLE_OUTPUT"]';
    else if (flight.downlink_receipt && selected !== NOOP) action = '[data-pick="NOOP"]';
    else if (!valid()) action = '[data-argument]';
    else if (selected !== NOOP || flight.baseline_apps?.includes('sample_app')) action = '[data-send]';
    guide(action && root.querySelector(action));
  }
  function draw() {
    if (disposed) return;
    const flight = first(), connected = local();
    const stage = [!!flight.downlink_receipt, !!flight.receipt?.send_id, !!flight.answer];
    const cards = ['Telemetry on', 'First command', 'Answer'].map((label,i) =>
      `<li class="fs-panel" data-done="${stage[i]}" ${error && (i===0 && selected===ENABLE || i===2 && selected===NOOP)?'data-failed':''}>
        <i>${stage[i]?check:i+1}</i><strong>${label}</strong></li>`).join('');
    const active = selected || (flight.downlink_receipt ? NOOP : ENABLE);
    const destination = flight.return_host;
    const commands = connected ? station.commands : [];
    const sent = commands.at(-1);
    const ready = valid() && (selected !== NOOP || flight.baseline_apps?.includes('sample_app') && flight.downlink_receipt);
    const field = selected?.field ? `<label class="lesson-field">${selected.field}<input data-argument autocomplete="off" spellcheck="false"
        value="${esc(draft)}" placeholder="${esc(destination || '')}" aria-label="${selected.field}"></label>` : '';
    const cli = !connected ? './start --no-ui ground connect --target '+target :
      './start --no-ui ground send '+ active.app+' '+active.name+(active===ENABLE?' --arg dest_IP='+(draft || destination):'');
    paint(root, `<section class="ground-lesson fs-in">
      <aside class="lesson-list"><h2>Commands</h2>${[ENABLE,NOOP].map(command=>row(command,selected)).join('')}</aside>
      <div class="lesson-body"><ol class="lesson-cards">${cards}</ol>
      <form class="lesson-form fs-panel" novalidate>
        ${selected?`<span><small>${esc(selected.app)}</small><strong>${esc(selected.name)}</strong></span>`:''}
        ${field}${!connected?`<button type="button" class="primary" data-connect ${!station||busy?'disabled':''}>Connect</button>`:
          selected?`<button type="submit" class="primary" data-send ${!ready||busy||waiting?'disabled':''}>Send</button>`:''}
        ${error?`<output role="alert">${esc(error)}</output>`:''}
      </form>
      ${drawPath(active.app, connected)}
      ${sent?`<details class="lesson-bytes fs-panel fs-in"><summary>See the bytes</summary><code>${esc(sent.hex.match(/../g).join(' '))}</code><small>${sent.bytes} B · CCSDS</small></details>`:''}
      <details class="terminal-twin"><summary>In the terminal</summary><pre>${esc(cli)}</pre></details></div>
      ${telemetry(station,flight,'sample_app')}</section>`);
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
    if (waiting===ENABLE && flight.downlink_receipt || waiting===NOOP && flight.answer) {stopWait();error='';}
    draw();
    const reply = flight.receipt?.reply || flight.downlink_receipt?.send_id || 0;
    if (reply > responseSeen) {
      responseSeen = reply;
      packet(flight.receipt?.reply ? ['sample_app','to_lab','Ground'] : ['to_lab','Ground'],
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
    if (button.hasAttribute('data-connect')) operate('connect');
    if (button.dataset.pick) {
      selected=[ENABLE,NOOP].find(command => command.name===button.dataset.pick);
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
  draw();read().catch(fail);
  return () => {
    disposed=true;unsubscribe();stopWait();flights.forEach(cancel=>cancel());
    root.removeEventListener('click',click);root.removeEventListener('submit',submit);root.removeEventListener('input',input);
  };
}
