"""Small behavior diagrams derived from indexed C definitions and API calls.

Blocks describe responsibilities, not files. Edges only represent observed calls
or an API used inside a function; they do not claim runtime ordering. The lexical
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


# Sections whose prose introduces an application in a README.
INTRODUCTION = {'introduction', 'overview', 'purpose', 'description'}
# cFS READMEs open with a sentence stating only that the app belongs to the bundle.
MEMBERSHIP = ('plug in to', 'plug-in to', 'framework component')


def _introduction(lines):
    """Prose paragraphs with their first line, up to the first non-introduction section."""
    paragraphs, current, first, fenced, titled = [], [], 0, False, False
    for number, line in enumerate([*lines, ''], 1):
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            fenced = not fenced
            continue
        heading = not fenced and stripped.startswith('#')
        if stripped and not fenced and not heading and not stripped.startswith(('![', '- ', '* ', '|')):
            first = first or number
            current.append(stripped)
            continue
        if current:
            paragraphs.append((' '.join(current), first))
            current, first = [], 0
        if heading:
            # The first heading is the title; any other section ends the introduction.
            if titled and stripped.lstrip('#').strip().lower() not in INTRODUCTION:
                break
            titled = True
    return paragraphs


def _documented_purpose(app, root):
    """First sentence of the app's README.md introduction that says what it does.

    This quotes local documentation; it is not an app-name lookup table or an
    inferred runtime feature. Without a README.md, or without such a sentence,
    the caller keeps the summary of observed source calls. A README.md that
    exists but cannot be used returns only an 'error'.
    """
    if root is None or not app.get('path'):
        return None
    path = root / app['path'] / 'README.md'
    try:
        if not path.resolve().is_relative_to(root):
            return {'error': 'README.md points outside the workspace; it was not read.'}
        if path.stat().st_size > 128_000:
            return {'error': 'README.md exceeds 128 kB; it was not read.'}
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as error:
        return {'error': 'README.md could not be read: ' + str(error)}
    for paragraph, line in _introduction(lines):
        paragraph = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', paragraph).replace('`', '').replace('*', '')
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])', paragraph):
            if not any(marker in sentence.lower() for marker in MEMBERSHIP):
                text = sentence if len(sentence) <= 500 else sentence[:499].rstrip() + '…'
                return {'text': text, 'source': {'path': path.relative_to(root).as_posix(),
                                                 'line': line, 'kind': 'documentation'}}
    return None


def _words(symbol):
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', symbol).lower().split('_')


def _reference(function, **extra):
    return {**{key: function[key] for key in ('id', 'symbol', 'path', 'line', 'end_line')}, **extra}


def _entry(functions, symbol):
    if symbol:
        matches = [fn for fn in functions if fn['symbol'] == symbol]
        if len(matches) == 1:
            return matches[0]
        return None
    matches = [fn for fn in functions if 'CFE_ES_RunLoop' in fn.get('calls', [])]
    if len(matches) == 1:
        return matches[0]
    # A source name alone does not establish which of several entrypoints runs.
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
    # Reading a message ID while copying its data is application processing,
    # rather than evidence that the function selects a command handler.
    if 'packet_assembly' in _capabilities(function, application_has_files):
        return 'work'
    if (calls & DISPATCH and not words & {'verify', 'validate', 'check'}) or words & {'dispatch'} or {'task', 'pipe'} <= words:
        return 'dispatch'
    if words & {'verify', 'validate'} and not re.search(r'\w+Cmd_t\b', function.get('signature', '')):
        return None
    if words & {'cmd', 'command', 'commands', 'noop'} or re.search(r'\w+Cmd_t\b', function.get('signature', '')):
        # Housekeeping commands are represented by what they actually do: publish.
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


def _describe(role, functions, capabilities):
    calls = {name for fn in functions for name in fn.get('calls', [])}
    if role == 'entry':
        return ('Application loop', 'Owns the cFE application run loop.') if 'CFE_ES_RunLoop' in calls else (
            'Application entry', 'Entry function configured by the native startup script.')
    if role == 'initialize':
        pieces = []
        if 'CFE_SB_CreatePipe' in calls or any(name.startswith('CFE_SB_Subscribe') for name in calls):
            pieces.append('message pipes and subscriptions')
        if any(name.startswith('CFE_TBL_') for name in calls):
            pieces.append('tables')
        if 'CFE_EVS_Register' in calls:
            pieces.append('event reporting')
        return ('Initialize', 'Sets up ' + ', '.join(pieces) + '.' if pieces else 'Sets up application state and resources.')
    if role == 'receive':
        return ('Receive messages', 'Receives software-bus messages for the application to process.')
    if role == 'dispatch':
        return ('Route messages', 'Reads message IDs or function codes and selects the corresponding handler.')
    if role == 'commands':
        return ('Handle commands', 'Implements the application’s command handlers.')
    if role == 'publish':
        publishers = [fn for fn in functions if set(fn.get('calls', [])) & PUBLISH]
        telemetry = publishers and all('CFE_SB_TimeStampMsg' in fn.get('calls', []) for fn in publishers)
        return ('Publish telemetry' if telemetry else 'Publish messages',
                'Time-stamps and publishes telemetry on the software bus.' if telemetry else
                'Publishes outgoing messages on the software bus.')
    if role == 'timer':
        return ('Configure timing', 'Configures OS timers used by the application.')
    descriptions = []
    if 'sensors' in capabilities:
        descriptions.append('accesses sensor interfaces')
    if 'network_receive' in capabilities:
        descriptions.append('receives network data')
    if 'network_send' in capabilities:
        descriptions.append('sends network data')
    if 'files' in capabilities:
        descriptions.append('accesses files and directories')
    if 'checksums' in capabilities:
        descriptions.append('calculates checksums with cFE CRC services')
    if 'monitoring' in capabilities:
        descriptions.append('reads execution information or services the watchdog')
    if 'packet_assembly' in capabilities:
        descriptions.append('copies incoming message fields into application buffers')
    if 'evaluation' in capabilities:
        descriptions.append('evaluates expressions and compares values')
    title = ('Sensor I/O' if capabilities == {'sensors'} else
             'Receive uplink data' if capabilities == {'network_receive'} else
             'Send network data' if capabilities == {'network_send'} else
             'Access files' if capabilities == {'files'} else
             'Calculate checksums' if capabilities == {'checksums'} else
             'Monitor execution' if capabilities == {'monitoring'} else
             'Assemble packets' if capabilities == {'packet_assembly'} else
             'Evaluate conditions' if capabilities == {'evaluation'} else 'Process application data')
    description = '; '.join(descriptions)
    return title, (description[:1].upper() + description[1:] + '.' if description else
                   'Contains application-specific processing.')


def summarize_application(app, entry_symbol=None, *, root=None):
    """Summarize a SourceIndex application in <= 8 behavior blocks.

    ``app`` requires ``functions`` and ``call_edges`` from SourceIndex. Supplying
    the entry symbol from native startup removes ambiguity without app manifests.
    ``root`` only improves API-call navigation; no source or runtime is modified.
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
    # EDS and regular builds can define the same handler in separate files. A
    # shared responsibility is still known when all visible candidates agree;
    # the exact compiled definition is deliberately left as an alternative.
    alternatives = {}
    for fn in functions:
        resolved = {by_id[ident]['symbol'] for ident in graph[fn['id']]}
        for symbol in set(fn.get('calls', [])) - resolved:
            candidates = names[symbol]
            local = [candidate for candidate in candidates if candidate['path'] == fn['path']]
            candidates = local or [candidate for candidate in candidates
                                   if not candidate.get('static') or candidate['path'].endswith('.h')]
            roles = {primary[candidate['id']] for candidate in candidates}
            if len(candidates) > 1 and len(roles) == 1 and None not in roles:
                representative = sorted(candidates, key=lambda candidate: (candidate['path'], candidate['line']))[0]
                graph[fn['id']].add(representative['id'])
                alternatives[(fn['id'], representative['id'])] = candidates
    # Computation symbols and APIs are useful evidence only on an observed
    # entry/handler call path. An unrelated Compare or CRC utility must not
    # become the application's principal behavior simply by existing on disk.
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

    # API facets expose behavior inside a main routine without inventing a second
    # function or an unconditional sequential edge (e.g. scheduler wait + send).
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
        capabilities = {cap for fn in members for cap in _capabilities(fn, files)} if role == 'work' else set()
        title, summary = _describe(role, members, capabilities)
        apis = {call for fn in members for call in fn.get('calls', []) if call.startswith(('CFE_', 'OS_'))}
        if role in facets:
            apis &= facets[role]
        references = [source_reference(fn, role) for fn in members]
        nodes.append({'id': role, 'role': role, 'order': ROLE_ORDER[role], 'icon': ROLE_ICONS[role],
                      'title': title, 'summary': summary, 'source': references[0],
                      'functions': references, 'function_count': len(members),
                      'apis': sorted(apis), 'capabilities': sorted(capabilities)})

    edge_map = {}

    def add_edge(source, target, first, last, *, kind='calls', label='calls', via=(), candidate_sources=()):
        if source == target or source not in groups or target not in groups:
            return
        key = (source, target, kind)
        edge = edge_map.setdefault(key, {'source': source, 'target': target, 'kind': kind,
                                         'label': label, 'count': 0, 'examples': []})
        edge['count'] += 1
        if len(edge['examples']) < 3:
            example = {'source': _reference(first), 'target': source_reference(last, target),
                       'via': [_reference(by_id[ident]) for ident in via]}
            if candidate_sources:
                example['alternatives'] = [_reference(fn) for fn in candidate_sources]
            edge['examples'].append(example)

    # Collapse supporting helpers, retaining the actual call path as evidence.
    # A node arrow means one member can call a member of the destination, not
    # that every member runs in that order or that a live app is executing it.
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
                    add_edge(source, target, first, by_id[ident], via=via,
                             candidate_sources=alternatives.get((caller, ident), ()))
                continue
            if len(via) < 4:
                pending.extend((child, (*via, ident)) for child in sorted(graph[ident]))
    for role, apis in facets.items():
        for fn in groups.get(role, {}).values():
            if primary[fn['id']] and primary[fn['id']] != role:
                add_edge(primary[fn['id']], role, fn, fn, kind='uses',
                         label={'receive': 'receives', 'publish': 'publishes', 'timer': 'configures'}[role])

    edges = sorted(edge_map.values(), key=lambda edge: (ROLE_ORDER[edge['source']], ROLE_ORDER[edge['target']], edge['kind']))
    descriptions = {'receive': 'receives software-bus messages', 'commands': 'handles commands',
                    'timer': 'configures timers', 'publish': 'publishes software-bus messages'}
    work = next((node for node in nodes if node['role'] == 'work'), None)
    described = [work['summary'].rstrip('.').lower()] if work else []
    described.extend(descriptions[node['role']] for node in nodes if node['role'] in descriptions)
    source_summary = '; '.join(described).capitalize() + '.' if described else 'Application behavior from its C entry points and calls.'
    purpose = _documented_purpose(app, root) or {}
    covered = set().union(*(set(group) for group in groups.values())) if groups else set()
    return {'nodes': nodes, 'edges': edges, 'entry': _reference(entry) if entry else None,
            'details': describe_application(app, root=root) if root else {},
            'description': purpose.get('text') or source_summary,
            'purpose_source': purpose.get('source'), 'purpose_error': purpose.get('error'), 'source_summary': source_summary,
            'entry_symbol': entry_symbol or (entry['symbol'] if entry else None),
            'scope': 'Source-level calls and API uses; conditional branches included. Not a runtime trace.',
            'omitted_function_count': len(functions) - len(covered)}
