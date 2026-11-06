"""Small behavior diagrams derived from indexed C definitions and API calls.

Blocks group functions by responsibility, not by file. An edge is a call found in
the source, or an API used inside a function, not an execution order. The lexical
index includes conditional branches and cannot resolve every callback or queue.
"""
from collections import defaultdict, deque
from pathlib import Path
import re

from interface.backend.source_index import mask_source
from interface.backend.architecture_details import describe_application


RECEIVE = {'CFE_SB_ReceiveBuffer', 'CFE_SB_RcvMsg'}
PUBLISH = {'CFE_SB_TransmitMsg', 'CFE_SB_TransmitBuffer', 'CFE_SB_SendMsg',
           'CFE_SB_ZeroCopySend', 'CFE_SB_ZeroCopyPass'}
TIMERS = {'OS_TimerAdd', 'OS_TimerCreate', 'OS_TimerSet', 'OS_TimeBaseSet'}
DISPATCH = {'CFE_MSG_GetMsgId', 'CFE_MSG_GetFcnCode', 'CFE_SB_GetMsgId', 'CFE_SB_GetCmdCode'}
FILE_APIS = {'OS_OpenCreate', 'OS_cp', 'OS_mv', 'OS_remove', 'OS_rename', 'OS_mkdir',
             'OS_rmdir', 'OS_stat', 'OS_chmod', 'OS_DirectoryOpen', 'OS_DirectoryRead',
             'OS_FileSysStatVolume', 'OS_FileOpenCheck'}
FILE_STREAM_APIS = {'OS_read', 'OS_write', 'OS_lseek'}
NETWORK_RX = {'OS_SocketRecvFrom', 'OS_SocketRecv', 'recv', 'recvfrom', 'recvmsg'}
NETWORK_TX = {'OS_SocketSendTo', 'OS_SocketSend', 'send', 'sendto', 'sendmsg'}
MONITOR_APIS = {'CFE_PSP_WatchdogService', 'CFE_ES_GetAppInfo', 'CFE_ES_GetTaskInfo', 'CFE_ES_GetGenCount'}
COMPUTATION = {'checksums', 'monitoring', 'packet_assembly', 'evaluation'}

ROLE_ORDER = {'entry': 0, 'initialize': 1, 'receive': 2, 'dispatch': 3,
              'commands': 4, 'work': 5, 'publish': 6, 'timer': 7}
ROLE_ICONS = {'entry': 'play', 'initialize': 'settings', 'receive': 'arrow-down',
              'dispatch': 'workflow', 'commands': 'terminal', 'work': 'cpu',
              'publish': 'arrow-up-right', 'timer': 'rotate'}
ROLE_TITLES = {'initialize': 'Initialize', 'receive': 'Receive messages', 'dispatch': 'Route messages',
               'commands': 'Handle commands', 'timer': 'Configure timing'}
# Title of a work block whose functions share exactly one capability.
WORK_TITLES = {'sensors': 'Sensor I/O', 'network_receive': 'Receive uplink data',
               'network_send': 'Send network data', 'files': 'Access files',
               'checksums': 'Calculate checksums', 'monitoring': 'Monitor execution',
               'packet_assembly': 'Assemble packets', 'evaluation': 'Evaluate conditions'}
FACET_LABELS = {'receive': 'receives', 'publish': 'publishes', 'timer': 'configures'}


def _words(symbol):
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', symbol).lower().split('_')


def _reference(function, **extra):
    reference = {key: function[key] for key in ('id', 'symbol', 'path', 'line', 'end_line')}
    reference.update(extra)
    return reference


def _entry(functions, symbol):
    if symbol:
        matches = [fn for fn in functions if fn['symbol'] == symbol]
        if len(matches) == 1:
            return matches[0]
        return None
    matches = [fn for fn in functions if 'CFE_ES_RunLoop' in fn.get('calls', [])]
    if len(matches) == 1:
        return matches[0]
    # Without a startup entry symbol, several run loops leave the entry unknown.
    return None


def _capabilities(function, application_has_files):
    calls = set(function.get('calls', []))
    words = set(_words(function['symbol']))
    capabilities = set()
    if 'sensors' in Path(function['path']).parts:
        capabilities.add('sensors')
    if calls & NETWORK_RX:
        capabilities.add('network_receive')
    if calls & NETWORK_TX:
        capabilities.add('network_send')
    if calls & FILE_APIS or application_has_files and calls & FILE_STREAM_APIS:
        capabilities.add('files')
    if 'CFE_ES_CalculateCRC' in calls:
        capabilities.add('checksums')
    if calls & MONITOR_APIS:
        capabilities.add('monitoring')
    if words & {'evaluate', 'compare'}:
        capabilities.add('evaluation')
    if ('memcpy' in calls and calls & {'CFE_MSG_GetMsgId', 'CFE_SB_GetMsgId'} and
            words & {'incoming', 'assemble', 'combine', 'combined'}):
        capabilities.add('packet_assembly')
    return capabilities


