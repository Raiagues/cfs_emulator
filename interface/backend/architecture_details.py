"""Navigable, source-only relationships for the application architecture view.

This module never invokes a compiler, reads a generated communication catalog,
or uses app manifests. Numbers are evaluated only from unambiguous integer C
constants. Dynamic routing and unsupported declarations retain their expressions.
"""
import ast
from collections import defaultdict, deque
from pathlib import Path
import re

from ground_station.discovery import arguments
from interface.backend.source_index import SourceIndex, mask_source


_FILES = {}
_INDEXES = {}
_COMMENTS = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*')
_PUBLISH = {'CFE_SB_TransmitMsg', 'CFE_SB_TransmitBuffer', 'CFE_SB_SendMsg', 'CFE_SB_ZeroCopySend'}


def _read(root, path):
    path = Path(path)
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        return None
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        cached = _FILES.get(path)
        if cached is None or cached[0] != stamp:
            raw = path.read_text(encoding='utf-8')
            clean = _COMMENTS.sub(lambda match: re.sub(r'[^\n]', ' ', match[0]), raw)
            cached = (stamp, {'path': path.relative_to(root).as_posix(), 'raw': raw,
                              'clean': clean, 'mask': mask_source(raw)})
            _FILES[path] = cached
        return cached[1]
    except (OSError, UnicodeError):
        return None


def _ref(file, position, symbol=None):
    line = file['raw'].count('\n', 0, position) + 1
    ref = {'path': file['path'], 'line': line, 'end_line': line}
    if symbol:
        ref['symbol'] = symbol
    return ref


def _fnref(fn):
    return {key: fn[key] for key in ('id', 'symbol', 'path', 'line', 'end_line')}


def _closing(text, opening, left='(', right=')'):
    depth = 1
    for position in range(opening + 1, len(text)):
        if text[position] == left:
            depth += 1
        elif text[position] == right:
            depth -= 1
            if not depth:
                return position
    return None


def _calls(file, symbols=None, start=0, end=None):
    end = len(file['mask']) if end is None else end
    for match in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', file['mask'][start:end]):
        name = match[1]
        if symbols is not None and name not in symbols:
            continue
        position = start + match.start()
        opening = start + match.end() - 1
        closing = _closing(file['mask'], opening)
        if closing is not None and closing < end:
            yield name, position, closing, arguments(file['clean'][opening + 1:closing])


def _bounds(file, fn):
    lines = file['raw'].splitlines(keepends=True)
    start = sum(map(len, lines[:fn['line'] - 1]))
    end = sum(map(len, lines[:fn['end_line']]))
    opening = file['mask'].find('{', start, end)
    return (opening + 1 if opening >= 0 else start), end


def _identifier(expression):
    symbols = re.findall(r'\b\w+_MID(?:_BASE)?\b', expression)
    return symbols[0] if len(set(symbols)) == 1 else expression.strip()


def _packet(expression):
    expression = re.sub(r'\s+', '', expression).replace('->', '.')
    expression = re.sub(r'^(?:CFE_MSG_PTR|CFE_SB_MSG_PTR)\((.*)\)$', r'\1', expression)
    expression = expression.lstrip('&(').rstrip(')')
    return re.sub(r'\.(?:TelemetryHeader|CommandHeader|Msg)$', '', expression)


def _handle(expression):
    return re.sub(r'\[[^\]]*\]', '[]', re.sub(r'\s+', '', expression).lstrip('&'))


def _conditions(file, position):
    """Keep preprocessor conditions visible rather than guess compiler flags."""
    stack = []
    for line in file['clean'][:position].splitlines():
        match = re.match(r'\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)', line)
        if not match:
            continue
        kind, expression = match[1], match[2].strip()
        if kind in {'if', 'ifdef', 'ifndef'}:
            stack.append(expression if kind == 'if' else f'{"!" if kind == "ifndef" else ""}defined({expression})')
        elif kind == 'endif' and stack:
            stack.pop()
        elif kind == 'else' and stack:
            stack[-1] = '!(' + stack[-1] + ')'
        elif kind == 'elif' and stack:
            stack[-1] = expression
    return stack


