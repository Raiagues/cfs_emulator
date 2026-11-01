// Each shell keeps its own ANSI screen and output cursor when switching tabs.
export function mountShells({api,onError}) {
 const host=document.querySelector('#shell-terminal'), shells=new Map();
 let active=null;
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
   const term=new window.Terminal({cursorBlink:true,fontFamily:'"DejaVu Sans Mono", monospace',fontSize:12,lineHeight:1.35,scrollback:5000,theme:{background:'#191c22',foreground:'#c2ccd5',cursor:'#c4ac8d',selectionBackground:'#59616d77'},allowProposedApi:false});
   const fitAddon=new window.FitAddon.FitAddon();term.loadAddon(fitAddon);term.open(element);
   const shell={element,term,fit:fitAddon,cursor:0,ended:false,queue:Promise.resolve()};shells.set(job.id,shell);
   term.onData(data=>{shell.queue=shell.queue.then(()=>api('terminal/input',{id:job.id,data})).catch(onError);});
   term.onResize(({rows,cols})=>{api('terminal/resize',{id:job.id,rows,cols}).catch(onError);});
   term.attachCustomKeyEventHandler(event=>!(event.ctrlKey&&event.code==='Backquote'));
  }
  const shell=shells.get(active);shell.element.hidden=false;
  requestAnimationFrame(()=>fit(shell));
 }
 async function poll(){
  const id=active,shell=shells.get(id);
  if(shell&&!shell.ended&&!host.hidden&&!document.hidden){
   try{
    const result=await api('terminal/read',{id,cursor:shell.cursor});
    if(result.truncated)shell.term.writeln('\r\n[Older output exceeded the terminal buffer]\r\n');
    if(result.data)await new Promise(resolve=>shell.term.write(Uint8Array.from(atob(result.data),c=>c.charCodeAt(0)),resolve));
    shell.cursor=result.cursor;
    if(result.exited&&!result.data){shell.ended=true;shell.term.writeln('\r\n[Shell exited]');}
   }catch(error){onError(error);await new Promise(resolve=>setTimeout(resolve,2000));}
  }
  setTimeout(poll,120);
 }
 poll();
 return {select,focus:()=>shells.get(active)?.term.focus(),dispose:id=>{const shell=shells.get(id);if(shell){shell.term.dispose();shell.element.remove();shells.delete(id);}if(active===id)active=null;}};
}
