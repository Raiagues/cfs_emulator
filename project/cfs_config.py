"""Read upstream cFS configuration and plan native mission overrides on demand."""
from pathlib import Path
import os
import re
import subprocess
import tempfile


STARTUP = 'cFS/sample_defs/cpu1_cfe_es_startup.scr'
GENERATED = 'cFS/sample_defs/generated/'


def build_profile(root, config=None):
    from project.model import load_config, board_catalog, ProjectError
    config = load_config(root) if config is None else config
    if config['board'] is None:
        return {'architecture': 'native', 'cmake': {}}
    profile = board_catalog(config['board'], root).get('build', {}).get(config['os'])
    if not profile or not re.fullmatch(r'[A-Za-z0-9_.-]+', profile.get('architecture', '')):
        raise ProjectError('No build toolchain configured for this board and operating system')
    for name, value in profile.get('cmake', {}).items():
        if not re.fullmatch(r'(?:CMAKE|CFE|OSAL)_[A-Z0-9_]+', name) or not isinstance(value, str) or ']=]' in value:
            raise ProjectError('Invalid native toolchain setting: ' + name)
    return profile


def evaluate_mission(root, config=None):
    """Evaluate NASA's own targets/startup generator without writing the checkout."""
    from project.model import safe_path, ProjectError
    root = Path(root)
    quote = lambda value: '[=[' + str(value) + ']=]'
    architecture = build_profile(root, config)['architecture']
    with tempfile.TemporaryDirectory(prefix='cfs-native-config-') as directory:
        work = Path(directory)
        (work / 'cpu1/cf').mkdir(parents=True)
        script = '\n'.join([
            'set(CFE_EDS_ENABLED OFF)', f'set(SIMULATION {architecture})',
            f'include({quote(safe_path(root, "cFS/cfe/cmake/mission_defaults.cmake"))})',
            f'include({quote(safe_path(root, "cFS/sample_defs/targets.cmake"))})',
            'list(APPEND cpu1_APPLIST ${MISSION_GLOBAL_APPLIST})',
            'list(REMOVE_DUPLICATES cpu1_APPLIST)',
            f'file(WRITE {quote(work / "compiled")} "${{cpu1_APPLIST}}")',
            f'file(WRITE {quote(work / "core")} "${{MISSION_CORE_MODULES}}")',
            f'file(WRITE {quote(work / "libraries")} "${{MISSION_LIBRARIES}}")',
            f'include({quote(safe_path(root, "cFS/sample_defs/generate_startup.cmake"))})',
            'set(CFS_STARTUP_IGNORE_OVERRIDE TRUE)',
            f'set(CMAKE_INSTALL_PREFIX {quote(work)})',
            'generate_cfs_startup_script("cpu1/cf" ${cpu1_APPLIST})',
        ])
        (work / 'inspect.cmake').write_text(script)
        environment = os.environ.copy()
        environment.pop('DESTDIR', None)
        result = subprocess.run(['cmake', '-P', str(work / 'inspect.cmake')], cwd=root,
                                env=environment, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ProjectError('Cannot evaluate native mission configuration: ' + result.stderr.strip()[-2000:])
        values = {name: [item for item in (work / file).read_text().split(';') if item]
                  for name, file in [('compiled', 'compiled'), ('core', 'core'), ('library_roots', 'libraries')]}
        values['default'] = (work / 'cpu1/cf/cfe_es_startup.scr').read_text()
        return values


def native_startup(root, config=None):
    from project.model import safe_path
    path = safe_path(root, STARTUP)
    return path.read_text() if path.is_file() else evaluate_mission(root, config)['default']


def configured(root, config):
    """An untouched native clone needs no generated mission files for sync/build."""
    return bool(config['board'] or config['apps'] or (Path(root) / GENERATED / 'appgen.cmake').exists())


def module_limits_plan(root, files):
    """Size the native loader buffers for the final startup, including the NUL."""
    from project.model import safe_path
    from project.appgen.native_startup import parse_startup
    if STARTUP not in files:
        return {}
    active, archived = parse_startup(files[STARTUP])
    records = active + archived
    defaults = safe_path(root, 'cFS/osal/default_config.cmake').read_text()
    default = lambda name: int(re.search(r'\bset\s*\(\s*OSAL_CONFIG_' + name + r'\s+(\d+)\b', defaults, re.I)[1])
    # cFE's wire definitions require name buffers to be multiples of four.
    aligned = lambda size: (size + 3) // 4 * 4
    api = aligned(max([default('MAX_API_NAME')] + [len(value) + 1 for entry in records for value in entry.fields[2:4]]))
    file = aligned(max([default('MAX_FILE_NAME')] + [len(Path(entry.fields[1]).name.removesuffix('.so') + '.so') + 1 for entry in records]))
    minimum = {'MAX_API_NAME': api, 'MAX_FILE_NAME': file, 'MAX_MODULES': max(default('MAX_MODULES'), len(active))}
    plan = {}
    marker = 'MISSION MODULE LIMITS'
    def original(relative):
        path = safe_path(root, relative)
        text = files.get(relative, path.read_text() if path.is_file() else '')
        return re.sub(r'\n(?:#|/\*) ' + marker + r' BEGIN.*?' + marker + r' END(?: \*/)?\n?', '', text, flags=re.S).rstrip()
    osconfig = 'cFS/sample_defs/default_osconfig.cmake'
    text = original(osconfig)
    lines = [f'# {marker} BEGIN']
    for name, size in minimum.items():
        if size > default(name):
            lines += [f'if(OSAL_CONFIG_{name} LESS {size})', f'    set(OSAL_CONFIG_{name} {size})', 'endif()']
    if api > default('MAX_API_NAME'):
        # EVS checks its event text + API name + port prefix against OS_BUFFER_SIZE.
        overhead = default('PRINTF_BUFFER_SIZE') - default('MAX_API_NAME')
        lines += [f'math(EXPR MISSION_PRINTF_MIN "${{OSAL_CONFIG_MAX_API_NAME}} + {overhead}")',
                  'if(OSAL_CONFIG_PRINTF_BUFFER_SIZE LESS MISSION_PRINTF_MIN)',
                  '    set(OSAL_CONFIG_PRINTF_BUFFER_SIZE ${MISSION_PRINTF_MIN})', 'endif()']
    if len(lines) > 1:
        text += '\n\n' + '\n'.join([*lines, f'# {marker} END'])
    plan[osconfig] = text + '\n'
    header = 'cFS/sample_defs/cfe_core_api_interface_cfg_values.h'
    text = original(header)
    if api > default('MAX_API_NAME') or file > default('MAX_FILE_NAME'):
        if not text:
            text = safe_path(root, 'cFS/cfe/modules/core_api/config/default_cfe_core_api_interface_cfg_values.h').read_text().rstrip()
        match = re.search(r'^#define\s+CFE_MISSION_CORE_API_CFGVAL\(x\)\s+([^\n]+)$', text, re.M)
        if not match or match[1].endswith('\\'):
            raise ValueError('Define CFE_MISSION_CORE_API_CFGVAL(x) on one line before extending native module names')
        interface = safe_path(root, 'cFS/cfe/modules/core_api/fsw/inc/cfe_core_api_interface_cfg.h').read_text()
        names = sorted(set(re.findall(r'CFE_MISSION_CORE_API_CFGVAL\(([A-Z_]+)\)', interface)))
        lines = [f'/* {marker} BEGIN */', '#define MODULE_LIMIT_BASE_CFGVAL(x) ' + match[1],
                 '#undef CFE_MISSION_CORE_API_CFGVAL', '#define CFE_MISSION_CORE_API_CFGVAL(x) MODULE_LIMIT_##x']
        for name in names:
            base = 'MODULE_LIMIT_BASE_CFGVAL(' + name + ')'
            size = {'MAX_API_LEN': api, 'MAX_FILE_LEN': file}.get(name)
            value = f'(({base} > {size}) ? {base} : {size})' if size else base
            lines.append(f'#define MODULE_LIMIT_{name} {value}')
        text += '\n\n' + '\n'.join([*lines, f'/* {marker} END */'])
    if text:
        plan[header] = text + '\n'
    return plan


def _startup_override(text):
    if 'CFS_STARTUP_IGNORE_OVERRIDE' in text:
        return text
    renamed = re.sub(r'(function\s*\(\s*)generate_cfs_startup_script\b', r'\1generate_upstream_startup_script', text, count=1, flags=re.I)
    renamed = re.sub(r'(endfunction\s*\(\s*)generate_cfs_startup_script\b', r'\1generate_upstream_startup_script', renamed, flags=re.I)
    if renamed == text:
        raise ValueError('The upstream startup generator does not define generate_cfs_startup_script')
    return renamed.rstrip() + '''

set(MISSION_CPU1_STARTUP "${CMAKE_CURRENT_LIST_DIR}/cpu1_cfe_es_startup.scr")
set(MISSION_APPGEN_STARTUP "${CMAKE_CURRENT_LIST_DIR}/generated/appgen_startup.scr")
function(generate_cfs_startup_script CFS_INSTALL_DIR)
    set(STARTUP_FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/${CFS_INSTALL_DIR}/cfe_es_startup.scr")
    if(CFS_INSTALL_DIR MATCHES "^cpu1/" AND EXISTS "${MISSION_CPU1_STARTUP}" AND NOT CFS_STARTUP_IGNORE_OVERRIDE)
        file(READ "${MISSION_CPU1_STARTUP}" ACTIVE_STARTUP)
        string(FIND "${ACTIVE_STARTUP}" "!" EOF_POSITION)
        if(EOF_POSITION GREATER_EQUAL 0)
            string(SUBSTRING "${ACTIVE_STARTUP}" 0 ${EOF_POSITION} ACTIVE_STARTUP)
        endif()
        string(REGEX MATCHALL "CFE_(APP|LIB),[^,;]+," STARTUP_MODULES "${ACTIVE_STARTUP}")
        foreach(ENTRY IN LISTS STARTUP_MODULES)
            string(REGEX REPLACE "^CFE_(APP|LIB),[ \\t]*([^,]+),$" "\\\\2" MODULE "${ENTRY}")
            string(STRIP "${MODULE}" MODULE)
            get_filename_component(MODULE "${MODULE}" NAME_WE)
            list(FIND ARGN "${MODULE}" MODULE_INDEX)
            if(MODULE_INDEX LESS 0)
                message(FATAL_ERROR "Startup module '${MODULE}' is not in the CPU1 APPLIST")
            endif()
        endforeach()
        configure_file("${MISSION_CPU1_STARTUP}" "${STARTUP_FILE}" COPYONLY)
    else()
        generate_upstream_startup_script("${CFS_INSTALL_DIR}" ${ARGN})
        if(CFS_INSTALL_DIR MATCHES "^cpu1/" AND EXISTS "${MISSION_APPGEN_STARTUP}")
            file(READ "${MISSION_APPGEN_STARTUP}" GENERATED_STARTUP)
            file(APPEND "${STARTUP_FILE}" "${GENERATED_STARTUP}")
        endif()
    endif()
endfunction()
'''


def bootstrap_plan(root, config=None):
    """Prepare ordinary CMake, startup and table edits for an explicit mutation."""
    from project.model import safe_path, load_config, appgen
    root = Path(root)
    config = load_config(root) if config is None else config
    plan = {}
    targets = 'cFS/sample_defs/targets.cmake'
    text = safe_path(root, targets).read_text()
    if 'generated/appgen.cmake' not in text:
        text = text.rstrip() + '''

include(${CMAKE_CURRENT_LIST_DIR}/generated/appgen.cmake OPTIONAL)
include(${CMAKE_CURRENT_LIST_DIR}/libraries.cmake OPTIONAL)
list(APPEND cpu1_APPLIST ${APPGEN_LIBS} ${APPGEN_APPS} ${MISSION_LIBRARIES})
'''
        plan[targets] = text
    libraries = 'cFS/sample_defs/libraries.cmake'
    if not safe_path(root, libraries).exists():
        plan[libraries] = '# Libraries explicitly selected for CPU1.\nset(MISSION_LIBRARIES)\n'
    for path, content in appgen(root).render_mission([], []).items():
        relative = 'cFS/' + path
        if not safe_path(root, relative).exists():
            plan[relative] = content
    if not safe_path(root, STARTUP).exists():
        plan[STARTUP] = native_startup(root, config)
    elif any(config[key] != load_config(root)[key] for key in ('board', 'os')):
        from project.appgen.native_startup import parse_startup, render_startup
        active, archived = parse_startup(native_startup(root, config))
        compiled = set(evaluate_mission(root, config)['compiled'])
        unavailable = [entry for entry in active if entry.name not in compiled]
        if unavailable:
            archive = {entry.name: entry for entry in archived + unavailable}
            plan[STARTUP] = render_startup([entry for entry in active if entry.name in compiled], list(archive.values()))
    generator = 'cFS/sample_defs/generate_startup.cmake'
    original = safe_path(root, generator).read_text()
    updated = _startup_override(original)
    if updated != original:
        plan[generator] = updated
    install = 'cFS/sample_defs/cpu1/install_custom.cmake'
    original = safe_path(root, install).read_text()
    if 'APPGEN_ENABLED' not in original:
        block = '''list(APPEND APP_DEFINITION_TABLE_LIST APPGEN_ENABLED)
list(APPEND APP_INCLUDE_TABLE_LIST ${MISSION_DEFS}/generated)
foreach(APP IN LISTS APPGEN_APPS)
    if(TARGET ${APP})
        list(APPEND APP_INCLUDE_TABLE_LIST $<TARGET_PROPERTY:${APP},INCLUDE_DIRECTORIES>)
    endif()
endforeach()

'''
        match = re.search(r'(?m)^target_include_directories\(', original)
        if not match:
            raise ValueError('CPU1 install_custom.cmake has no native table target configuration')
        plan[install] = original[:match.start()] + block + original[match.start():]
    for name, field, fragment in [('sch_lab_table.c', 'Config', 'appgen_schedule.inc'),
                                  ('to_lab_sub.c', 'Subs', 'appgen_telemetry.inc')]:
        path = 'cFS/sample_defs/tables/' + name
        original = safe_path(root, path).read_text()
        updated = original
        if 'appgen_includes.h' not in updated:
            marker = re.search(r'/\*\s*clang-format:\s*off\s*\*/', updated)
            if not marker:
                raise ValueError('Cannot locate native message table declaration: ' + name)
            updated = updated[:marker.start()] + '#ifdef APPGEN_ENABLED\n#include "appgen_includes.h"\n#endif\n\n' + updated[marker.start():]
        if fragment not in updated:
            updated, count = re.subn(r'(\.' + field + r'\s*=\s*\{)',
                lambda m: m[0] + '\n#ifdef APPGEN_ENABLED\n#include "' + fragment + '"\n#endif', updated, count=1)
            if not count:
                raise ValueError('Cannot locate native message table entries: ' + name)
        if updated != original:
            plan[path] = updated
    profile = build_profile(root, config)
    if profile['architecture'] != 'native':
        path = 'cFS/sample_defs/toolchain-' + profile['architecture'] + '.cmake'
        if not safe_path(root, path).is_file():
            plan[path] = '# Selected board and operating-system toolchain.\n' + ''.join(
                f'set({name} [=[{value}]=])\n' for name, value in profile['cmake'].items())
    return plan
