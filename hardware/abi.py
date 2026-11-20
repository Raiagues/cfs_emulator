"""Compare the glibc versions required by every deployed ELF object with the board."""
from pathlib import Path
import re
import subprocess


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(\.\d+)+', value):
        raise ValueError('The board did not report its glibc version')
    return tuple(map(int, value.split('.')))


def check_payload(payload, available):
    board = version(available)
    files = [Path(payload) / 'core-cpu1', *sorted(Path(payload).rglob('*.so'))]
    for artifact in files:
        result = subprocess.run(['readelf', '--wide', '--version-info', str(artifact)], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f'Could not inspect {artifact.name}: {result.stderr.strip()}')
        needs = result.stdout.partition('Version needs section')[2]
        for needed in re.findall(r'\bName: GLIBC_(\d+(?:\.\d+)+)', needs):
            if version(needed) > board:
                raise ValueError(f'{artifact.name} requires glibc {needed}. Board has {available}. Build the Bookworm profile.')