class Constants:
    """Small integer/macro evaluator; unresolved C stays unresolved, never eval()."""
    def __init__(self, files):
        self.definitions = defaultdict(list)
        for file in files:
            text = file['clean'].replace('\\\n', '  ')
            for match in re.finditer(r'^[ \t]*#[ \t]*define[ \t]+(\w+)(\([^\n)]*\))?[ \t]+([^\n]*(?:\\\n[^\n]*)*)', text, re.M):
                name, params, expression = match.groups()
                if not expression.strip():
                    continue
                self.definitions[name].append({'parameters': params[1:-1].split(',') if params else None,
                                               'expression': expression.replace('\\\n', ' ').strip(),
                                               'source': _ref(file, match.start(), name)})
            for enum in re.finditer(r'\benum\s*(?:\w+\s*)?\{([^{}]*)\}', text):
                previous = None
                for entry in arguments(enum[1]):
                    match = re.fullmatch(r'\s*(\w+)\s*(?:=\s*(.*))?', entry, re.S)
                    if not match:
                        continue
                    name, expression = match.groups()
                    expression = expression or (previous + ' + 1' if previous else '0')
                    offset = text.find(name, enum.start(), enum.end())
                    self.definitions[name].append({'parameters': None, 'expression': expression,
                                                   'source': _ref(file, offset, name)})
                    previous = name

    def definition(self, name):
        found = self.definitions.get(name, [])
        distinct = {(tuple(item['parameters'] or ()), item['expression']) for item in found}
        return found[0] if len(distinct) == 1 else None

    def expand(self, expression, seen=()):
        if len(seen) > 30 or len(expression) > 8000:
            raise ValueError('Unsupported constant expansion')
        # Expand function-like macros from the outside, including token paste.
        for match in re.finditer(r'\b(\w+)\s*\(', expression):
            definition = self.definition(match[1])
            if not definition or definition['parameters'] is None or match[1] in seen:
                continue
            closing = _closing(expression, match.end() - 1)
            if closing is None:
                continue
            values = arguments(expression[match.end():closing])
            if len(values) != len(definition['parameters']):
                continue
            replacement = definition['expression']
            for name, value in zip(definition['parameters'], values):
                replacement = re.sub(r'\b' + re.escape(name.strip()) + r'\b', lambda _: value, replacement)
            replacement = re.sub(r'\s*##\s*', '', replacement)
            replacement = self.expand(replacement, (*seen, match[1]))
            return self.expand(expression[:match.start()] + '(' + replacement + ')' + expression[closing + 1:], seen)
        def substitute(match):
            name = match[0]
            definition = self.definition(name)
            if definition and definition['parameters'] is None and name not in seen:
                return '(' + self.expand(definition['expression'], (*seen, name)) + ')'
            return name
        return re.sub(r'\b[A-Za-z_]\w*\b', substitute, expression)

    def value(self, expression):
        try:
            expanded = self.expand(expression)
            expanded = re.sub(r'(?<=\d)[uUlL]+\b', '', expanded)
            tree = ast.parse(expanded, mode='eval')
            def integer(node):
                if isinstance(node, ast.Constant) and type(node.value) is int:
                    return node.value
                if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert)):
                    value = integer(node.operand)
                    return value if isinstance(node.op, ast.UAdd) else -value if isinstance(node.op, ast.USub) else ~value
                if isinstance(node, ast.BinOp):
                    left, right = integer(node.left), integer(node.right)
                    if abs(left) > 2**64 or abs(right) > 2**64:
                        raise ValueError('Constant outside integer range')
                    operations = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                                  ast.Mult: lambda: left * right, ast.BitOr: lambda: left | right,
                                  ast.BitAnd: lambda: left & right, ast.BitXor: lambda: left ^ right,
                                  ast.LShift: lambda: left << right if 0 <= right < 64 else None,
                                  ast.RShift: lambda: left >> right if 0 <= right < 64 else None}
                    if type(node.op) in operations:
                        return operations[type(node.op)]()
                raise ValueError('Unsupported C expression')
            return integer(tree.body)
        except (ValueError, SyntaxError, RecursionError, TypeError):
            return None

    def reference(self, expression, source=None):
        symbol = _identifier(expression)
        definition = self.definition(symbol)
        alternatives = self.definitions.get(symbol, [])
        return {'symbol': symbol, 'expression': definition['expression'] if definition else expression,
                'value': self.value(symbol), 'source': definition['source'] if definition else
                alternatives[0]['source'] if alternatives else source}


