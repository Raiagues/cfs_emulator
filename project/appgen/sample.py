"""Create mission modules from the sample sources in the selected cFS checkout."""
from pathlib import Path


def copy_sample(root, sample, name):
    parent = 'libs' if sample == 'sample_lib' else 'apps'
    directory = Path(root).parent / "cFS" / parent / sample
    if not (directory / 'CMakeLists.txt').is_file():
        raise ValueError(f"Download the cFS {sample} submodule first")
    def rename(text):
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


def extend_app(root, manifest, additions, values):
    """Keep upstream initialization, tables, commands and run loop. Insert mission hooks."""
    name = manifest['name']
    prefix = name.upper()
    files = {path:(source,False) for path,source in copy_sample(root,'sample_app',name).items()}

    def insert(path, anchor, text):
        source = files[path][0]
        if source.count(anchor) != 1:
            raise ValueError(f'Cannot locate sample integration point in {path}: {anchor}')
        files[path] = source.replace(anchor, text + anchor), True

    # The checked-out sample owns its dispatch and its four standard commands.
    # The generator owns the new sensor, command, telemetry and user-hook files.
    for path, data in additions.items():
        if path not in files and path.startswith('fsw/src/'):
            files[path] = data
    for suffix in ('msgids','perfids'):
        path = f'config/default_{name}_{suffix}.h'
        files[path] = additions[path]
    src = f'fsw/src/{name}'
    dispatch = src+'_dispatch.c'
    include = f'#include "{name}_components.h"\n'
    insert(src+'.c',f'#include "{name}.h"',include)
    insert(src+'.c','    return status;',f'''
    /* Attach the mission readers after the sample has initialized its tables. */
    if (status == CFE_SUCCESS)
    {{
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId({prefix}_WAKEUP_MID), {prefix}_Data.CommandPipe);
    }}
    if (status == CFE_SUCCESS)
    {{
        status = {prefix}_ComponentsInit();
    }}
''')
    insert(dispatch,f'#include "{name}.h"', include + values['COMMAND_INCLUDES']+'\n')
    insert(dispatch,'        default:', values['COMMAND_CASES']+'\n')
    insert(dispatch,'    else if (CFE_SB_MsgId_Equal(MsgId, CMD_MID))',f'''    else if (CFE_SB_MsgId_Equal(MsgId, CFE_SB_ValueToMsgId({prefix}_WAKEUP_MID)))
    {{
        if ({prefix}_VerifyCmdLength(&SBBufPtr->Msg, sizeof(CFE_MSG_CommandHeader_t)))
        {{
            {prefix}_ComponentsWakeup();
        }}
    }}
''')
    insert(f'fsw/inc/{name}_fcncodes.h','#endif',values['COMMAND_CODES']+'\n')
    insert(f'fsw/inc/{name}_eventids.h','#endif',f'#define {prefix}_SENSOR_READ_ERR_EID 13\n#define {prefix}_SENSOR_VALUE_INF_EID 14\n\n')
    extra = [line for line in values['SOURCES'].splitlines() if line.strip() not in
             (src+'.c',src+'_cmds.c',dispatch)]
    insert('CMakeLists.txt','set(APP_SRC_FILES', 'if(CFE_EDS_ENABLED)\n  message(FATAL_ERROR "Studio mission extensions require the non-EDS build profile.")\nendif()\n\n')
    insert('CMakeLists.txt','# Create the app module',
           'list(APPEND APP_SRC_FILES\n# APPGEN BEGIN SOURCES\n'+'\n'.join(extra)+'\n# APPGEN END SOURCES\n)\n\n')
    insert('CMakeLists.txt','# Add table',f'target_include_directories({name} PRIVATE fsw/src)\n# APPGEN BEGIN DEPENDENCIES\n'+values['DEPENDENCIES']+'\n# APPGEN END DEPENDENCIES\n\n')
    return files
