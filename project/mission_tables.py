"""Keep native mission tables consistent with CPU1's compiled applications."""
from collections import defaultdict
from pathlib import Path
import re

from project.flight_sources import module_directories


FLAG = "CFS_CPU1_MODULE_SELECTION"


def _mask(text):
    return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda match: re.sub(r'[^\n]', ' ', match[0]), text)


def _owners(root):
    headers, symbols = defaultdict(set), defaultdict(set)
    for application in module_directories(root, "apps"):
        if application.is_symlink() or not (application / "CMakeLists.txt").is_file():
            continue
        # Example missions (notably SBN's) redeclare the entire cFE MID map.
        # Only the app's flight and configuration headers are part of this build.
        roots = (application / "fsw", application / "config")
        for header in (h for directory in roots for h in directory.rglob("*.h")):
            if header.is_symlink():
                continue
            # cFE exposes default_/eds_ configuration headers without their
            # implementation prefix in each CPU's generated include directory.
            for name in {header.name, re.sub(r'^(?:default|eds)_', '', header.name)}:
                headers[name].add(application.name)
            for name in re.findall(r'^\s*#\s*define\s+(\w+)', _mask(header.read_text()), re.M):
                symbols[name].add(application.name)
    return ({name: next(iter(owners)) for name, owners in headers.items() if len(owners) == 1},
            {name: next(iter(owners)) for name, owners in symbols.items() if len(owners) == 1})


def _guard_tables(text, headers, symbols):
    if not re.search(r'\bCFE_SB_MSGID_WRAP_VALUE\s*\(', _mask(text)):
        return text
    # Recompute only guards emitted by this function. This also repairs
    # older missions that attributed a core MID to an example application.
    wrapper = (r"^#if !defined\(CFS_CPU1_MODULE_SELECTION\) \|\| \(defined\(CFS_MODULE_[A-Z0-9_]+\)"
               r"(?: && defined\(CFS_MODULE_[A-Z0-9_]+\))*\)\n([^#]*?|#include[^\n]*)\n#endif$")
    text = re.sub(wrapper, r"\1", text, flags=re.M)
    spans = {}
    for match in re.finditer(r'^[ \t]*#[ \t]*include\s+"([^"\n]+)"[^\n]*', text, re.M):
        owner = headers.get(Path(match[1]).name)
        if owner:
            start = text.rfind('\n', 0, match.start()) + 1
            spans[(start, match.end())] = {owner}
    clean = _mask(text)
    stack, braces = [], []
    for position, char in enumerate(clean):
        if char == '{':
            stack.append(position)
        elif char == '}' and stack:
            braces.append((stack.pop(), position + 1))
    for match in re.finditer(r'\bCFE_SB_MSGID_WRAP_VALUE\s*\(', clean):
        containing = [(start, end) for start, end in braces if start < match.start() < end]
        if not containing:
            continue
        start, end = min(containing, key=lambda pair: pair[1] - pair[0])
        owners = {symbols[word] for word in re.findall(r'\b\w+\b', clean[start:end]) if word in symbols}
        if not owners:
            continue
        line_start = text.rfind('\n', 0, start) + 1
        line_end = text.find('\n', end)
        line_end = len(text) if line_end == -1 else line_end
        if text[line_start:start].strip() or clean[end:line_end].strip().strip(','):
            raise ValueError("Put each native message table entry on its own line before editing mission membership")
        spans[(line_start, line_end)] = owners
    for (start, end), owners in sorted(spans.items(), reverse=True):
        previous = text[:start].rstrip('\n').rsplit('\n', 1)[-1]
        if FLAG in previous:
            continue
        enabled = ' && '.join('defined(CFS_MODULE_' + owner.upper() + ')' for owner in sorted(owners))
        guard = f'#if !defined({FLAG}) || ({enabled})\n'
        text = text[:start] + guard + text[start:end] + '\n#endif' + text[end:]
    return text


