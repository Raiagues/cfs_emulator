"""Refactor a Studio module and its native consumers in one mission transaction."""
from contextlib import ExitStack
import json
from pathlib import Path
import re

from project.flight_sources import module_directories

from ground_station.c_source import blank_lexemes
from project.source_index import parse_functions
from project import model
from project.appgen.native_startup import parse_startup
from project.appgen.sample import copy_sample
from project.driver_catalog import dependencies
from project.manage import commit


WORD = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
SOURCE_EXTENSIONS = {'.c', '.h', '.cpp', '.hpp', '.cmake', '.inc', '.xml', '.eds', '.scr',
                     '.tbl', '.lua', '.py', '.sh', '.dox', '.md', '.txt', '.json', '.cfg', '.in'}


class ModuleNames:
    """Map identifiers from the module template, then extend it with project-owned symbols.

    A plain substring replacement would change other modules (or even the .c
    extension of every file for a module named c). Use complete identifiers,
    actual filenames and the CMake target name in argument position.
    """
    def __init__(self, root, old, new, manifest, siblings):
        self.old, self.new = old, new
        self.longer = tuple(name + '_' for name in siblings if name.startswith(old + '_'))
        self.other = set(siblings)
        self.words = {f'CFS_MODULE_{old.upper()}': f'CFS_MODULE_{new.upper()}'}
        self.files = {}
        marker = 'zzstudionamespace'
        while marker in json.dumps(manifest).lower():
            marker += 'x'
        if manifest:
            template = {path: text for path, (text, _) in model.appgen(root).renderer()(
                {**manifest, 'name': marker}, root / 'mission').items()}
        else:
            template = copy_sample(root / 'mission', 'sample_lib', marker)
        # Unmodified template lines include things outside the C namespace,
        # e.g. cFE table owner strings, EDS package paths and documentation.
        # Translate those exactly, without regenerating hand-edited files.
        self.template_lines = {}
        self.template_filenames = {}
        for path, source in template.items():
            filename = self._expand(path, marker, old)
            basename = Path(path).name
            if marker in basename.lower():
                self.template_filenames[Path(filename).name] = self._expand(basename, marker, new)
            self.template_lines[filename] = {
                self._expand(line, marker, old): self._expand(line, marker, new)
                for line in source.splitlines() if marker in line.lower()
            }
        fixed = set()
        for word in WORD.findall('\n'.join([*template, *template.values()])):
            if marker not in word.lower():
                fixed.add(word)
            elif word.lower() != marker:
                self.words[self._expand(word, marker, old)] = self._expand(word, marker, new)
        self.fixed = fixed | {'CFE_APP', 'CFE_LIB'}
        for word in self.fixed:
            self.words.pop(word, None)
        token = re.escape(old)
        self.module_argument = re.compile(r'(?<![^\s(";=/])' + token + r'(?=[\s)";/]|$)')
        self.module_path = re.compile(r'(?<=/)' + token + r'(?=/)|(?<![\w.])' + token + r'(?=\.so\b)')

    @staticmethod
    def _expand(word, marker, name):
        return (word.replace(marker, name).replace(marker.upper(), name.upper())
                .replace(marker.title(), name.replace('_', ' ').title()))

    def _belongs(self, word):
        name = word.lower()
        return name not in self.other and not name.startswith(self.longer)

    def filename(self, name):
        if name in self.template_filenames:
            return self.template_filenames[name]
        if not self._belongs(name.split('.')[0]):
            return name
        if name == self.old or name.startswith((self.old + '_', self.old + '.')):
            return self.new + name[len(self.old):]
        prefix = re.match(r'(?:default_|eds_|cpu\d+_)', name)
        if prefix:
            return prefix[0] + self.filename(name[prefix.end():])
        return name

    def collect(self, path, content):
        # Public API extensions and user-written helpers need the same mapping
        # as generated symbols. A call into another API does not establish ownership.
        if path.suffix.lower() not in {'.c', '.h', '.cpp', '.hpp'}:
            return
        candidates = {word for word in WORD.findall(content) if word not in self.fixed and word not in self.words
                      and word.startswith((self.old + '_', self.old.upper() + '_')) and self._belongs(word)}
        if not candidates:
            return
        code = blank_lexemes(content)
        declared = set(re.findall(r'^\s*#\s*define\s+(\w+)', code, re.M))
        declared.update(re.findall(r'(?:\b(?:struct|union|enum)\s+|\}\s*)(\w+)', code))
        for type_name, symbol in re.findall(r'\b(\w+)\s+\**\s*(\w+)\s*(?=[;=\[])', code):
            if type_name not in ('return', 'case'):
                declared.add(symbol)
        for enum in re.findall(r'\benum\b[^{};]*\{([^{}]*)\}', code):
            declared.update(re.findall(r'(?:^|,)\s*(\w+)', enum))
        functions, _ = parse_functions(content, path.as_posix())
        declared.update(fn['symbol'] for fn in functions)
        for word in candidates & declared:
            prefix = self.new.upper() if word.startswith(self.old.upper() + '_') else self.new
            self.words[word] = prefix + word[len(self.old):]

    def text(self, content, path, local=False):
        # Match entire filenames first, including configuration header aliases
        # exposed by cFE after removing the default_ / eds_ prefix.
        content = self.references.sub(lambda m: self.files.get(m[0], self.words.get(m[0], m[0])), content)
        content = self.module_path.sub(self.new, content)
        content = re.sub(r'\b' + re.escape(self.old.upper()) + r'(?=[./][A-Za-z_])', self.new.upper(), content)
        if path.name == 'CMakeLists.txt' or path.suffix == '.cmake':
            content = self.module_argument.sub(self.new, content)
        if local and path.suffix.lower() in {'.xml', '.eds', '.c', '.h', '.lua', '.py', '.sh'}:
            for old, new in ((self.old, self.new), (self.old.upper(), self.new.upper())):
                content = re.sub(r'(["\'])' + re.escape(old) + r'\1', lambda m: m[1] + new + m[1], content)
        elif path.suffix.lower() in {'.c', '.h'}:
            lookup = r'(\bCFE_ES_Get(?:App|Lib)IDByName\s*\([^,]*,\s*")' + re.escape(self.old.upper()) + '"'
            content = re.sub(lookup, lambda m: m[1] + self.new.upper() + '"', content)
        return content

    def owned_text(self, content, path, relative):
        template = self.template_lines.get(relative, {})
        lines = []
        for line in content.splitlines(keepends=True):
            original = line.rstrip('\r\n')
            if original in template:
                lines.append(template[original] + line[len(original):])
            else:
                lines.append(self.text(line, path, local=True))
        return ''.join(lines)

    def prepare(self, paths):
        for path, content in paths.items():
            name = self.filename(path.name)
            if name != path.name:
                self.files[path.name] = name
                for prefix in ('default_', 'eds_'):
                    if path.name.startswith(prefix):
                        self.files[path.name[len(prefix):]] = name[len(prefix):]
            if content is not None:
                self.collect(path, content)
        filenames = '|'.join(re.escape(key) for key in sorted(self.files, key=len, reverse=True))
        self.references = re.compile((r'(?<!\w)(?:' + filenames + r')(?!\w)|' if filenames else '') + WORD.pattern)


