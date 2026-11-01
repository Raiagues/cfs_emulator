import {icon} from './ui.js';

// Native menus ignore most of the workbench theme. Keep these small lists
// keyboard accessible and populate them only from validated backend profiles.
export function mountSelector(id, onChange, esc) {
 const trigger=document.getElementById(id),menu=document.getElementById(id+'-options');
 let options=[],value='';
 const close=()=>{menu.hidden=true;trigger.setAttribute('aria-expanded','false');};
 function open(){
  if(trigger.disabled)return;
  document.querySelectorAll('.profile-menu:not([hidden])').forEach(other=>{
   other.hidden=true;document.querySelector(`[aria-controls="${other.id}"]`)?.setAttribute('aria-expanded','false');
  });
  menu.hidden=false;trigger.setAttribute('aria-expanded','true');
  (menu.querySelector('[aria-selected=true]')||menu.querySelector('button'))?.focus();
 }
 trigger.addEventListener('click',()=>menu.hidden?open():close());
 trigger.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();open();}});
 menu.addEventListener('click',event=>{
  const option=event.target.closest('[role=option]');if(!option)return;
  close();trigger.focus();onChange(option.dataset.value);
 });
 menu.addEventListener('keydown',event=>{
  const items=[...menu.querySelectorAll('[role=option]')],current=items.indexOf(document.activeElement);
  const index={ArrowDown:(current+1)%items.length,ArrowUp:(current-1+items.length)%items.length,Home:0,End:items.length-1}[event.key];
  if(index!==undefined){event.preventDefault();items[index]?.focus();}
  if(['Enter',' '].includes(event.key)){event.preventDefault();items[current]?.click();}
  if(event.key==='Escape'){event.preventDefault();close();trigger.focus();}
  if(event.key==='Tab')close();
 });
 document.addEventListener('click',event=>{if(!trigger.parentElement.contains(event.target))close();});
 return {update(next,selected,disabled){
  trigger.disabled=disabled;
  if(disabled)close();
  if(value===selected&&JSON.stringify(options)===JSON.stringify(next))return;
  options=next;value=selected;
  const label=options.find(option=>option.value===value)?.label||'Unavailable';
  trigger.querySelector('.profile-value').textContent=label;
  trigger.dataset.value=value;
  menu.innerHTML=options.map(option=>`<button type="button" role="option" tabindex="-1" data-value="${esc(option.value)}" aria-selected="${option.value===value}"><span>${esc(option.label)}</span>${icon('check')}</button>`).join('');
 }};
}