def _guard_install(text):
    declaration = 'list(APPEND APP_DEFINITION_TABLE_LIST "CFS_MODULE_${MODULE_SYMBOL}")'
    # CPU1 can compile a module while its startup entry is archived. Only
    # loaded modules should contribute scheduled messages and subscriptions.
    startup = 'set(STUDIO_STARTUP "${MISSION_DEFS}/../cpu1_cfe_es_startup.scr")'
    read_startup = "\n".join([
        startup, 'if(EXISTS "${STUDIO_STARTUP}")',
        '    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${STUDIO_STARTUP}")',
        '    file(STRINGS "${STUDIO_STARTUP}" STUDIO_ACTIVE_LINES REGEX "^[ \\t]*CFE_(APP|LIB),")',
        '    set(STUDIO_LOADED_MODULES)',
        '    foreach(RECORD IN LISTS STUDIO_ACTIVE_LINES)',
        '        string(REGEX REPLACE "^[^,]+,[ \\t]*([^, \\t]+).*" "\\\\1" ACTIVE_MODULE "${RECORD}")',
        '        list(APPEND STUDIO_LOADED_MODULES "${ACTIVE_MODULE}")',
        '    endforeach()', 'endif()', ''])
    def apply_startup(source):
        if startup in source:
            return source
        guard = ('if(NOT EXISTS "${STUDIO_STARTUP}" OR MODULE IN_LIST STUDIO_LOADED_MODULES)\n'
                 '            ' + declaration + '\n        endif()')
        return source.replace('list(APPEND APP_DEFINITION_TABLE_LIST ' + FLAG + ')',
                              read_startup + 'list(APPEND APP_DEFINITION_TABLE_LIST ' + FLAG + ')').replace(declaration, guard)
    if FLAG in text:
        return apply_startup(text)
    # Remove references to a fixed set of app targets; derive them from the
    # actual APPLIST below. Keep custom non-target include paths intact.
    text = re.sub(r'^\s*\$<TARGET_PROPERTY:[A-Za-z][A-Za-z0-9_]*,INCLUDE_DIRECTORIES>\s*$', '', text, flags=re.M)
    dynamic = '\n'.join([
        f'list(APPEND APP_DEFINITION_TABLE_LIST {FLAG})',
        'foreach(MODULE IN LISTS ${TGTNAME}_APPLIST)',
        '    if(TARGET ${MODULE})',
        '        string(TOUPPER "${MODULE}" MODULE_SYMBOL)',
        '        list(APPEND APP_DEFINITION_TABLE_LIST "CFS_MODULE_${MODULE_SYMBOL}")',
        '        list(APPEND APP_INCLUDE_TABLE_LIST $<TARGET_PROPERTY:${MODULE},INCLUDE_DIRECTORIES>)',
        '    endif()',
        'endforeach()', '',
    ])
    first = re.search(r'(?m)^target_(?:include_directories|compile_definitions)\(', text)
    if not first:
        raise ValueError("CPU1 install_custom.cmake has no native table target configuration")
    text = text[:first.start()] + dynamic + '\n' + text[first.start():]
    pattern = r'(?m)^([ \t]*)(target_include_directories|target_compile_definitions|add_cfe_tables)\(\s*([A-Za-z][A-Za-z0-9_.]*)\b([^)]*)\)'
    def guard(match):
        indent, command, target, arguments = match.groups()
        return (f'{indent}if(TARGET {target})\n{indent}    {command}({target}{arguments})\n'
                f'{indent}endif()')
    return apply_startup(re.sub(pattern, guard, text))


def table_membership_plan(root, sources=None):
    """Return native C/CMake edits; application source files are not edited.

    Guards use CPU1 APPLIST at CMake configure time. CPU2 retains the original
    shared-table behavior because it does not define the CPU1 selection flag.
    """
    root = Path(root)
    sources = sources or {}
    headers, symbols = _owners(root)
    plan = {}
    definitions = root / "mission/sample_defs"
    for path in sorted(definitions.rglob("*.c")):
        if path.is_symlink():
            raise ValueError("Mission tables must remain inside the project")
        relative = path.relative_to(root).as_posix()
        original = sources.get(relative, path.read_text())
        if original is None:
            continue
        updated = _guard_tables(original, headers, symbols)
        if updated != original:
            plan[path.relative_to(root).as_posix()] = updated
    install = definitions / "cpu1/install_custom.cmake"
    original = sources.get(install.relative_to(root).as_posix(), install.read_text())
    updated = _guard_install(original)
    if updated != original:
        plan[install.relative_to(root).as_posix()] = updated
    return plan