def _files(directory):
    return (p for p in sorted(directory.rglob('*')) if p.is_file() and not p.is_symlink()
            and not any(part.startswith('.') for part in p.relative_to(directory).parts))


def _read_source(path):
    if path.suffix.lower() not in SOURCE_EXTENSIONS and path.name != 'Makefile':
        return None
    raw = path.read_bytes()
    if b'\0' in raw:
        return None
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _startup(text, names):
    active, archived = parse_startup(text)
    if not any(item.name == names.old for item in active + archived):
        return text
    # Keep spacing, numeric fields, archive comments and the cFE EOF marker.
    record = re.compile(r'^[ \t]*\#[^\n]*|(\bCFE_(?:APP|LIB)\s*,\s*)([\w/.-]+)(\s*,\s*)(\w+)(\s*,\s*)(\w+)', re.M)
    def replace(match):
        if not match[1] or Path(match[2]).name.removesuffix('.so') != names.old:
            return match[0]
        module = match[2].removesuffix('.so')[:-len(names.old)] + names.new
        if match[2].endswith('.so'):
            module += '.so'
        task = names.new.upper() if match[6] == names.old.upper() else match[6]
        return match[1] + module + match[3] + names.words.get(match[4], match[4]) + match[5] + task
    updated = record.sub(replace, text)
    active, archived = parse_startup(updated)
    if any(item.name == names.old for item in active + archived):
        raise ValueError('Could not rename the native startup record for ' + names.old)
    return updated


