"""Source relationships for the two first-contact commands, frozen with their wire catalog."""
from ground_station.c_source import calls
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


def first_contact_routes(root, catalog):
    active = {a['name'] for a in catalog['apps']}
    index = SourceIndex(root)
    source = {}
    details = {}
    for name in ('ci_lab', 'to_lab', 'sample_app', 'cfe_evs'):
        if name not in active:
            continue
        directory = root / 'cFS/cfe/modules/evs' if name == 'cfe_evs' else module_directory(root, 'apps', name)
        source[name] = index.application(directory)
        details[name] = describe_application(source[name], root=root)
    result = {'commands': {}, 'returns': {}}
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
        if cmd['app'] not in ('to_lab', 'sample_app'):
            continue
        for sub in details.get(cmd['app'], {}).get('subscriptions', []):
            if sub['kind'] == 'direct' and sub['mid']['symbol'] == cmd.get('mid_symbol'):
                result['commands'].setdefault(cmd['id'], []).append(
                    dict(app=cmd['app'], mid=cmd['mid'], pipe=sub['pipe'], source=sub['source'], via=sub.get('via', [])))
    subscribed = {row['mid'] for row in catalog['transport'].get('subscriptions', [])}
    for packet in catalog['packets']:
        if packet['mid'] not in subscribed:
            continue
        publishers = [p['call_source'] for pub in details.get(packet['app'], {}).get('publications', [])
                      if pub['mid']['symbol'] == packet.get('mid_symbol') for p in pub['publishers']]
        result['returns'][str(packet['mid'])] = dict(app=packet['app'], packet=packet['id'], publishers=publishers)
    return result
