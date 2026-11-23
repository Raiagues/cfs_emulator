"""Evidence recording shared by the final technical evaluation."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def checked_workspace(root):
    root = Path(root).resolve()
    if not (root / '.evaluation.json').is_file():
        raise ValueError('Use a dedicated workspace created by validation prepare')
    return root


def environment(root):
    return {**os.environ, 'BUILD_JOBS': '1', 'CMAKE_BUILD_PARALLEL_LEVEL': '1',
            'FLIGHT_STUDIO_RUNTIME': str(Path(root) / 'hardware/.runtime'),
            'FLIGHT_STUDIO_NATIVE_DEVICES': str(Path(root) / 'hardware/.runtime/devices'),
            'PYTHONDONTWRITEBYTECODE': '1'}


def manifest(root, folders):
    root = Path(root)
    return {path.relative_to(root).as_posix(): {'sha256': sha256(path), 'bytes': path.stat().st_size}
            for folder in folders for path in sorted((root / folder).rglob('*'))
            if path.is_file() and not path.is_symlink()
            and not set(path.relative_to(root).parts) & {'.git', '__pycache__', '.runtime'}
            and not any(part.startswith('build-') for part in path.relative_to(root).parts)}


def input_manifest(root):
    root = Path(root)
    result = manifest(root, ['project', 'cFS', 'mission/sample_defs', 'sensors', 'scripts', 'hardware',
                             'ground_station', 'jobs', 'journey', 'validation', 'config'])
    for relative in ('start', 'Dockerfile', '.dockerignore', 'cfs.service', 'boot.sh', 'stop.sh',
                     'mission/cpu1_cfe_es_startup.scr', 'mission/modules.cmake', 'mission/libraries.cmake'):
        path = root / relative
        if path.is_file():
            result[relative] = {'sha256': sha256(path), 'bytes': path.stat().st_size}
    return result


def describe(values):
    values = list(values)
    if not values:
        return {'n': 0}
    result = {'n': len(values), 'min': min(values), 'median': statistics.median(values), 'max': max(values)}
    if len(values) >= 2:
        q1, _, q3 = statistics.quantiles(values, n=4, method='inclusive')
        result.update(q1=q1, q3=q3, iqr=q3-q1, quartile_method='inclusive')
    return result


class Recorder:
    def __init__(self, root, output):
        self.root = Path(root).resolve()
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.started = utc()

    def command(self, name, arguments, timeout=3600):
        index = len(self.records) + 1
        stem = f'{index:03d}-{name}'
        stdout = self.output / (stem + '.stdout.log')
        stderr = self.output / (stem + '.stderr.log')
        if 'build' in arguments:
            save(self.output / (stem + '-build-inputs.json'), input_manifest(self.root))
        record = {'name': name, 'argv': list(map(str, arguments)), 'started_utc': utc(),
                  'stdout': stdout.name, 'stderr': stderr.name}
        start = time.monotonic()
        self.records.append(record)
        self.flush()
        with stdout.open('w') as out, stderr.open('w') as err:
            process = subprocess.Popen(arguments, cwd=self.root, env=environment(self.root),
                                       stdout=out, stderr=err, text=True)
            try:
                record['exit_code'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
                record['timeout'] = True
                raise
            finally:
                record.update(elapsed_s=time.monotonic()-start, ended_utc=utc())
                self.flush()
        if record['exit_code']:
            raise RuntimeError(f'{name} exited {record["exit_code"]}; see {stderr}')
        return record

    def cli(self, name, *arguments, timeout=3600):
        return self.command(name, [str(self.root / 'start'), '--no-ui', *arguments], timeout)

    def flush(self):
        save(self.output / 'commands.json', {'started_utc': self.started, 'commands': self.records})


def host_info():
    return {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
            'cpu_count_available': os.cpu_count(), 'build_jobs': 1}