def assert_no_module_references(root, modules, name, headers, functions):
    """Reject a mutation that would leave another module with unresolved flight references."""
    include = re.compile(r'^\s*#\s*include\s*["<]([^">]+)[">]', re.M)
    public_call = re.compile(r'\b(?:' + '|'.join(map(re.escape, sorted(functions))) + r')\s*\(') if functions else None
    for module in modules:
        if name in dependencies(root, module.name):
            raise ValueError(f'{module.name} depends on {name}')
        for path in _files(module):
            if path.suffix not in ('.c', '.h', '.cpp', '.hpp'):
                continue
            content = _read_source(path)
            if not content:
                continue
            code = blank_lexemes(content, literals=False)
            if (any(Path(header).name in headers for header in include.findall(code))
                    or public_call and public_call.search(blank_lexemes(content))):
                raise ValueError(f'{path.relative_to(root)} references {name}')


def _check_consumers(root, protected, names):
    headers = {name for name in names.files if name.endswith(('.h', '.hpp')) and names.old in name}
    functions = {symbol for symbol in names.words if symbol.startswith(names.old.upper() + '_')}
    assert_no_module_references(root, protected, names.old, headers, functions)


def rename_module(workspace, kind, old, new, revision):
    root, mission = workspace.root, workspace.mission
    model.identifier(old)
    model.identifier(new)
    if kind not in ('app', 'library') or old == new:
        raise ValueError('Choose an app or library and enter a different module name')
    config = model.load_config(root)
    manifests = model.read_manifests(root, config)
    model.validate_config(root, config, manifests)
    apps = {app['name']: app for app in manifests}
    modules = [p for group in ('apps', 'libs') for p in module_directories(root, group) if (p / 'CMakeLists.txt').is_file()]
    compiled = mission._evaluate(revision)
    libraries = {p.name for p in modules if p.parent.name == 'libs' and mission._library_deletable(p.name, compiled)}
    owned = {root / 'mission/apps' / app for app in apps} | {root / 'mission/libs' / lib for lib in libraries}
    source = model.safe_path(root, Path('mission') / ('apps' if kind == 'app' else 'libs') / old)
    if source not in owned or (source / '.git').exists() or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Only project-created modules with local source files can be renamed')
    reserved = mission.available_module_name(new, compiled)
    manifest = apps.get(old) if kind == 'app' else None
    names = ModuleNames(root, old, new, manifest, reserved - {old})
    sources = {p: _read_source(p) for p in _files(source)}
    names.prepare(sources)
    destination = source.with_name(new)
    inputs, plan, moved, renames = {}, {}, {}, []
    relative = lambda p: p.relative_to(root).as_posix()

    def edit(path, before, after, target=None):
        if before != after:
            if path.suffix in ('.c', '.h') and '/* @studio.begin ' in before:
                from project.appgen.source_tags import renamed_source
                after = renamed_source(before, after, path)
            inputs[relative(path)] = before.encode()
            plan[relative(target or path)] = after

    # Rename the original files on disk so permissions, binary assets and
    # user-only files survive. Record path mappings for already-open editors.
    for path in sorted(source.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        suffix = path.relative_to(source)
        target = destination.joinpath(*(names.filename(part) for part in suffix.parts))
        if path.name != names.filename(path.name):
            renames.append((path, path.with_name(names.filename(path.name))))
        if path.is_file():
            moved[relative(path)] = relative(target)
            original = sources.get(path)
            if original is not None:
                edit(path, original, names.owned_text(original, path, suffix.as_posix()), target)
    renames.append((source, destination))

    owned_locations = {path.resolve() for path in owned}
    _check_consumers(root, [path for path in modules if path.resolve() not in owned_locations], names)

    defs = root / 'mission/sample_defs'
    settings = [root / p for p in (mission.STARTUP, mission.MODULES, 'mission/libraries.cmake') if (root / p).is_file()]
    for directory in [defs, *sorted(owned - {source})]:
        files = [*_files(defs), *settings] if directory == defs else _files(directory)
        for path in files:
            content = _read_source(path)
            if content is None:
                continue
            target = path
            if path.is_relative_to(defs) and names.filename(path.name) != path.name:
                target = path.with_name(names.filename(path.name))
                renames.append((path, target))
                moved[relative(path)] = relative(target)
            if relative(path) == mission.STARTUP or path == defs / 'generated/appgen_startup.scr':
                updated = _startup(content, names)
            else:
                updated = names.text(content, path, local=(directory == defs))
            edit(path, content, updated, target)

    if manifest:
        config['apps'] = [{**app, 'name': new} if app['name'] == old else app for app in config['apps']]
        updated = [{**app, 'name': new} if app['name'] == old else app for app in manifests]
        model.validate_config(root, config, updated, new_apps=[new])
        config_path = root / 'project/config.json'
        edit(config_path, config_path.read_bytes().decode(), json.dumps(config, indent=2) + '\n')
        old_manifest = root / 'project/apps' / (old + '.json')
        new_manifest = old_manifest.with_name(new + '.json')
        renames.append((old_manifest, new_manifest))
        moved[relative(old_manifest)] = relative(new_manifest)
        edit(old_manifest, old_manifest.read_bytes().decode(), json.dumps({**manifest, 'name': new}, indent=2) + '\n', new_manifest)
        # Keep generated fragments in appgen's canonical sort order when two
        # module names switch positions. Preserve manual native overrides.
        gen = model.appgen(root)
        excluded = mission.selection()['removed']
        generated_libs = parse_startup((defs / 'generated/appgen_startup.scr').read_text())[0]
        drivers = [{'name': item.name, 'entry_point': item.fields[2]} for item in generated_libs if item.kind == 'CFE_LIB']
        active = [app for app in manifests if app['name'] not in excluded]
        prior = gen.render_mission(active, drivers)
        next_files = gen.render_mission([{**app, 'name': new} if app['name'] == old else app for app in active], drivers)
        for path, original in prior.items():
            path_on_disk = root / 'mission' / path
            content = path_on_disk.read_bytes().decode()
            if content.replace('\r\n', '\n') == original:
                edit(path_on_disk, content, next_files[path])
        overrides = model.safe_path(root, 'ground_station/overrides.json')
        if overrides.is_file():
            content = overrides.read_bytes().decode()
            data = json.loads(content)
            for packet in data.get('commands', []) + data.get('packets', []):
                if packet.get('app') == old:
                    packet['app'] = new
                for key in ('id', 'name', 'mid_expr', 'code_expr', 'struct', 'source'):
                    if isinstance(packet.get(key), str):
                        packet[key] = names.text(packet[key], overrides)
            if data != json.loads(content):
                edit(overrides, content, json.dumps(data, indent=2) + '\n')

    mission.assert_revision(revision)
    workspace._assert_inputs(inputs, 'Module source changed during rename. Reload before saving.')
    result = {}
    def validate_renamed_mission():
        model.validate_config(root, model.load_config(root))
        result['mission'] = mission.snapshot()

    with ExitStack() as undo:
        for path, target in renames:
            if target.exists() or target.is_symlink():
                raise ValueError('A file or directory already uses this name: ' + relative(target))
            path.rename(target)
            undo.callback(target.rename, path)
        changed = commit(root, plan, mutable_libraries=(libraries | {new} if kind == 'library' else libraries),
                         validate=validate_renamed_mission)
        undo.pop_all()
    return {**result, 'moved': moved, 'deleted': list(moved),
            'changed': sorted(set(changed) | set(moved.values()))}
