"""Read explicit dispatch and packet initialization relationships from C sources.

Discovery names the wire objects; catalog.py asks the target compiler for every
MID, code, size and field offset. No app-specific command dictionary lives here.
"""
import re


def arguments(text):
    parts, start, level = [], 0, 0
    for index, char in enumerate(text):
        if char in '([{': level += 1
        elif char in ')]}': level -= 1
        elif char == ',' and level == 0:
            parts.append(text[start:index].strip()); start = index + 1
    return parts + [text[start:].strip()]


def calls(text, symbol):
    for match in re.finditer(r'\b' + re.escape(symbol) + r'\s*\(', text):
        level, end = 1, match.end()
        while end < len(text) and level:
            if text[end] == '(': level += 1
            elif text[end] == ')': level -= 1
            end += 1
        if not level:
            yield match.start(), arguments(text[match.end():end - 1])


def function_bodies(text):
    masked = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', lambda m:' ' * len(m[0]), text)
    found = {}
    pattern = re.compile(r'\b(\w+)\s*\([^;{}]*\)\s*\{')
    position = 0
    while match := pattern.search(masked, position):
        name = match[1]
        level, end = 1, match.end()
        while end < len(masked) and level:
            if masked[end] == '{': level += 1
            elif masked[end] == '}': level -= 1
            end += 1
        if name not in {'if','for','while','switch'}:
            found[name] = text[match.end():end - 1]
        position = end
    return found


def command_mappings(text, structs, defined, prefix):
    """Resolve direct casts, validation wrappers, length arrays and handler tables."""
    packet_types = {name for name, fields in structs.items()
                    if any(typ == 'CFE_MSG_CommandHeader_t' for typ, _, _ in fields)}
    bodies = function_bodies(text)
    parameters = {name: arguments(match[1]) for name in bodies
                  if (match := re.search(r'\b' + re.escape(name) + r'\s*\(([^;{}]*)\)\s*\{', text))}
    validators = {}
    for name, body in bodies.items():
        names = [re.findall(r'\w+', parameter)[-1] for parameter in parameters.get(name, []) if re.findall(r'\w+', parameter)]
        for _, args in calls(body, 'CFE_MSG_GetSize'):
            if len(args) != 2 or not re.fullmatch(r'&\s*\w+', args[1]): continue
            actual = args[1].lstrip('&').strip()
            for index, expected in enumerate(names):
                if re.search(r'\b(?:' + actual + r'\s*(?:==|!=)\s*' + expected + '|' + expected + r'\s*(?:==|!=)\s*' + actual + r')\b', body):
                    validators[name] = index
    def sizes_in(block, seen=()):
        sizes = set()
        for name, index in validators.items():
            for _, args in calls(block, name):
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
    mappings, explicit, expected = {}, {}, set()
    mid = prefix + '_CMD_MID'
    aliases = dict(re.findall(r'\b(\w+)\s*=\s*CFE_SB_ValueToMsgId\s*\(\s*(\w+_MID)\s*\)', text))
    routes, branches = {}, []
    for match in re.finditer(r'CFE_SB_MsgId_Equal\s*\([^,]+,\s*(?:CFE_SB_ValueToMsgId\s*\(\s*)?(\w+)\s*(?:\)\s*)?\)\s*\)\s*\{', text):
        received = aliases.get(match[1], match[1]); level, end = 1, match.end()
        while end < len(text) and level:
            if text[end] == '{': level += 1
            elif text[end] == '}': level -= 1
            end += 1
        if received in defined and received.startswith(prefix + '_'):
            branches.append((received, text[match.end():end - 1]))
    def route_calls(block, received, seen=()):
        if len(seen) >= 5: return
        for name in re.findall(r'\b(\w+)\s*\(', block):
            if name in bodies and name not in seen:
                routes.setdefault(name, set()).add(received)
                route_calls(bodies[name], received, (*seen, name))
    for received, block in branches:
        route_calls(block, received)
        if received != mid:
            candidates = types_in(block)
            if len(candidates) == 1: mappings[received] = (received, '0', candidates.pop())
    for function, body in bodies.items():
        for match in re.finditer(r'\bcase\s+(\w+_CC)\s*:(.*?)(?=\bbreak\s*;|\bcase\s+|\bdefault\s*:)', body, re.S):
            code, block = match.groups()
            if code not in defined or not code.startswith(prefix + '_'):
                continue
            candidates = types_in(block)
            sizes = sizes_in(block)
            received = routes.get(function, {mid})
            if len(candidates) == 1 and len(received) == 1:
                mappings[code] = (next(iter(received)), code, candidates.pop())
            elif len(sizes) == 1 and len(received) == 1:
                explicit[code] = (next(iter(received)), code, sizes.pop())
            # A dispatch branch that never consumes the message has no external
            # packet layout to expose (for example, an internal scheduler wakeup).
            message_parameters = [re.findall(r'\w+', parameter)[-1] for parameter in parameters.get(function, [])
                                  if re.search(r'\b(?:CFE_MSG_Message_t|CFE_SB_Buffer_t)\b', parameter)]
            if not message_parameters or candidates or sizes or code in mappings or code in explicit or any(
                    re.search(r'\b' + re.escape(name) + r'\b', block) for name in message_parameters):
                expected.add(code)
    for code, typ in re.findall(r'\[\s*(\w+_CC)\s*\]\s*=\s*sizeof\s*\(\s*(\w+)\s*\)', text):
        if code in defined and code.startswith(prefix + '_'):
            expected.add(code)
            if typ in packet_types: mappings[code] = (mid, code, typ)
    for table_mid, code, typ in re.findall(r'\b\w+\(\s*(\w+_MID)\s*,\s*(\w+_CC|0)\s*,\s*(\w+)\s*,', text):
        if not table_mid.startswith(prefix + '_') or typ not in packet_types:
            continue
        if code == '0': mappings[table_mid] = (table_mid, '0', typ)
        elif code in defined:
            expected.add(code); mappings[code] = (table_mid, code, typ)
    explicit = {code: layout for code, layout in explicit.items() if code not in mappings}
    return mappings, sorted(expected - mappings.keys() - explicit.keys()), explicit


