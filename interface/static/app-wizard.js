import {guide} from './coach.js';
import {paint} from './dom.js';
import {icon} from './ui.js';

const settingsFields = [['priority','Priority'],['stack_size','Stack · bytes'],['wakeup_hz','Wakeup · Hz'],['hk_hz','Housekeeping · Hz']];
const tick = '<svg class="fs-tick fs-draw" viewBox="0 0 16 16" aria-label="Written"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';

function selectedFiles(files, name) {
  const root = 'mission/apps/'+name+'/';
  return [
    ['CMakeLists.txt','Build this app'],
    ['fsw/src/'+name+'.c','Main flight loop'],
    ['config/default_'+name+'_msgstruct.h','Flight message definitions'],
    ['fsw/inc/'+name+'_fcncodes.h','Command function codes']
  ].filter(([path])=>Object.hasOwn(files,root+path)).map(([path,purpose])=>({path:root+path,purpose}));
}

export function openAppWizard({initialName='',workspace,api,esc,sourcePath,refresh,onClose,requireSaved}) {
  if(document.querySelector('.app-wizard[open]'))return;
  requireSaved();
  const modal=document.createElement('dialog');
  modal.className='app-wizard';modal.setAttribute('aria-labelledby','wizard-title');
  let name=initialName, draft, settings={}, written, error='', busy=false, editingName = true;
  const valid=()=>/^[a-z][a-z0-9]*(_[a-z0-9]+)*$/.test(name) && name.length<=19;
  const field=()=>modal.querySelector('[name=app_name]');
  function coach() {
    const submit=modal.querySelector('[type=submit]');
    if(submit)submit.disabled=busy || editingName && !valid();
    guide(busy ? null : editingName && (!valid() || error) ? field() : submit);
  }
  function files(){
    const important=selectedFiles(draft.files,name), other=Object.keys(draft.files).filter(path=>!important.some(f=>f.path===path));
    const item=(path,purpose,index)=>`<div class="wizard-file ${written?'fs-pop':'fs-in'}" data-scene="${written?'saved':'preview'}-${esc(path)}"
      style="animation-delay:${index*.09}s">${written?.has(path)?tick:icon('files')}<code>${esc(path.split('/').at(-1))}</code><small>${esc(purpose)}</small></div>`;
    return '<div class="wizard-files">'+important.map((f,i)=>item(f.path,f.purpose,i)).join('')+
      (other.length?'<details class="wizard-more"><summary>and '+other.length+' more</summary>'+other.map(path=>'<code>'+esc(sourcePath(path))+'</code>').join('')+'</details>':'')+'</div>';
  }
  function render() {
    const folder=sourcePath('mission/apps/'+(name || '…')+'/');
    const nameStep=`<label class="wizard-name">Name<input name="app_name" autocomplete="off" spellcheck="false"
      placeholder="orbit_demo" value="${esc(name)}"><small data-name-error>${name&&!valid()?'Use snake_case, up to 19 characters.':''}</small></label><code data-folder>${esc(folder)}</code>`;
    const review=draft && !editingName?`${files()}<div class="wizard-records ${written?'fs-pop':''}">
      <span>Build <code>${esc(draft.preview.build.module)}</code></span><span>Startup <code>${esc(draft.preview.entry_point)}</code>
      · priority ${esc(settings.priority)} · ${esc(settings.stack_size)} B</span></div>
      <details class="wizard-settings"><summary>Settings</summary><div>${settingsFields.map(([key,label])=>
        `<label>${label}<input type="number" name="${key}" value="${esc(settings[key])}" step="${key.endsWith('_hz')?'any':'1'}" required></label>`).join('')}</div></details>`:'';
    paint(modal,`<form novalidate><header><h2 id="wizard-title">New app</h2><ol class="wizard-steps"><li aria-current="${editingName?'step':'false'}">Name</li><li aria-current="${!editingName?'step':'false'}">Its files</li></ol>
      <button type="button" data-close aria-label="Close" ${busy?'disabled':''}>${icon('close')}</button></header>
      <div class="wizard-content wizard-step" data-scene="${editingName?'name':'files'}">${editingName?nameStep:review}</div>
      <footer><output role="alert">${esc(error)}</output>${editingName?'':'<button type="button" data-back>Back</button>'}
      <button type="submit" class="primary">${editingName?'See its files':'Create '+esc(name)}</button></footer></form>`);
    coach();
  }
  modal.oninput=e=>{
    if(e.target.name!=='app_name')return;
    name=e.target.value;error='';render();
  };
  modal.onclick=e=>{
    if(busy)return;
    if(e.target.closest('[data-close]'))modal.close();
    if(e.target.closest('[data-back]')){editingName=true;error='';render();field().focus();}
  };
  modal.oncancel=e=>{if(busy)e.preventDefault();};
  modal.onclose=()=>{modal.remove();onClose?.();};
  modal.onsubmit=async e=>{
    e.preventDefault();if(busy || !valid())return;
    busy=true;error='';coach();
    try{
      requireSaved();
      const plan=parameters=>api('mission/draft',{kind:'app',mode:'create',name,settings:parameters,expected_hash:workspace.mission.source.hash});
      if(editingName){
        draft=await plan(settings);
        settings={...draft.draft.settings};editingName=false;
      }else{
        const inputs=e.target.elements;
        const proposed=Object.fromEntries(settingsFields.map(([key])=>[key,Number(inputs[key].value)]));
        if(Object.keys(proposed).some(k=>proposed[k]!==settings[k])){draft=await plan(proposed);settings={...draft.draft.settings};}
        const result=await api('mission/save',{...draft.draft,expected_hash:draft.expected_hash,plan_hash:draft.plan_hash});
        written=new Set(result.changed);render();
        const animations=modal.querySelector('.wizard-files').getAnimations({subtree:true});
        await Promise.all([refresh(result.changed,result.deleted),...animations.map(animation=>animation.finished)]);
        modal.close();return;
      }
    }catch(e){error=e.message;}
    finally{busy=false;if(modal.open)render();}
  };
  document.body.append(modal);modal.showModal();render();field().focus();
  return modal;
}
