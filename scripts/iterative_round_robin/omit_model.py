"""Revise a frozen roster while its coordinator is stopped; preserve all artifacts."""
import argparse,datetime,fcntl,json,shutil
from pathlib import Path
from coordinator import save,read

def omit(root,model):
 with (root/'coordinator.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  manifest=read(root/'manifest.json');removed=[r for r in manifest['roster'] if r['model']==model]
  if not removed:return {'removed':[]}
  ids={r['id'] for r in removed};stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');archive=root/'roster_changes'/stamp;archive.mkdir(parents=True)
  shutil.copy2(root/'manifest.json',archive/'previous_manifest.json');shutil.copy2(root/'status.json',archive/'previous_status.json')
  active=[]
  for p in (root/'claims').glob('*.json'):
   if not ids.intersection(p.stem.split('__')):continue
   c=read(p)
   if c.get('status')=='running' and not (root/'matches'/p.stem/'result.json').exists():
    active.append(dict(id=p.stem,claim=c,progress=read(root/'progress'/(c['worker']+'.json'),{})))
  manifest['roster']=[r for r in manifest['roster'] if r['id'] not in ids];manifest.setdefault('excluded_roster',[]).extend(removed)
  manifest['reused_matches']=[j for j in manifest['reused_matches'] if not ids.intersection(j.split('__'))]
  n=len(manifest['roster']);manifest['total_matches']=n*(n-1)*len(manifest['seeds']);manifest.setdefault('roster_changes',[]).append(dict(at=stamp,excluded_model=model,excluded_bot_ids=sorted(ids),reason='User requested omission'))
  receipt=dict(removed=sorted(ids),active=active,total_matches=manifest['total_matches'],retained_runs=n,archive=str(archive));save(archive/'omission.json',receipt);save(root/'manifest.json',manifest);save(root/'last_omission.json',receipt)
  return receipt
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--model',required=True);a=p.parse_args();print(json.dumps(omit(a.root,a.model),indent=2))
