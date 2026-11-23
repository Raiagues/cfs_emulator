// Add presentation to actual process lines only. Text remains selectable/copyable;
// never interpret terminal output as markup or a verdict on the whole operation.
export function terminalOutputText(value) {
 return String(value).replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '');
}
const escapeHTML = value => value.replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function lineTone(line) {
 if (/^(?:\$ |[\w.-]+@[\w.-]+:[^\n]*[$#] )/.test(line)) return 'command';
 if (/(?:^|:\s)(?:fatal error|error|FAILED|CMake Error)(?:[:\s]|$)/i.test(line)) return 'error';
 if (/(?:^|:\s)(?:warning|CMake Warning)(?:[:\s]|$)/i.test(line)) return 'warning';
 if (/^\s*(?:\[\s*\d+%\] )?Built target\s/.test(line) || /^Build ready:/.test(line)) return 'success';
 if (/^-- (?:Configuring|Generating|Build files|Installing|Up-to-date)/.test(line)) return 'dim';
 if (/^(?:EVS Port|CFE_EVS)/.test(line)) return 'event';
 return '';
}
export function terminalOutputHTML(value) {
 return terminalOutputText(value).split('\n').map(line => {
  const tone = lineTone(line), text = escapeHTML(line);
  return tone ? `<span class="terminal-line-${tone}">${text}</span>` : text;
 }).join('\n');
}
