import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fieldValues, userFields, renderContact} from '../static/contact-view.js';

const command = fields => ({fields});
const field = (name, format, count = 1) => ({name, format, count});

test('wire inputs preserve leading zero bytes and exact 64-bit integer text', () => {
  const c = command([field('Bytes', 'raw', 4), field('Address', 'Q')]);
  assert.deepEqual(fieldValues(c, {Bytes:'00 01 0a ff', Address:'18446744073709551615'}),
    {Bytes:'00 01 0a ff', Address:'18446744073709551615'});
});

test('integer arrays reject rounded JSON numbers and accept exact quoted values', () => {
  const c = command([field('Counters', 'Q', 2)]);
  assert.deepEqual(fieldValues(c, {Counters:'["18446744073709551615", "9007199254740993"]'}),
    {Counters:['18446744073709551615', '9007199254740993']});
  assert.throws(() => fieldValues(c, {Counters:'[18446744073709551615, 1]'}), /quote large integers/);
  assert.throws(() => fieldValues(c, {Counters:'[1]'}), /expected 2 values/);
  assert.throws(() => fieldValues(c, {Counters:'1, 2'}), /enter an array/);
});

test('booleans retain false and nested padding is left to the encoder', () => {
  const c = command([field('Enabled', '?'), field('Payload.Padding1', 'B', 2), field('spare', 'B')]);
  assert.deepEqual(userFields(c).map(f => f.name), ['Enabled']);
  assert.deepEqual(fieldValues(c, {Enabled:false}), {Enabled:false});
  assert.deepEqual(fieldValues(c, {Enabled:true}), {Enabled:true});
});


test('confirmed history only marks a separate app when source subscriptions include one', () => {
  const c = {id:'TO_LAB_OUTPUT_ENABLE_CC', app:'to_lab', mid:0x1880, code:6, fields:[], event_id:1, sent_at:1};
  const routes = {ingress:{app:'ci_lab'}, egress:{app:'to_lab'}, commands:{[c.id]:[{app:'to_lab'}]}};
  const v = {catalog:{apps:[], commands:[c], first_contact_routes:routes}, command:c,
    station:{commands:[c]}, receipts:new Map([[1, {message:'Telemetry enabled'}]]), values:{},
    commandGroups:new Set(), telemetryGroups:new Set(), packetGroups:new Set(), target:'native'};
  const history = () => renderContact(v).match(/class="history-dots"[\s\S]*?<\/span>/)[0];
  assert.equal((history().match(/class="done"/g)||[]).length, 4);
  assert.match(history(), /class="skipped"/);
  routes.commands[c.id] = [{app:'sample_app'}];
  assert.equal((history().match(/class="done"/g)||[]).length, 5);
  assert.doesNotMatch(history(), /class="skipped"/);
  delete routes.commands[c.id];
  assert.match(history(), /class="skipped"/);
});
