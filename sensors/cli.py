"""Inspect and edit the same signal session used by the Studio widgets."""
import argparse
import json
from pathlib import Path

from interface.backend.workspace import Workspace
from sensors.orbit import from_tle
from sensors.runtime import ROOT
from sensors.session import FUNCTIONS


def parser():
    cli = argparse.ArgumentParser(prog='./start --no-ui signals', description=__doc__)
    commands = cli.add_subparsers(dest='command', required=True)
    show = commands.add_parser('show', help='List devices, outputs, physical units and current settings')
    show.add_argument('device', nargs='?')
    select = commands.add_parser('select', help='Choose devices for a simulation with no explicit IDs')
    select.add_argument('devices', nargs='+', metavar='DEVICE')
    cfg = commands.add_parser('configure', help='Edit outputs of a configured device')
    cfg.add_argument('device')
    outputs = cfg.add_mutually_exclusive_group()
    outputs.add_argument('--outputs', nargs='+', metavar='NAME', help='Enable exactly these outputs and edit them')
    outputs.add_argument('--channel', nargs='+', metavar='NAME', help='Edit named outputs, preserving selection')
    cfg.add_argument('--interval', type=float, help='Seconds per session update')
    cfg.add_argument('--function', help='Waveform: ' + ', '.join(FUNCTIONS) + ', or a named Python function')
    cfg.add_argument('--noise', choices=['none', 'gaussian', 'uniform'])
    for name, help_text in [('initial', 'Starting value in displayed units'), ('noise-level', 'Gaussian standard deviation or uniform half-width'),
                            ('amplitude', 'Sine amplitude or sunlit offset'), ('period', 'Sine period in seconds'),
                            ('slope', 'Ramp slope per second'), ('response-time', 'Sunlight response time in seconds')]:
        cfg.add_argument('--'+name, type=float, help=help_text)
    cfg.add_argument('--material', type=json.loads, metavar='JSON',
                     help='Thermal profile with size, mass, alpha, emissivity and power')
    orb = commands.add_parser('orbit', help='Read or change the session orbit')
    orb.add_argument('--tle', type=Path, help='Read a two-line element set from a file')
    orb.add_argument('--model', choices=['Two-body', 'J2'])
    orb.add_argument('--epoch', help='ISO 8601 timestamp with UTC offset')
    for field in ('perigee', 'apogee', 'inclination', 'node', 'argument', 'anomaly'):
        unit = 'altitude in km' if field in ('perigee', 'apogee') else 'angle in degrees'
        orb.add_argument('--'+field, type=float, help=unit)
    return cli


def configure(args, entry):
    signals = entry['signals']
    names = args.outputs or args.channel or list(signals)
    if len(names) != len(set(names)) or set(names) - set(signals):
        raise ValueError('Choose distinct outputs from: ' + ', '.join(signals))
    updates = {k: getattr(args, k) for k in ('function', 'initial', 'noise', 'noise_level',
               'amplitude', 'period', 'slope', 'response_time', 'material') if getattr(args, k) is not None}
    waveform_fields = {
        'sine': {'period', 'amplitude'},
        'ramp': {'slope'},
        'orbit.sunlight': {'amplitude', 'response_time'},
        'orbit.thermal': {'material'},
    }
    supplied_fields = set(updates) & {'period', 'amplitude', 'slope', 'response_time', 'material'}
    for name, settings in signals.items():
        if args.outputs:
            settings['enabled'] = name in names
        if name in names:
            kind = updates.get('function', settings['function'])
            invalid = supplied_fields - waveform_fields.get(kind, set())
            if invalid:
                raise ValueError(f'{name}: {kind} does not use {", ".join(sorted(invalid))}')
            settings.update(updates)


def execute(workspace, args):
    state = workspace.simulation_snapshot()
    available = {item['id']: item for item in state['available']}
    settings = state['settings']
    selected = {item['device']: item for item in settings['sensors']}
    if args.command == 'show':
        if args.device is None:
            return state
        if args.device not in available:
            raise ValueError('Unknown device: ' + args.device)
        device = dict(available[args.device])
        current = selected.get(args.device, device['defaults'])
        device.pop('defaults')
        device.update(enabled=args.device in selected and current['enabled'], signals=current['signals'])
        return device
    if args.command == 'select':
        if set(args.devices) - available.keys() or len(set(args.devices)) != len(args.devices):
            raise ValueError('Choose distinct devices from: ' + ', '.join(available))
        settings['sensors'] = [
            {**selected.get(name, available[name]['defaults']), 'enabled': True}
            for name in args.devices
        ]
    elif args.command == 'orbit':
        orbit = settings['orbit']
        changes = {k: getattr(args, k) for k in orbit if getattr(args, k) is not None}
        if not args.tle and not changes:
            return orbit
        if args.tle:
            if set(changes) - {'model'}:
                raise ValueError('Use either a TLE or manual orbital elements')
            settings['orbit'] = from_tle(args.tle.read_text(), changes.get('model', orbit['model']))
        else:
            orbit.update(changes)
    else:
        if args.device not in available:
            raise ValueError('Unknown device: ' + args.device)
        entry = selected.get(args.device)
        if entry is None:
            entry = available[args.device]['defaults']
            settings['sensors'].append(entry)
        entry['enabled'] = True
        configure(args, entry)
        if args.interval is not None:
            settings['interval'] = args.interval
    saved = workspace.save_simulation(settings, state['hash'])
    return {'settings': saved['settings'], 'changed': saved['changed']}


def main():
    cli = parser()
    args = cli.parse_args()
    try:
        print(json.dumps(execute(Workspace(ROOT), args), ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError) as error:
        cli.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
