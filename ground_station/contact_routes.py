"""Source relationships for catalog commands and downlinks, frozen with their wire catalog.

These are configured source routes, not a trace of runtime execution. Numeric
MIDs from the compiled catalog take precedence over source default constants.
"""
from collections import defaultdict
from pathlib import Path
import re

from ground_station.c_source import arguments, blank_lexemes, calls, closing
from project.architecture_details import describe_application
from project.flight_sources import module_directory
from project.source_index import SourceIndex


def _io(root, index, symbols):
    """Keep calls from the same function together, including their pipe arguments."""
    groups = []
    for module in index['source_modules']:
        path = module['path']
        if not path.endswith('.c') or '_eds_' in path:
            continue
        text = (root / path).read_text()
        functions = [fn for fn in index['functions'] if fn['path'] == path]
        grouped = {}
        for api, offset, _, args in calls(text, symbols):
            line = text.count('\n', 0, offset) + 1
            fn = next((fn for fn in functions if fn['start_line'] <= line <= fn['end_line']), None)
            if fn:
                group = grouped.setdefault(fn['id'], {})
                # Several calls in one function need dataflow analysis to disambiguate.
                group[api] = None if api in group else dict(path=path, line=line, args=args)
        groups.extend(group for group in grouped.values() if all(group.values()))
    return groups


def _indirect_routes(root, index):
    """Resolve bounded const-MID loops and explicit local packet-pointer aliases.

    Dynamic tables, index ranges other than the full const array and reassigned
    pointers are deliberately left unresolved.
    """
    subscriptions, initializations, transmissions = [], [], []
    for module in index['source_modules']:
        path = module['path']
        if not path.endswith('.c') or '_eds_' in path:
            continue
        text = (root / path).read_text()
        lines = text.splitlines(keepends=True)
        for fn in (f for f in index['functions'] if f['path'] == path):
            body = blank_lexemes(''.join(lines[fn['start_line'] - 1:fn['end_line']]))

            def ref(offset, symbol):
                return dict(path=path, line=fn['start_line'] + body.count('\n', 0, offset), symbol=symbol)

            for match in re.finditer(r'\bconst\s+CFE_SB_MsgId_Atom_t\s+(\w+)\s*\[\s*\]\s*=\s*\{([^{}]*)\}', body):
                array, entries = match[1], arguments(match[2])
                if not all(re.fullmatch(r'\w+_MID', entry) for entry in entries):
                    continue
                for _, loop, end, _ in calls(body, {'for'}):
                    parts = re.sub(r'\s+', '', body[body.index('(', loop) + 1:end]).split(';')
                    variable = re.fullmatch(r'(\w+)=0', parts[0]) if len(parts) == 3 else None
                    if not variable or match.start() > loop:
                        continue
                    variable = variable[1]
                    bound = parts[1].replace('(', '').replace(')', '')
                    if bound != f'{variable}<sizeof{array}/sizeof{array}[0]' or parts[2] not in (f'++{variable}', f'{variable}++'):
                        continue
                    opening = end + 1
                    while opening < len(body) and body[opening].isspace():
                        opening += 1
                    finish = closing(body, opening, '{', '}') if body[opening:opening + 1] == '{' else None
                    if finish is None:
                        continue
                    for api, position, _, args in calls(body, start=opening, end=finish):
                        if not api.startswith('CFE_SB_Subscribe') or len(args) < 2:
                            continue
                        expression = re.sub(r'\s+', '', args[0])
                        if expression != f'CFE_SB_ValueToMsgId({array}[{variable}])':
                            continue
                        for mid in entries:
                            subscriptions.append(dict(mid={'symbol': mid, 'value': None}, pipe=args[1],
                                                      kind='direct', source=ref(position, api),
                                                      via=[ref(match.start(), array), ref(loop, 'for')]))

            aliases = {}
            for assignment in re.finditer(r'\b(\w+)\s*=\s*(?:\(\s*\w+(?:\s+\w+)*\s*\*\s*\)\s*|&\s*)'
                                          r'(\w+(?:\s*(?:\.|->)\s*\w+)*)\s*;', body):
                name = assignment[1]
                # All writes, including unsupported ones, invalidate a reused pointer.
                if len(re.findall(r'\b' + re.escape(name) + r'\s*=(?!=)', body)) == 1:
                    aliases[name] = (re.sub(r'\s+', '', assignment[2]).replace('->', '.'),
                                     ref(assignment.start(), name), assignment.start())

            def packet(expression, position):
                value = re.sub(r'\s+', '', expression).replace('->', '.')
                value = re.sub(r'^(?:CFE_MSG_PTR|CFE_SB_MSG_PTR)\((.*)\)$', r'\1', value).lstrip('&')
                value = re.sub(r'\.(?:TelemetryHeader|CommandHeader|Msg)$', '', value)
                via, seen = [], set()
                while value.split('.')[0] in aliases and value.split('.')[0] not in seen:
                    name = value.split('.')[0]
                    seen.add(name)
                    replacement, source, assigned_at = aliases[name]
                    if assigned_at >= position:
                        break
                    value = replacement + value[len(name):]
                    via.append(source)
                name = value.split('.')[0]
                # Simple buffer names and local/parameter structs belong only to
                # their function; equal names in other functions are not aliases.
                local = ('.' not in value or re.search(r'\b' + re.escape(name) + r'\b', fn['signature'])
                         or re.search(r'(?:^|[;{}])\s*(?:const\s+|static\s+)?\w+\s+\**\s*'
                                      + re.escape(name) + r'\b', body, re.M))
                return (fn['id'] if local else '', value), via

            for api, position, _, args in calls(body, {'CFE_MSG_Init', 'CFE_SB_TransmitMsg', 'CFE_SB_TransmitBuffer',
                                                     'CFE_SB_SendMsg', 'CFE_SB_ZeroCopySend'}):
                if not args:
                    continue
                identity, via = packet(args[0], position)
                if api == 'CFE_MSG_Init' and len(args) >= 2:
                    mids = set(re.findall(r'\b\w+_MID\b', args[1]))
                    if len(mids) == 1:
                        initializations.append((identity, mids.pop(), via))
                elif api != 'CFE_MSG_Init':
                    transmissions.append((identity, ref(position, api), via))
    publications = []
    for identity, mid, initialization_aliases in initializations:
        publishers = [dict(call_source=source, via=initialization_aliases + aliases)
                      for destination, source, aliases in transmissions
                      if destination == identity and (aliases or initialization_aliases)]
        if publishers:
            publications.append(dict(mid={'symbol': mid, 'value': None}, publishers=publishers, kind='packet'))
    return subscriptions, publications


