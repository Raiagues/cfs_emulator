"""Verify that evaluation operations preserved every original NASA tracked file."""
import argparse, hashlib, json
from pathlib import Path
from datetime import datetime, timezone
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('campaign',type=Path)
args=parser.parse_args()
base=args.campaign.resolve(); source=base/'flight/cFS'
expected=json.loads((base/'nasa-before.json').read_text())
actual={}; missing=[]
for name in sorted(expected):
 path=source/name
 if not path.resolve().is_relative_to(source.resolve()):
  raise ValueError('Source path leaves the NASA checkout: '+name)
 if path.is_file():actual[name]=hashlib.sha256(path.read_bytes()).hexdigest()
 else:missing.append(name)
changed=[name for name in actual if actual[name]!=expected[name]]
report={'checked_utc':datetime.now(timezone.utc).isoformat(),'status':'passed' if not changed and not missing else 'failed',
        'original_tracked_files':len(expected),'verified_files':len(actual),'changed':changed,'missing':missing,
        'scope':'Original NASA tracked files only; additional platform-generated modules are outside this set.',
        'verification_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
for name,value in [('nasa-after.json',actual),('nasa-preservation.json',report)]:
 (base/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
raise SystemExit(0 if report['status']=='passed' else 1)
