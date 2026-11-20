"""Present the same bounded job stream consumed by the HTTP adapter."""
import json
import sys

from jobs.service import Laboratory


def run(root, action, options, machine=False):
    lab = Laboratory(root)
    try:
        ident = lab.job(action, options)['id']
        for frame in lab.job_updates(ident):
            for line in frame['lines']:
                if line != frame.get('error'):
                    print(line, file=sys.stderr, flush=True)
        if frame['status'] != 'succeeded':
            raise ValueError(frame.get('error') or frame['status'])
        result = frame.get('result') or {}
        if machine:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f'{action} · {frame["target"] or "local"} · {frame["status"]}')
        return result
    except KeyboardInterrupt:
        if 'ident' in locals():
            lab.cancel(ident)
        raise
    finally:
        lab.close()