def first_contact_routes(root, catalog):
    root = Path(root).resolve()
    active = {a['name']: a for a in catalog['apps']}
    index = SourceIndex(root)
    source = {}
    details = {}
    for name, app in sorted(active.items()):
        core = app.get('kind') == 'core' or name.startswith('cfe_')
        directory = (root / 'cFS/cfe/modules' / name.removeprefix('cfe_')
                     if core else module_directory(root, 'apps', name))
        if not directory.is_dir():
            continue
        source[name] = index.application(directory)
        details[name] = describe_application(source[name], root=root)
        subscriptions, publications = _indirect_routes(root, source[name])
        details[name]['subscriptions'].extend(subscriptions)
        details[name]['publications'].extend(publications)
    result = {'commands': {}, 'returns': {}}
    # A source constant may have a different default than the selected build.
    # Resolve named MIDs through the compiler's catalog, including aliases used
    # by another active application's subscription to the same wire MID.
    mids = defaultdict(set)
    for packet in [*catalog['commands'], *catalog['packets']]:
        if packet.get('mid_symbol'):
            mids[packet['mid_symbol']].add(packet['mid'])

    def wire_mid(reference):
        values = mids.get(reference.get('symbol'))
        if values:
            return next(iter(values)) if len(values) == 1 else None
        return reference.get('value')

    receivers = defaultdict(list)
    producers = defaultdict(list)
    for app, description in details.items():
        for sub in description.get('subscriptions', []):
            mid = wire_mid(sub['mid'])
            if mid is None:
                continue
            route = dict(app=app, mid=mid, pipe=sub['pipe'], source=sub['source'], via=sub.get('via', []))
            # Conditional/static-table relationships remain explicitly source
            # configuration; they are not evidence of a live subscription.
            for key in ('kind', 'conditions', 'table'):
                if key in sub:
                    route[key] = sub[key]
            if route not in receivers[mid]:
                receivers[mid].append(route)
        for publication in description.get('publications', []):
            mid = wire_mid(publication['mid'])
            if mid is None:
                continue
            for publisher in publication.get('publishers', []):
                ref = publisher.get('call_source') or publisher
                route = dict(ref, app=app)
                if publisher.get('via'):
                    route['via'] = publisher['via']
                for key in ('kind', 'conditions', 'table'):
                    if key in publication:
                        route[key] = publication[key]
                if route not in producers[mid]:
                    producers[mid].append(route)
    # Preserve every resolved bus relationship for the scalable Ground view.
    # Apps with no resolved relationship stay visible without invented edges.
    result['applications'] = {
        name: {'subscriptions': [route for rows in receivers.values() for route in rows if route['app'] == name],
               'publications': [dict(route, mid=mid) for mid, rows in producers.items()
                                for route in rows if route['app'] == name]}
        for name in active
    }
    for name in ('ci_lab', 'to_lab'):
        if name not in source:
            continue
        if name == 'ci_lab':
            for group in _io(root, source[name], {'OS_SocketRecvFrom', 'CFE_SB_TransmitBuffer'}):
                if len(group) == 2:
                    result['ingress'] = dict(app=name, receive=group['OS_SocketRecvFrom'], publish=group['CFE_SB_TransmitBuffer'])
                    break
        else:
            groups = _io(root, source[name], {'CFE_SB_ReceiveBuffer', 'OS_SocketSendTo', 'CFE_SB_SubscribeEx'})
            subscriptions = [g['CFE_SB_SubscribeEx'] for g in groups if 'CFE_SB_SubscribeEx' in g]
            for group in groups:
                read, send = group.get('CFE_SB_ReceiveBuffer'), group.get('OS_SocketSendTo')
                if read and send:
                    sub = next((s for s in subscriptions if s['args'][1] == read['args'][1]), None)
                    if sub:
                        result['egress'] = dict(app=name, pipe=read['args'][1], subscribe=sub, receive=read, send=send,
                                                table=catalog['transport'].get('subscription_source'))
                        break
    for cmd in catalog['commands']:
        result['commands'][cmd['id']] = receivers.get(cmd['mid'], [])
    subscribed = {row['mid'] for row in catalog['transport'].get('subscriptions', [])}
    for packet in catalog['packets']:
        if packet['mid'] not in subscribed:
            continue
        result['returns'][str(packet['mid'])] = dict(
            app=packet['app'], packet=packet['id'], publishers=producers.get(packet['mid'], []))
    return result