def _configuration_files(root, files):
    """Source defaults plus mission/CPU1 overrides; no generated build headers."""
    paths = set(root.glob('cFS/apps/*/config/*.h')) | set(root.glob('cFS/apps/*/fsw/inc/*ids.h'))
    paths |= set(root.glob('cFS/cfe/modules/*/config/*msgid*.h'))
    paths |= set(root.glob('cFS/cfe/modules/*/config/*topicid*.h'))
    paths |= set(root.glob('cFS/cfe/modules/*/fsw/inc/*topicids.h'))
    paths |= set(root.glob('cFS/sample_defs/inc/*.h')) | set(root.glob('cFS/sample_defs/cpu1/*.h'))
    selected = {file['path']: file for file in files}
    overrides = {path.name: path for path in root.glob('cFS/sample_defs/inc/*.h')}
    overrides.update({path.name: path for path in root.glob('cFS/sample_defs/cpu1/*.h')})
    for path in sorted(paths):
        if path.name.startswith('eds_') or '_eds_' in path.name:
            continue
        if path.name.startswith('default_') and path.name[8:] in overrides:
            selected.pop(path.relative_to(root).as_posix(), None)
            continue
        file = _read(root, path)
        if file:
            selected[file['path']] = file
    return list(selected.values())


def _structures(files):
    structs, sources, variables, incomplete = {}, {}, defaultdict(set), set()
    for file in files:
        for match in re.finditer(r'typedef\s+struct\s*(?:\w+\s*)?\{([^{}]*)\}\s*(\w+)\s*;', file['clean']):
            body, name = match.groups()
            fields = []
            for member in re.finditer(r'\b(\w+)\s+([^;]+);', body):
                field_type, declarations = member.groups()
                for declaration in arguments(declarations):
                    field = re.fullmatch(r'\s*(\w+)\s*(\[[^;]*?\])?\s*', declaration)
                    if not field:
                        incomplete.add(name)
                        continue
                    field_name, array = field.groups()
                    fields.append({'name': field_name, 'type': field_type,
                                   'array': array[1:-1].strip() if array else None,
                                   'source': _ref(file, match.start(1) + member.start(), field_name)})
            structs[name] = fields
            sources[name] = _ref(file, match.start(), name)
    if structs:
        pattern = re.compile(r'\b(' + '|'.join(map(re.escape, structs)) + r')\s+(?:const\s+)?\**\s*(\w+)\b')
        for file in files:
            for typ, variable in pattern.findall(file['clean']):
                variables[variable].add(typ)
    def resolve(expression):
        expression = re.sub(r'\[[^\]]*\]', '', expression).replace('->', '.')
        parts = re.findall(r'\w+', expression)
        if len(parts) == 1 and parts[0] in structs:
            return parts[0]
        possible = variables.get(parts[0], set()) if parts else set()
        for part in parts[1:]:
            possible = {field['type'] for typ in possible for field in structs.get(typ, []) if field['name'] == part}
        return next(iter(possible)) if len(possible) == 1 else None
    def fields(typ, prefix='', visited=()):
        if typ in visited or len(visited) > 6:
            return []
        result = []
        for field in structs.get(typ, []):
            if field['type'] in {'CFE_MSG_TelemetryHeader_t', 'CFE_MSG_CommandHeader_t'}:
                continue
            name = prefix + field['name']
            if field['type'] in structs and not field['array']:
                result.extend(fields(field['type'], name + '.', (*visited, typ)))
            else:
                result.append({**field, 'name': name.removeprefix('Payload.')})
        return result
    def complete(typ, visited=()):
        if typ not in structs or typ in incomplete or typ in visited:
            return False
        return all(complete(field['type'], (*visited, typ)) for field in structs[typ]
                   if field['type'] in structs and not field['array'])
    return structs, sources, resolve, fields, complete


