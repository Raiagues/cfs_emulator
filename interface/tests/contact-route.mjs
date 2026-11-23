import {test} from 'node:test';
import assert from 'node:assert/strict';
import {contactRouteModel,routeMarkup,renderContact,confirmedReplyMid} from '../static/contact-view.js';

const fixture = () => {
 const apps=Array.from({length:40},(_,i)=>({name:'app_'+i}));
 const command={id:'APP_9_NOOP_CC',app:'app_9',mid:0x1888,code:0,size:8,fields:[]};
 const packet={id:'APP_2_EVENT_MID',app:'app_2',mid:0x0808,size:16,fields:[]};
 const routes={ingress:{app:'app_0'},egress:{app:'app_1',pipe:'Downlink.TlmPipe'},commands:{[command.id]:[{app:'app_9',mid:command.mid,pipe:'App9.CmdPipe'},{app:'app_8',mid:command.mid,pipe:'App8.CmdPipe'}]},returns:{[packet.mid]:{app:'app_2',publishers:[{app:'app_2',path:'event.c',line:1}]}},applications:{}};
 for(const app of apps)routes.applications[app.name]={subscriptions:[{mid:0x0999,pipe:app.name+'.OtherPipe'}],publications:[]};
 routes.applications.app_7.publications.push({mid:command.mid,path:'publisher.c',line:2});
 routes.applications.app_4.subscriptions.push({mid:packet.mid,pipe:'EventPipe'});
 return {command,packet,catalog:{apps,commands:[command],packets:[packet],first_contact_routes:routes}};
};
const names=model=>model.nodes.map(n=>n.name).sort();

test('a selected command shows only its senders, subscribers and real uplink',()=>{
 const {catalog,command}=fixture(),model=contactRouteModel(catalog,command),html=routeMarkup(catalog,command,null,'native',null);
 assert.deepEqual(names(model),['app_0','app_7','app_8','app_9']);
 assert.deepEqual(model.recipients,['app_9','app_8']);assert.deepEqual(model.producers,[]);
 assert.equal(model.ingress,'app_0');assert.equal(model.egress,null);
 assert.equal((html.match(/data-route-node="app"/g)||[]).length,4);
 assert.equal((html.match(/data-up /g)||[]).length,2);
 assert.equal((html.match(/class="software-bus"/g)||[]).length,1);
 assert.doesNotMatch(html,/0x0999|data-down |data-play|app_39/);
 for(const node of model.nodes)for(const row of [...node.subscriptions,...node.publications])assert.equal(row.mid,command.mid);
});

test('a confirmed return adds only its own MID participants and downlink',()=>{
 const {catalog,command,packet}=fixture(),model=contactRouteModel(catalog,command,packet.mid);
 assert.deepEqual(names(model),['app_0','app_1','app_2','app_4','app_7','app_8','app_9']);
 assert.deepEqual(model.producers,['app_2']);assert.equal(model.egress,'app_1');
 assert.equal(model.height,270);assert(model.nodes.some(n=>n.row===0)&&model.nodes.some(n=>n.row===1));
 assert.equal(new Set(model.nodes.map(n=>n.x+'/'+n.y)).size,model.nodes.length);
 assert.equal(model.nodes.find(n=>n.name==='app_1').subscriptions[0].pipe,'Downlink.TlmPipe');
});

test('telemetry selection shows its publishers and subscribers without a command uplink',()=>{
 const {catalog,packet}=fixture(),model=contactRouteModel(catalog,packet),html=routeMarkup(catalog,packet,null,'native',null);
 assert.deepEqual(names(model),['app_1','app_2','app_4']);
 assert.equal(model.ingress,null);assert.equal(model.egress,'app_1');
 assert.equal(model.nodes.find(n=>n.name==='app_2').row,0);assert.equal(model.nodes.find(n=>n.name==='app_4').row,1);
 assert.doesNotMatch(html,/data-up |app_9|0x1888/);assert.match(html,/data-down data-producer="app_2"/);
});

test('unresolved commands and replies do not fall back to a different MID',()=>{
 const {catalog,command}=fixture();
 const missing={...command,id:'UNKNOWN_CC',mid:0x1fff};
 assert.deepEqual(contactRouteModel(catalog,missing).nodes,[]);
 const model=contactRouteModel(catalog,command,0x0fff);
 assert.deepEqual(names(model),['app_0','app_7','app_8','app_9']);
 assert.equal(model.egress,null);assert.deepEqual(model.producers,[]);
 catalog.first_contact_routes.commands[command.id]=[{app:'absent',mid:command.mid}];
 assert.deepEqual(contactRouteModel(catalog,command).recipients,[]);
});

