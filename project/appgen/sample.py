"""Create mission modules from the sample sources in the selected cFS checkout."""
from pathlib import Path
import re

from project.c_source import blank_lexemes, closing
from project.appgen.source_tags import region


def in_function(source, name, anchor, path):
    """Locate a semantic integration point inside a single upstream C definition."""
    code = blank_lexemes(source)
    definitions = list(re.finditer(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", code))
    if len(definitions) == 1:
        start = definitions[0].end() - 1
        end = closing(code, start, "{", "}")
        matches = list(re.finditer(anchor, code[start:end], re.M)) if end is not None else []
        if len(matches) == 1:
            return start + matches[0].start()
    raise ValueError(f"{path}: expected one integration point in NASA function {name}")


def hal_fragment(name, prefix):
    template = Path(__file__).with_name("templates") / "hal_sensor" / (name + ".c.in")
    return template.read_text().replace("@PREFIX@", prefix)


def copy_sample(root, sample, name):
    parent = 'libs' if sample == 'sample_lib' else 'apps'
    directory = Path(root).parent / "cFS" / parent / sample
    if not (directory / 'CMakeLists.txt').is_file():
        raise ValueError(f"Download the cFS {sample} submodule first")
    def rename(text):
        if sample == "sample_app":
            text = text.replace('"SAMPLE:', '"' + name.upper() + ':')
        return (text.replace(sample.upper(), name.upper()).replace(sample, name)
                .replace(sample.replace('_', ' ').title(), name.replace('_', ' ').title()))
    files = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory)
        if any(part.startswith('.') for part in relative.parts) or not path.is_file() or path.is_symlink():
            continue
        if relative.parts[0] in ('CHANGELOG.md','SECURITY.md','CONTRIBUTING.md'):
            continue
        files[rename(relative.as_posix())] = rename(path.read_text())
    return files


def library_sources(root, name):
    """Expose edit points in the library copied from the selected NASA source."""
    files = copy_sample(root, "sample_lib", name)
    path = f"fsw/src/{name}.c"
    for suffix, point in (("Init", "init"), ("Function", "function")):
        source = files[path]
        # The example function is optional in other versions of sample_lib.
        symbol = f"{name.upper()}_{suffix}"
        if suffix == "Function" and symbol not in blank_lexemes(source):
            continue
        offset = in_function(source, symbol, r"\A\{", path) + 1
        files[path] = source[:offset] + f"\n    /* @studio.edit library.{point} */" + source[offset:]
    return files


def extend_app(root, manifest, additions, values):
    """Keep upstream initialization, tables, commands and run loop. Insert mission hooks."""
    name = manifest['name']
    prefix = name.upper()
    files = {path:(source,False) for path,source in copy_sample(root,'sample_app',name).items()}

    def insert(path, anchor, text, slot=None, function=None):
        source = files[path][0]
        if function:
            offset = in_function(source, prefix + "_" + function, anchor, path)
        else:
            if source.count(anchor) != 1:
                raise ValueError(f"Cannot locate unique NASA sample integration point in {path}: {anchor}")
            offset = source.index(anchor)
        if slot:
            text = region(slot, text)
        files[path] = source[:offset] + text + source[offset:], True

    # Start with the active upstream checkout. The editor locates user code by
    # @studio.edit, while synchronization only replaces the bounded regions.
    for path, (source, managed) in additions.items():
        if path not in files and path.startswith('fsw/src/'):
            files[path] = (source, managed and "/* @studio.begin " in source)
    for suffix in ('msgids', 'perfids'):
        path = f'config/default_{name}_{suffix}.h'
        files[path] = additions[path]
    src = f'fsw/src/{name}'
    dispatch = src + '_dispatch.c'
    include = f'#include "{name}_components.h"\n'
    insert(src + '.c', f'#include "{name}.h"', include, 'app.includes')
    insert(src + '.c', r'^[ \t]*return\s+status\s*;', hal_fragment('subscribe', prefix),
           'app.subscribe', 'Init')
    insert(dispatch, f'#include "{name}.h"', include + values['COMMAND_INCLUDES'] + '\n', 'dispatch.includes')
    insert(dispatch, r'^[ \t]*default\s*:', values['COMMAND_CASES'] + '\n', 'dispatch.commands', 'ProcessGroundCommand')
    insert(dispatch, r'^[ \t]*else\s+if\s*\(\s*CFE_SB_MsgId_Equal\s*\(\s*MsgId\s*,\s*CMD_MID\s*\)',
           hal_fragment('wakeup', prefix), 'dispatch.wakeup', 'TaskPipe')
    insert(f'fsw/inc/{name}_fcncodes.h', '#endif', values['COMMAND_CODES'] + '\n', 'command.codes')
    insert(f'fsw/inc/{name}_eventids.h', '#endif',
           f'#define {prefix}_SENSOR_READ_ERR_EID 13\n#define {prefix}_SENSOR_VALUE_INF_EID 14\n\n', 'sensor.events')
    extra = [line for line in values['SOURCES'].splitlines() if line.strip() not in
             (src+'.c',src+'_cmds.c',dispatch)]
    insert('CMakeLists.txt','set(APP_SRC_FILES', 'if(CFE_EDS_ENABLED)\n  message(FATAL_ERROR "Studio mission extensions require the non-EDS build profile.")\nendif()\n\n')
    insert('CMakeLists.txt','# Create the app module',
           'list(APPEND APP_SRC_FILES\n# APPGEN BEGIN SOURCES\n'+'\n'.join(extra)+'\n# APPGEN END SOURCES\n)\n\n')
    insert('CMakeLists.txt','# Add table',f'target_include_directories({name} PRIVATE fsw/src)\n# APPGEN BEGIN DEPENDENCIES\n'+values['DEPENDENCIES']+'\n# APPGEN END DEPENDENCIES\n\n')
    return files
