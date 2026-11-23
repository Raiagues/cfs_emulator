"""Create an independent mission from committed platform sources and public CLIs."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from .common import Recorder, host_info, manifest, save, sha256, utc
from .protocol import LEVELS, SENSORS


def run(source, directory, source_copy=None):
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if directory == source or directory.is_relative_to(source):
        raise ValueError('Evaluation directory must be outside the platform checkout')
    directory.mkdir(parents=True, exist_ok=False)
    root = directory / 'flight'; root.mkdir()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', '--format=tar', revision], cwd=source)
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        package.extractall(root, filter='data')
    configuration = json.loads((root / 'project/config.json').read_text())
    if configuration.get('apps') or configuration.get('devices'):
        raise ValueError('Committed platform defaults must start without mission apps or devices')
    marker = {'schema': 1, 'created_utc': utc(), 'platform_commit': revision,
              'source_method': 'official installer network clone' if source_copy is None else 'independent copy of official local checkout',
              'host': host_info(), 'protocol': 'final-technical-v1'}
    save(root / '.evaluation.json', marker)
    recorder = Recorder(root, directory / 'prepare')
    if source_copy is not None:
        checkout = Path(source_copy).resolve()
        from project.nasa_source import source_status
        status = source_status(checkout.parent)
        if status['state'] != 'ready' or checkout.name != 'cFS':
            raise ValueError('Local source copy must be a ready official cFS checkout')
        dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=checkout, text=True)
        if dirty.strip():
            raise ValueError('Local NASA checkout must be clean before preparing the evaluation')
        shutil.copytree(checkout, root / 'cFS', symlinks=True, ignore=shutil.ignore_patterns('__pycache__'))
        for path in (root / 'cFS').rglob('*'):
            if path.is_symlink() and not path.resolve().is_relative_to(root / 'cFS'):
                raise ValueError('Copied NASA checkout contains an external symlink')
    recorder.cli('source-install', 'source', 'install', '--json', timeout=1800)
    nasa_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root / 'cFS', text=True).strip()
    paths = subprocess.check_output(['git', 'ls-files', '--recurse-submodules', '-z'], cwd=root / 'cFS').split(b'\0')
    nasa = {path.decode(): sha256(root / 'cFS' / path.decode()) for path in paths
            if path and (root / 'cFS' / path.decode()).is_file()}
    save(directory / 'nasa-before.json', nasa)
    recorder.cli('profile', 'profile', '--board', 'raspi4b', '--os', 'raspios', '--json')
    recorder.cli('add-bus', 'project', 'add-bus', 'i2c-bus.1')
    for sensor in SENSORS:
        values = [argument for key, value in LEVELS[sensor['model']][0].items() for argument in ('--value', f'{key}={value}')]
        recorder.cli('device-' + sensor['device'], 'project', 'add-device', sensor['model'], '--id', sensor['device'],
                     '--model', sensor['model'], '--bus', 'i2c-bus.1', '--address', hex(sensor['address']), *values)
        recorder.cli('app-' + sensor['app'], 'app', 'new', sensor['app'], '--json')
        recorder.cli('reader-' + sensor['app'], 'project', 'link-hal', sensor['app'], 'sample', '--device', sensor['device'])
    recorder.cli('sync', 'project', 'sync')
    marker.update(nasa_commit=nasa_revision, nasa_tracked_files=len(nasa))
    save(root / '.evaluation.json', marker)
    changed = [name for name, digest in nasa.items() if sha256(root / 'cFS' / name) != digest]
    if changed:
        raise ValueError('Preparation changed original NASA files: ' + ', '.join(changed))
    save(directory / 'sources.json', manifest(root, ['project', 'mission/sample_defs', 'cFS/apps', 'cFS/libs', 'sensors', 'validation']))
    result = {'status': 'passed', **marker, 'workspace': str(root), 'sensors': SENSORS,
              'nasa_originals_unchanged': True, 'prepared_utc': utc(), 'commands': len(recorder.records)}
    save(directory / 'prepare.json', result)
    return result
