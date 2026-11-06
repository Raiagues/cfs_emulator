"""Read explicit dispatch and packet initialization relationships from C sources.

Discovery names the wire objects; catalog.py asks the target compiler for every
MID, code, size and field offset.
"""
from collections import Counter, defaultdict
import re

from ground_station.c_source import (arguments, blank_lexemes, calls, closing, entry_routes,
                                     mid_aliases, mid_regions, mids_at)


def function_bodies(text):
    """Return (name, parameters, begin, end) of each brace-delimited definition."""
    masked = blank_lexemes(text)
    found = []
    pattern = re.compile(r'\b(\w+)\s*\(([^;{}]*)\)\s*\{')
    position = 0
    while match := pattern.search(masked, position):
        end = closing(masked, match.end() - 1, '{', '}')
        if end is None:
            break
        if match[1] not in {'if', 'for', 'while', 'switch'}:
            found.append((match[1], arguments(text[match.start(2):match.end(2)]), match.end(), end))
        position = end + 1
    return found


def command_mappings(text, structs, defined, prefix):
    """Resolve direct casts, validation wrappers, length arrays and handler tables.

    A code belongs to the MID that reaches its dispatch: a CFE_SB_MsgId_Equal
    branch, a negated test that returns for every other MID, or an explicit
    handler table entry. A code without one of these is returned as unresolved,
    with the reason.
    Returns (mappings, {unresolved code: reason}, size-only mappings).
    """
    packet_types = {name for name, fields in structs.items()
                    if any(typ == 'CFE_MSG_CommandHeader_t' for typ, _, _ in fields)}
    masked = blank_lexemes(text)
    definitions = function_bodies(text)
    counts = Counter(name for name, _, _, _ in definitions)
    # Static functions in separate sources can share a name. After
    # preprocessing the called definition is unknown, so neither is followed.
    functions = {name: (parameters, begin, end) for name, parameters, begin, end in definitions if counts[name] == 1}
    bodies = {name: masked[begin:end] for name, (_, begin, end) in functions.items()}
    owned = lambda code: code in defined and code.startswith(prefix + '_')
    validators = {}
    for name, body in bodies.items():
        names = [re.findall(r'\w+', parameter)[-1] for parameter in functions[name][0] if re.findall(r'\w+', parameter)]
        for _, _, _, args in calls(body, {'CFE_MSG_GetSize'}):
            if len(args) != 2 or not re.fullmatch(r'&\s*\w+', args[1]): continue
            actual = args[1].lstrip('&').strip()
            for index, expected in enumerate(names):
                if re.search(r'\b(?:' + actual + r'\s*(?:==|!=)\s*' + expected + '|' + expected + r'\s*(?:==|!=)\s*' + actual + r')\b', body):
                    validators[name] = index
    def sizes_in(block, seen=()):
        sizes = set()
        for name, index in validators.items():
            for _, _, _, args in calls(block, {name}):
                if len(args) > index:
                    size = args[index]
                    if size in defined or size.isdigit() or re.fullmatch(r'sizeof\s*\(\s*\w+\s*\)', size):
                        sizes.add(size)
        if sizes or len(seen) >= 4: return sizes
        for name in re.findall(r'\b(\w+)\s*\(', block):
            if name in bodies and name not in seen:
                sizes.update(sizes_in(bodies[name], (*seen, name)))
        return sizes
    def types_in(block, seen=()):
        types = set(re.findall(r'\b(\w+)\s*\*', block))
        types.update(re.findall(r'\bsizeof\s*\(\s*(\w+)\s*\)', block))
        types &= packet_types
        if types or len(seen) >= 4:
            return types
        for name in re.findall(r'\b(\w+)\s*\(', block):
            if name in bodies and name not in seen:
                types.update(types_in(bodies[name], (*seen, name)))
        return types
    aliases = mid_aliases(masked)
    regions = {name: mid_regions(body, aliases) for name, body in bodies.items()}
    sites = {name: [(call[1], call.start()) for call in re.finditer(r'\b(\w+)\s*\(', body) if call[1] in bodies]
             for name, body in bodies.items()}
    routes = entry_routes(regions, sites)
    layouts, sized, reasons, expected = defaultdict(set), defaultdict(set), {}, set()
    def route(code, function, position, candidates, sizes):
        received = mids_at(regions[function], routes[function], position)
        if len(received) > 1:
            several = ', '.join(sorted(received))
            reasons.setdefault(code, f'{function} is reached from several MIDs ({several})')
        elif not received:
            reasons.setdefault(code, f'no MID comparison or handler table reaches {function}')
        elif len(candidates) == 1:
            layouts[code].add((next(iter(received)), code, next(iter(candidates))))
        elif len(sizes) == 1:
            sized[code].add((next(iter(received)), code, next(iter(sizes))))
    for function, body in bodies.items():
        # A dispatch branch that never consumes the message has no external
        # packet layout to expose (for example, an internal scheduler wakeup).
        message_parameters = [re.findall(r'\w+', parameter)[-1] for parameter in functions[function][0]
                              if re.search(r'\b(?:CFE_MSG_Message_t|CFE_SB_Buffer_t)\b', parameter)]
        for match in re.finditer(r'\bcase\s+(\w+_CC)\s*:(.*?)(?=\bbreak\s*;|\bcase\s+|\bdefault\s*:)', body, re.S):
            code, block = match.groups()
            if not owned(code):
                continue
            candidates, sizes = types_in(block), sizes_in(block)
            mentioned = any(re.search(r'\b' + re.escape(name) + r'\b', block) for name in message_parameters)
            if not message_parameters or candidates or sizes or mentioned:
                expected.add(code)
            route(code, function, match.start(), candidates, sizes)
    for name, _, begin, end in definitions:
        if counts[name] > 1:
            for code in re.findall(r'\bcase\s+(\w+_CC)\s*:', masked[begin:end]):
                if owned(code):
                    expected.add(code)
                    reasons.setdefault(code, f'{name} has several definitions')
    spans = [(begin, end, name) for name, (_, begin, end) in functions.items()]
    for match in re.finditer(r'\[\s*(\w+_CC)\s*\]\s*=\s*sizeof\s*\(\s*(\w+)\s*\)', masked):
        code, typ = match.groups()
        if not owned(code):
            continue
        expected.add(code)
        # The length array takes its MID from the function that indexes it.
        container = next(((name, begin) for begin, end, name in spans if begin <= match.start() < end), None)
        if container is None:
            reasons.setdefault(code, 'its length array is not inside a single function definition')
        elif typ in packet_types:
            route(code, container[0], match.start() - container[1], {typ}, set())
    for table_mid, code, typ in re.findall(r'\b\w+\(\s*(\w+_MID)\s*,\s*(\w+_CC|0)\s*,\s*(\w+)\s*,', masked):
        if not table_mid.startswith(prefix + '_') or typ not in packet_types:
            continue
        if code == '0': layouts[table_mid].add((table_mid, '0', typ))
        elif code in defined:
            expected.add(code); layouts[code].add((table_mid, code, typ))
    # MIDs that reach function-code cases are dispatched by CC. Any other MID
    # branch with a single command type is one command with code 0.
    dispatched = set()
    for function, body in bodies.items():
        for match in re.finditer(r'\bcase\s+(\w+_CC)\s*:|\[\s*(\w+_CC)\s*\]\s*=', body):
            if owned(match[1] or match[2]):
                dispatched |= mids_at(regions[function], routes[function], match.start())
    for function, body in bodies.items():
        for mid, begin, end in regions[function]:
            if mid in dispatched or mid not in defined or not mid.startswith(prefix + '_'):
                continue
            candidates = types_in(body[begin:end])
            if len(candidates) == 1: layouts[mid].add((mid, '0', candidates.pop()))
    mappings, explicit, unresolved = {}, {}, {}
    for code, found in layouts.items():
        if len(found) == 1:
            mappings[code] = found.pop()
        else:
            unresolved[code] = 'conflicting dispatch evidence: ' + ', '.join(f'{mid} {typ}' for mid, _, typ in sorted(found))
    for code, found in sized.items():
        if code in mappings or code in unresolved:
            continue
        if len(found) == 1:
            explicit[code] = found.pop()
        else:
            unresolved[code] = 'conflicting validated lengths: ' + ', '.join(f'{mid} {size}' for mid, _, size in sorted(found))
    for selected in (mappings, explicit):
        for code, (mid, _, _) in list(selected.items()):
            if mid not in defined:
                del selected[code]
                unresolved[code] = mid + ' is not defined by the compiled headers'
    for code in expected - mappings.keys() - explicit.keys() - unresolved.keys():
        unresolved[code] = reasons.get(code, 'no command structure or validated length was found')
    return mappings, dict(sorted(unresolved.items())), explicit


