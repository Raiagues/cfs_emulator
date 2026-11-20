// Keep live SVG strokes, focused buttons and scrolling console nodes across polls.
export function updateNode(current,next){
  if (current.nodeType === Node.ELEMENT_NODE && next.nodeType === Node.ELEMENT_NODE) {
    if (current.classList.contains('fs-coach')) next.classList.add('fs-coach');
    if (current.hasAttribute('data-motion-layer') && next.hasAttribute('data-motion-layer')) return;
    if (current.localName === 'details' && current.open) next.open = true;
  }
  if(current.isEqualNode(next))return;
  if(current.nodeName!==next.nodeName || current.getAttribute?.('data-scene')!==next.getAttribute?.('data-scene')){
    current.replaceWith(next);
    return;
  }
  if(current.nodeType===Node.TEXT_NODE){current.nodeValue=next.nodeValue;return;}
  for(const attr of Array.from(current.attributes)){
    if(!next.hasAttribute(attr.name))current.removeAttribute(attr.name);
  }
  for(const attr of next.attributes){
    if(current.getAttribute(attr.name)!==attr.value)current.setAttribute(attr.name,attr.value);
  }
  const children=Array.from(next.childNodes);
  children.forEach((child,i)=>{
    if(current.childNodes[i])updateNode(current.childNodes[i],child);
    else current.append(child);
  });
  while(current.childNodes.length>children.length)current.lastChild.remove();
}

export function paint(container, html) {
  const template = document.createElement('template');
  template.innerHTML = html.trim();
  const next = template.content.firstElementChild;
  if (container.firstElementChild) updateNode(container.firstElementChild, next);
  else container.append(next);
}

export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
