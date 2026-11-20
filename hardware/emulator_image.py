"""Prepare the platform-specific Docker image containing this mission's register models."""
from pathlib import Path
import subprocess
import sys

from hardware.infrastructure import emulator_config
from project.defaults import docker_platform
from project.qemu.generate import fingerprint


def prepare(root, *, build=False, options=()):
    root = Path(root)
    image = emulator_config(root)['image']
    platform = docker_platform()
    models = fingerprint()
    inspect = ['docker', 'image', 'inspect', '--format',
               '{{.Os}}/{{.Architecture}} {{index .Config.Labels "org.flight-studio.register-models"}}', image]

    def matches():
        result = subprocess.run(inspect, capture_output=True, text=True)
        return result.returncode == 0 and result.stdout.strip() == platform + ' ' + models

    if not build and not matches():
        print(f'Pulling {image} for {platform}', file=sys.stderr, flush=True)
        pull = subprocess.run(['docker', 'pull', '--platform', platform, image], stdout=sys.stderr)
        build = pull.returncode != 0 or not matches()
    if build:
        subprocess.run(['docker', 'build', '--platform', platform, '--build-arg', 'REGISTER_MODELS=' + models,
                        '--tag', image, *options, '.'], cwd=root, stdout=sys.stderr, check=True)
    if not matches():
        raise ValueError('Emulator image does not contain the selected platform and register models')
    return {'image':image, 'platform':platform, 'models':models}


if __name__ == '__main__':
    try:
        print(prepare(Path.cwd(), build=True, options=sys.argv[1:])['image'])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
