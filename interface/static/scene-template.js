// Bind the design's conditional scenes and repeated SVG/HTML elements in place.
// Keeping nodes alive lets transitions, focus and CSS animation clocks continue between ticks.
const binding = /{{\s*([\w.]+)\s*}}/g;

function value(scope, path) {
  return path.split('.').reduce((current, name) => current?.[name], scope);
}

function evaluate(template, scope) {
  return template.replace(binding, (_, path) => value(scope, path) ?? '');
}

function reference(element, attribute) {
  return element.getAttribute(attribute).slice(2, -2).trim();
}

function children(source, parent, before, action) {
  const updates = Array.from(source.childNodes, (node) => bind(node, parent, before, action));
  return (scope) => updates.forEach((update) => update(scope));
}

function region(source, parent, before, action) {
  const start = document.createComment('');
  const end = document.createComment('');
  parent.insertBefore(start, before);
  parent.insertBefore(end, before);
  const update = children(source, parent, end, action);
  return {
    update,
    moveBefore(node) {
      if (end.nextSibling === node) return;
      const range = document.createRange();
      range.setStartBefore(start);
      range.setEndAfter(end);
      parent.insertBefore(range.extractContents(), node);
    },
    start,
    remove() {
      const range = document.createRange();
      range.setStartBefore(start);
      range.setEndAfter(end);
      range.deleteContents();
    },
  };
}

function bind(source, parent, before, action) {
  if (source.nodeType === Node.TEXT_NODE) {
    const node = parent.insertBefore(source.cloneNode(), before);
    if (!source.data.includes('{{')) return () => {};
    return (scope) => {
      const text = evaluate(source.data, scope);
      if (node.data !== text) node.data = text;
    };
  }
  if (source.nodeType !== Node.ELEMENT_NODE) return () => {};
  const tag = source.localName;
  if (tag === 'sc-if') {
    const key = reference(source, 'value');
    const anchor = parent.insertBefore(document.createComment(key), before);
    let current;
    return (scope) => {
      if (value(scope, key)) {
        current ??= region(source, parent, anchor, action);
        current.update(scope);
      } else if (current) {
        current.remove();
        current = null;
      }
    };
  }
  if (tag === 'sc-for') {
    const key = reference(source, 'list');
    const name = source.getAttribute('as');
    const anchor = parent.insertBefore(document.createComment(key), before);
    const entries = new Map();
    return (scope) => {
      const items = value(scope, key) || [];
      const used = new Set();
      const ordered = [];
      items.forEach((item, index) => {
        let id = index;
        if (key.endsWith('.log') || key.endsWith('.chat')) {
          id = [item.time, item.arrow, item.t].join('|');
          while (used.has(id)) id += '|';
        }
        const entry = entries.get(id) ?? region(source, parent, anchor, action);
        ordered.push(entry);
        entries.set(id, entry);
        used.add(id);
        entry.update(Object.assign(Object.create(scope), { [name]: item }));
      });
      for (const [id, entry] of entries) {
        if (!used.has(id)) {
          entry.remove();
          entries.delete(id);
        }
      }
      let next = anchor;
      for (let i = ordered.length - 1; i >= 0; i--) {
        ordered[i].moveBefore(next);
        next = ordered[i].start;
      }
    };
  }
  const el = source.cloneNode(false);
  const attrs = [...source.attributes].filter((attribute) => attribute.value.includes('{{'));
  let scope;
  for (const { name, value: eventPath } of [...el.attributes]) {
    if (!name.startsWith('data-on-')) continue;
    const event = name.slice('data-on-'.length);
    el.removeAttribute(name);
    el.dataset.act = eventPath;
    const handler = (e) => {
      e.stopPropagation();
      action(value(scope, eventPath), e);
    };
    el.addEventListener(event, handler);
    if (event === 'click' && !['a', 'button', 'input', 'select'].includes(tag)) {
      el.setAttribute('role', 'button');
      el.setAttribute('tabindex', '0');
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handler(e);
        }
      });
    }
  }
  parent.insertBefore(el, before);
  const updateChildren = children(source, el, null, action);
  return (next) => {
    scope = next;
    for (const attr of attrs) {
      const output = evaluate(attr.value, scope);
      if (el.getAttribute(attr.name) !== output) el.setAttribute(attr.name, output);
    }
    updateChildren(scope);
  };
}

export function mountScene(template, parent, action) {
  return children(template.content, parent, null, action);
}
