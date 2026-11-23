import {escapeHtml as esc} from './dom.js';

// Selection is navigation; only supplied evidence can complete a step.
export function renderActivityProgress({steps, selected=0, attribute='data-activity-step', next='', actions=''}) {
  return `<div class="activity-progress"><nav aria-label="Activity progress">${steps.map((step,i)=>{
    const done=!!step.done,active=i===selected;
    return `${i?`<span class="activity-connector" data-done="${!!steps[i-1].done}" aria-hidden="true"></span>`:''}<button type="button" ${attribute}="${i}" data-state="${done?'done':active?'active':'pending'}" ${active?'aria-current="step"':''} ${step.disabled?'disabled':''} title="${esc(step.title||step.label)}"><span class="activity-circle">${done?'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3 8 3 3 7-7"/></svg>':i+1}</span><span>${esc(step.label)}</span></button>`;
  }).join('')}</nav>${next||actions?`<div class="activity-actions">${actions}${next}</div>`:''}</div>`;
}