def raw_telemetry_mappings(text, defined):
    """Find initialized byte buffers and their explicit compiler-sized packets."""
    result = {}
    for body in function_bodies(text).values():
        buffers = dict(re.findall(r'\b(?:uint8|uint8_t|unsigned\s+char|char)\s+(\w+)\s*\[([^\]]+)\]', body))
        pointers = dict(re.findall(r'\b(\w+)\s*=\s*\(\s*CFE_MSG_Message_t\s*\*\s*\)\s*&?\s*(\w+)\b', body))
        aliases = dict(re.findall(r'\b(\w+)\s*=\s*CFE_SB_ValueToMsgId\s*\(\s*(\w+)\s*\)', body))
        for _, args in calls(body, 'CFE_MSG_Init'):
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
        pointer = list(calls(expression, 'CFE_MSG_PTR'))
        if pointer: expression = pointer[0][1][0]
        expression = re.sub(r'\([^)]*\*\s*\)', '', expression).strip('& ')
        return resolve(expression.removesuffix('.TelemetryHeader').removesuffix('->TelemetryHeader'))
    mappings, used = {}, set()
    for position, args in calls(text, 'CFE_MSG_Init'):
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
    for _, args in calls(text, 'CFE_SB_TransmitMsg'):
        if not args: continue
        typ = message_type(args[0])
        if typ in packet_types: used.add(typ)
    variable = {}
    for position, args in calls(text, 'CFE_MSG_SetSize'):
        if len(args) != 2: continue
        pointer = list(calls(args[0], 'CFE_MSG_PTR'))
        if not pointer: continue
        expression = pointer[0][1][0].removesuffix('.TelemetryHeader').removesuffix('->TelemetryHeader')
        typ = resolve(expression)
        if typ not in packet_types: continue
        # sizeof(packet) - maximum trailing data + used bytes is the firmware's
        # exact lower bound, not an inferred payload length from field names.
        sizes = re.findall(r'\b' + re.escape(args[1]) + r'\s*=\s*(sizeof\s*\(\s*' + re.escape(typ) + r'\s*\)\s*-\s*[^;+]+)\s*\+', text[:position])
        if sizes: variable[typ] = sizes[-1].strip()
    return mappings, variable, used
