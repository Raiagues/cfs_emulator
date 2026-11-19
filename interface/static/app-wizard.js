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

const tick = '<svg class="fs-tick" viewBox="0 0 16 16" aria-label="Written"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';

export function busDiagram(workspace, name, saved, esc, mids={}) {
  const enabled=new Set(workspace.mission.enabled);
  const nodes=names=>names.filter(n=>enabled.has(n)).map(n=>'<code>'+esc(n)+'</code>').join('');
  const addresses=Object.entries(mids).map(([key,value])=>
    '<code>'+esc(key)+' · 0x'+Number(value).toString(16).toUpperCase()+'</code>').join('');
  return '<figure class="app-bus-picture"><figcaption>Where it lives</figcaption>'+
    '<div class="bus-drawing"><div class="bus-top">'+nodes(['ci_lab','to_lab'])+
    '<code class="app-slot '+(saved?'written':'')+'" data-app-slot>'+esc(name||'Your app')+'</code></div>'+
    '<div class="bus-rail"><span>Software Bus</span></div><div class="bus-bottom">'+nodes(['sch_lab','sample_app'])+
    '</div></div>'+(addresses?'<div class="wizard-mids">'+addresses+'</div>':'')+'</figure>';
}

export function openAppWizard({initialName='',workspace,api,esc,refresh,onCommand,requireSaved}) {
  if(document.querySelector('.app-wizard'))return;
  requireSaved();
  const revision=workspace.mission.source.hash, modal=document.createElement('dialog');
  modal.className='app-wizard';modal.setAttribute('aria-labelledby','wizard-title');
  let step=0,name=initialName,draft=null,settings={},written=null,busy=false;
  const titles=['What it is','Its files','Create'];
  const facts=[['cpu','Its own task'],['workflow','Talks through the bus'],['link','Has bus addresses']];
  const numbers=[['priority','Priority'],['stack_size','Stack · bytes'],['wakeup_hz','Wakeup · Hz'],['hk_hz','Housekeeping · Hz']];

  function files() {
    const records=Object.keys(draft.files).map(path=>({path,role:fileRole(path,name)}));
    function row({path,role}) {
      const mark=written?.has(path)?tick:'<i aria-hidden="true"></i>';
      const prefix='mission/apps/'+name+'/';
      return '<div class="wizard-file" title="'+esc(path)+'">'+mark+'<code>'+esc(path.startsWith(prefix)?path.slice(prefix.length):path)+'</code><small>'+role[1]+'</small></div>';
    }
    return groups.map((title,index)=>{
      const rows=records.filter(record=>record.role[0]===index);
      const main=rows.filter(record=>record.role[2]),more=rows.filter(record=>!record.role[2]);
      return '<section><h3>'+title+'</h3>'+main.map(row).join('')+(more.length?'<details class="wizard-more"><summary>'+more.length+
        ' more '+(more.length===1?'file':'files')+'</summary>'+more.map(row).join('')+'</details>':'')+'</section>';
    }).join('');
  }

  function render(){
    const steps=titles.map((title,i)=>{
      const done=i<step || !!written;
      return '<li '+(i===step?'aria-current="step"':'')+' class="'+(done?'done':'')+'"><b>'+ (done?tick:(i+1))+'</b>'+title+'</li>';
    }).join('');
    const info='<div class="wizard-intro"><div class="wizard-facts">'+facts.map(([glyph,title])=>
      '<span><i>'+icon(glyph)+'</i>'+title+'</span>').join('')+'</div><label>Name<input name="app_name" autocomplete="off" spellcheck="false" required pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*" maxlength="19" placeholder="orbit_demo" value="'+esc(name)+'"></label></div>';
    const options=step===1?'<details class="wizard-settings"><summary>'+icon('settings')+'Settings</summary><div>'+
      numbers.map(([n,t])=>'<label>'+t+'<input required type="number" name="'+n+'" min="'+(n.endsWith('_hz')?'0.000001':'0')+'" step="'+(n.endsWith('_hz')?'any':'1')+'" value="'+esc(settings[n])+'"></label>').join('')+'</div></details>':'';
    const review=draft?'<div class="wizard-review"><div class="wizard-files">'+files()+'</div>'+options+'<div class="wizard-records"><code>'+
      esc(draft.preview.startup.record)+'</code><code>'+esc(draft.preview.build.statement)+'</code></div></div>':'';
    modal.innerHTML='<form><header><h2 id="wizard-title">New app</h2><ol class="wizard-steps">'+steps+'</ol>'+
      '<button type="button" data-close aria-label="Close" '+(busy?'disabled':'')+'>'+icon('close')+'</button></header>'+
      '<div class="wizard-content">'+busDiagram(workspace,name,!!written,esc,written?draft.preview.mids:{})+(step===0?info:review)+'</div>'+
      '<footer><output role="status">'+(written?tick+' '+esc(name)+' on the bus':'')+'</output>'+
      (step===1?'<button type="button" data-back>Back</button>':'')+'<button type="submit" class="primary" '+(busy?'disabled':'')+'>'+
      (written?'Next → add a command':step===2?'Creating…':step===1?'Create '+esc(name):'See its files →')+'</button></footer></form>';
  }

  modal.oninput=e=>{if(e.target.name==='app_name'){name=e.target.value;modal.querySelector('[data-app-slot]').textContent=name||'Your app';}};
  modal.onclick=e=>{
    if(busy)return;
    if(e.target.closest('[data-close]'))modal.close();
    if(e.target.closest('[data-back]')){step=0;render();modal.querySelector('input').focus();}
  };
  modal.oncancel=e=>{if(busy)e.preventDefault();};
  modal.onclose=()=>modal.remove();
  modal.onsubmit=async e=>{
    e.preventDefault();if(busy)return;
    if(written){modal.close();onCommand(name);return;}
    const form=e.target;
    busy=true;form.querySelector('[type=submit]').disabled=true;
    try {
      requireSaved();
      if(step===0){
        draft=await api('mission/draft',{kind:'app',mode:'create',name,settings,expected_hash:revision});
        settings={...draft.draft.settings};step=1;
      }else{
        const proposed=Object.fromEntries(Object.keys(settings).map(k=>[k,Number(form.elements[k].value)]));
        if(Object.keys(proposed).some(k=>proposed[k]!==settings[k])){
          draft=await api('mission/draft',{kind:'app',mode:'create',name,settings:proposed,expected_hash:revision});
          settings={...draft.draft.settings};
        }
        step=2;render();
        const result=await api('mission/save',{...draft.draft,expected_hash:draft.expected_hash,plan_hash:draft.plan_hash});
        written=new Set(result.changed);
        await refresh(result.changed,result.deleted);
      }
      busy=false;render();
    }catch(error){
      busy=false;if(step===2&&!written)step=1;
      render();const output=modal.querySelector('output');output.setAttribute('role','alert');output.textContent=error.message;
    }
  };
  document.body.append(modal);render();modal.showModal();modal.querySelector('input').focus();
}