def _primary_role(function, entry, application_has_files):
    calls = set(function.get('calls', []))
    words = set(_words(function['symbol']))
    if entry and function['id'] == entry['id']:
        return 'entry'
    if _words(function['symbol'])[-1] in {'init', 'initialize', 'startup'} or calls & {'CFE_ES_RegisterApp', 'CFE_SB_CreatePipe'}:
        return 'initialize'
    # Copying incoming message fields is processing, even when the MID is read.
    if 'packet_assembly' in _capabilities(function, application_has_files):
        return 'work'
    if (calls & DISPATCH and not words & {'verify', 'validate', 'check'}) or words & {'dispatch'} or {'task', 'pipe'} <= words:
        return 'dispatch'
    if words & {'verify', 'validate'} and not re.search(r'\w+Cmd_t\b', function.get('signature', '')):
        return None
    if words & {'cmd', 'command', 'commands', 'noop'} or re.search(r'\w+Cmd_t\b', function.get('signature', '')):
        # A housekeeping request handler that publishes belongs to the publish block.
        if calls & PUBLISH and words & {'hk', 'housekeeping', 'telemetry', 'tlm'}:
            return 'publish'
        return 'commands'
    if _capabilities(function, application_has_files):
        return 'work'
    if calls & PUBLISH:
        return 'publish'
    if calls & RECEIVE:
        return 'receive'
    if words & {'wakeup', 'wake', 'tick'} and any(name for name in calls if not name.startswith(('CFE_', 'OS_'))):
        return 'work'
    return None


def _title(role, functions, capabilities):
    calls = {name for fn in functions for name in fn.get('calls', [])}
    if role == 'entry':
        return 'Application loop' if 'CFE_ES_RunLoop' in calls else 'Application entry'
    if role == 'publish':
        publishers = [fn for fn in functions if set(fn.get('calls', [])) & PUBLISH]
        telemetry = publishers and all('CFE_SB_TimeStampMsg' in fn.get('calls', []) for fn in publishers)
        return 'Publish telemetry' if telemetry else 'Publish messages'
    if role != 'work':
        return ROLE_TITLES[role]
    if len(capabilities) == 1:
        return WORK_TITLES[next(iter(capabilities))]
    return 'Process application data'


