"""Lexical C operations shared by the communication catalog and the architecture view.

These read C text, not a syntax tree. Comments and literals never open or close
a call, and a MID is attributed to code only through a comparison that decides
which message reaches it. Callers report everything else as unresolved.
"""
import re


_LEXEME = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\[\s\S]|[^"\\\n])*"|\'(?:\\[\s\S]|[^\'\\\n])*\'')
_CALL = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
_MID_VALUE = r'(?:CFE_SB_ValueToMsgId|CFE_SB_MSGID_WRAP_VALUE)'


def blank_lexemes(text, literals=True):
    """Blank comments, and literals unless kept, without moving offsets or lines."""
    def blank(match):
        if not literals and match[0][0] in '"\'':
            return match[0]
        return re.sub(r'[^\n]', ' ', match[0])
    return _LEXEME.sub(blank, text)


def closing(text, opening, left='(', right=')'):
    """Offset of the delimiter that closes text[opening], or None when unbalanced."""
    depth = 1
    for position in range(opening + 1, len(text)):
        if text[position] == left:
            depth += 1
        elif text[position] == right:
            depth -= 1
            if not depth:
                return position
    return None


def arguments(text):
    """Split top-level C arguments; commas and brackets in literals stay intact."""
    masked = blank_lexemes(text)
    parts, start, level = [], 0, 0
    for index, char in enumerate(masked):
        if char in '([{':
            level += 1
        elif char in ')]}':
            level -= 1
        elif char == ',' and level == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    return parts + [text[start:].strip()]


def calls(text, symbols=None, start=0, end=None, masked=None):
    """Yield (name, offset, closing offset, arguments) for balanced calls in [start, end).

    ``masked`` is text with comments and literals already blanked; the
    arguments are always taken from ``text``.
    """
    masked = blank_lexemes(text) if masked is None else masked
    end = len(masked) if end is None else end
    for match in _CALL.finditer(masked[start:end]):
        if symbols is not None and match[1] not in symbols:
            continue
        opening = start + match.end() - 1
        finish = closing(masked, opening)
        if finish is not None and finish < end:
            yield match[1], start + match.start(), finish, arguments(text[opening + 1:finish])


def mid_aliases(masked):
    """Variables assigned through the cFE MID conversion API: {variable: {MIDs}}."""
    found = {}
    for alias, mid in re.findall(r'\b(\w+)\s*=\s*' + _MID_VALUE + r'\s*\(\s*(\w+)\s*\)', masked):
        found.setdefault(alias, set()).add(mid)
    return found


def _unwrap(expression):
    expression = expression.strip()
    while expression.startswith('(') and closing(expression, 0) == len(expression) - 1:
        expression = expression[1:-1].strip()
    return expression


def _operand_mid(expression, aliases):
    expression = _unwrap(expression)
    converted = re.fullmatch(_MID_VALUE + r'\s*\(\s*(\w+)\s*\)', expression)
    if converted:
        return converted[1]
    if expression in aliases:
        # A variable assigned different MIDs in different places proves none of them.
        return next(iter(aliases[expression])) if len(aliases[expression]) == 1 else None
    return expression if re.fullmatch(r'[A-Za-z_]\w*_MID', expression) else None


def _tested_mid(predicate, aliases):
    """(MID, negated) when the whole predicate is one CFE_SB_MsgId_Equal test."""
    predicate = _unwrap(predicate)
    negated = predicate.startswith('!')
    if negated:
        predicate = _unwrap(predicate[1:])
    call = re.match(r'CFE_SB_MsgId_Equal\s*\(', predicate)
    if not call or closing(predicate, call.end() - 1) != len(predicate) - 1:
        return None
    operands = arguments(predicate[call.end():-1])
    mids = [mid for mid in (_operand_mid(operand, aliases) for operand in operands) if mid]
    return (mids[0], negated) if len(operands) == 2 and len(mids) == 1 else None


def _rest_of_block(masked, position):
    """End of the statements after position that share its block and case label."""
    depth = 0
    for match in re.finditer(r'[{}]|\b(?:case\b[^:;{}]*|default\s*):', masked[position:]):
        if match[0] == '{':
            depth += 1
        elif match[0] == '}':
            depth -= 1
            if depth < 0:
                return position + match.start()
        elif depth == 0:
            # Another label of the enclosing switch is entered without the test.
            return position + match.start()
    return len(masked)


def mid_regions(masked, aliases=None):
    """Spans of a masked function body that run only for one received MID.

    ``if (CFE_SB_MsgId_Equal(a, b)) {...}`` covers its block. A negated test whose
    block ends with return covers the rest of its own block. Other predicates,
    unbraced branches and runtime operands give no evidence.
    Returns [(MID, begin, end)].
    """
    aliases = {**(aliases or {}), **mid_aliases(masked)}
    regions = []
    for condition in re.finditer(r'\bif\s*\(', masked):
        opening = condition.end() - 1
        finish = closing(masked, opening)
        if finish is None:
            continue
        tested = _tested_mid(masked[opening + 1:finish], aliases)
        brace = re.match(r'\s*\{', masked[finish + 1:])
        if not tested or not brace:
            continue
        begin = finish + brace.end()
        block_end = closing(masked, begin, '{', '}')
        if block_end is None:
            continue
        mid, negated = tested
        if not negated:
            regions.append((mid, begin + 1, block_end))
        elif re.search(r'(?:^|[;{}])\s*return\b[^;{}]*;\s*$', masked[begin + 1:block_end]):
            # After `else if`, the remaining code is also reached from earlier branches.
            chained = re.search(r'\belse\Z', masked[:condition.start()].rstrip()[-5:])
            if not chained:
                regions.append((mid, block_end + 1, _rest_of_block(masked, block_end + 1)))
    return regions


def mids_at(regions, entry, position):
    """MID of the innermost region containing position, otherwise the entry MIDs."""
    inside = [(end - begin, mid) for mid, begin, end in regions if begin <= position < end]
    return {min(inside)[1]} if inside else set(entry)


def entry_routes(regions, sites):
    """MIDs with which each function is entered, following resolved local calls.

    ``regions`` maps a function to its mid_regions and ``sites`` maps it to
    [(callee, position)]. A call inside a region passes that MID; elsewhere it
    passes the MIDs of the caller itself.
    """
    routes = {function: set() for function in sites}
    changed = True
    while changed:
        changed = False
        for function, calls_made in sites.items():
            for callee, position in calls_made:
                received = mids_at(regions.get(function, []), routes[function], position)
                if callee in routes and not received <= routes[callee]:
                    routes[callee] |= received
                    changed = True
    return routes
