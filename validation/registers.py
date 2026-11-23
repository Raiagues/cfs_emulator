"""Measure the actual C HAL against new deterministic register traces, without orbit."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from project.sensor_models import display_units, load, model_paths
from sensors.scenarios import RegisterBench
from .common import host_info, manifest, save, utc
from .protocol import SENSORS, trace


def run(root, output, repetitions=3):
    if repetitions < 1:
        raise ValueError('Choose at least one repetition')
    root, output = Path(root).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'kind': 'register_hal', 'started_utc': utc(), 'host': host_info(),
              'repetitions': repetitions, 'runs': [], 'status': 'running',
              'sample_time': 'index only; no real-time or orbital interpretation',
              'compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0]}
    report['sources'] = manifest(root, ['project/drivers/hal', 'project/drivers/models', 'sensors'])
    save(output / 'registers.json', report)
    actual_run = subprocess.run
    try:
        for sensor in SENSORS:
            model = sensor['model']; spec = load(model_paths(root)[model])
            scales = {field['name']: display_units(field['unit'])[0] for field in spec['outputs']}
            units = {field['name']: display_units(field['unit'])[1] for field in spec['outputs']}
            with tempfile.TemporaryDirectory(prefix='evaluation-hal-') as temporary:
                commands = []
                def compile_record(argv, **kwargs):
                    commands.append(list(map(str, argv)))
                    with (output / (model + '-compile.log')).open('a') as log:
                        return actual_run(argv, **kwargs, stdout=log, stderr=subprocess.STDOUT)
                with patch('sensors.scenarios.subprocess.run', compile_record):
                    bench = RegisterBench(root, spec, Path(temporary))
                save(output / (model + '-compile.json'), commands)
                for repetition in range(1, repetitions + 1):
                    for scenario in ('constant', 'step', 'dropout'):
                        measured = {'model': model, 'scenario': scenario, 'repetition': repetition, 'units': units,
                                    'samples': [], 'checks': {'valid_readings_match_input': True, 'invalid_during_dropout': True,
                                                              'first_read_after_recovery_valid': True}}
                        for point in trace(model, scenario):
                            status, read, tolerance = bench.measure(point['input'], point['disconnected'])
                            if point['disconnected']:
                                measured['checks']['invalid_during_dropout'] &= status != 0
                            else:
                                measured['checks']['valid_readings_match_input'] &= status == 0 and all(
                                    abs(read[key] - value) <= tolerance[key] for key, value in point['input'].items())
                            if scenario == 'dropout' and point['index'] == 10:
                                measured['checks']['first_read_after_recovery_valid'] = status == 0
                            measured['samples'].append({'index': point['index'], 'disconnected': point['disconnected'],
                                'input_scaled': point['input'], 'input': {k:v/scales[k] for k,v in point['input'].items()},
                                'register_hex': bytes(bench.registers).hex(), 'status': status,
                                'read_scaled': read if status == 0 else {},
                                'read': {k:v/scales[k] for k,v in read.items()} if status == 0 else {},
                                'tolerance': {k:v/scales[k] for k,v in tolerance.items()}})
                        measured['passed'] = all(measured['checks'].values())
                        report['runs'].append(measured); save(output / 'registers.json', report)
        report['status'] = 'passed' if all(run['passed'] for run in report['runs']) else 'failed'
    except BaseException as error:
        report['status'] = 'failed'; report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['ended_utc'] = utc(); report['samples'] = sum(len(run['samples']) for run in report['runs'])
        save(output / 'registers.json', report)
    return report
