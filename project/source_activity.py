"""Source-review evidence belongs to Studio, never to the flight source tree."""
import hashlib
import json
import time

from hardware.state import RuntimeState

STEPS = ('Code', 'Struct', 'Prototype', 'Dispatch', 'Events', 'Handler', 'Test')


class SourceActivity:
    def __init__(self, workspace, target, app, command):
        if target not in ('native', 'qemu', 'physical'):
            raise ValueError('Choose a target for this activity')
        if not isinstance(app, str) or not isinstance(command, str):
            raise ValueError('Choose an indexed application and command')
        self.workspace, self.target, self.app, self.command = workspace, target, app, command
        module = next((a for a in workspace.snapshot()['apps'] if a['name'] == app), None)
        routes = (module or {}).get('behavior', {}).get('details', {}).get('commands', [])
        item = next(((route, handler) for route in routes for handler in route.get('handlers', [])
                     if ((handler.get('cc') or {}).get('symbol') or (route.get('mid') or {}).get('symbol')) == command), None)
        if item is None:
            raise ValueError('Command is not in the current source index')
        route, handler = item
        self.placeholder = bool(handler.get('placeholder'))
        groups = [
            [(handler.get('cc') or {}).get('source') or (route.get('mid') or {}).get('source')],
            [handler.get('packet_source')], handler.get('prototypes', []), [handler.get('source')],
            [ref for event in handler.get('events', []) for ref in [(event.get('id') or {}).get('source'), event.get('source')]],
            [handler.get('handler')], []]
        self.refs = [[ref for ref in group if ref and ref.get('path')] for group in groups]
        identity = json.dumps([target, app, command], separators=(',', ':')).encode()
        self.key = 'source-review-' + hashlib.sha256(identity).hexdigest() + '.json'
        self.store = RuntimeState(workspace.root)

    def snapshot(self):
        record = self.store.read(self.key, {})
        checked = record.get('reviewed', {})
        steps = []
        for i, refs in enumerate(self.refs):
            sources, available = {}, bool(refs) and i < 6 and not (i == 5 and self.placeholder)
            for ref in refs:
                path = self.workspace.source_path(ref['path'])
                file = self.workspace.path(path)
                if not file.is_file():
                    available = False
                    continue
                sources[path] = hashlib.sha256(file.read_bytes()).hexdigest()
            fingerprint = hashlib.sha256(json.dumps([refs, sources], sort_keys=True).encode()).hexdigest()
            steps.append(dict(id=i, label=STEPS[i], available=available, sources=sources, refs=refs,
                              fingerprint=fingerprint, done=available and checked.get(str(i), {}).get('fingerprint') == fingerprint))
        files = {}
        for step in steps:
            for path in step['sources']:
                files.setdefault(path, []).append(step['done'])
        return dict(target=self.target, app=self.app, command=self.command, steps=steps,
                    files={path: all(states) for path, states in files.items()})

    def review(self, step, fingerprint):
        if type(step) is not int or not 0 <= step < 6:
            raise ValueError('Source review cannot confirm a flight test')
        current = self.snapshot()['steps'][step]
        if not current['available']:
            raise ValueError('This source step is not ready for review')
        if fingerprint != current['fingerprint']:
            raise ValueError('Source changed. Reopen the step before continuing.')
        with self.store.edit(self.key) as record:
            record.update(target=self.target, app=self.app, command=self.command)
            record.setdefault('reviewed', {})[str(step)] = dict(fingerprint=fingerprint, at=time.time())
        return self.snapshot()
