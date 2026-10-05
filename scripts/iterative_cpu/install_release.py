"""Validate the frozen harness before installing an immutable CPU overlay."""
from pathlib import Path
import argparse,hashlib,json,shutil
p=argparse.ArgumentParser();p.add_argument('release',type=Path);p.add_argument('run',type=Path);a=p.parse_args()
m=json.loads((a.release/'manifest.json').read_text())
for name,expected in m['files'].items():
    assert hashlib.sha256((a.release/name).read_bytes()).hexdigest()==expected,name
for name,expected in m['baseline'].items():
    target=a.run/'harness'/name
    actual=hashlib.sha256(target.read_bytes()).hexdigest()
    # A repeated staging attempt may already contain this exact release's patched file.
    assert actual in {expected,m['files'].get('harness/'+name)},name
for name in m['files']:
    target=a.run/name;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==m['files'][name]:continue
    shutil.copy2(a.release/name,target)
shutil.copy2(a.release/'manifest.json',a.run/'cpu-acceleration-manifest.json')
print('Installed verified CPU-only overlay:',a.run,flush=True)
