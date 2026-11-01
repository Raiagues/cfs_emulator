"""The CLI and Studio share the same run guard and cross-process execution lock."""
from pathlib import Path
import sys

from hardware.manager import HardwareError, HardwareManager


def main():
    manager = HardwareManager(Path(__file__).resolve().parents[1])
    try:
        manager.execute('run')
        manager.execute('logs')
    except HardwareError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
