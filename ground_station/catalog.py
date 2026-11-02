"""Read packet definitions from cFS headers using its actual target C compiler.

The compiler supplies sizes, offsets and constants. Python never guesses C padding.
Unsupported C declarations remain raw bytes instead of reporting invented values.
"""
import copy
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from ground_station.discovery import command_mappings, telemetry_mappings, raw_telemetry_mappings
from ground_station.tables import table_packets
from ground_station.subscriptions import subscription_metadata

CATALOG_VERSION = 11

TYPES = {'uint8': 'B', 'uint16': 'H', 'uint32': 'I', 'uint64': 'Q',
         'int8': 'b', 'int16': 'h', 'int32': 'i', 'int64': 'q',
         'uint8_t': 'B', 'uint16_t': 'H', 'uint32_t': 'I', 'uint64_t': 'Q',
         'int8_t': 'b', 'int16_t': 'h', 'int32_t': 'i', 'int64_t': 'q',
         'float': 'f', 'double': 'd', 'char': 's', 'bool': '?', '_Bool': '?'}


def clean(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def definition_source(root, appdir, symbol):
    """Locate a C type declaration for display; app manifests are not packet schemas."""
    pattern = re.compile(r'\b' + re.escape(symbol) + r'\s*;')
    for header in sorted(appdir.rglob('*.h')):
        if pattern.search(clean(header.read_text(errors='replace'))):
            return header.relative_to(root).as_posix()
    return ''


def source_locations(root, appdir, packet):
    """Navigable C symbols, retaining source line numbers and never modifying files."""
    root, appdir = Path(root), Path(appdir)
    identifier = packet['id'].split('[')[0]
    symbol = packet.get('struct') or packet.get('name', '')
    result = {}
    files = sorted(appdir.rglob('*.h')) + sorted(appdir.rglob('*.c'))
    for path in files:
        text = path.read_text(errors='replace')
        # Comments cannot become definitions, and their lines still count.
        clean_text = re.sub(r'/\*.*?\*/|//[^\n]*', lambda match: '\n' * match[0].count('\n'), text, flags=re.S)
        patterns = {'identifier': r'^[ \t]*#[ \t]*define[ \t]+' + re.escape(identifier) + r'\b',
                    'dispatch': r'\bcase\s+' + re.escape(identifier) + r'\s*:|\[\s*' + re.escape(identifier) + r'\s*\]',
                    'packet': r'\b' + re.escape(symbol) + r'\s*;'}
        if packet.get('struct') is None:
            patterns['packet'] = r'\b' + re.escape(identifier) + r'\b' if path.suffix == '.c' else r'(?!)'
        for kind, pattern in patterns.items():
            if kind in result or not symbol and kind == 'packet':
                continue
            match = re.search(pattern, clean_text, flags=re.M)
            if not match and kind == 'dispatch' and path.suffix == '.c' and 'dispatch' in path.stem:
                alias = re.search(r'(\w+)\s*=\s*CFE_SB_ValueToMsgId\(\s*' + re.escape(identifier) + r'\s*\)', clean_text)
                if alias:
                    match = re.search(r'(?:else\s+)?if\s*\(\s*CFE_SB_MsgId_Equal\([^)]*\b' + re.escape(alias[1]) + r'\b[^)]*\)\s*\)', clean_text)
                if not match:
                    match = re.search(r'\b' + re.escape(identifier) + r'\b', clean_text)
            if not match:
                continue
            start, end = match.span()
            if kind == 'packet':
                typedef = clean_text.rfind('typedef', 0, start)
                if typedef >= 0:
                    start = typedef
            elif kind == 'dispatch':
                block = clean_text.find('{', end)
                if block >= 0 and not clean_text[end:block].strip():
                    closing = clean_text.find('}', block)
                    if closing >= 0:
                        end = closing + 1
            result[kind] = {'path': path.relative_to(root).as_posix(),
                            'line': clean_text.count('\n', 0, start) + 1,
                            'end_line': clean_text.count('\n', 0, end) + 1,
                            'symbol': symbol if kind == 'packet' else identifier}
    return result


def structures(text):
    result = {}
    for body, name in re.findall(r'typedef\s+struct\s*(?:\w+\s*)?\{([^{}]*)\}\s*(\w+)\s*;', text):
        members = []
        for declaration in body.split(';'):
            match = re.fullmatch(r'\s*(\w+)\s+(.+?)\s*', declaration, re.S)
            if not match:
                continue
            typ, names = match.groups()
            for item in names.split(','):
                match = re.fullmatch(r'\s*(\w+)\s*(\[.*\])?\s*', item)
                if match:
                    array = match[2]
                    numeric = re.fullmatch(r'\[\s*(\d+)\s*\]', array or '')
                    members.append((typ, match[1], int(numeric[1]) if numeric else (-1 if array else 1)))
        result[name] = members
    return result


def fields_for(typ, structs, prefix='', depth=0, formats=None):
    formats = formats or TYPES
    if depth > 5:
        return []
    fields = []
    for field_type, name, count in structs.get(typ, []):
        if field_type in ('CFE_MSG_TelemetryHeader_t', 'CFE_MSG_CommandHeader_t'):
            continue
        path = prefix + name
        if field_type in formats:
            fields.append({'name': path.removeprefix('Payload.'), 'member': path,
                           'type': field_type, 'format': formats[field_type], 'count': count})
        elif count == 1 and field_type in structs:
            fields.extend(fields_for(field_type, structs, path + '.', depth + 1, formats))
        else:
            fields.append({'name': path.removeprefix('Payload.'), 'member': path,
                           'type': field_type, 'format': 'raw', 'count': max(1, count)})
    return fields


def run(argv, **kwargs):
    p = subprocess.run(argv, capture_output=True, timeout=30, **kwargs)
    if p.returncode:
        raise ValueError(p.stderr.decode(errors='replace')[-1800:])
    return p.stdout


def resolve_build(root, build_dir=None):
    root = Path(root).resolve()
    if build_dir is None:
        from project.model import load_config
        build_dir = 'cFS/build-flight' if load_config(root)['board'] else 'cFS/build-native'
    path = Path(build_dir)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root / 'cFS'):
        raise ValueError('Build directory must remain in this cFS checkout')
    return path


