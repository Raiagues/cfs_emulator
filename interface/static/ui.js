const icons = {
  'link':'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
  'table':'M3 3h18v18H3z M3 9h18 M9 9v12 M15 9v12 M3 15h18',
  'sidebar':'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z M9 3v18',
  'workflow':'M9 2h6v5H9z M2 17h6v5H2z M16 17h6v5h-6z M12 7v5 M5 17v-5h14v5',
  'circuit':'M4 3h16v18H4z M8 7h6v6H8z M10 3v4 M14 3v4 M4 9h4 M14 9h6 M10 13v4h6 M7 18h.1 M17 6h.1',
  'check':'m5 12 4 4L19 6',
  'power':'M12 2v10 M6 5a9 9 0 1 0 12 0',
  'wave':'M2 12h3c2 0 2-8 4-8s2 16 4 16 2-8 4-8h5',
  'build':'M14 3a6 6 0 0 0-7 7L2 15l7 7 5-5a6 6 0 0 0 7-7l-4 4-4-4 4-4z',
  'antenna':'M4.9 4.9a10 10 0 0 0 0 14.2 M7.7 7.7a6 6 0 0 0 0 8.6 M16.3 7.7a6 6 0 0 1 0 8.6 M19.1 4.9a10 10 0 0 1 0 14.2 M12 14l-3 8 M12 14l3 8 M10 19h4 M14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0',
  'chevron-down':'m6 9 6 6 6-6',
  'chevron-right':'m9 6 6 6-6 6',
  'code':'m8 6-6 6 6 6 M16 6l6 6-6 6 M14 3l-4 18',
  'cube':'m12 2 10 5v10l-10 5-10-5V7z M2 7l10 5 10-5 M12 12v10',
  'play':'m7 4 13 8-13 8z',
  'stop':'M6 6h12v12H6z',
  'files':'M8 3h11v15H8z M5 7H3v14h12v-1',
  'search':'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6',
  'terminal':'M3 4h18v16H3z m4 4 4 4-4 4 M14 16h3',
  'folder':'M3 5h6l2 3h10v12H3z',
  'plus':'M12 5v14 M5 12h14',
  'minus':'M5 12h14',
  'settings':'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 2h6l1 4 4 1 2 5-3 3v5l-5 2-3-3H6l-4-5 2-4V5z',
  'more':'M5 12h.1 M12 12h.1 M19 12h.1',
  'arrow-down':'M12 3v18 m-6-6 6 6 6-6',
  'close':'M5 5l14 14 M19 5 5 19',
  'cpu':'M6 6h12v12H6z M9 9h6v6H9z M9 3v3 M15 3v3 M9 18v3 M15 18v3 M3 9h3 M3 15h3 M18 9h3 M18 15h3',
  'expand':'M14 3h7v7 M21 3l-8 8 M10 21H3v-7 M3 21l8-8',
  'rotate':'M3 11a9 9 0 1 1 3 8 M3 5v6h6',
  'layers':'m12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5',
  'compass':'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 m4 6-3 7-7 3 3-7z',
  'thermometer':'M9 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0 M12 8v9 M18 6h3 M18 10h2',
  'arrow-up-right':'M6 18 18 6 M6 6h12v12'
};

export function icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[name] || icons.code}"/></svg>`
}


icons.monitor='M3 3h18v13H3z M12 16v5 M7 21h10';
icons.refresh=icons.rotate;
icons.trash='M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7';
function html(text){return String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function highlight(text,path='') {
  if (path.endsWith('.py')) return highlightPython(text)
  const pattern = /\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|^\s*#[a-zA-Z_]+|\b(?:void|float|double|int|char|bool|uint8_t|uint16_t|uint32_t|int32_t|size_t)\b|\b(?:static|const|let|function|new|throw|return|if|else|while|for|typedef|struct|true|false|null|NULL|sizeof|switch|case|break|continue)\b|\b\d+(?:\.\d+)?(?:[fFuUlL])?\b|\b[A-Z][A-Z_0-9]+\b|\b[a-zA-Z_]\w*(?=\s*\()/gm
  let output = ''
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    output += html(text.slice(cursor,match.index))
    const token = match[0]
    let type = 'function'
    if (token.startsWith('/*') || token.startsWith('//')) type = 'comment'
    else if (token.startsWith('"') || token.startsWith("'")) type = 'string'
    else if (token.trim().startsWith('#')) type = 'directive'
    else if (/^(void|float|double|int|char|bool|uint8_t|uint16_t|uint32_t|int32_t|size_t)$/.test(token)) type = 'type'
    else if (/^(static|const|let|function|new|throw|return|if|else|while|for|typedef|struct|true|false|null|NULL|sizeof|switch|case|break|continue)$/.test(token)) type = 'keyword'
    else if (/^\d/.test(token)) type = 'number'
    else if (/^[A-Z][A-Z_0-9]+$/.test(token)) type = 'constant'
    output += `<span class="token-${type}">${html(token)}</span>`
    cursor = match.index + token.length
  }
  return output + html(text.slice(cursor)) + '\n'
}

function highlightPython(text) {
  const tokens = /#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:def|return|import|from|as|if|elif|else|for|while|in|is|not|and|or|True|False|None|try|except|with|class|pass|raise|lambda)\b|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*(?=\s*\()/g
  let result = ''
  let cursor = 0
  for (const match of text.matchAll(tokens)) {
    const token = match[0]
    const type = token.startsWith('#') ? 'comment' : /^['"]/.test(token) ? 'string' : /^\d/.test(token) ? 'number' : /^(def|return|import|from|as|if|elif|else|for|while|in|is|not|and|or|True|False|None|try|except|with|class|pass|raise|lambda)$/.test(token) ? 'keyword' : 'function'
    result += html(text.slice(cursor,match.index))+'<span class="token-'+type+'">'+html(token)+'</span>'
    cursor = match.index+token.length
  }
  return result+html(text.slice(cursor))+'\n'
}

