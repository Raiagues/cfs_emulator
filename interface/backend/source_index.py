"""Source-level C function inventory for the editable flight applications.

This is a lexical index, not a compiler or a runtime trace. It preserves functions
in conditional branches, skips comments/macros/prototypes, and resolves direct
calls only when a definition in the same application is unambiguous.
"""
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
import os
import re


_LEXEME = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_TOKEN = re.compile(r'[A-Za-z_]\w*|->|\.\.\.|[^\s]')
_IDENTIFIER = re.compile(r'[A-Za-z_]\w*\Z')
_NOT_CALL = {'if', 'for', 'while', 'switch', 'sizeof', '_Alignof', 'alignof',
             'typeof', '__typeof__', '__attribute__', '__declspec', '_Static_assert',
             'return', 'do', 'else', 'case'}
_ATTRIBUTES = {'__attribute__', '__attribute', '__declspec', 'asm', '__asm__'}
_CATEGORIES = {'app.main': 'lifecycle', 'app.init': 'lifecycle', 'app.standard_init': 'lifecycle',
               'app.dispatch': 'dispatch', 'app.wakeup': 'dispatch'}
_EXCLUDED = {'.git', '__pycache__', 'node_modules', 'examples', 'docs', 'doc',
             'unit-test', 'unit-tests', 'ut-stubs', 'ut-coverage', 'coveragetest', 'tests'}


def _blank(match):
    return re.sub(r'[^\n]', ' ', match.group())


def mask_source(source):
    """Blank comments, strings and entire continued directives without shifting offsets."""
    masked = _LEXEME.sub(_blank, source)
    continued = False
    lines = []
    for line in masked.splitlines(keepends=True):
        directive = continued or line.lstrip().startswith('#')
        continued = directive and line.rstrip('\r\n').rstrip().endswith('\\')
        lines.append(re.sub(r'[^\n]', ' ', line) if directive else line)
    return ''.join(lines)


def _declarator(tokens, begin, end):
    """Find the function parameter list, including pointer-return declarators."""
    values = [t[0] for t in tokens[begin:end]]
    if not values or '=' in values or 'typedef' in values:
        return None
    stack, pairs, depth = [], {}, {}
    for index in range(begin, end):
        value = tokens[index][0]
        depth[index] = len(stack)
        if value == '(':
            stack.append(index)
        elif value == ')':
            if not stack:
                return None
            pairs[stack.pop()] = index
    if stack:
        return None
    ignored = set()
    for opening, closing in pairs.items():
        if opening > begin and tokens[opening - 1][0] in _ATTRIBUTES:
            ignored.update(range(opening - 1, closing + 1))
    candidates = []
    for opening, closing in pairs.items():
        index = opening - 1
        if index <= begin or index in ignored:
            continue
        name = tokens[index][0]
        if not _IDENTIFIER.fullmatch(name) or name in _NOT_CALL or name in _ATTRIBUTES:
            continue
        # A name in a parameter declaration belongs to the enclosing function.
        if any(start < opening < finish and start - 1 > begin and
               _IDENTIFIER.fullmatch(tokens[start - 1][0]) and start not in ignored
               for start, finish in pairs.items()):
            continue
        candidates.append((depth[opening], index, opening, closing))
    if not candidates:
        return None
    _, name_index, opening, closing = min(candidates)
    prefix = [tokens[i][0] for i in range(begin, name_index)
              if i not in ignored and tokens[i][0] not in {'(', '*'}]
    if not prefix or prefix[0] in _NOT_CALL:
        return None
    return name_index, opening, closing


def _category(function):
    symbol = function['symbol']
    words = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', symbol).lower().split('_')
    calls = set(function['calls'])
    path = Path(function['path'])
    if 'sensors' in path.parts:
        return 'sensor', 'source directory'
    if any(word in {'init', 'initialize', 'main', 'startup'} for word in words) or calls & {
            'CFE_ES_RegisterApp', 'CFE_ES_RunLoop', 'CFE_ES_ExitApp'}:
        return 'lifecycle', 'initialization/entry symbol or cFE lifecycle call'
    if any(word in {'dispatch', 'wakeup'} for word in words) or calls & {
            'CFE_MSG_GetFcnCode', 'CFE_SB_ReceiveBuffer', 'CFE_SB_RcvMsg'}:
        return 'dispatch', 'dispatch symbol or cFE message-receive call'
    if any(word in {'hk', 'housekeeping', 'telemetry', 'tlm'} for word in words):
        return 'telemetry', 'telemetry symbol'
    if any(word in {'cmd', 'command', 'commands', 'noop'} for word in words) or re.search(r'\w+Cmd_t\b', function['signature']):
        return 'command', 'command symbol or typed command payload'
    return 'support', 'source definition'


