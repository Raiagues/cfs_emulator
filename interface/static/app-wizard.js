import {icon} from './ui.js';

const groups=['How it runs','What it understands','How others reach it','How cFS finds it'];
function fileRole(path, name) {
  const file=path.split('/').at(-1);
  if(path.includes('/unit-test/'))return [3,'Unit tests',false];
  if(file===name+'.c')return [0,'Main loop',true];
  if(/_eventids\.h$/.test(file))return [2,'Event numbers',true];
  if(/msgids|topicids/.test(file))return [2,'Bus addresses',file.startsWith('default_') && file.endsWith('_msgids.h')];
  if(/dispatch/.test(file))return [1,'Route messages',file===name+'_dispatch.c'];
  if(/fcncode/.test(file))return [1,'Command numbers',file===name+'_fcncodes.h'];
  if(/cmds/.test(file))return [1,'Command handlers',file===name+'_cmds.c'];
  if(/msg|payload/.test(file))return [1,'Packet layout',file.endsWith('_msgstruct.h') && file.startsWith('default_')];
  if(/wakeup|schedule/.test(file))return [0,'Task schedule',false];
  if(/\.[ch]$/.test(file))return [0,file.endsWith('.c')?'Task implementation':'Task interface',false];
  if(file.endsWith('.scr'))return [3,'Startup record',true];
  if(/cmake/i.test(file))return [3,'Build inputs',file==='CMakeLists.txt'];
  return [3,file.endsWith('.json')?'Mission settings':'Project files',false];
}

export function busDiagram(workspace, name, saved, esc) {
  const enabled=new Set(workspace.mission.enabled);
  const peers=['ci_lab','to_lab','sch_lab','sample_app'].filter(n=>enabled.has(n));
  const node=n=>'<code>'+esc(n)+'</code>';
  return '<div class="app-bus-picture"><div>'+peers.slice(0,2).map(node).join('')+'</div><strong>'+icon('workflow')+
    'Software Bus</strong><div>'+peers.slice(2).map(node).join('')+'<code class="app-slot '+(saved?'written':'')+'" data-app-slot>'+esc(name||'Your app')+'</code></div></div>';
}

export function openAppWizard({initialName='',workspace,api,esc,refresh,onCommand,requireSaved}) {
  if(document.querySelector('.app-wizard'))return;
  requireSaved();
  const revision=workspace.mission.source.hash, modal=document.createElement('dialog');
  modal.className='app-wizard';modal.setAttribute('aria-labelledby','wizard-title');
  let step=0,name=initialName,draft=null,settings={},written=null,busy=false;
  const titles=['What it is','Its files','Create'];
  function files() {
    const records=Object.keys(draft.files).map(path=>({path,role:fileRole(path,name)}));
    function row({path,role}) {
      const mark=written?.has(path)?'<svg class="fs-tick" viewBox="0 0 16 16" aria-label="Written"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>':icon('files');
      return '<div class="wizard-file" title="'+esc(path)+'">'+mark+'<code>'+esc(path.split('/').at(-1))+'</code><small>'+role[1]+'</small></div>';
    }
    return groups.map((title,index)=>{
      const rows=records.filter(record=>record.role[0]===index);
      const main=rows.filter(record=>record.role[2]),more=rows.filter(record=>!record.role[2]);
      return '<section><h3>'+title+'</h3>'+main.map(row).join('')+(more.length?'<details class="wizard-more"><summary>'+more.length+
        ' more '+(more.length===1?'file':'files')+'</summary>'+more.map(row).join('')+'</details>':'')+'</section>';
    }).join('');
  }
  function render(){
    const facts=[['clock','Its own task'],['workflow','Talks through the bus'],['link','Has bus addresses']];
    const numbers=[['priority','Priority'],['stack_size','Stack · bytes'],['wakeup_hz','Wakeup · Hz'],['hk_hz','Housekeeping · Hz']];
    modal.innerHTML='<form><header><div><small>Mission app</small><h2 id="wizard-title">'+titles[step]+'</h2></div><button type="button" data-close aria-label="Close">'+icon('close')+'</button></header>'+
      '<ol class="wizard-steps">'+titles.map((t,i)=>'<li '+(i===step?'aria-current="step"':'')+'>'+String(i+1)+' · '+t+'</li>').join('')+'</ol><div class="wizard-content">'+
      (step===0?busDiagram(workspace,name,false,esc)+'<div class="wizard-facts">'+facts.map(([g,t])=>'<span>'+icon(g)+t+'</span>').join('')+'</div>'+
       '<label>App name<input name="app_name" autocomplete="off" required pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*" maxlength="19" placeholder="orbit_demo" value="'+esc(name)+'"></label>':
       (step===2?busDiagram(workspace,name,!!written,esc):'')+
       '<div class="wizard-files">'+files()+'</div>'+
       (step===1?'<details class="wizard-settings"><summary>'+icon('settings')+'Settings</summary><div>'+
         numbers.map(([n,t])=>'<label>'+t+'<input required type="number" name="'+n+'" min="'+(n.endsWith('_hz')?'0.000001':'0')+'" step="'+(n.endsWith('_hz')?'any':'1')+'" value="'+esc(settings[n])+'"></label>').join('')+'</div></details>':'')+
       '<div class="wizard-records"><code>'+esc(draft.preview.startup.record)+'</code><code>'+esc(draft.preview.build.statement)+'</code></div>'+
       (written?'<div class="wizard-mids">'+Object.entries(draft.preview.mids).map(([k,v])=>'<code>'+esc(k)+' · 0x'+Number(v).toString(16).toUpperCase()+'</code>').join('')+'</div>':''))+
      '</div><footer><output role="alert"></output>'+(step&&!written?'<button type="button" data-back>Back</button>':'')+
      '<button type="submit" class="primary">'+(written?'Next → add a command':step===2?'Create app':'Next')+'</button></footer></form>';
    if(step===0)modal.querySelector('input').focus();
  }
  modal.oninput=e=>{if(e.target.name==='app_name'){name=e.target.value;modal.querySelector('[data-app-slot]').textContent=name||'Your app';}};
  modal.onclick=e=>{
    if(busy)return;
    if(e.target.closest('[data-close]'))modal.close();
    if(e.target.closest('[data-back]')){step--;render();}
  };
  modal.oncancel=e=>{if(busy)e.preventDefault();};
  modal.onclose=()=>modal.remove();
  modal.onsubmit=async e=>{
    e.preventDefault();if(busy)return;
    if(written){modal.close();onCommand(name);return;}
    const form=e.target, output=form.querySelector('output');
    const controls=[...form.querySelectorAll('button,input')];for(const control of controls)control.disabled=true;
    output.textContent='';busy=true;
    try{
      requireSaved();
      if(step<2){
        if(step===1)settings=Object.fromEntries(Object.keys(settings).map(k=>[k,Number(form.elements[k].value)]));
        draft=await api('mission/draft',{kind:'app',mode:'create',name,settings,expected_hash:revision});
        settings={...draft.draft.settings};step++;
      }else{
        const result=await api('mission/save',{...draft.draft,expected_hash:draft.expected_hash,plan_hash:draft.plan_hash});
        written=new Set(result.changed);
        await refresh(result.changed,result.deleted);
      }
      render();
    }catch(error){if(written)render();modal.querySelector('output').textContent=error.message;}
    finally{busy=false;for(const control of controls)control.disabled=false;}
  };
  document.body.append(modal);render();modal.showModal();modal.querySelector('input')?.focus();
}
