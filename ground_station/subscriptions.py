"""TO_LAB subscription policy read from the installed table and target headers."""
from collections import Counter
from pathlib import Path
import re


def subscription_metadata(root, evaluate, build_dir=None):
    from .tables import table_layout, table_file_data

    root = Path(root)
    from .catalog import resolve_build
    installed = resolve_build(root, build_dir) / 'exe/cpu1/cf'
    source = (root / 'cFS/apps/to_lab/fsw/src/to_lab_app.c').read_text()
    match = re.search(r'CFE_TBL_Load\(\s*[^,]*SubsTbl[^,]*,\s*CFE_TBL_SRC_FILE,\s*"([^"]+)"', source)
    if not match:
        raise ValueError('TO_LAB subscription table not found in the compiled software')
    path = installed / Path(match[1]).name
    table_name, payload = table_file_data(path, table_layout(evaluate))
    declarations = '#include "to_lab_tbl.h"\n#include "to_lab_internal_cfg.h"\n#include "to_lab_eventids.h"\n'
    expressions = ['sizeof(TO_LAB_Subs_t)', 'offsetof(TO_LAB_Subs_t,Subs)', 'sizeof(TO_LAB_Sub_t)',
                   'TO_LAB_MISSION_MAX_SUBSCRIPTIONS', 'TO_LAB_PLATFORM_TLM_PIPE_DEPTH']
    members = ('Stream', 'Flags.Priority', 'Flags.Reliability', 'BufLimit')
    for member in members:
        expressions += [f'offsetof(TO_LAB_Sub_t,{member})', f'sizeof(((TO_LAB_Sub_t*)0)->{member})']
    expressions += ['TO_LAB_ADDPKT_INF_EID', 'TO_LAB_ADDPKT_EXISTS_INF_EID',
                    'TO_LAB_ADDPKT_ERR_EID', 'TO_LAB_ADDPKT_BUFLIM_ERR_EID']
    values = evaluate(declarations, expressions)
    size, offset, stride, capacity, pipe_depth = values[:5]
    if len(payload) != size or offset + stride * capacity > size:
        raise ValueError('TO_LAB table does not match the compiled layout')
    subscriptions = []
    for index in range(capacity):
        entry = payload[offset + index * stride:offset + (index + 1) * stride]
        fields = [int.from_bytes(entry[values[5 + n * 2]:values[5 + n * 2] + values[6 + n * 2]], 'little')
                  for n in range(len(members))]
        mid, priority, reliability, buffer_limit = fields
        if not buffer_limit:
            continue
        if not 0 < mid <= 0xffff or not buffer_limit < pipe_depth:
            raise ValueError('Invalid subscription in the compiled TO_LAB table')
        subscriptions.append(dict(mid=mid, priority=priority, reliability=reliability, buffer_limit=buffer_limit))
    if not subscriptions:
        raise ValueError('TO_LAB table has no usable subscription policy')
    # Reuse the predominant policy already selected by this mission's table.
    priority, reliability, buffer_limit = Counter(
        (s['priority'], s['reliability'], s['buffer_limit']) for s in subscriptions).most_common(1)[0][0]
    startup = (installed / 'cfe_es_startup.scr').read_text()
    app = re.search(r'CFE_APP\s*,\s*to_lab\s*,[^,]*,\s*(\w+)', startup)
    if not app:
        raise ValueError('TO_LAB is missing from the installed startup script')
    return {'subscriptions': subscriptions, 'subscription_table': table_name,
            'subscription_source': path.relative_to(root).as_posix(),
            'subscription_defaults': dict(priority=priority, reliability=reliability, buffer_limit=buffer_limit),
            'max_subscriptions': capacity, 'subscription_app': app[1],
            'subscription_events': dict(added=values[13], exists=values[14], errors=list(values[15:17]))}