def parse_functions(source, path):
    """Return actual definitions, not declarations or function-like macro bodies."""
    masked = mask_source(source)
    tokens = [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(masked)]
    newlines = [m.start() for m in re.finditer('\n', source)]
    line = lambda position: bisect_right(newlines, position) + 1
    functions, errors = [], []
    boundary, index = 0, 0
    while index < len(tokens):
        value = tokens[index][0]
        if value == '{':
            # C headers may surround declarations with extern "C" when included by C++.
            prefix = [t[0] for t in tokens[boundary:index]]
            if prefix == ['extern']:
                boundary = index + 1
                index += 1
                continue
            declaration = _declarator(tokens, boundary, index)
            closing, nesting = index + 1, 1
            while closing < len(tokens) and nesting:
                if tokens[closing][0] == '{':
                    nesting += 1
                elif tokens[closing][0] == '}':
                    nesting -= 1
                closing += 1
            if nesting:
                errors.append({'path': path, 'line': line(tokens[index][1]), 'message': 'Unclosed brace; partial index.'})
                break
            if declaration:
                name_index, opening, ending = declaration
                symbol = tokens[name_index][0]
                begin = tokens[boundary][1]
                signature = re.sub(r'\s+', ' ', masked[begin:tokens[index][1]]).strip()
                body_tokens = tokens[index + 1:closing - 1]
                parameters = masked[tokens[opening][2]:tokens[ending][1]]
                callbacks = set(re.findall(r'\(\s*\*\s*(\w+)\s*\)', parameters))
                calls = sorted({t[0] for n, t in enumerate(body_tokens[:-1])
                                if _IDENTIFIER.fullmatch(t[0]) and body_tokens[n + 1][0] == '('
                                and t[0] not in _NOT_CALL and t[0] not in callbacks
                                and (n == 0 or body_tokens[n - 1][0] not in {'.', '->'})})
                function = {'id': path + '#' + symbol, 'symbol': symbol, 'path': path,
                            'line': line(tokens[name_index][1]), 'start_line': line(begin),
                            'end_line': line(tokens[closing - 1][1]), 'signature': signature,
                            'static': bool(re.search(r'\bstatic\b', signature)), 'calls': calls,
                            'editable': True, 'generated': any(marker in source for marker in ('Generated mission integration', 'Generated application configuration', 'Generated from app.json'))}
                function['category'], function['category_evidence'] = _category(function)
                functions.append(function)
            index = closing
            boundary = index
            continue
        if value in {';', '}'}:
            boundary = index + 1
        index += 1
    counts = defaultdict(int)
    for function in functions:
        counts[function['id']] += 1
        if counts[function['id']] > 1:
            function['id'] += ':' + str(function['line'])
    return functions, errors


class SourceIndex:
    """Cache parsed files; stat-based invalidation also notices edits outside the UI."""
    def __init__(self, root):
        self.root = Path(root)
        self.files = {}

    def application(self, directory, anchors=()):
        files = []
        for base, dirs, names in os.walk(directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED and not d.startswith('build')
                             and not (Path(base) / d).is_symlink())
            for name in sorted(names):
                path = Path(base) / name
                relative = path.relative_to(directory)
                if path.suffix.lower() in {'.c', '.h'} and not path.is_symlink() and (
                        'fsw' in relative.parts or relative.parts[0] in {'config', 'inc', 'src'}):
                    files.append(path)
        functions, modules, errors = [], [], []
        for path in sorted(files):
            relative = path.relative_to(self.root).as_posix()
            try:
                stat = path.stat()
            except OSError as error:
                errors.append({'path': relative, 'message': str(error)})
                continue
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            cached = self.files.get(relative)
            if cached is None or cached[0] != stamp:
                try:
                    source = path.read_text(encoding='utf-8')
                    parsed, failures = parse_functions(source, relative)
                    cached = (stamp, parsed, failures, any(marker in source for marker in ('Generated mission integration', 'Generated application configuration', 'Generated from app.json')))
                except (OSError, UnicodeError) as error:
                    cached = (stamp, [], [{'path': relative, 'message': str(error)}], False)
                self.files[relative] = cached
            definitions = [dict(f) for f in cached[1]]
            for function in definitions:
                matching = [a for a in anchors if a['path'] == relative and (
                    a.get('symbol') == function['symbol'] or function['start_line'] <= a['line'] <= function['end_line'])]
                if matching:
                    anchor = matching[0]['id']
                    function['anchor'] = anchor
                    category = _CATEGORIES.get(anchor, {'command': 'command', 'telemetry': 'telemetry',
                                                      'sensor': 'sensor'}.get(anchor.split('.')[0]))
                    if category:
                        function['category'] = category
                        function['category_evidence'] = 'generator anchor: ' + anchor
            functions.extend(definitions)
            errors.extend(cached[2])
            modules.append({'path': relative, 'name': path.name,
                            'kind': 'source' if path.suffix.lower() == '.c' else 'header',
                            'generated': cached[3], 'functions': [f['id'] for f in definitions]})
        by_name = defaultdict(list)
        for function in functions:
            by_name[function['symbol']].append(function)
        edges = []
        for function in functions:
            for name in function['calls']:
                candidates = by_name[name]
                local = [f for f in candidates if f['path'] == function['path']]
                candidates = local or [f for f in candidates if not f['static'] or f['path'].endswith('.h')]
                if len(candidates) == 1:
                    edges.append({'source': function['id'], 'target': candidates[0]['id']})
        return {'functions': functions, 'source_modules': modules, 'call_edges': edges,
                'source_index': {'function_count': len(functions), 'file_count': len(modules),
                                 'errors': errors, 'scope': 'flight source and configuration; conditional branches included'}}