def raw_telemetry_mappings(text, defined):
    """Find initialized byte buffers and their explicit compiler-sized packets."""
    result = {}
    for _, _, begin, end in function_bodies(text):
        body = text[begin:end]
        buffers = dict(re.findall(r'\b(?:uint8|uint8_t|unsigned\s+char|char)\s+(\w+)\s*\[([^\]]+)\]', body))
        pointers = dict(re.findall(r'\b(\w+)\s*=\s*\(\s*CFE_MSG_Message_t\s*\*\s*\)\s*&?\s*(\w+)\b', body))
        aliases = dict(re.findall(r'\b(\w+)\s*=\s*CFE_SB_ValueToMsgId\s*\(\s*(\w+)\s*\)', body))
        for _, _, _, args in calls(body, {'CFE_MSG_Init'}):
            if len(args) != 3: continue
            pointer = re.sub(r'\(\s*CFE_MSG_Message_t\s*\*\s*\)', '', args[0]).strip('& ')
            buffer = pointers.get(pointer, pointer)
            if buffer not in buffers: continue
            mids = re.findall(r'\b\w+\b', args[1])
            mids = [aliases.get(name, name) for name in mids]
            mids = [name for name in mids if name in defined and re.search(r'_MID$', name)]
            size = args[2]
            if re.fullmatch(r'sizeof\s*\(\s*' + re.escape(buffer) + r'\s*\)', size):
                size = '(' + buffers[buffer] + ')'
            if len(mids) == 1:
                result[mids[0]] = size
    return result