def _table_source(root, path):
    name = path.name
    mission = root / 'cFS/sample_defs'
    for candidate in (mission / 'cpu1/tables' / name, mission / 'tables' / ('cpu1_' + name),
                      mission / 'tables' / name, mission / 'cpu1' / name,
                      mission / ('cpu1_' + name), mission / name, path):
        file = _read(root, candidate)
        if file:
            return file
    return None


def describe_application(app, *, root):
    root = Path(root).resolve()
    functions = app.get('functions', [])
    files = {}
    for module in app.get('source_modules', []):
        file = _read(root, root / module['path'])
        if file and 'eds_' not in Path(file['path']).name and '_eds_' not in Path(file['path']).name:
            files[file['path']] = file
    # Alternate EDS dispatch implementations remain in the source inventory;
    # this view exposes the ordinary C definitions without asserting a live build.
    functions = [fn for fn in functions if fn['path'] in files]
    by_name = defaultdict(list)
    for fn in functions:
        by_name[fn['symbol']].append(fn)
    constants = Constants(_configuration_files(root, list(files.values())))
    structs, type_sources, resolve_type, fields_for, fields_complete = _structures(list(files.values()))
    subscriptions, commands, telemetry, publications, tables, unresolved = [], [], [], [], [], []
    resources = defaultdict(lambda: {'tables': [], 'libraries': []})
    occurrences = []
    for fn in functions:
        file = files[fn['path']]
        start, end = _bounds(file, fn)
        for name, position, closing, args in _calls(file, start=start, end=end):
            occurrences.append({'api': name, 'position': position, 'end': closing, 'args': args,
                                'function': _fnref(fn), 'source': _ref(file, position, name), 'file': file})

    def packet_record(typ):
        return {'packet_type': typ, 'packet_source': type_sources.get(typ),
                'fields': fields_for(typ) if typ else [], 'fields_complete': fields_complete(typ)}

    for item in occurrences:
        name, args, source = item['api'], item['args'], item['source']
        if name.startswith('CFE_SB_Subscribe') and args:
            mid = constants.reference(args[0], source)
            if re.fullmatch(r'\w+_MID', mid['symbol']) or mid['value'] is not None:
                subscriptions.append({'mid': mid, 'pipe': args[1] if len(args) > 1 else '',
                                      'source': source, 'function': item['function'], 'kind': 'direct'})
            else:
                unresolved.append({'kind': 'subscription', 'expression': args[0], 'source': source})
        if name == 'CFE_MSG_Init' and len(args) >= 3:
            mid = constants.reference(args[1], source)
            packet = _packet(args[0])
            size = re.fullmatch(r'\s*sizeof\s*\((.*)\)\s*', args[2], re.S)
            typ = resolve_type(size[1]) if size else resolve_type(packet)
            if re.fullmatch(r'\w+_MID', mid['symbol']) or mid['value'] is not None:
                publishers = []
                for send in occurrences:
                    if send['api'] in _PUBLISH and send['args'] and _packet(send['args'][0]) == packet:
                        publishers.append({**send['function'], 'call_source': send['source']})
                record = {'mid': mid, 'packet': packet, **packet_record(typ), 'publishers': publishers,
                          'source': source, 'function': item['function'], 'kind': 'packet'}
                if publishers:
                    publications.append(record)
                if typ and any(field['type'] == 'CFE_MSG_TelemetryHeader_t' for field in structs.get(typ, [])):
                    telemetry.append(record)
            else:
                unresolved.append({'kind': 'packet_initialization', 'expression': args[1], 'source': source})

    # A small subscribe helper is common in cFS: substitute an actual caller's
    # MID argument for the corresponding parameter, retaining both call sites.
    for item in occurrences:
        if not item['api'].startswith('CFE_SB_Subscribe') or not item['args']:
            continue
        fn = next((fn for fn in functions if fn['id'] == item['function']['id']), None)
        parameter_list = re.search(r'\((.*)\)', fn['signature']) if fn else None
        if not parameter_list:
            continue
        for index, declaration in enumerate(arguments(parameter_list[1])):
            words = re.findall(r'\w+', declaration)
            if not words or not re.search(r'\b' + re.escape(words[-1]) + r'\b', item['args'][0]):
                continue
            for caller in occurrences:
                if caller['api'] != fn['symbol'] or index >= len(caller['args']):
                    continue
                mid = constants.reference(caller['args'][index], caller['source'])
                if re.fullmatch(r'\w+_MID', mid['symbol']) or mid['value'] is not None:
                    subscriptions.append({'mid': mid, 'pipe': item['args'][1] if len(item['args']) > 1 else '',
                                          'source': caller['source'], 'function': caller['function'],
                                          'via': [item['source']], 'kind': 'direct'})

    # First map received MID branches to local functions, then use their actual
    # CC cases. There is deliberately no assumed APP_CMD_MID fallback.
    routes = defaultdict(set)
    mid_branches, cc_cases = [], []
    for fn in functions:
        file = files[fn['path']]
        start, end = _bounds(file, fn)
        body = file['mask'][start:end]
        aliases = dict(re.findall(r'\b(\w+)\s*=\s*CFE_SB_ValueToMsgId\s*\(\s*(\w+_MID)\s*\)', body))
        for condition in re.finditer(r'\bif\s*\(', body):
            opening = start + condition.end() - 1
            closing = _closing(file['mask'], opening)
            if closing is None:
                continue
            predicate = file['mask'][opening:closing + 1]
            if 'CFE_SB_MsgId_Equal' not in predicate:
                continue
            mids = {aliases.get(word, word) for word in re.findall(r'\b\w+_MID\b', predicate)}
            mids.update(aliases[word] for word in re.findall(r'\b\w+\b', predicate) if word in aliases)
            brace = re.match(r'\s*\{', file['mask'][closing + 1:end])
            if len(mids) != 1 or not brace:
                continue
            begin = closing + 1 + brace.end() - 1
            finish = _closing(file['mask'], begin, '{', '}')
            if finish is not None:
                mid_branches.append((next(iter(mids)), file, begin + 1, finish, fn))
        for case in re.finditer(r'\bcase\s+(\w+_CC)\s*:', body):
            begin = start + case.end()
            next_case = re.search(r'\b(?:case\s+\w+\s*:|default\s*:|break\s*;)', file['mask'][begin:end])
            finish = begin + next_case.start() if next_case else end
            cc_cases.append((case[1], file, begin, finish, fn))

    def local_calls(file, begin, finish):
        return [name for name, _, _, _ in _calls(file, start=begin, end=finish) if name in by_name]

    for mid, file, begin, finish, _ in mid_branches:
        pending = deque(local_calls(file, begin, finish))
        seen = set()
        while pending:
            symbol = pending.popleft()
            if symbol in seen:
                continue
            seen.add(symbol)
            routes[symbol].add(mid)
            for target in by_name[symbol]:
                pending.extend(call for call in target.get('calls', []) if call in by_name)

    def handler(file, begin, finish):
        pending = deque((symbol, []) for symbol in local_calls(file, begin, finish))
        seen, fallback = set(), None
        while pending:
            symbol, via = pending.popleft()
            if symbol in seen or len(via) > 5:
                continue
            seen.add(symbol)
            candidates = by_name[symbol]
            if len(candidates) != 1:
                continue
            fn = candidates[0]
            if re.search(r'(?:Verify|Validate|Get)\w*(?:Length|Size)', symbol):
                continue
            typ = re.search(r'\b(\w+Cmd_t)\b', fn['signature'])
            candidate = {'handler': _fnref(fn), 'via': via, **packet_record(typ[1] if typ else None)}
            fallback = fallback or candidate
            if typ:
                return candidate
            pending.extend((call, [*via, _fnref(fn)]) for call in fn.get('calls', []) if call in by_name)
        return fallback

    command_groups = {}
    for code, file, begin, finish, fn in cc_cases:
        received = routes.get(fn['symbol'], set())
        found = handler(file, begin, finish)
        if len(received) != 1 or found is None:
            unresolved.append({'kind': 'command_route', 'expression': code, 'source': _ref(file, begin, code)})
            continue
        mid = next(iter(received))
        group = command_groups.setdefault(mid, {'mid': constants.reference(mid), 'handlers': [], 'source': _ref(file, begin, mid)})
        group['handlers'].append({'cc': constants.reference(code, _ref(file, begin, code)), **found,
                                  'source': _ref(file, begin, code)})
    case_functions = {fn['symbol'] for _, _, _, _, fn in cc_cases}
    for mid, file, begin, finish, fn in mid_branches:
        if any(mid in routes[symbol] for symbol in case_functions):
            continue
        found = handler(file, begin, finish)
        if found:
            group = command_groups.setdefault(mid, {'mid': constants.reference(mid), 'handlers': [], 'source': _ref(file, begin, mid)})
            record = {'cc': None, **found, 'source': _ref(file, begin, mid)}
            if not any(item['handler']['id'] == record['handler']['id'] for item in group['handlers']):
                group['handlers'].append(record)
    commands = list(command_groups.values())

    # Register/load/use relationships refer to the same handle in C. Resolve
    # the CMake table basename using the mission's CPU1 override precedence.
    table_definitions = []
    for module in app.get('source_modules', []):
        path = root / module['path']
        if 'tables' not in path.parts or path.suffix != '.c':
            continue
        file = _table_source(root, path)
        if not file:
            continue
        for _, pos, _, args in _calls(file, {'CFE_TBL_FILEDEF'}):
            if len(args) >= 4:
                table_definitions.append({'name': args[1], 'variable': args[0], 'filename': args[3].strip('" '),
                                          'source': _ref(file, pos, args[0]), 'file': file})
    for item in occurrences:
        args = item['args']
        if item['api'] != 'CFE_TBL_Register' or len(args) < 2:
            continue
        name = args[1].strip('" ')
        handle = args[0].strip()
        uses = [call for call in occurrences if call['api'].startswith('CFE_TBL_') and
                any(_handle(argument) == _handle(handle) for argument in call['args'])]
        loads = [call for call in uses if call['api'] == 'CFE_TBL_Load']
        matches = [definition for definition in table_definitions if definition['name'].endswith('.' + name)]
        loaded_files = set()
        for load in loads:
            if len(load['args']) >= 3:
                try:
                    expanded = constants.expand(load['args'][2]).strip(' ()')
                except ValueError:
                    expanded = ''
                literal = re.fullmatch(r'"([^"]+)"', expanded)
                if literal:
                    loaded_files.add(Path(literal[1]).name)
        if loaded_files:
            matches = [definition for definition in matches if definition['filename'] in loaded_files]
        definition = matches[0] if len(matches) == 1 else None
        table = {'name': name, 'handle': handle, 'source': item['source'],
                 'definition': definition['source'] if definition else None,
                 'load_sources': [call['source'] for call in loads],
                 'functions': list({call['function']['id']: call['function'] for call in uses}.values())}
        tables.append(table)
        for function in table['functions']:
            resources[function['symbol']]['tables'].append(table)

    # Dynamic packet loops can be tied to a single loaded packet table. Rows
    # carry table source provenance and stay configured relationships, not a
    # claim that the peer app is running or that the table is currently loaded.
    for definition in table_definitions:
        if not any(table['definition'] == definition['source'] and table['load_sources'] for table in tables):
            continue
        table_files = [(definition['file'], [])]
        for include in re.finditer(r'^\s*#\s*include\s+"([^"\n]+\.inc)"', definition['file']['clean'], re.M):
            included = _read(root, root / 'cFS/sample_defs/generated' / include[1])
            if included:
                table_files.append((included, _conditions(definition['file'], include.start())))
        dynamic_subs = []
        for call in occurrences:
            if not call['api'].startswith('CFE_SB_Subscribe') or not call['args']:
                continue
            members = re.findall(r'\b\w+\b', call['args'][0])
            fn = next(fn for fn in functions if fn['id'] == call['function']['id'])
            start, end = _bounds(call['file'], fn)
            body = call['file']['mask'][start:end]
            if members and re.search(r'\b' + re.escape(members[0]) + r'\s*=\s*[^;]*(?:Tbl|Table)\w*', body):
                dynamic_subs.append(call)
        dynamic_sends = [call for call in occurrences if call['api'] in _PUBLISH and call['args'] and
                         not any(_packet(call['args'][0]) == record['packet'] for record in publications if 'packet' in record)]
        for file, inherited_conditions in table_files:
            for _, pos, _, args in _calls(file, {'CFE_SB_MSGID_WRAP_VALUE'}):
                if not args:
                    continue
                mid = constants.reference(args[0], _ref(file, pos))
                source = _ref(file, pos, mid['symbol'])
                conditions = inherited_conditions + _conditions(file, pos)
                if dynamic_subs:
                    subscriptions.append({'mid': mid, 'pipe': dynamic_subs[0]['args'][1] if len(dynamic_subs[0]['args']) > 1 else '',
                                          'source': source, 'function': dynamic_subs[0]['function'], 'kind': 'table',
                                          'table': definition['source'], 'conditions': conditions})
                elif dynamic_sends:
                    publications.append({'mid': mid, 'source': source, 'kind': 'scheduled', 'table': definition['source'],
                                         'publishers': [call['function'] for call in dynamic_sends],
                                         'packet_type': None, 'fields': [], 'conditions': conditions})

    index = _INDEXES.setdefault(root, SourceIndex(root))
    library_symbols = defaultdict(list)
    for directory in sorted((root / 'cFS/libs').glob('*')):
        if directory.is_dir() and not directory.is_symlink():
            for fn in index.application(directory)['functions']:
                if not fn.get('static'):
                    library_symbols[fn['symbol']].append((directory.name, fn))
    libraries = []
    for symbol, candidates in library_symbols.items():
        callers = [fn for fn in functions if symbol in fn.get('calls', [])]
        if not callers or len(candidates) != 1:
            continue
        name, fn = candidates[0]
        library = {'name': name, 'symbol': symbol, 'source': _fnref(fn), 'kind': 'library',
                   'functions': [_fnref(caller) for caller in callers]}
        libraries.append(library)
        for caller in callers:
            resources[caller['symbol']]['libraries'].append(library)

    return {'subscriptions': subscriptions, 'commands': commands, 'telemetry': telemetry,
            'publications': publications, 'tables': tables, 'libraries': libraries,
            'function_resources': dict(resources), 'unresolved': unresolved,
            'scope': 'Source relationships in the ordinary C implementation; conditional table entries may be included. '
                     'Constants are source expressions, not compiler-verified wire layouts or live traffic.'}