def _build_catalog(root, overrides_root=None, container=None, temp_root=None, build_dir=None):
    root = Path(root).resolve()
    build = resolve_build(root, build_dir)
    result = {'packets': [], 'commands': [], 'unresolved_commands': [], 'errors': [], 'transport': {},
              'source': build.relative_to(root).as_posix(), 'byte_order': 'little',
              'catalog_version': CATALOG_VERSION, 'apps': []}
    compiler_build = build / 'cache' if (build / 'cache').is_dir() else build
    flags_files = sorted(compiler_build.glob('**/default_cpu1/apps/*/CMakeFiles/*.dir/flags.make'))
    flags_files += sorted(compiler_build.glob('**/default_cpu1/*/CMakeFiles/*.dir/flags.make'))
    script = (root / 'scripts/build-cfs.sh').read_text()
    image_match = re.search(r'--target cfs-builder -t ([\w./:-]+)', script)
    builder_image = image_match[1] if image_match else None
    if not flags_files:
        result['errors'].append('Build cFS to generate the headers and communication catalog.')
        return result
    # Only apps in the installed startup script are eligible to receive commands.
    startup = build / 'exe/cpu1/cf/cfe_es_startup.scr'
    if not startup.exists():
        result['errors'].append('Build startup script unavailable.')
        return result
    from project.appgen.native_startup import parse_startup
    active = {entry.name for entry in parse_startup(startup.read_text())[0]
              if entry.kind == 'CFE_APP'}
    for flags_file in flags_files:
        target = flags_file.parents[2].name
        core_module = flags_file.parents[3].name == 'default_cpu1'
        app = 'cfe_' + target if core_module else target
        if flags_file.parent.name != target + '.dir':
            continue
        if app not in active and not core_module:
            continue
        if not core_module:
            result['apps'].append({'name': app, 'kind': 'app'})
        flags_text = flags_file.read_text()
        compiler_match = re.search(r'# compile C with (.+)', flags_text)
        if not compiler_match:
            continue
        compiler = compiler_match[1].strip()
        container_build = '-I/cFS/' in flags_text
        compiler_name = Path(compiler).name
        copy_name = compiler_name.removesuffix('gcc') + 'objcopy' if compiler_name.endswith('gcc') else 'objcopy'
        objcopy = copy_name if container_build else shutil.which(copy_name)
        if not objcopy:
            result['errors'].append('Target compiler objcopy unavailable.')
            break
        args = []
        for key in ('C_DEFINES', 'C_INCLUDES', 'C_FLAGS'):
            match = re.search(r'^' + key + r' = (.*)$', flags_text, re.M)
            if match:
                args += shlex.split(match[1])
        appdir = root / 'cFS/cfe/modules' / target if core_module else root / 'cFS/apps' / app
        if not list(appdir.rglob('*' + app + '_msg.h')):
            continue
        if core_module:
            result['apps'].append({'name': app, 'kind': 'core'})
        headers = [f'{app}_{kind}_cfg.h' for kind in ('mission', 'interface')
                   if any(appdir.rglob('*' + app + '_' + kind + '_cfg.h'))]
        headers += [f'{app}_msg.h', f'{app}_msgids.h']
        fcn = next(iter(appdir.rglob(f'{app}_fcncodes.h')), appdir / 'fsw/inc' / f'{app}_fcncodes.h')
        if fcn.exists():
            headers.append(str(fcn))
        headers += [str(p) for category in ('sensors', 'commands', 'telemetry')
                    for p in (appdir / 'fsw/src' / category).glob('*.h')]
        if app == 'to_lab':
            headers += ['to_lab_interface_cfg.h', 'ci_lab_interface_cfg.h']
            args += ['-I' + str(root / 'cFS/apps/ci_lab/fsw/inc')]
        def compile_run(argv, **kwargs):
            if container_build:
                if not builder_image:
                    raise ValueError('Compiler image not found in scripts/build-cfs.sh')
                if not container:
                    raise ValueError('Docker compiler unavailable')
                prefix = ['docker', 'exec', '-i', container]
                argv = [str(a).replace(str(root / 'cFS'), '/cFS') for a in argv]
                if 'input' in kwargs:
                    kwargs['input'] = kwargs['input'].replace(str(root / 'cFS').encode(), b'/cFS')
                argv = prefix + argv
            return run(argv, **kwargs)

        source = '#include <stddef.h>\n#include <stdint.h>\n#include "cfe.h"\n' + ''.join(
            '#include ' + json.dumps(h) + '\n' for h in headers)
        def evaluate(declarations, expressions):
            schema = source + '\n' + declarations + '\nconst uint64_t flight_schema[] __attribute__((section(".flight_schema"),used)) = {' + ','.join(expressions) + '};\n'
            with tempfile.TemporaryDirectory(prefix='flight-schema-', dir=temp_root) as temp:
                obj, binary = str(Path(temp) / 'schema.o'), str(Path(temp) / 'schema.bin')
                compile_run([compiler, *args, '-c', '-x', 'c', '-', '-o', obj], input=schema.encode())
                compile_run([objcopy, '-O', 'binary', '--only-section=.flight_schema', obj, binary])
                data = Path(binary).read_bytes()
            return struct.unpack('<' + 'Q' * (len(data) // 8), data)
        try:
            preprocessed = compile_run([compiler, *args, '-E', '-P', '-x', 'c', '-'], input=source.encode()).decode()
            structs = structures(preprocessed)
            formats = dict(TYPES)
            aliases = re.findall(r'typedef\s+(\w+)\s+(\w+)\s*;', preprocessed)
            native_aliases = set(re.findall(r'typedef\s+(?:(?:unsigned|signed|long|short|int|char)\s+)+(\w+)\s*;', preprocessed)) - formats.keys()
            used_types = {typ for members in structs.values() for typ, _, _ in members}
            for _ in range(8):
                used_types.update(base for base, alias in aliases if alias in used_types)
            native_aliases = sorted(native_aliases & used_types)
            if native_aliases:
                layout = evaluate('', [expression for typ in native_aliases for expression in
                                      (f'sizeof({typ})', f'(({typ})-1 < ({typ})0)')])
                for index, typ in enumerate(native_aliases):
                    width, signed = layout[index * 2:index * 2 + 2]
                    if width in (1, 2, 4, 8):
                        formats[typ] = {1:'b', 2:'h', 4:'i', 8:'q'}[width]
                        if not signed: formats[typ] = formats[typ].upper()
            for _ in range(8):
                for base, alias in aliases:
                    if base in formats:
                        formats[alias] = formats[base]
                    if base in structs and alias not in structs:
                        structs[alias] = structs[base]
            macros = compile_run([compiler, *args, '-E', '-dM', '-x', 'c', '-'], input=source.encode()).decode()
            defined = set(re.findall(r'#define\s+(\w+)', macros))
            mids = {name for name in defined if name.startswith(app.upper() + '_') and
                    (name.endswith('_MID') or name.endswith('_MID_BASE'))}
            prefix = app.upper()
            dependencies = flags_file.with_name('DependInfo.cmake')
            paths = re.findall(r'"([^"\n]+\.c)"', dependencies.read_text()) if dependencies.exists() else []
            sources = [Path(path.replace('/cFS/', str(root / 'cFS') + '/', 1)) if path.startswith('/cFS/') else Path(path) for path in paths]
            sources = [p for p in sources if p.is_file() and p.is_relative_to(appdir)]
            if not sources:
                raise ValueError('Compiled source list unavailable; the catalog cannot be inferred.')
            # Keep symbols but evaluate #if using precisely the flight compiler flags.
            dispatch_files = [p for p in sources if re.search(r'\bcase\s+\w+_CC|\[\s*\w+_CC\s*\]|\b\w+_ENTRY\(', p.read_text(errors='replace'))]
            def preprocess_sources(paths):
                if not paths: return ''
                included = ''.join('#include ' + json.dumps(str(p)) + '\n' for p in paths)
                text = compile_run([compiler, *args, '-E', '-P', '-fdirectives-only', '-x', 'c', '-'], input=included.encode()).decode()
                lines, continued = [], False
                for line in clean(text).splitlines():
                    directive = continued or line.lstrip().startswith('#')
                    continued = directive and line.rstrip().endswith('\\')
                    if not directive: lines.append(line)
                return '\n'.join(lines)
            dispatch = preprocess_sources(dispatch_files)
            initialized = preprocess_sources([p for p in sources if re.search(r'CFE_MSG_(?:Init|SetSize)', p.read_text(errors='replace'))])
            packet_types = {name for name, members in structs.items() if name.startswith(prefix + '_') and
                            any(t == 'CFE_MSG_TelemetryHeader_t' for t, _, _ in members)}
            all_structs = {**structures(initialized), **structs}
            telemetry, variable_types, used_telemetry = telemetry_mappings(initialized, all_structs, packet_types, '')
            # A normalized exact-name fallback covers packets initialized by wrappers.
            norm = lambda value: re.sub(r'[^A-Z0-9]', '', value.upper()).replace('TLM', '')
            for name in sorted(packet_types):
                if any(item[0] == name for item in telemetry.values()): continue
                candidates = [m for m in mids if norm(m.removesuffix('_MID')) == norm(name.removesuffix('_t'))]
                if not candidates and re.search(r'(?:Hk|Housekeeping)', name):
                    candidates = [m for m in mids if m in (prefix + '_HK_TLM_MID', prefix + '_HK_MID')]
                if not candidates:
                    key = norm(name.removesuffix('_t')).removesuffix('MESSAGE')
                    candidates = [m for m in mids if norm(m.removesuffix('_MID')).removesuffix('MSG') == key]
                if len(candidates) == 1: telemetry[candidates[0]] = (name, None)
            packets = [{'id': mid, 'name': typ, 'app': app, 'mid_expr': mid,
                        'struct': typ, 'fields': fields_for(typ, structs, formats=formats),
                        'kind': 'telemetry', 'repeat_expr': repeat or '1'}
                       for mid, (typ, repeat) in sorted(telemetry.items()) if mid in defined]
            mappings, unresolved, explicit = command_mappings(dispatch, structs, defined, prefix)
            commands = [{'id': code, 'name': typ, 'app': app, 'mid_expr': mid,
                         'code_expr': expression, 'struct': typ,
                         'fields': fields_for(typ, structs, formats=formats), 'kind': 'command',
                         'dispatch': 'mid' if code == mid else 'function_code'}
                        for code, (mid, expression, typ) in sorted(mappings.items())]
            for mid, size in sorted(raw_telemetry_mappings(initialized, defined).items()):
                if mid not in telemetry:
                    packets.append({'id': mid, 'name': mid, 'app': app, 'mid_expr': mid, 'struct': None,
                                    'fields': [], 'kind': 'telemetry', 'size_expr': size})
            commands += [{'id': code, 'name': code, 'app': app, 'mid_expr': mid, 'code_expr': expression,
                          'struct': None, 'fields': [], 'kind': 'command', 'size_expr': size,
                          'dispatch': 'function_code'}
                         for code, (mid, expression, size) in sorted(explicit.items())]
            # Unresolved commands stay listed with their reason; none is sendable.
            for code, reason in unresolved.items():
                result['unresolved_commands'].append({'id': code, 'app': app, 'reason': reason})
                result['errors'].append(f'{app}: command {code} is unresolved: {reason}')
            missing_telemetry = used_telemetry - {packet['struct'] for packet in packets}
            if missing_telemetry:
                result['errors'].append(app + ': telemetry with unresolved MIDs: ' + ', '.join(sorted(missing_telemetry)))
            expressions = ['sizeof(CFE_MSG_CommandHeader_t)', 'sizeof(CFE_MSG_TelemetryHeader_t)',
                           'offsetof(CFE_MSG_CommandHeader_t,Sec.FunctionCode)',
                           'offsetof(CFE_MSG_CommandHeader_t,Sec.Checksum)']
            if app == 'to_lab':
                expressions += ['CI_LAB_MISSION_BASE_UDP_PORT', 'TO_LAB_MISSION_TLM_PORT']
            for packet in packets + commands:
                packet['_index'] = len(expressions)
                expressions += [packet['mid_expr'], packet.get('size_expr') or 'sizeof(' + packet['struct'] + ')', packet.get('code_expr', packet.get('repeat_expr', '1'))]
                for field in packet['fields']:
                    expressions += [f'offsetof({packet["struct"]},{field["member"]})',
                                    f'sizeof((({packet["struct"]}*)0)->{field["member"]})']
                if packet['struct'] in variable_types:
                    packet['_minimum_index'] = len(expressions)
                    expressions.append(variable_types[packet['struct']])
            values = evaluate('', expressions)
            if values[:4] != (8, 16, 6, 7):
                raise ValueError('Unsupported CCSDS layout; commands will not be sent.')
            if app == 'to_lab':
                result['transport'] = {'command_port': values[4], 'telemetry_port': values[5],
                                       'command_header_size': values[0], 'telemetry_header_size': values[1]}
            for packet in packets + commands:
                i = packet.pop('_index')
                packet['mid'], packet['size'], code = values[i:i+3]
                if packet['kind'] == 'command':
                    packet['code'] = code
                if packet['struct'] is None:
                    header = values[0 if packet['kind'] == 'command' else 1]
                    if not header <= packet['size'] <= 65536:
                        raise ValueError('Explicit packet size is out of range: ' + packet['id'])
                    size = packet['size'] - header
                    if size:
                        packet['fields'] = [{'name': 'Payload', 'type': 'uint8', 'format': 'raw',
                                             'count': size, 'offset': header, 'size': size}]
                for n, field in enumerate(packet['fields']):
                    if packet['struct'] is None: break
                    field['offset'], field['size'] = values[i+3+n*2:i+5+n*2]
                    field.pop('member')
                    if field['format'] not in ('raw', 's'):
                        scalar_size = struct.calcsize('<' + field['format'])
                        if field['size'] % scalar_size:
                            raise ValueError('Field is incompatible with its type: ' + field['name'])
                        field['count'] = field['size'] // scalar_size
                    elif field['format'] == 's':
                        field['count'] = field['size']
                if '_minimum_index' in packet:
                    packet['variable_size'] = True
                    packet['min_size'] = values[packet.pop('_minimum_index')]
                    packet['max_size'] = packet['size']
                packet.pop('mid_expr')
                packet.pop('code_expr', None)
                packet.pop('repeat_expr', None)
                packet.pop('size_expr', None)
                if packet['kind'] == 'telemetry': packet['_repeat'] = code
                packet['source'] = definition_source(root, appdir, packet['name'])
                packet['locations'] = source_locations(root, appdir, packet)
                if packet['struct'] is None:
                    packet['source'] = packet['locations'].get('packet', packet['locations'].get('dispatch', {})).get('path', '')
            for packet in packets:
                repeat = packet.pop('_repeat')
                if not 1 <= repeat <= 256:
                    raise ValueError('MID count is out of range: ' + packet['id'])
                for index in range(repeat):
                    entry = copy.deepcopy(packet)
                    if repeat > 1:
                        entry['id'] += '[' + str(index) + ']'
                        entry['name'] += ' [' + str(index) + ']'
                        entry['mid'] += index
                    result['packets'].append(entry)
            result['commands'] += commands
            try:
                result['packets'] += table_packets(root, app, evaluate, build_dir=build)
                if app == 'to_lab':
                    result['transport'].update(subscription_metadata(root, evaluate, build_dir=build))
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                result['errors'].append(f'{app}: communication table: {error}')
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            result['errors'].append(f'{app}: {error}')
    return result


def build_catalog(root, overrides_root=None, build_dir=None):
    """Use one temporary builder container so metadata does not require host GCC."""
    root = Path(root).resolve()
    build = resolve_build(root, build_dir)
    container_flags = any('-I/cFS/' in path.read_text() for path in build.glob('**/flags.make'))
    if not container_flags:
        return _build_catalog(root, overrides_root, build_dir=build)
    script = (root / 'scripts/build-cfs.sh').read_text()
    image = re.search(r'--target cfs-builder -t ([\w./:-]+)', script)
    if not image:
        raise ValueError('Compiler image not found in scripts/build-cfs.sh')
    with tempfile.TemporaryDirectory(prefix='flight-schema-') as temp:
        container = run(['docker', 'run', '--rm', '-d', '--network', 'none',
                         '--user', f'{os.getuid()}:{os.getgid()}',
                         '-v', str(root / 'cFS') + ':/cFS:ro', '-v', temp + ':' + temp,
                         image[1], 'sleep', '600']).decode().strip()
        try:
            return _build_catalog(root, overrides_root, container, temp, build_dir=build)
        finally:
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=60)


def apply_overrides(catalog, root):
    """Apply editable local definitions to a copy, never mutate a deployed schema."""
    result = copy.deepcopy(catalog)
    path = Path(root) / 'ground_station/overrides.json'
    if not path.exists():
        return result
    custom = json.loads(path.read_text())
    if not isinstance(custom, dict) or set(custom) - {'packets', 'commands'}:
        raise ValueError('overrides.json only accepts packets and commands')
    for category in ('packets', 'commands'):
        entries = custom.get(category, [])
        if not isinstance(entries, list):
            raise ValueError(category + ' must be a list')
        mapping = {p['id']: p for p in result[category]}
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                raise ValueError('Override requires a string id')
            packet = {**mapping.get(item['id'], {}), **item}
            header = 8 if category == 'commands' else 16
            mid, size = packet.get('mid'), packet.get('size')
            if type(mid) is not int or not 0 <= mid <= 65535 or type(size) is not int or not header <= size <= 65507:
                raise ValueError('Invalid MID/size: ' + item['id'])
            if mid & 0xF800 != (0x1800 if category == 'commands' else 0x0800):
                raise ValueError('MID does not match the CCSDS type: ' + item['id'])
            if category == 'commands' and (type(packet.get('code')) is not int or not 0 <= packet['code'] <= 127):
                raise ValueError('Invalid command code: ' + item['id'])
            packet.setdefault('name', item['id'])
            packet.setdefault('app', 'custom')
            packet.setdefault('source', 'ground_station/overrides.json')
            packet.setdefault('fields', [])
            names, occupied = set(), set()
            for field in packet['fields']:
                if not isinstance(field, dict) or not isinstance(field.get('name'), str) or field['name'] in names:
                    raise ValueError('Invalid or duplicate field name: ' + item['id'])
                names.add(field['name'])
                offset, length, count = field.get('offset'), field.get('size'), field.get('count', 1)
                fmt = field.get('format')
                if any(type(n) is not int for n in (offset, length, count)) or offset < header or length < 1 or offset+length > size or count < 1:
                    raise ValueError('Invalid field bounds: ' + field['name'])
                if fmt not in set(TYPES.values()) | {'raw'}:
                    raise ValueError('Invalid field format: ' + field['name'])
                if fmt not in ('s', 'raw') and struct.calcsize('<' + fmt) * count != length:
                    raise ValueError('Size does not match the format: ' + field['name'])
                positions = set(range(offset, offset+length))
                if occupied & positions:
                    raise ValueError('Overlapping fields: ' + field['name'])
                occupied.update(positions)
                field.setdefault('count', count)
                field.setdefault('type', fmt)
            mapping[item['id']] = packet
        result[category] = list(mapping.values())
    return result