def telemetry_mappings(text, structs, packet_types, declarations):
    """Match CFE_MSG_Init MIDs to its sizeof type or a typed member expression."""
    type_names = '|'.join(re.escape(name) for name in sorted(structs, key=len, reverse=True))
    declaration = re.compile(r'\b(' + type_names + r')\s+(?:const\s+)?\**\s*(\w+)\b')
    variables = {}
    for typ, name in declaration.findall(declarations + '\n' + text):
        variables.setdefault(name, set()).add(typ)
    def resolve(expression):
        expression = re.sub(r'\[[^\]]*\]', '', expression).replace('->', '.')
        words = re.findall(r'\w+', expression)
        if len(words) == 1 and words[0] in structs: return words[0]
        if not words: return None
        candidates = variables.get(words[0], set())
        for member in words[1:]:
            candidates = {typ for parent in candidates for typ, name, _ in structs.get(parent, []) if name == member}
        return next(iter(candidates)) if len(candidates) == 1 else None
    def message_type(expression):
        pointer = next(calls(expression, {'CFE_MSG_PTR'}), None)
        if pointer: expression = pointer[3][0]
        expression = re.sub(r'\([^)]*\*\s*\)', '', expression).strip('& ')
        return resolve(expression.removesuffix('.TelemetryHeader').removesuffix('->TelemetryHeader'))
    mappings, used = {}, set()
    for _, position, _, args in calls(text, {'CFE_MSG_Init'}):
        if len(args) < 3: continue
        mids = re.findall(r'\b(\w+_MID(?:_BASE)?)\b', args[1])
        size = re.fullmatch(r'sizeof\s*\((.*)\)', args[2], re.S)
        typ = resolve(size[1]) if size else None
        used.update(candidate for candidate in (typ, message_type(args[0])) if candidate in packet_types)
        if typ not in packet_types: continue
        if len(mids) != 1: continue
        repeat = None
        if mids[0].endswith('_BASE'):
            loops = re.findall(r'for\s*\(\s*(\w+)\s*=\s*0\s*;\s*\1\s*<\s*(\w+)\s*;', text[:position])
            if loops and re.search(r'\+\s*' + re.escape(loops[-1][0]) + r'\b', args[1]):
                repeat = loops[-1][1]
            else: continue
        mappings[mids[0]] = (typ, repeat)
    for _, _, _, args in calls(text, {'CFE_SB_TransmitMsg'}):
        if not args: continue
        typ = message_type(args[0])
        if typ in packet_types: used.add(typ)
    variable = {}
    for _, position, _, args in calls(text, {'CFE_MSG_SetSize'}):
        if len(args) != 2: continue
        pointer = next(calls(args[0], {'CFE_MSG_PTR'}), None)
        if not pointer: continue
        expression = pointer[3][0].removesuffix('.TelemetryHeader').removesuffix('->TelemetryHeader')
        typ = resolve(expression)
        if typ not in packet_types: continue
        # sizeof(packet) - maximum trailing data + used bytes is the firmware's
        # exact lower bound for the message length.
        sizes = re.findall(r'\b' + re.escape(args[1]) + r'\s*=\s*(sizeof\s*\(\s*' + re.escape(typ) + r'\s*\)\s*-\s*[^;+]+)\s*\+', text[:position])
        if sizes: variable[typ] = sizes[-1].strip()
    return mappings, variable, used
