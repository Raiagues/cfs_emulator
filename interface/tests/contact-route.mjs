import {test} from 'node:test';
import assert from 'node:assert/strict';
import {contactRouteModel,routeMarkup,renderContact} from '../static/contact-view.js';

const fixture = count => {
 const apps=Array.from({length:count},(_,i)=>({name:'app_'+i}));
 const command={id:'APP_9_NOOP_CC',app:'app_9',mid:0x1888,code:0,size:8,fields:[]};
 const routes={ingress:{app:'app_0'},egress:{app:'app_1'},commands:{[command.id]:[{app:'app_9',mid:command.mid,pipe:'App9.CmdPipe'},{app:'app_8',mid:command.mid,pipe:'App8.CmdPipe'}]},returns:{2056:{app:'app_2',publishers:[{app:'app_2',path:'event.c',line:1}]}},applications:{}};
 for(const app of apps)routes.applications[app.name]={subscriptions:app.name==='app_39'?[]:[{mid:command.mid,pipe:app.name+'.CmdPipe'}],publications:[]};
 return {command,catalog:{apps,commands:[command],packets:[],first_contact_routes:routes}};
};

test('every catalog app gets exactly one readable node, with only source-derived bus edges',()=>{
 const {catalog,command}=fixture(40),model=contactRouteModel(catalog,command,2056),html=routeMarkup(catalog,command,2056,'native',null);
 assert.equal(model.nodes.length,40);
 assert.equal(new Set(model.nodes.map(n=>n.name)).size,40);
 assert.equal(new Set(model.nodes.map(n=>n.x+'/'+n.y)).size,40);
 assert.equal(model.ingress,'app_0');assert.equal(model.egress,'app_1');
 assert.deepEqual(model.recipients,['app_9','app_8']);assert.deepEqual(model.producers,['app_2']);
 assert.equal((html.match(/data-route-node="app"/g)||[]).length,40);
 assert.equal((html.match(/data-up /g)||[]).length,2);
 assert.doesNotMatch(html,/data-bus-app="app_39"/);
 assert.doesNotMatch(html,/ci_lab|to_lab|sample_app|cfe_evs|sch_lab/);
 assert.doesNotMatch(html,/data-play/);
});

test('unresolved or missing apps never become send or return paths',()=>{
 const {catalog,command}=fixture(40);
 catalog.first_contact_routes.commands[command.id]=[{app:'absent'}];
 catalog.first_contact_routes.returns[2056].publishers=[{app:'absent'}];
 const html=routeMarkup(catalog,command,2056,'native',null);
 assert.doesNotMatch(html,/data-up |data-down /);
 assert.equal(contactRouteModel(catalog,command,2056).nodes.length,40);
});

test('rendered totals use session counters rather than limited history arrays',()=>{
 const {catalog,command}=fixture(40);
 const html=renderContact({catalog,command,target:'native',values:{},guided:false,commandGroups:new Set(['app_9']),telemetryGroups:new Set(),packetGroups:new Set(),receipts:new Map(),
 station:{commands:[],packets:[],communication:{totals:{commands_sent:5000,telemetry_received:6000},commands:{[command.id]:750}}}});
 assert.match(html,/5,000 sent/);assert.match(html,/6,000 received/);assert.match(html,/↑ 750/);
});
