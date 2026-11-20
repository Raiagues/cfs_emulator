import test from 'node:test';
import assert from 'node:assert/strict';
import {boardProgress} from '../static/board-setup.js';

test('the Board sheet requires Use before deployment and shows the named running target',()=>{
  const hardware={launch:{physical:{action:'active',target:'native',label:'View active flight'}}};
  assert.equal(boardProgress('native',hardware,[],null).action,'use');
  assert.deepEqual(boardProgress('physical',hardware,[],null),{action:'stop',target:'native',label:'Stop cFS · Native'});
  for(const [action,label] of [['build','Build cFS'],['run','Run cFS']]){
    hardware.launch.physical={action,label};
    assert.deepEqual(boardProgress('physical',hardware,[],null),{action,label});
    assert.equal(boardProgress('physical',hardware,[{action,status:'running'}],null).action,undefined);
  }
  assert.equal(boardProgress('physical',hardware,[],{steps:{board:{observed_at:10,ref:{run:'instance'}}}}).complete,true);
});
