"""Library relationships from C calls/CMake and local Git changes."""
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess


def _git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=10)
    return result.stdout if result.returncode == 0 else b''


def _changes(root):
    records = _git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=normal').decode().split('\0')
    changed = []
    skip = False
    for record in records:
        if skip:
            skip = False
            continue
        if not record:
            continue
        status, path = record[:2], record[3:].rstrip('/')
        changed.append((path, 'new' if status == '??' or status[0] == 'A' else 'modified'))
        skip = 'R' in status or 'C' in status
    return changed


def _module_change(path, changes):
    matches = [status for entry, status in changes if entry == path or entry.startswith(path + '/')
               or path.startswith(entry + '/')]
    return 'modified' if 'modified' in matches else 'new' if matches else 'clean'


def _reference(function):
    return {key: function[key] for key in ('path', 'line', 'end_line', 'symbol')}


def _declared(root, module, names):
    path = root / module['path'] / 'CMakeLists.txt'
    if not path.is_file():
        return []
    text = re.sub(r'#[^\n]*', '', path.read_text())
    result = []
    for match in re.finditer(r'\badd_cfe_app_dependency\s*\(([^)]*)\)', text, re.I):
        parts = match[1].split()
        if parts and parts[0] == module['name']:
            for name in parts[1:]:
                if name in names:
                    result.append((name, {'path': path.relative_to(root).as_posix(),
                                         'line': text.count('\n', 0, match.start()) + 1,
                                         'symbol': 'add_cfe_app_dependency'}))
    return result


def inspect_libraries(root, apps, source_index, mission):
    root = Path(root)
    changes = _changes(root / 'cFS')
    mission['source_changes'] = {name: _module_change(path, changes) for name, path in
                                 [('core', 'cfe'), ('osal', 'osal'), ('psp', 'psp')]}
    app_names = {app['name'] for app in apps}
    compiled = set(mission.get('compiled', []))
    loaded = {item['name']: item['entry_point'] for item in mission.get('libraries', [])}
    libraries = []
    for directory in sorted((root / 'cFS/libs').glob('*')):
        if directory.is_symlink() or not (directory / 'CMakeLists.txt').is_file():
            continue
        inventory = source_index.application(directory)
        functions = [fn for fn in inventory['functions'] if not fn.get('static')]
        init = next((fn for fn in functions if fn['symbol'] == loaded.get(directory.name)), None)
        libraries.append({'name': directory.name, 'path': directory.relative_to(root).as_posix(),
                          'entry': init['path'] if init else (directory / 'CMakeLists.txt').relative_to(root).as_posix(),
                          'loaded': directory.name in loaded, 'built': directory.name in compiled,
                          'functions': inventory['functions'], 'exports': [_reference(fn) for fn in functions],
                          'used_by': [], 'libraries': []})
    by_name = {lib['name']: lib for lib in libraries}
    symbols = defaultdict(list)
    for lib in libraries:
        for function in lib['exports']:
            symbols[function['symbol']].append((lib['name'], function))
    for module in [*apps, *libraries]:
        module['change'] = _module_change(module['path'].removeprefix('cFS/'), changes)
        dependencies = {}
        for name, source in _declared(root, module, by_name):
            dependencies[name] = {'name': name, 'declared': source, 'calls': []}
        local_symbols = {fn['symbol'] for fn in module['functions']}
        for caller in module['functions']:
            for symbol in caller.get('calls', []):
                matches = symbols.get(symbol, [])
                if symbol in local_symbols or len(matches) != 1:
                    continue
                name, definition = matches[0]
                dependency = dependencies.setdefault(name, {'name': name, 'declared': None, 'calls': []})
                dependency['calls'].append({'caller': _reference(caller), 'definition': definition})
        module['libraries'] = sorted(dependencies.values(), key=lambda item: item['name'])
        for dependency in module['libraries']:
            by_name[dependency['name']]['used_by'].append({
                'name': module['name'], 'kind': 'app' if module['name'] in app_names else 'library',
                'enabled': module.get('enabled', module.get('loaded', False)),
                'calls': dependency['calls'], 'declared': dependency['declared']})
    for lib in libraries:
        lib.pop('functions')
    return libraries


def hardware_changes(root, config):
    """Compare device instances to this repository's committed configuration."""
    try:
        previous = json.loads(_git(root, 'show', 'HEAD:project/config.json'))
    except (ValueError, OSError):
        return {'board': 'unknown', 'devices': {item['id']: 'unknown' for item in config['devices']}}
    devices = {item['id']: item for item in previous.get('devices', [])}
    return {'board': 'clean' if all(config.get(key) == previous.get(key) for key in ('board', 'os')) else 'modified',
            'devices': {item['id']: ('new' if item['id'] not in devices else
                        'clean' if item == devices[item['id']] else 'modified') for item in config['devices']}}
