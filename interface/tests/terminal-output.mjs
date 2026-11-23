import {test} from 'node:test';
import assert from 'node:assert/strict';
import {terminalOutputHTML, terminalOutputText} from '../static/terminal-output.js';

test('process output is escaped before adding presentation', () => {
 const text = 'src/demo.c:7: error: <img src=x onerror="alert(1)"> & \'value\'';
 assert.equal(terminalOutputHTML(text), '<span class="terminal-line-error">src/demo.c:7: error: &lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &#39;value&#39;</span>');
});

test('ANSI removal preserves spaces, blank lines and Unicode from the process', () => {
 const output = '\u001b[32m[100%] Built target core-cpu1\u001b[0m\n\n  → cFS ready\t1\n';
 const text = '[100%] Built target core-cpu1\n\n  → cFS ready\t1\n';
 assert.equal(terminalOutputText(output), text);
 assert.equal(terminalOutputHTML(output), '<span class="terminal-line-success">[100%] Built target core-cpu1</span>\n\n  → cFS ready\t1\n');
});

test('ordinary output is retained without adding a status or synthetic lines', () => {
 assert.equal(terminalOutputHTML('0 errors\nWaiting for process output…'), '0 errors\nWaiting for process output…');
 assert.equal(terminalOutputHTML(''), '');
});
