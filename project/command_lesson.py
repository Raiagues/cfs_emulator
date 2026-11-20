"""Progressively add SET_RATE to a person's NASA sample_app-derived mission app."""

from difflib import SequenceMatcher
import hashlib
import json
import re

from hardware.manager import HardwareManager
from hardware.targets import selected_target
from journey import SHIPPED_APPS, Store
from project import model
from project.c_source import blank_lexemes
from project.manage import commit

STOPS = ('Code', 'Struct', 'Prototype', 'Dispatch', 'Events', 'Handler', 'Test')
STUB = 'return CFE_STATUS_NOT_IMPLEMENTED;'

class MissingApp(ValueError):
    """A previously observed application may have been removed from the mission."""


def before_guard(source, addition):
    guard = list(re.finditer(r'^#endif\b', source, re.M))
    if not guard:
        raise ValueError('Cannot find the closing header guard')
    at = guard[-1].start()
    return source[:at] + addition + '\n' + source[at:]


class CommandLesson:
    def __init__(self, workspace, target, app=None):
        self.workspace, self.root = workspace, workspace.root
        if target != selected_target(self.root):
            raise ValueError('Choose the active target before editing its app.')
        self.target = target
        self.config = model.load_config(self.root)
        self.manifests = model.read_manifests(self.root, self.config)
        mine = {m['name']: m for m in self.manifests if m['name'] not in SHIPPED_APPS}
        if app is None:
            app = next(
                (
                    ref['app']
                    for ref in reversed(Store(self.root).references(target, 'app'))
                    if ref.get('app') in mine
                ),
                None,
            )
        if app is None:
            raise MissingApp('Create your mission app first.')
        if app not in mine:
            raise ValueError('Create your mission app first.')
        self.app, self.manifest = model.identifier(app), mine[app]
        self.prefix = app.upper()
        folder = 'mission/apps/' + app + '/fsw/'
        self.paths = {
            k: folder + p
            for k, p in {
                'code': 'inc/' + app + '_fcncodes.h',
                'struct': 'src/commands/' + app + '_set_rate_cmd.h',
                'handler': 'src/commands/' + app + '_set_rate_cmd.c',
                'dispatch': 'src/' + app + '_dispatch.c',
                'events': 'inc/' + app + '_eventids.h',
                'data': 'src/' + app + '.h',
            }.items()
        }
        self.source = {}
        for key, relative in self.paths.items():
            path = workspace.path(relative)
            self.source[key] = path.read_text() if path.is_file() else ''
        self.symbol = self.prefix + '_SET_RATE_CC'
        self.proto = f'CFE_Status_t {self.prefix}_SetRateCmd(const {self.prefix}_SetRateCmd_t *Msg);'
        self.line = self.prefix + '_Data.Rate_Hz = Rate_Hz;'
        self.macro = re.search(r'^#define\s+' + self.symbol + r'\s+(\d+)\s*$', self.source['code'], re.M)
        registered = next((c for c in self.manifest['commands'] if c['name'] == 'set_rate'), None)
        used = {c['code'] for c in self.manifest['commands']}
        used.update(
            int(value, 0)
            for value in re.findall(r'^#define\s+\w+_CC\s+(0[xX][a-fA-F0-9]+|\d+)\b', self.source['code'], re.M)
        )
        self.code = (
            registered['code']
            if registered
            else (
                int(self.macro[1])
                if self.macro
                else model.appgen(self.root).allocate(
                    range(4 if self.manifest['schema_version'] == 2 else 2, 128), used, 'command code'
                )
            )
        )
        self.definition = f'#define {self.symbol} {self.code}\n'
        if not self.macro:
            self.stage = 0
        elif not self.source['struct']:
            self.stage = 1
        elif self.proto not in self.source['struct']:
            self.stage = 2
        elif not registered:
            self.stage = 3
        elif self.prefix + '_SET_RATE_INF_EID' not in self.source['events']:
            self.stage = 4
        elif STUB in self.source['handler']:
            self.stage = 5
        else:
            self.stage = 6

    def registered_plan(self):
        commands = self.manifest['commands']
        if any(c['code'] == self.code or c['name'] == 'set_rate' for c in commands):
            raise ValueError('This function code or command name is already in use.')
        commands.append({'name': 'set_rate', 'code': self.code})
        try:
            model.validate_config(self.root, self.config, self.manifests)
            plan = model.planned_project_files(self.root, self.config, self.manifests)
        finally:
            commands.pop()
        # Registration transfers the original declaration into appgen's managed code block.
        path = self.paths['code']
        end = plan[path].rfind(self.definition)
        if end < 0 or plan[path].count(self.definition) != 2:
            raise ValueError('The function code changed before dispatch was registered.')
        plan[path] = plan[path][:end] + plan[path][end + len(self.definition) :]
        return plan

    def boilerplate(self):
        prefix = self.prefix
        return f'''#include "{self.app}_set_rate_cmd.h"
#include "{self.app}.h"
#include "{self.app}_eventids.h"

/** @brief Store the requested sampling rate in the application. */
CFE_Status_t {prefix}_SetRateCmd(const {prefix}_SetRateCmd_t *Msg)
{{
    const uint16 Rate_Hz = Msg->Payload.Rate_Hz;
    if (Rate_Hz < 1 || Rate_Hz > 50)
    {{
        CFE_EVS_SendEvent({prefix}_SET_RATE_ERR_EID, CFE_EVS_EventType_ERROR,
                          "Rate %u out of range", (unsigned int)Rate_Hz);
        return CFE_STATUS_BAD_COMMAND_CODE;
    }}

    /* Store the new rate here. */
    {STUB}

    CFE_EVS_SendEvent({prefix}_SET_RATE_INF_EID, CFE_EVS_EventType_INFORMATION,
                      "Rate set to %u Hz", (unsigned int)Rate_Hz);
    return CFE_SUCCESS;
}}
'''

    def changes(self):
        p, src, name = self.paths, self.source, self.prefix
        if self.stage == 0:
            return {p['code']: before_guard(src['code'], self.definition)}
        if self.stage == 1:
            header = f'''#ifndef {name}_SET_RATE_CMD_H
#define {name}_SET_RATE_CMD_H
#include "cfe.h"

typedef struct
{{
    uint16 Rate_Hz; /**< Reads per second. @unit Hz @range 1..50 */
}} {name}_SetRate_Payload_t;

typedef struct
{{
    CFE_MSG_CommandHeader_t CommandHeader;
    {name}_SetRate_Payload_t Payload;
}} {name}_SetRateCmd_t;

#endif
'''
            return {p['struct']: header}
        if self.stage == 2:
            if src['handler'] or 'Rate_Hz;' not in src['struct']:
                raise ValueError('A different command already owns the SET_RATE files.')
            stub = f'#include "{self.app}_set_rate_cmd.h"\n\n{self.proto[:-1]}\n{{\n    (void)Msg;\n    {STUB}\n}}\n'
            return {p['struct']: before_guard(src['struct'], self.proto + '\n'), p['handler']: stub}
        if self.stage == 3:
            return self.registered_plan()
        if self.stage == 4:
            if not re.search(r'\buint16\s+Rate_Hz\s*;', src['struct']) or STUB not in src['handler']:
                raise ValueError(
                    'SET_RATE already has a different payload or implementation. Open its source in Code.'
                )
            ids = {
                int(v, 0)
                for v in re.findall(r'^#define\s+\w+_EID\s+(0[xX][0-9a-fA-F]+|\d+)\b', src['events'], re.M)
            }
            numbers = iter(i for i in range(1, 65536) if i not in ids)
            event_ids = f'#define {name}_SET_RATE_INF_EID {next(numbers)}\n#define {name}_SET_RATE_ERR_EID {next(numbers)}\n'
            anchor = '} ' + name + '_Data_t;'
            if src['data'].count(anchor) != 1:
                raise ValueError('Cannot locate the app data structure.')
            data = src['data'].replace(
                anchor, '    uint16 Rate_Hz; /**< Requested reads per second. */\n' + anchor
            )
            return {
                p['events']: before_guard(src['events'], event_ids),
                p['data']: data,
                p['handler']: self.boilerplate(),
            }
        return {}

    def snapshot(self):
        key = ('code', 'struct', 'struct', 'dispatch', 'events', 'handler', 'handler')[self.stage]
        path = self.paths[key]
        source = self.source[key]
        proposed = source
        if self.stage < 5:
            proposed = self.changes()[path]
        delta = SequenceMatcher(None, source.splitlines(), proposed.splitlines(), autojunk=False)
        ranges = [[i + 1, j] for op, _, _, i, j in delta.get_opcodes() if op != 'equal' and j > i]
        if self.stage == 5:
            at = next(i for i, line in enumerate(source.splitlines(), 1) if STUB in line)
            ranges = [[at, at]]
        revision = self.workspace.mission._revision()
        digest = hashlib.sha256(
            json.dumps([revision, self.manifest, self.source], sort_keys=True).encode()
        ).hexdigest()
        return {
            'app': self.app,
            'stage': self.stage,
            'steps': STOPS,
            'symbol': self.symbol,
            'code': self.code,
            'path': path,
            'content': proposed,
            'ranges': ranges,
            'expected_hash': revision,
            'source_hash': digest,
            'file_hash': hashlib.sha256(source.encode()).hexdigest(),
            'ghost': self.line,
            'stub': STUB,
            'files': [p for k, p in self.paths.items() if self.source[k] or p == path],
        }

    def compile(self):
        lines = []
        try:
            HardwareManager(self.root).execute('check-app', lines.append, target=self.target, app=self.app)
        except (RuntimeError, OSError, ValueError) as error:
            diagnostic = next((s for s in lines if 'error:' in s.lower() or 'cmake error' in s.lower()), None)
            raise ValueError(diagnostic or '\n'.join(lines[-4:]) or str(error)) from error

    def confirm(self, stage, source_hash):
        current = self.snapshot()
        if stage != self.stage or source_hash != current['source_hash']:
            raise ValueError('Source changed. Reopen this step before saving.')
        if self.stage >= 5:
            raise ValueError('Write the handler line in its source file.')
        commit(self.root, self.changes(), validate=self.compile if self.stage >= 3 else None)
        return CommandLesson(self.workspace, self.target, self.app).snapshot()

    def save_handler(self, path, content, expected_hash):
        if self.stage != 5 or path != self.paths['handler']:
            raise ValueError('Open the SET_RATE handler before saving this line.')
        source = self.source['handler']
        if expected_hash != hashlib.sha256(source.encode()).hexdigest():
            raise ValueError('File changed on disk. Reopen the handler.')
        if not isinstance(content, str) or len(content.encode()) > self.workspace.MAX_TEXT:
            raise ValueError('Invalid handler contents.')
        code = blank_lexemes(content)
        if STUB in code or not re.search(
            re.escape(self.prefix) + r'_Data\s*\.\s*Rate_Hz\s*=\s*(?:Rate_Hz|Msg->Payload\.Rate_Hz)\s*;', code
        ):
            raise ValueError('Store the received Rate_Hz in the app data.')
        commit(self.root, {path: content}, validate=self.compile)
        return self.workspace.read_file(path)
