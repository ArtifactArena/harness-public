"""Exclude the requested models from live registries without deleting artifacts.

Run on Host A with the artifactarena deployment root. Services must reload their
registries afterwards. Late result uploads for excluded runs are acknowledged
but cannot re-enter the tournament. Sampling opponents remain the frozen field.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil

MODELS={'claude-opus-5','minimaxai/minimax-m3'}
ROOTS=('iterative-roster-20260924','iterative-23x2-20260924','design-lab-23x2-20260924')


def excluded(record):
    return str(record.get('model','')).casefold() in MODELS


def replace_once(source, old, new):
    if source.count(old)!=1:raise ValueError(f'Expected one source anchor: {old[:90]!r}')
    return source.replace(old,new,1)


def patch_coordinator(source, kind):
    marker="\n# Explicitly omitted models cannot re-enter through a late worker upload.\n"
    if marker in source:return source
    guard=marker+"""_excluded_path=BASE/'excluded_runs.json'
EXCLUDED_RUNS={r['id'] for r in json.loads(_excluded_path.read_text())} if _excluded_path.exists() else set()
def omitted_result(result):
 return any(str(result.get(k,'')).rsplit('_',1)[0] in EXCLUDED_RUNS for k in ('candidate_id','opponent_id'))

"""
    anchor='def now():' if kind!='tooluse' else 'def read('
    pos=source.index(anchor);source=source[:pos]+guard+source[pos:]
    if kind=='roster':
        source,n=re.subn(r'RUNS=\[[^\n]*?\];SEEDS=',"RUNS=[r['id'] for r in json.loads((BASE/'registry.json').read_text())];SEEDS=",source,count=1)
        if n!=1:raise ValueError('Roster RUNS anchor missing')
    if kind=='iterative':
        old="   payload=json.loads(gzip.decompress(body));r=payload['result'];ident=r['id']"
    elif kind=='tooluse':
        old="   r=json.loads(gzip.decompress(raw))['result'];ident=r['id']"
    else:
        lines=[line for line in source.splitlines() if 'gzip.decompress' in line and "['result']" in line]
        if len(lines)!=1:raise ValueError('Roster result parsing anchor missing')
        old=lines[0]
    indent=old[:len(old)-len(old.lstrip())]
    source=replace_once(source,old,old+'\n'+indent+"if omitted_result(r):return self.send({'ok':True,'excluded':True})")
    compile(source,'coordinator.py','exec')
    return source


def prepare(base):
    changes={};removed={};run_paths={};stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    for name in ROOTS:
        root=base/name;path=root/'registry.json';records=json.loads(path.read_text())
        omitted=[r for r in records if excluded(r)];kept=[r for r in records if not excluded(r)]
        if not omitted:raise ValueError(f'No target records in {path}; inspect prior deployment')
        removed[name]=omitted
        for record in omitted:run_paths[Path(record['path']).resolve()]=record
        changes[path]=json.dumps(kept,indent=2)+'\n'
        changes[root/'excluded_runs.json']=json.dumps(omitted,indent=2)+'\n'
        kind={'iterative-roster-20260924':'roster','iterative-23x2-20260924':'iterative','design-lab-23x2-20260924':'tooluse'}[name]
        path=root/'tournament/coordinator.py';changes[path]=patch_coordinator(path.read_text(),kind)
    dashboard=base/'iterative-high-20260924/dashboard'
    path=dashboard/'tool_use_registry.json';records=json.loads(path.read_text())
    changes[path]=json.dumps([r for r in records if not excluded(r)],indent=2)+'\n'
    path=dashboard/'index.html';html=path.read_text()
    for old,new in [('Open-ended runs · 46','Open-ended runs · 42'),('23 models × 2 fresh runs, plus 5 third runs','21 models × 2 fresh runs, plus 5 third runs'),('2 prior runs registered to continue','1 prior run registered to continue'),('Current batch · all 53 runs','Current batch · all 48 runs'),('Repeat 1 · 23 fresh runs','Repeat 1 · 21 fresh runs'),('Repeat 2 · 23 fresh runs','Repeat 2 · 21 fresh runs')]:
        html=replace_once(html,old,new)
    changes[path]=html
    # Prevent recovery watchers or old launch commands from reviving omitted runs.
    for root,record in run_paths.items():
        with (root/'run.lock').open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        changes[root/'EXCLUDED.json']=json.dumps(dict(at=stamp,model=record['model'],reason='User requested omission from iterative and tool-use runs and tournaments'),indent=2)+'\n'
        launch=root/'launch.sh'
        if launch.exists():
            source=launch.read_text();lines=source.splitlines(keepends=True)
            guard="if [ -f \"$(dirname -- \"$0\")/EXCLUDED.json\" ]; then echo 'Run omitted by user'; exit 0; fi\n"
            lines.insert(1 if lines and lines[0].startswith('#!') else 0,guard)
            changes[launch]=''.join(lines)
    return changes,removed


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args()
    changes,removed=prepare(a.base)
    print(json.dumps({k:[r['id'] for r in v] for k,v in removed.items()},indent=2))
    if not a.apply:return
    audit=a.base/'model-exclusions-20260925';audit.mkdir(exist_ok=False)
    manifest=[]
    for path,new in changes.items():
        old=path.read_bytes() if path.exists() else None
        if old is not None:
            backup=audit/'before'/path.relative_to(a.base);backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
        manifest.append(dict(path=str(path),before_sha256=hashlib.sha256(old).hexdigest() if old is not None else None,after_sha256=hashlib.sha256(new.encode()).hexdigest()))
    (audit/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for path,new in changes.items():
        tmp=path.with_name(path.name+'.omit.tmp');tmp.write_text(new)
        if path.exists():shutil.copymode(path,tmp)
        tmp.replace(path)
    (audit/'removed.json').write_text(json.dumps(removed,indent=2)+'\n')
    print('Applied exclusions; reload coordinators and dashboard. Audit:',audit)


if __name__=='__main__':main()