def summarize_application(app, entry_symbol=None, *, root=None):
    """Summarize a SourceIndex application in <= 8 behavior blocks.

    ``app`` requires ``functions`` and ``call_edges`` from SourceIndex. Supplying
    the entry symbol from native startup removes ambiguity without app manifests.
    ``root`` adds source details and line references for API calls.
    """
    functions = app.get('functions', [])
    by_id = {function['id']: function for function in functions}
    entry = _entry(functions, entry_symbol)
    files = any(set(fn.get('calls', [])) & FILE_APIS for fn in functions)
    primary = {fn['id']: _primary_role(fn, entry, files) for fn in functions}
    groups = defaultdict(dict)
    graph = defaultdict(set)
    names = defaultdict(list)
    for fn in functions:
        names[fn['symbol']].append(fn)
    for edge in app.get('call_edges', []):
        if edge.get('source') in by_id and edge.get('target') in by_id:
            graph[edge['source']].add(edge['target'])
    # EDS and regular builds can define the same handler in separate files. When
    # every candidate has the same role, the call goes to the first one and the
    # others are kept as alternatives; which one is compiled is not determined.
    alternatives = {}
    for fn in functions:
        resolved = {by_id[ident]['symbol'] for ident in graph[fn['id']]}
        for symbol in set(fn.get('calls', [])) - resolved:
            candidates = names[symbol]
            local = [candidate for candidate in candidates if candidate['path'] == fn['path']]
            visible = [candidate for candidate in candidates if not candidate.get('static') or candidate['path'].endswith('.h')]
            candidates = local or visible
            roles = {primary[candidate['id']] for candidate in candidates}
            if len(candidates) > 1 and len(roles) == 1 and None not in roles:
                representative = sorted(candidates, key=lambda candidate: (candidate['path'], candidate['line']))[0]
                graph[fn['id']].add(representative['id'])
                alternatives[(fn['id'], representative['id'])] = candidates
    # Computation-only functions (checksums, comparisons, ...) are work only when
    # reachable from the entry, a dispatcher, a command handler or a receiver.
    reachable = {fn['id'] for fn in functions if primary[fn['id']] in
                 {'entry', 'dispatch', 'commands', 'receive'}}
    pending = deque(reachable)
    while pending:
        for target in graph[pending.popleft()]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    for fn in functions:
        capabilities = _capabilities(fn, files)
        if (primary[fn['id']] == 'work' and capabilities and capabilities <= COMPUTATION and
                fn['id'] not in reachable):
            primary[fn['id']] = None
    for fn in functions:
        if primary[fn['id']]:
            groups[primary[fn['id']]][fn['id']] = fn

    # A function that receives, publishes or configures timers also joins that
    # role's block; this adds no call edge between its blocks.
    facets = {'receive': RECEIVE, 'publish': PUBLISH, 'timer': TIMERS}
    for role, apis in facets.items():
        for fn in functions:
            if set(fn.get('calls', [])) & apis:
                groups[role][fn['id']] = fn

    root = Path(root).resolve() if root else None
    source_cache = {}

    def source_reference(fn, role):
        apis = sorted(set(fn.get('calls', [])) & facets.get(role, set()))
        if not root or not apis:
            return _reference(fn)
        try:
            path = root / fn['path']
            if not path.resolve().is_relative_to(root):
                return _reference(fn)
            if fn['path'] not in source_cache:
                source_cache[fn['path']] = mask_source(path.read_text()).splitlines()
            lines = source_cache[fn['path']]
            for line in range(fn['line'] - 1, min(len(lines), fn['end_line'])):
                for api in apis:
                    if re.search(r'\b' + re.escape(api) + r'\s*\(', lines[line]):
                        return _reference(fn, line=line + 1, end_line=line + 1, api=api)
        except (OSError, UnicodeError):
            pass
        return _reference(fn)

    distances = {entry['id']: 0} if entry else {}
    pending = deque(distances)
    while pending:
        current = pending.popleft()
        for target in sorted(graph[current]):
            if target not in distances:
                distances[target] = distances[current] + 1
                pending.append(target)

    def function_key(fn):
        return (distances.get(fn['id'], len(functions)), fn.get('static', False),
                0 if entry and fn['path'] == entry['path'] else 1,
                fn['path'], fn['line'], fn['symbol'])

    nodes = []
    for role in sorted(groups, key=ROLE_ORDER.get):
        members = sorted(groups[role].values(), key=function_key)
        capabilities = set()
        if role == 'work':
            for fn in members:
                capabilities |= _capabilities(fn, files)
        apis = {call for fn in members for call in fn.get('calls', []) if call.startswith(('CFE_', 'OS_'))}
        if role in facets:
            apis &= facets[role]
        references = [source_reference(fn, role) for fn in members]
        node = {'id': role, 'role': role, 'order': ROLE_ORDER[role], 'icon': ROLE_ICONS[role],
                'title': _title(role, members, capabilities), 'source': references[0],
                'functions': references, 'function_count': len(members),
                'apis': sorted(apis), 'capabilities': sorted(capabilities)}
        nodes.append(node)

    edge_map = {}

    def add_edge(source, target, first, last, *, kind='calls', label='calls', via=(), candidate_sources=()):
        if source == target or source not in groups or target not in groups:
            return
        key = (source, target, kind)
        if key not in edge_map:
            edge_map[key] = {'source': source, 'target': target, 'kind': kind, 'label': label, 'count': 0, 'examples': []}
        edge = edge_map[key]
        edge['count'] += 1
        if len(edge['examples']) < 3:
            example = {'source': _reference(first), 'target': source_reference(last, target),
                       'via': [_reference(by_id[ident]) for ident in via]}
            if candidate_sources:
                example['alternatives'] = [_reference(fn) for fn in candidate_sources]
            edge['examples'].append(example)

    # Edges pass through helpers without a role and keep the call path as examples.
    # An edge means some member can call a member of the target block.
    for first in functions:
        source = primary[first['id']]
        if not source:
            continue
        pending = deque((ident, ()) for ident in sorted(graph[first['id']]))
        seen = {first['id']}
        while pending:
            ident, via = pending.popleft()
            if ident in seen:
                continue
            seen.add(ident)
            target = primary[ident]
            if target:
                if target != source:
                    caller = via[-1] if via else first['id']
                    candidates = alternatives.get((caller, ident), ())
                    add_edge(source, target, first, by_id[ident], via=via, candidate_sources=candidates)
                continue
            if len(via) < 4:
                pending.extend((child, (*via, ident)) for child in sorted(graph[ident]))
    for role, apis in facets.items():
        for fn in groups.get(role, {}).values():
            if primary[fn['id']] and primary[fn['id']] != role:
                add_edge(primary[fn['id']], role, fn, fn, kind='uses', label=FACET_LABELS[role])

    edges = sorted(edge_map.values(), key=lambda edge: (ROLE_ORDER[edge['source']], ROLE_ORDER[edge['target']], edge['kind']))
    covered = set()
    for group in groups.values():
        covered |= set(group)
    return {'nodes': nodes, 'edges': edges, 'entry': _reference(entry) if entry else None,
            'details': describe_application(app, root=root) if root else {},
            'entry_symbol': entry_symbol or (entry['symbol'] if entry else None),
            'scope': 'Source-level calls and API uses; conditional branches included. Not a runtime trace.',
            'omitted_function_count': len(functions) - len(covered)}
