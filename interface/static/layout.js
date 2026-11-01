/** Resizable workspace boundaries. Only local layout preferences are persisted. */
export function mountLayout() {
  const $ = selector => document.querySelector(selector);
  const explorer = $('.explorer'), editor = $('.editor'), terminal = $('.terminal');
  const panes = $('.panes'), work = $('.workarea');
  const defaults = {explorer:220, editor:.48, terminal:240};
  let sizes = {...defaults};
  try { const saved=JSON.parse(localStorage.getItem('flight-studio-layout')||'{}');for(const key of Object.keys(defaults))if(Number.isFinite(saved[key]))sizes[key]=saved[key]; } catch {}
  const clamp = (value,min,max) => Math.max(min,Math.min(value,Math.max(min,max)));
  function apply() {
    const mobile=window.innerWidth<=760;
    sizes.explorer=clamp(sizes.explorer,150,Math.min(520,window.innerWidth*.4));
    explorer.style.width=sizes.explorer+'px';
    const available=mobile?panes.clientHeight:panes.clientWidth;
    const minimum=mobile?140:220;
    sizes.editor=clamp(sizes.editor,minimum/Math.max(1,available),1-minimum/Math.max(1,available));
    editor.style.width=mobile?'100%':(sizes.editor*100)+'%';
    editor.style.height=mobile?(sizes.editor*100)+'%':'';
    terminal.style.height=clamp(sizes.terminal,100,work.clientHeight-160)+'px';
    const split=$('#editor-splitter');split.setAttribute('aria-orientation',mobile?'horizontal':'vertical');
    for(const [key,id] of [['explorer','explorer-splitter'],['editor','editor-splitter'],['terminal','terminal-splitter']]) {
      const value=key==='editor'?Math.round(sizes.editor*100):Math.round(sizes[key]);
      $('#'+id).setAttribute('aria-valuenow',String(value));
    }
  }
  function persist(){try{localStorage.setItem('flight-studio-layout',JSON.stringify(sizes));}catch{}}
  function update(key,event){
    if(key==='explorer')sizes.explorer=event.clientX-explorer.getBoundingClientRect().left;
    else if(key==='terminal')sizes.terminal=work.getBoundingClientRect().bottom-event.clientY;
    else {const rect=panes.getBoundingClientRect(),position=window.innerWidth<=760?(event.clientY-rect.top)/rect.height:(event.clientX-rect.left)/rect.width;sizes.editor=document.body.classList.contains('simulation-mode')?1-position:position;}
    apply();
  }
  for(const key of Object.keys(defaults)) {
    const handle=$('#'+key+'-splitter');
    handle.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;
      event.preventDefault();handle.setPointerCapture(event.pointerId);handle.dataset.dragging='true';
      document.body.classList.add('resizing-panes');
    });
    handle.addEventListener('pointermove',event=>{if(handle.dataset.dragging)update(key,event);});
    const end=()=>{delete handle.dataset.dragging;document.body.classList.remove('resizing-panes');persist();};
    handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);handle.addEventListener('lostpointercapture',end);
    handle.addEventListener('dblclick',()=>{sizes[key]=defaults[key];apply();persist();});
    handle.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return;
      event.preventDefault();
      if(event.key==='Home')sizes[key]=defaults[key];
      else {let direction=['ArrowRight','ArrowDown'].includes(event.key)?1:-1;if(key==='terminal'||key==='editor'&&document.body.classList.contains('simulation-mode'))direction*=-1;sizes[key]+=direction*(key==='editor'?.025:20);}
      apply();persist();
    });
  }
  window.addEventListener('resize',apply);
  new ResizeObserver(()=>{if(!document.body.classList.contains('resizing-panes'))apply();}).observe(work);
  apply();
  return {apply};
}
