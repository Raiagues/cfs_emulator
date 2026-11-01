"""Check generated rows against the selected CPU1 table declarations.

The native C preprocessor evaluates table conditions; a C static assertion checks
the declared array capacity. Missing tables/tools, unsupported initializers
and unresolved constants are left to the normal build; no fallback limits are
invented. The generated includes are replaced in memory before counting rows.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


class Unresolved(Exception):
    pass


def _clean(text):
    # Keep strings intact, including filenames and comment-like text in strings.
    return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*',
                  lambda m: m[0] if m[0][0] in "\"'" else re.sub(r'[^\n]', ' ', m[0]), text)


def _read(root, path):
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise Unresolved()
    try:
        return _clean(path.read_text())
    except (OSError, UnicodeError) as error:
        raise Unresolved() from error


def _select(root, app, name, subdir):
    mission = root / 'sample_defs'
    if subdir == 'config':
        # SCH/TO table and interface headers belong to MISSION_CONFIG_FILE_LIST,
        # so generate_configfile_set runs without architecture/CPU prefixes.
        candidates = [mission / 'config' / name, mission / name]
        candidates.extend([root / 'apps' / app / 'config' / ('default_' + name),
                           root / 'apps' / app / 'fsw' / 'inc' / name,
                           root / 'apps' / app / 'fsw' / 'public_inc' / name])
    else:
        candidates = [mission / 'cpu1' / subdir / name, mission / subdir / ('cpu1_' + name),
                      mission / subdir / name, mission / 'cpu1' / name,
                      mission / ('cpu1_' + name), mission / name]
        candidates.append(root / 'apps' / app / 'fsw' / subdir / name)
    return next((path for path in candidates if path.is_file()), None)


def _header_directives(root, app, name, seen=None):
    """Keep native preprocessor directives; packet types are not needed here."""
    seen = set() if seen is None else seen
    path = _select(root, app, name, 'config')
    if path is None or path in seen:
        return ''
    seen.add(path)
    lines = []
    for line in _read(root, path).replace('\\\n', ' ').splitlines():
        include = re.match(r'\s*#\s*include\s+"([^"/]+)"', line)
        if include:
            lines.append(_header_directives(root, app, include[1], seen))
        elif re.match(r'\s*#', line):
            lines.append(line)
    return '\n'.join(lines)


def _capacity(root, app, field):
    path = _select(root, app, app + '_tblstruct.h', 'config')
    if path is None:
        raise Unresolved()
    arrays = re.findall(r'\b' + field + r'\s*\[([^\]]+)\]', _read(root, path))
    if len(arrays) != 1:
        raise Unresolved()
    return arrays[0], _header_directives(root, app, app + '_tblstruct.h')


def _compiler(source, *arguments):
    compiler = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if not compiler:
        raise Unresolved()
    try:
        return subprocess.run([compiler, '-x', 'c', '-std=c11', *arguments, '-'],
                              input=source, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Unresolved() from error


def _flags(definitions):
    return '\n'.join('#define ' + (item.replace('=', ' ', 1) if '=' in item else item + ' 1')
                     for item in definitions if item not in {'INTERFACE', 'PRIVATE', 'PUBLIC'})


def _compile_definitions(root):
    """Evaluate source CMake lists with the repository's builder arguments.

    CMake runs in script mode in a temporary directory. Installation, table
    generation and target mutations are replaced by no-op/capture functions.
    No configured build directory or deployed binary is consulted.
    """
    if not shutil.which('cmake'):
        raise Unresolved()
    from project.cfs_config import build_profile
    try:
        architecture = build_profile(root.parent)['architecture']
    except (OSError, ValueError) as error:
        raise Unresolved() from error
    custom = root / 'sample_defs/cpu1/install_custom.cmake'
    text = _read(root, custom)
    # TARGET is unavailable in script mode; substitute membership in the same
    # CPU1 module lists that create those targets in the real configure pass.
    text = re.sub(r'\bTARGET\s+(\$\{[^}]+\}|[A-Za-z_][\w.]*)', r'"\1" IN_LIST CAPACITY_MODULES', text)
    text = text.replace('${CMAKE_CURRENT_LIST_DIR}', custom.parent.as_posix())
    quote = lambda path: '[=[' + str(path) + ']=]'
    with tempfile.TemporaryDirectory(prefix='cfs-capacity-') as directory:
        temp = Path(directory)
        (temp / 'tables.cmake').write_text(text)
        script = '\n'.join([
            'cmake_minimum_required(VERSION 3.16)',
            f'set(SIMULATION {architecture})', 'set(CFE_EDS_ENABLED OFF)', 'set(TGTNAME cpu1)',
            f'set(MISSION_DEFS {quote(root / "sample_defs")})',
            f'set(MISSION_SOURCE_DIR {quote(root)})',
            f'include({quote(root / "cfe/cmake/mission_defaults.cmake")} OPTIONAL)',
            f'include({quote(root / "sample_defs/targets.cmake")})',
            'set(CAPACITY_MODULES ${MISSION_GLOBAL_APPLIST} ${MISSION_GLOBAL_STATIC_APPLIST} ${cpu1_APPLIST} ${cpu1_STATIC_APPLIST})',
            'function(install)\nendfunction()', 'function(add_cfe_tables)\nendfunction()',
            'function(target_include_directories)\nendfunction()',
            'function(target_compile_definitions name)',
            'message("CAPACITY_DEFINES:${name}:${ARGN}")', 'endfunction()',
            f'include({quote(temp / "tables.cmake")})',
        ])
        (temp / 'check.cmake').write_text(script)
        try:
            result = subprocess.run(['cmake', '-P', str(temp / 'check.cmake')], cwd=temp,
                                    capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Unresolved() from error
        if result.returncode:
            raise Unresolved()
    definitions = {}
    for name, values in re.findall(r'^CAPACITY_DEFINES:([^:]+):([^\n]*)', result.stderr + result.stdout, re.M):
        definitions.setdefault(name, set()).update(values.split(';'))
    return definitions


def _matching(text, start):
    depth = 0
    for index in range(start, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return index
    raise Unresolved()


def _row_count(root, table, field, fragment, count, definitions):
    text = _read(root, table)
    match = re.search(r'\.' + field + r'\s*=\s*\{', text)
    if not match:
        raise Unresolved()
    opening = match.end() - 1
    closing = _matching(text, opening)
    replaced = False
    def include(match):
        nonlocal replaced
        if match[1] != fragment:
            if opening < match.start() < closing:
                raise Unresolved()  # Additional initializer fragments need their own source analysis.
            return ''
        replaced = True
        return '{},' * count
    text = re.sub(r'^\s*#\s*include\s+"([^"\n]+)"[^\n]*', include, text, flags=re.M)
    if not replaced:
        raise Unresolved()
    result = _compiler(_flags(definitions) + '\n' + text, '-E', '-P')
    if result.returncode:
        raise Unresolved()
    match = re.search(r'\.' + field + r'\s*=\s*\{', result.stdout)
    if not match:
        raise Unresolved()
    opening = match.end() - 1
    body = result.stdout[opening + 1:_matching(result.stdout, opening)]
    rows, position = 0, 0
    while position < len(body):
        while position < len(body) and (body[position].isspace() or body[position] == ','):
            position += 1
        if position == len(body):
            break
        if body[position] != '{':
            raise Unresolved()
        position = _matching(body, position) + 1
        rows += 1
    return rows


def validate_mission_capacity(root, manifests):
    """Raise ValueError only for a source-proven CPU1 table overflow."""
    root = Path(root).resolve()
    specs = [('sch_lab', 'sch_lab_table.c', 'Config', 'appgen_schedule.inc', 2 * len(manifests)),
             ('to_lab', 'to_lab_sub.c', 'Subs', 'appgen_telemetry.inc',
              sum(1 + len(app['sensors']) + len(app['telemetry']) for app in manifests))]
    tables = [(app, _select(root, app, name, 'tables'), field, fragment, count)
              for app, name, field, fragment, count in specs]
    if not any(table for _, table, _, _, _ in tables):
        return
    try:
        definitions = _compile_definitions(root)
    except Unresolved:
        return
    for app, table, field, fragment, count in tables:
        if table is None or app + '.table' not in definitions:
            continue
        try:
            expression, directives = _capacity(root, app, field)
            rows = _row_count(root, table, field, fragment, count, definitions[app + '.table'])
            declaration = _flags(definitions[app + '.table']) + '\n' + directives
            declaration += '\nenum { CAPACITY = (' + expression + ') };\n'
            if _compiler(declaration, '-fsyntax-only').returncode:
                continue
            check = declaration + '_Static_assert(' + str(rows) + ' <= CAPACITY, \"Table capacity exceeded\");\n'
            overflow = _compiler(check, '-fsyntax-only').returncode != 0
        except Unresolved:
            continue
        if overflow:
            raise ValueError(f'{table.relative_to(root)}: {rows} {field} entries exceed '
                             f'{expression} ({count} generated rows). '
                             'Reduce the generated entries or update the mission table capacity.')
