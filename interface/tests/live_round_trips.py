"""Run the installed applications' NOOP checks on a connected Studio test mission."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ground_station.c_source import calls


def noop_signature(api, command):
    dispatch = command.get('locations', {}).get('dispatch')
    if not dispatch:
        raise ValueError(f"No indexed dispatch file for {command['id']}.")
    folder = str(PurePosixPath(dispatch['path']).parent)
    entries = api('tree?' + urlencode({'path': folder}))['entries']
    signatures = set()
    for entry in entries:
        if not entry['path'].endswith('.c'):
            continue
        source = api('file?' + urlencode({'path': entry['path']}))['content']
        for _, _, _, args in calls(source, {'CFE_EVS_SendEvent', 'EVS_SendEvent'}):
            if len(args) < 3 or not args[2].startswith('"') or 'INFORMATION' not in args[1]:
                continue
            word = re.search(r'\bno[- ]?op\b', args[2], re.I)
            if word:
                signatures.add(word[0].casefold())
    if len(signatures) != 1:
        raise ValueError(f"Configure the EVS assertion for {command['id']}: no unique NOOP message found.")
    return signatures.pop()


def exercise(port, target):
    base = f'http://127.0.0.1:{port}/api/'
    with urlopen(base + 'session', timeout=5) as response:
        token = json.load(response)['token']

    def api(path, body=None):
        request = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', 'X-Studio-Token': token})
        try:
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(error.read().decode()) from error

    session = api('ground')
    if not session['connected'] or session['target'] != target:
        raise RuntimeError('Connect the test mission before running the suite.')
    catalog = api('ground/catalog?target=' + target)
    results = []
    for app in catalog['apps']:
        name = app['name']
        command = next((c for c in catalog['commands'] if c['app'] == name and
                        c['id'].endswith('_NOOP_CC') and not c.get('fields')), None)
        if command is None:
            results.append({'app': name, 'status': 'no parameterless NOOP in catalog'})
            continue
        steps = [{'kind':'event', 'app':name.upper(), 'message':noop_signature(api, command)}]
        if name == 'sample_app':
            hk = next(p for p in catalog['packets'] if p['app'] == name and 'HK' in p['id'])
            field = next(f['name'] for f in hk['fields'] if f['name'].split('.')[-1] == 'CommandCounter')
            steps.append({'kind':'packet', 'packet':hk['id'], 'field':field, 'op':'increased'})
        plan = {'name':'NOOP downlink check', 'command':command['id'], 'timeout':12, 'steps':steps}
        saved = api('ground/tests', {'plan':plan, 'target':target,'revision':api('ground/tests')['revision']})
        try:
            sent = api('ground/send', {'test_id':saved['id'], 'target':target, 'command_id':command['id'], 'values':{}})
            until = time.monotonic() + plan['timeout'] + 5
            while time.monotonic() < until:
                run = next(r for r in api('ground')['runs'] if r['id'] == sent['event_id'])
                if run['status'] != 'waiting':
                    break
                time.sleep(.15)
            result = {'app':name,'command':command['id'],'status':run['status'],
                      'observations':[s['observation'] for s in run['steps'] if 'observation' in s]}
            print(json.dumps(result), flush=True)
            results.append(result)
        finally:
            api('ground/tests', {'id':saved['id'], 'delete':True, 'target':target, 'revision':api('ground/tests')['revision']})
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--target', choices=['native','qemu','physical'], default='native')
    args = parser.parse_args()
    cases = exercise(args.port, args.target)
    print('Without NOOP:', [r['app'] for r in cases if 'command' not in r])
    raise SystemExit(int(not any(r.get('status') == 'passed' for r in cases)
                         or any(r['status'] != 'passed' for r in cases if 'command' in r)))
