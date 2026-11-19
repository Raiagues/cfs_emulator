"""Exercise a configured waveform through its actual flight HAL on a local test bus."""
import argparse
import ctypes
import json
import subprocess
import tempfile
from pathlib import Path

from project.model import board_catalog, load_config
from project.sensor_driver import register_profile
from project.sensor_models import identity_bytes, load, model_paths, output_limits
from sensors.orbit import Orbit
from sensors.runtime import ROOT
from sensors.session import load_session, waveform_for
from sensors.simulator import configuration, sample_values

SCENARIOS = ('orbit', 'eclipse', 'dropout')


def schedule(name, orbit):
    if name == 'orbit':
        return [orbit.period*i/120 for i in range(121)]
    if name == 'dropout':
        return [float(i) for i in range(31)]
    if name != 'eclipse':
        raise ValueError('Unknown signal scenario')
    step = orbit.period / 360
    for i in range(1, 361):
        if orbit.sample((i-1)*step)[3] and not orbit.sample(i*step)[3]:
            start = i*step - 1200
            if start < 0:
                start += orbit.period
            return [start+20*j for j in range(121)]
    raise ValueError('No eclipse entry in this orbit')


class RegisterBench:
    def __init__(self, root, spec, directory):
        if spec.get('protocol') == 'custom':
            raise ValueError('Local test requires a register model')
        hal = root/'project/drivers/hal'
        (directory/'profile.h').write_text(register_profile(spec))
        lib = directory/'sensor.so'
        command = ['cc', '-std=c99', '-O2', '-fPIC', '-shared', '-I', str(hal/'include'), '-I', str(directory),
                   str(hal/'src/hal_sensor.c'), str(root/'sensors/scenario_bus.c'), '-o', str(lib)]
        subprocess.run(command, check=True, timeout=30)
        self.reader = ctypes.CDLL(str(lib)).read_sample
        self.reader.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_bool, ctypes.POINTER(ctypes.c_int32), ctypes.c_size_t]
        self.reader.restype = ctypes.c_int32
        self.registers = (ctypes.c_uint8*256)()
        for i, byte in enumerate(identity_bytes(spec)):
            self.registers[spec['id_register']+i] = byte
        ready = spec.get('ready', {})
        if ready:
            self.registers[ready['register']] = ready['mask']
        for control in spec['controls']:
            self.registers[control['register']] = control['setup']
        self.outputs = spec['outputs']
        self.values = (ctypes.c_int32*len(self.outputs))()

    def measure(self, sent, disconnected):
        tolerance = {}
        for output in self.outputs:
            name = output['name']
            if name not in sent:
                continue
            gain = output.get('counts')
            if 'range_register' in output:
                selector = self.registers[output['range_register']] >> output['range_shift']
                gains = output.get('gain_counts')
                gain = gains[selector & (len(gains)-1)] if gains else gain / (1 << (selector & 3))
            quantum = 1 + output.get('reserved_mask', 0)
            raw = round((sent[name]-output['offset'])*gain/output['divisor']/quantum)*quantum
            raw = max(-32768, min(32767 & ~(quantum-1), raw))
            self.registers[output['register']:output['register']+2] = raw.to_bytes(2, 'big', signed=True)
            tolerance[name] = .5*quantum*output['divisor']/gain + 1  # HAL returns integer engineering units.
        status = self.reader(self.registers, disconnected, self.values, len(self.outputs))
        return status, {o['name']: self.values[i] for i,o in enumerate(self.outputs) if o['name'] in sent}, tolerance


def run_scenario(root, device_id, name):
    root = Path(root)
    session = load_session(root)
    config = load_config(root)
    catalog = board_catalog(config['board'], root)
    device = next((dict(d) for d in config['devices'] if d['id'] == device_id), None)
    if not device:
        raise ValueError('Select a configured sensor')
    model = load(model_paths(root)[device['model']])
    sensor = next(d['defaults'] for d in session['available'] if d['id'] == device_id)
    device['values'] = {**catalog['models'][device['model']]['default_values'], **device['values']}
    orbit = Orbit(session['settings']['orbit'])
    waveform = waveform_for(root, device, sensor, catalog, orbit)
    binding = configuration(waveform, device, root, catalog)
    scales = {s.property:s.scale for s in binding.signals}
    units = {s.property:s.unit for s in binding.signals if s.property in waveform.enabled}
    if not units:
        raise ValueError('Select a sensor output')
    checks = {'Read ≈ sent':True, 'Sensor range':True}
    if name == 'dropout':
        checks.update({'Dropout detected':True, 'Read recovered':False})
    samples = []
    with tempfile.TemporaryDirectory(prefix='flight-signal-test-') as temporary:
        bench = RegisterBench(root, model, Path(temporary))
        for t in schedule(name, orbit):
            _, sent = sample_values([device], t, {device_id:waveform}, {device_id:binding}, root, catalog)[0]
            dropout = name == 'dropout' and 10 <= t < 16
            status, read, tolerance = bench.measure(sent, dropout)
            if dropout:
                checks['Dropout detected'] &= status != 0
            else:
                checks['Read ≈ sent'] &= status == 0 and all(abs(read[k]-v) <= tolerance[k] for k,v in sent.items())
                if name == 'dropout' and t == 16:
                    checks['Read recovered'] = status == 0
            for out in model['outputs']:
                low, high = output_limits(out)
                key = out['name']
                if not status and key in read:
                    checks['Sensor range'] &= low <= read[key] <= high
            samples.append({'time':t, 'sent':{k:v/scales[k] for k,v in sent.items()},
                            'read':{} if status else {k:v/scales[k] for k,v in read.items()}, 'status':status})
    return dict(device=device_id, scenario=name, units=units, checks=checks, samples=samples)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('scenario', choices=SCENARIOS)
    args = parser.parse_args()
    try:
        report = run_scenario(ROOT, args.device, args.scenario)
        print('@scenario ' + json.dumps(report, allow_nan=False, separators=(',', ':')), flush=True)
        if not all(report['checks'].values()):
            parser.exit(1, 'Some signal checks failed\n')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'{error}\n')
