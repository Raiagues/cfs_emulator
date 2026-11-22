"""Operations run on the selected guest over authenticated OpenSSH."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


def status(service):
    systemd = subprocess.run(['systemctl', 'show', service, '-p', 'ActiveState', '-p', 'InvocationID', '-p', 'MainPID'],
                             capture_output=True, text=True, check=True)
    scan = subprocess.run(['pgrep', '-x', 'core-cpu[0-9]+'], capture_output=True, text=True)
    if scan.returncode not in (0, 1):
        raise RuntimeError(scan.stderr.strip() or 'Could not inspect cFS processes')
    properties = dict(line.split('=', 1) for line in systemd.stdout.splitlines() if '=' in line)
    state = properties['ActiveState']
    pids = list(map(int, scan.stdout.split()))
    active = state in ('active', 'activating', 'deactivating', 'reloading')
    known = active or state in ('inactive', 'failed')
    return {'service': state, 'pids': pids, 'running': True if pids or active else False if known else None,
            'instance': properties.get('InvocationID') if int(properties.get('MainPID') or 0) in pids else None}


def create_directory(path, exclusive):
    Path(path).mkdir(mode=0o700, parents=True, exist_ok=not exclusive)


def unpack(path):
    directory = Path(path)
    upload = directory / '.flight-upload.tar'
    with tarfile.open(upload) as archive:
        for member in archive:
            location = (directory / member.name).resolve()
            if not location.is_relative_to(directory.resolve()) or not (member.isdir() or member.isfile()):
                raise ValueError('Unexpected item in the flight payload')
            if member.isdir():
                location.mkdir(parents=True, exist_ok=True)
            else:
                location.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, location.open('xb') as destination:
                    shutil.copyfileobj(source, destination)
                location.chmod(member.mode & 0o755)
    upload.unlink()


def start_emulator(path, staging):
    current, staged = Path(path), Path(staging)
    if staged.parent != current.parent or not staged.name.startswith(current.name + '.upload-'):
        raise ValueError('Invalid emulator upload directory')
    if status('cfs.service')['running'] is not False:
        raise RuntimeError('Stop the running cFS process before replacing its installation')
    # Keep the other Pi 4B vCPUs available to the guest kernel and SSH.
    subprocess.run(['systemctl', 'set-property', '--runtime', 'cfs.service', 'AllowedCPUs=1'], check=True)
    previous = current.with_suffix('.previous')
    if previous.exists():
        shutil.rmtree(previous)
    if current.exists():
        current.rename(previous)
    try:
        staged.rename(current)
        subprocess.run(['systemctl', 'start', 'cfs.service'], check=True)
    except (OSError, subprocess.CalledProcessError):
        if current.exists():
            current.rename(staged)
        if previous.exists():
            previous.rename(current)
        raise


if __name__ == '__main__':
    actions = {'status': status, 'directory': create_directory, 'unpack': unpack, 'start-emulator': start_emulator,
               'connection': lambda: os.environ['SSH_CONNECTION'].split()}
    try:
        result = actions[sys.argv[1]](*json.loads(sys.argv[2]))
        if result is not None:
            print(json.dumps(result))
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        sys.exit(str(error))
