// xterm paints its own canvas. Supply resolved tokens on open and theme change.
function terminalAppearance(reducedMotion) {
 const style=getComputedStyle(document.documentElement);
 const token=name=>style.getPropertyValue('--fs-'+name).trim();
 const theme={
  background:token('terminal-bg'), foreground:token('terminal-output'), cursor:token('accent'),
  cursorAccent:token('on-accent'), selectionBackground:token('console-selection'),
  black:token('bg'), brightBlack:token('muted'), white:token('text'), brightWhite:token('text'),
 };
 for(const [color,name] of Object.entries({red:'danger',green:'success',yellow:'accent',blue:'blue',magenta:'code',cyan:'cyan'})){
  theme[color]=token(name);
  theme['bright'+color[0].toUpperCase()+color.slice(1)]=theme[color];
 }
 return {theme,fontFamily:token('mono'),fontSize:parseFloat(token('label')),cursorBlink:!reducedMotion.matches};
}

// Each shell keeps its own ANSI screen and output cursor when switching tabs.
export function mountShells({api,onError,onExit}) {
 const host=document.querySelector('#shell-terminal'), shells=new Map();
 const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
 let active=null;
 function updateAppearance(){
  const appearance=terminalAppearance(reducedMotion);
  for(const shell of shells.values()){
   shell.term.options={...appearance,cursorBlink:!shell.ended&&appearance.cursorBlink};
  }
 }
 new MutationObserver(updateAppearance).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
 reducedMotion.addEventListener('change',updateAppearance);
 function fit(shell){
  if(!shell||host.hidden||!host.clientWidth||!host.clientHeight)return;
  shell.fit.fit();
 }
 new ResizeObserver(()=>fit(shells.get(active))).observe(host);
 function select(job){
  host.hidden=!job;
  active=job?.id||null;
  for(const [id,shell] of shells)shell.element.hidden=id!==active;
  if(!job)return;
  if(!shells.has(job.id)){
   const element=document.createElement('div');element.className='shell-screen';host.append(element);
   const term=new window.Terminal({
    ...terminalAppearance(reducedMotion),fontWeight:'400',fontWeightBold:'600',lineHeight:1.7,
    minimumContrastRatio:4.5,screenReaderMode:true,scrollback:5000,allowProposedApi:false
   });
   const fitAddon=new window.FitAddon.FitAddon();term.loadAddon(fitAddon);term.open(element);
   const shell={element,term,fit:fitAddon,cursor:0,ended:false,queue:Promise.resolve()};shells.set(job.id,shell);
   term.onData(data=>{shell.queue=shell.queue.then(()=>api('terminal/input',{id:job.id,data})).catch(onError);});
   term.onResize(({rows,cols})=>{api('terminal/resize',{id:job.id,rows,cols}).catch(onError);});
   term.attachCustomKeyEventHandler(event=>!(event.ctrlKey&&event.code==='Backquote'));
  }
  const shell=shells.get(active);shell.element.hidden=false;
  requestAnimationFrame(()=>fit(shell));
  readOutput();
 }
 async function readOutput(){
  const id=active,shell=shells.get(id);
  if (!shell || shell.ended || shell.reading || host.hidden) return;
  shell.reading=true;
  try {
   while (active===id && !shell.ended && !host.hidden && !document.hidden) {
    const result=await api('terminal/read',{id,cursor:shell.cursor,wait:true});
    if(result.truncated)shell.term.writeln('\r\n[Older output exceeded the terminal buffer]\r\n');
    if(result.data)await new Promise(resolve=>shell.term.write(Uint8Array.from(atob(result.data),c=>c.charCodeAt(0)),resolve));
    shell.cursor=result.cursor;
    if(result.exited&&!result.data){
     shell.ended=true;
     shell.term.options.disableStdin=true;
     shell.term.options.cursorBlink=false;
     if(!onExit?.(id,result.exit_code))shell.term.writeln('\r\n[Shell exited]');
    }
   }
  } catch(error){onError(error);}
  finally{shell.reading=false;}
 }
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)readOutput();});
 return {select,focus:()=>shells.get(active)?.term.focus(),dispose:id=>{const shell=shells.get(id);if(shell){shell.term.dispose();shell.element.remove();shells.delete(id);}if(active===id)active=null;}};
}
