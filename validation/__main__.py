"""Run explicit phases of the final technical evaluation, one build job at a time."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='phase', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    prepare.add_argument('--directory', type=Path, required=True)
    prepare.add_argument('--source-copy', type=Path, help='Use an independent copy of an existing clean official cFS checkout; record this limit')
    registers = commands.add_parser('registers')
    registers.add_argument('--workspace', type=Path, required=True)
    registers.add_argument('--output', type=Path, required=True)
    registers.add_argument('--repetitions', type=int, default=3)
    target = commands.add_parser('target', help='Collect evidence from an already-running dedicated mission')
    for command in (target, commands.add_parser('build'), commands.add_parser('cycles'),
                    commands.add_parser('starts'), commands.add_parser('boots')):
        command.add_argument('--workspace', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
        if command.prog.split()[-1] != 'cycles':
            command.add_argument('--target', choices=('native', 'qemu', 'physical'), required=True)
        if command.prog.split()[-1] not in ('build',):
            command.add_argument('--repetitions', type=int, default=3 if command is target else 5 if command.prog.split()[-1] == 'boots' else 10)
        if command.prog.split()[-1] in ('starts', 'boots'):
            command.add_argument('--leave-running', action='store_true')
    target.add_argument('--samples', type=int, default=5)
    args = parser.parse_args()
    if args.phase == 'prepare':
        from .prepare import run
        result = run(args.source, args.directory, args.source_copy)
    elif args.phase == 'registers':
        from .common import checked_workspace
        from .registers import run
        result = run(checked_workspace(args.workspace), args.output, args.repetitions)
    elif args.phase == 'target':
        from .flight import run
        result = run(args.workspace, args.output, args.target, args.repetitions, args.samples)
    elif args.phase == 'build':
        from .metrics import build
        result = build(args.workspace, args.output, args.target)
    elif args.phase == 'cycles':
        from .metrics import cycles
        result = cycles(args.workspace, args.output, args.repetitions)
    else:
        from .metrics import starts
        result = starts(args.workspace, args.output, args.target, args.repetitions,
                        guest_boots=args.phase == 'boots', leave_running=args.leave_running)
    print(json.dumps({k:v for k,v in result.items() if k not in ('runs', 'sources')}, ensure_ascii=False, indent=2))
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