test('older frozen catalogs keep their exact command and return relationships',()=>{
 const {catalog,command,packet}=fixture();delete catalog.first_contact_routes.applications;
 assert.deepEqual(names(contactRouteModel(catalog,command,packet.mid)),['app_0','app_1','app_2','app_8','app_9']);
});

test('many actual subscribers expand sideways around one bus rather than adding unrelated apps',()=>{
 const {catalog,command}=fixture();
 for(const app of catalog.apps)catalog.first_contact_routes.applications[app.name].subscriptions=[{mid:command.mid,pipe:app.name+'.Cmd'}];
 const model=contactRouteModel(catalog,command),html=routeMarkup(catalog,command,null,'native',null);
 assert.equal(model.nodes.length,40);assert.equal(model.height,270);assert(model.width>760);
 assert.equal((html.match(/class="software-bus"/g)||[]).length,1);
 assert.equal(new Set(model.nodes.map(n=>n.x+'/'+n.y)).size,40);
});

test('rendered totals use session counters rather than limited history arrays',()=>{
 const {catalog,command}=fixture();
 const html=renderContact({catalog,command,target:'native',values:{},guided:false,commandGroups:new Set(['app_9']),telemetryGroups:new Set(),packetGroups:new Set(),receipts:new Map(),
 station:{commands:[],packets:[],communication:{totals:{commands_sent:5000,telemetry_received:6000},commands:{[command.id]:750}}}});
 assert.match(html,/5,000 sent/);assert.match(html,/6,000 received/);assert.match(html,/↑ 750/);
});


test('the guided Event accepts only its displayed sample_app NOOP receipt',()=>{
 const {catalog,command}=fixture();
 const sample={...command,id:'SAMPLE_APP_NOOP_CC',app:'sample_app'};
 catalog.commands.push(sample);catalog.apps.push({name:'sample_app'});
 const receipt={command:command.id,send_id:20,reply:21,increase:22,baseline:0,count:1,message:'Other app NOOP'};
 const v={catalog,command:sample,target:'native',values:{},guided:true,nextUrl:'/studio#app',
  commandGroups:new Set(),telemetryGroups:new Set(),packetGroups:new Set(),receipts:new Map([[20,receipt]]),
  station:{commands:[],packets:[],first_flight:{noop_command:sample.id,downlink_receipt:{send_id:1},answer:true,receipt}}};
 const wrong=renderContact(v);
 assert.equal((wrong.match(/data-fact="done"/g)||[]).length,1,'Only Telemetry on is complete');
 assert.doesNotMatch(wrong,/class="contact-next"/);
 v.station.first_flight.receipt={...receipt,command:sample.id};
 const right=renderContact(v);
 assert.equal((right.match(/data-fact="done"/g)||[]).length,3);
 assert.match(right,/class="contact-next"/);
});


test('a confirmed reply stays in the selected route after playback, scoped to the latest send',()=>{
 const {catalog,command,packet}=fixture();
 const receipt={command:command.id,send_id:30,reply:31,increase:32,event_mid:packet.mid};
 const receipts=new Map([[30,receipt]]),station={commands:[{...command,event_id:30}],packets:[]};
 const v={catalog,command,station,target:'native',values:{},guided:false,commandGroups:new Set(),telemetryGroups:new Set(),packetGroups:new Set(),receipts};
 assert.equal(confirmedReplyMid(station,command,receipts),packet.mid);
 const afterPlayback=renderContact(v);
 assert.match(afterPlayback,/data-down data-producer="app_2"/);
 assert.match(afterPlayback,/data-route-node="app" data-app="app_1"/);
 assert.doesNotMatch(afterPlayback,/data-app="app_39"|contact-playback/);
 station.commands.push({...command,id:'OTHER_CC',event_id:35});
 assert.equal(confirmedReplyMid(station,command,receipts),packet.mid,"Sending another command does not replace this command's receipt");
 station.commands.push({...command,event_id:40});
 assert.equal(confirmedReplyMid(station,command,receipts),null,'A later unanswered send cannot reuse an earlier confirmation');
 assert.doesNotMatch(renderContact(v),/data-down /);
 receipts.set(40,{...receipt,send_id:40,increase:null});
 assert.equal(confirmedReplyMid(station,command,receipts),null,'An event without the counter is not confirmed');
 receipts.set(40,{...receipt,send_id:40});
 assert.equal(confirmedReplyMid(station,command,receipts),packet.mid);
 const selectedPacket=renderContact({...v,routePacket:packet});
 assert.doesNotMatch(selectedPacket.match(/<section class="contact-trip"[\s\S]*?<\/section>/)[0],/data-up |0x1888/);
});
