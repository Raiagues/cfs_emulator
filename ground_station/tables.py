"""Read installed cFE tables with layouts from the flight compiler."""
import re
from pathlib import Path


def table_layout(evaluate):
    members = ('Std.ContentType', 'Std.SubType', 'Std.Length', 'Tbl.Offset',
               'Tbl.NumBytes', 'Tbl.TableName')
    expressions = ['sizeof(CFE_TBL_CombinedFileHdr_t)', 'sizeof(CFE_FS_Header_t)',
                   'CFE_FS_SubType_TBL_IMG']
    for member in members:
        expressions += [f'offsetof(CFE_TBL_CombinedFileHdr_t,{member})',
                        f'sizeof(((CFE_TBL_CombinedFileHdr_t*)0)->{member})']
    values = evaluate('#include "cfe_tbl_extern_typedefs.h"', expressions)
    return {'size': values[0], 'fs_size': values[1], 'subtype': values[2],
            **{member: values[3 + i * 2:5 + i * 2] for i, member in enumerate(members)}}


def table_file_data(path, layout, expected_name=None):
    """Return (full table name, payload); reject partial or corrupt table images."""
    data = Path(path).read_bytes()
    if len(data) < layout['size']:
        raise ValueError('Truncated table header: ' + str(path))

    def field(member):
        offset, size = layout[member]
        return data[offset:offset + size]

    number = lambda member: int.from_bytes(field(member), 'big')
    if (field('Std.ContentType') != b'cFE1' or number('Std.SubType') != layout['subtype']
            or number('Std.Length') != layout['fs_size']):
        raise ValueError('Invalid cFE table header: ' + str(path))
    if number('Tbl.Offset') != 0:
        raise ValueError('A partial table cannot define the complete catalog: ' + str(path))
    name = field('Tbl.TableName').split(b'\0', 1)[0].decode('ascii')
    if not name or expected_name is not None and name != expected_name:
        raise ValueError('Incompatible table name: ' + name)
    payload = data[layout['size']:]
    if len(payload) != number('Tbl.NumBytes'):
        raise ValueError('Invalid table size: ' + str(path))
    return name, payload


def table_packets(root, app, evaluate, build_dir=None):
    """HK builds packets from byte ranges, not from a C telemetry structure."""
    if app != 'hk':
        return []
    root = Path(root)
    from .catalog import resolve_build
    build = resolve_build(root, build_dir)
    declarations = ('#include "hk_tbldefs.h"\n#include "hk_internal_cfg.h"\n'
                    '#include "cfe_sb_internal_cfg.h"\n'
                    '#undef CFE_SB_MSGID_C\n#define CFE_SB_MSGID_C(value) (value)')
    members = {'input_mid': 'InputMid.Value', 'input_offset': 'InputOffset',
               'output_mid': 'OutputMid.Value', 'output_offset': 'OutputOffset', 'size': 'NumBytes'}
    expressions = ['sizeof(HK_CopyTableEntry_t)', 'HK_COPY_TABLE_ENTRIES',
                   'sizeof(CFE_MSG_TelemetryHeader_t)', 'HK_MAX_COMBINED_PACKET_SIZE',
                   'CFE_PLATFORM_SB_HIGHEST_VALID_MSGID', 'CFE_SB_INVALID_MSG_ID',
                   '__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__',
                   'sizeof(HK_COPY_TABLE_FILENAME)', 'sizeof(HK_COPY_TABLE_NAME)']
    for member in members.values():
        expressions += [f'offsetof(HK_CopyTableEntry_t,{member})',
                        f'sizeof(((HK_CopyTableEntry_t*)0)->{member})']
    values = evaluate(declarations, expressions)
    entry_size, count, header_size, max_size, max_mid, invalid_mid, little, file_len, name_len = values[:9]
    strings = evaluate(declarations,
                       [f'(unsigned char)HK_COPY_TABLE_FILENAME[{i}]' for i in range(file_len)] +
                       [f'(unsigned char)HK_COPY_TABLE_NAME[{i}]' for i in range(name_len)])
    filename = bytes(strings[:file_len]).rstrip(b'\0').decode()
    local_name = bytes(strings[file_len:]).rstrip(b'\0').decode()
    installed = (build / 'exe/cpu1').resolve()
    table_path = (installed / filename.lstrip('/')).resolve()
    if not table_path.is_relative_to(installed):
        raise ValueError('Table path is outside the compiled image')
    from project.appgen.native_startup import parse_startup
    startup = parse_startup((installed / 'cf/cfe_es_startup.scr').read_text())[0]
    runtime_name = next((entry.fields[3] for entry in startup
                         if entry.kind == 'CFE_APP' and entry.name == 'hk'), None)
    expected_name = runtime_name + '.' + local_name if runtime_name else None
    name, payload = table_file_data(table_path, table_layout(evaluate), expected_name)
    if len(payload) != entry_size * count:
        raise ValueError('HK table does not match the compiled layout')
    grouped = {}
    for start in range(0, len(payload), entry_size):
        entry = {}
        for index, key in enumerate(members):
            offset, size = values[9 + index * 2:11 + index * 2]
            entry[key] = int.from_bytes(payload[start + offset:start + offset + size],
                                        'little' if little else 'big')
        valid = lambda mid: mid != invalid_mid and mid <= max_mid
        input_valid, output_valid = valid(entry['input_mid']), valid(entry['output_mid'])
        if not input_valid and not output_valid:
            continue
        if not input_valid or not output_valid or any(
                entry[key] + entry['size'] > max_size for key in ('input_offset', 'output_offset')):
            raise ValueError('Invalid HK table entry: ' + str(start // entry_size))
        grouped.setdefault(entry.pop('output_mid'), []).append(entry)
    # Source comes from the actual table target's dependencies, including mission overrides.
    source = str(table_path.relative_to(root))
    compiler_build = build / 'cache' if (build / 'cache').is_dir() else build
    dependencies = compiler_build.glob('**/default_cpu1/apps/hk/CMakeFiles/tblobj_*.dir/DependInfo.cmake')
    for dependency in dependencies:
        for candidate in re.findall(r'"([^"\n]+\.c)"', dependency.read_text()):
            path = root / 'cFS' / candidate.removeprefix('/cFS/') if candidate.startswith('/cFS/') else Path(candidate)
            if path.stem == table_path.stem and path.is_file() and path.is_relative_to(root):
                source = str(path.relative_to(root))
    packets = []
    for mid, copies in grouped.items():
        size = max(entry['output_offset'] + entry['size'] for entry in copies)
        if size < header_size or mid & 0xF800 != 0x0800:
            raise ValueError('HK packet is incompatible with CCSDS transport: ' + hex(mid))
        warnings = []
        if any(entry['input_offset'] < header_size or entry['output_offset'] < header_size for entry in copies):
            warnings.append('The table copies bytes from the CCSDS header; content is kept as raw bytes.')
        packets.append({'id': f'{name}:{mid:04X}', 'name': f'{name} · 0x{mid:04X}',
                        'app': app, 'mid': mid, 'size': size, 'kind': 'telemetry', 'source': source,
                        'table': str(table_path.relative_to(root)), 'copies': copies, 'warnings': warnings,
                        'fields': [{'name': 'Data', 'type': 'bytes', 'format': 'raw', 'count': 1,
                                    'offset': header_size, 'size': size - header_size}] if size > header_size else []})
    return packets
