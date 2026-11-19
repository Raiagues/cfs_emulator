// The browser owns only the replay cutoff. Each check belongs to a backend observation.
const stages = [
  ['target','Target','Choose where cFS will run'], ['boot','Boot','Start cFS for the first time'],
  ['event','Event','Send a first message and get an answer'], ['app','App','Create your own app'],
  ['command','Command','Teach your app a new command'], ['send','Send','Send your new command'],
  ['sensor','Sensor','Give your app sensor data'], ['test','Test','Check that everything works'],
  ['board','Board','Run it on the real board']
];
const area = {target:'setup',board:'board',boot:'boot',event:'ground',send:'ground',app:'architecture',
              command:'code',sensor:'simulation',test:'simulation'};
export function stepUrl(step) {
  if (step === 'target') return '/';
  if (step === 'board') return '/?target=physical';
  return '/studio#'+step;
}
const bar = document.querySelector('#flight-guide');
const tick = '<svg class="fs-tick" viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="m3 8 3 3 7-7"/></svg>';
let signature='', data, requestNumber=0, since=0, previousDone=[];
try {since=Number(localStorage.getItem('fs-journey-reset')) || 0;} catch {}
function render() {
  if (!bar) return;
  const done = stages.map(([id]) => Boolean(data?.steps[id]?.done && data.steps[id].observed_at > since));
  const count=done.filter(Boolean).length, next=stages.findIndex((_,i)=>!done[i]);
  const view=document.body.classList.contains('code-only')?'code':document.body.dataset.view||
    (new URLSearchParams(location.search).get('target')==='physical'?'board':'setup');
  const key=JSON.stringify([done,view]);if(key===signature)return;
  signature=key;
  const focus=bar.contains(document.activeElement)?document.activeElement.dataset.flight:null;
  document.body.dataset.journeyStep=stages[next]?.[0] || 'complete';
  bar.innerHTML='<strong>First flight <output>'+count+'/9</output></strong><div class="flight-stops">'+stages.map(([id,label,tip],i)=>
    (i ? '<span aria-hidden="true" class="flight-line'+(done[i-1] && done[i]?' complete':'')+'"></span>' : '')+
    '<a href="'+stepUrl(id)+'" data-flight="'+id+'" title="'+tip+'" aria-label="'+label+(done[i]?', complete':'')+'" '+(i===next?'aria-current="step" ':'')+
    'class="'+(done[i]?'done ':'')+(done[i] && !previousDone[i]?'confirmed':'')+'"><i>'+(done[i]?tick:i+1)+'</i><span>'+label+'</span></a>').join('')+
    '</div><div class="flight-guide-actions">'+(next>=0&&area[stages[next][0]]!==view?'<a class="flight-next" href="'+stepUrl(stages[next][0])+'">Next '+stages[next][1]+' →</a>':'')+
    '<button type="button" data-flight="reset" title="Start over" aria-label="Start over"><svg viewBox="0 0 24 24"><path d="M4 10a8 8 0 1 1 1 7M4 4v6h6"/></svg></button></div>';
  previousDone=done;
  if(focus)bar.querySelector('[data-flight="'+focus+'"]')?.focus({preventScroll:true});
}
export async function refreshJourney() {
  if(!bar)return;
  const request=++requestNumber;
  const selected=document.querySelector('#targets .target-option[aria-pressed=true],.target-switch button[aria-pressed=true]')?.dataset.target;
  try {
    const result=await fetch('/api/journey'+(selected?'?target='+encodeURIComponent(selected):''),{cache:'no-store'});
    if(!result.ok)return;
    const next=await result.json();if(request!==requestNumber)return;
    data=next;render();
  } catch { /* Keep the last confirmed evidence while the server reconnects. */ }
}
if(bar){
  bar.setAttribute('aria-label','First flight');
  bar.addEventListener('click',event=>{
    if(!event.target.closest('[data-flight="reset"]'))return;
    since=Date.now()/1000;
    try{localStorage.setItem('fs-journey-reset',String(since));}catch{}
    location.assign('/');
  });
  window.addEventListener('storage',e=>{if(e.key==='fs-journey-reset'){since=Number(e.newValue)||0;render();}});
  window.addEventListener('flight:updated',refreshJourney);
  new MutationObserver(render).observe(document.body,{attributes:true,attributeFilter:['data-view','class']});
  render();refreshJourney();
  setInterval(()=>{if(!document.hidden)refreshJourney();},3500);
}
