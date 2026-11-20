// Test steps are checked by the receiver against its connected flight catalog.
export function editTrip(state, commandId, testId, {api,dialog,esc,icon,refresh}) {
  const catalog=state.catalog, target=state.target;
  const current=state.testPlans.plans.find(p=>p.id===testId);
  const appCommands=catalog.commands.filter(c=>c.app===catalog.commands.find(selected=>selected.id===commandId)?.app);
  const originalRevision=state.testPlans.revision;
  const defaultEvent=()=>({kind:'event',app:catalog.commands.find(c=>c.id===commandId)?.app.toUpperCase()||'',event_id:null,message:''});
  let steps=current?structuredClone(current.steps):[defaultEvent()];
  const option=(value,text,selected)=>'<option value="'+esc(value)+'" '+(String(selected)===String(value)?'selected':'')+'>'+esc(text)+'</option>';
  const options=(items,selected)=>items.map(p=>option(p.id,p.id,selected)).join('');
  function formStep(step,index) {
    const packet=catalog.packets.find(p=>p.id===step.packet)||catalog.packets[0];
    const title='<div class="test-step-heading"><span>Step '+(index+1)+'</span><select aria-label="Observation type" data-step-key="kind">'+option('event','Flight event',step.kind)+option('packet','Telemetry packet',step.kind)+'</select><button type="button" data-step-op="up" aria-label="Move step up" '+(!index?'disabled':'')+'>↑</button><button type="button" data-step-op="down" aria-label="Move step down" '+(index===steps.length-1?'disabled':'')+'>↓</button><button type="button" data-step-op="remove" aria-label="Remove step">'+icon('trash')+'</button></div>';
    const input=(label,key,type,value,extra='')=>'<label>'+label+'<input data-step-key="'+key+'" type="'+type+'" value="'+esc(value??'')+'" '+extra+'></label>';
    const fields=step.kind==='event'?input('EVS app name','app','text',step.app,'required maxlength="64"')+
      input('Event ID','event_id','number',step.event_id,'min="0" max="65535"')+input('Message contains','message','text',step.message,'maxlength="160"'):
      '<label>Packet<select data-step-key="packet" required>'+options(catalog.packets,step.packet)+'</select></label>'+
      '<label>Observation<select data-step-key="op">'+['received','equals','changed','increased'].map((op,i)=>option(op,['Packet arrives','Field equals','Field changes','Field increases'][i],step.op)).join('')+'</select></label>'+
      (step.op==='received'?'':'<label>Field<select data-step-key="field" required>'+(packet?.fields||[]).map(f=>option(f.name,f.name,step.field)).join('')+'</select></label>')+
      (step.op==='equals'?input('Expected value','value','text',step.value,'required'):'');
    return '<fieldset data-step-index="'+index+'">'+title+'<div class="test-step-fields">'+fields+'</div></fieldset>';
  }
  const form='<div class="test-fields"><label>Test name<input name="testName" maxlength="80" required value="'+esc(current?.name||'')+'"></label><label>Timeout (s)<input type="number" min="1" max="300" required name="timeout" value="'+(current?.timeout||15)+'"></label></div><label>Command<select name="command">'+options(appCommands,commandId)+'</select></label><div id="test-steps"></div><div class="test-actions"><button type="button" id="append-step">+ Observation</button>'+(current?'<button type="button" id="delete-trip">'+icon('trash')+' Delete test</button>':'')+'</div>';
  async function save(body){
    const result=await api('ground/tests',{...body,id:current?.id,revision:originalRevision,target});
    state.testPlans=result;
    state.selectedTests??={};
    if(body.plan){
      state.groundApp='';
      state.groundSelection=body.plan.command;
      state.groundQuery='';
      state.selectedTests[body.plan.command]=result.id;
    }else delete state.selectedTests[commandId];
    refresh();
  }
  dialog(current?'Edit round-trip test':'New round-trip test',form,async values=>{
    read();
    await save({plan:{name:values.testName,command:values.command,timeout:Number(values.timeout),steps}});
  },'Save test');
  const owner=document.querySelector('#dialog'), list=owner.querySelector('#test-steps');
  function read() {
    for(const row of list.children){
      const step=steps[Number(row.dataset.stepIndex)];
      for(const control of row.querySelectorAll('[data-step-key]')){
        const key=control.dataset.stepKey;
        if(key==='event_id')step[key]=control.value===''?null:Number(control.value);
        else if(key==='value' && step.op==='equals'){
          const def=catalog.packets.find(p=>p.id===step.packet)?.fields?.find(f=>f.name===step.field);
          if(def?.format==='s'||def?.format==='raw')step[key]=control.value;
          else{try{step[key]=JSON.parse(control.value);}catch{step[key]=control.value;}}
        }else step[key]=control.value;
      }
    }
  }
  function paint(){
    list.innerHTML=steps.map(formStep).join('');
    owner.querySelector('#append-step').disabled=steps.length>=16;
  }
  list.addEventListener('change',event=>{
    const key=event.target.dataset.stepKey;
    if(!['kind','packet','op'].includes(key))return;
    const index=Number(event.target.closest('fieldset').dataset.stepIndex);
    read();
    if(key==='kind')steps[index]=steps[index].kind==='event'?defaultEvent():{kind:'packet',packet:catalog.packets[0]?.id||'',op:'received'};
    paint();
    list.children[index].querySelector('[data-step-key="'+key+'"]')?.focus();
  });
  list.addEventListener('click',event=>{
    const button=event.target.closest('[data-step-op]');if(!button)return;
    const i=Number(button.closest('fieldset').dataset.stepIndex);
    read();
    if(button.dataset.stepOp==='remove')steps.splice(i,1);
    else {const other=button.dataset.stepOp==='up'?i-1:i+1;[steps[i],steps[other]]=[steps[other],steps[i]];}
    paint();
  });
  owner.querySelector('#append-step').onclick=()=>{read();steps.push(defaultEvent());paint();list.lastElementChild.querySelector('select').focus();};
  if(current)owner.querySelector('#delete-trip').onclick=async()=>{
    try{await save({delete:true});owner.close();}catch(error){owner.querySelector('#dialog-error').textContent=error.message;}
  };
  paint();
}
