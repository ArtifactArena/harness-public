"""One authorized retry of terminal credit failures; preserve every prior revision."""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,json,shutil,subprocess,uuid

def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();records=json.loads((a.root/'registry.json').read_text());resumed=[]
 for record in records:
  run=Path(record['path']);status=json.loads((run/'status.json').read_text())
  if status.get('status')!='failed':continue
  failures=[]
  for path in run.glob('revision_*/response.json'):
   response=json.loads(path.read_text())
   if response.get('status')=='failed' and (response.get('error') or {}).get('code')=='credit_balance_exhausted':failures.append(path)
  if not failures:continue
  assert len(failures)==1,(record['id'],len(failures))
  directory=failures[0].parent;revision=int(directory.name[-2:]);session=record['session']
  assert not (directory/'evaluation_summary.json').exists(),'Failed revision has an evaluation'
  assert not (run/'STOPPED_TRUNCATED.json').exists(),'Truncation requires separate handling'
  assert 'request_retry.json' in (run/'provider_adapter.py').read_text(),'Adapter must support fresh idempotency keys'
  assert subprocess.run(['tmux','has-session','-t','='+session],capture_output=True).returncode!=0,'Run session already exists'
  with (run/'run.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   ident=uuid.uuid4().hex;archive=directory/'failed_attempts'/('billing-'+ident);archive.mkdir(parents=True)
   audit=dict(run=record['id'],revision=revision,retry_id=ident,reason='User added funds and authorized continuation',at=datetime.datetime.now(datetime.timezone.utc).isoformat(),prompt_sha256=hashlib.sha256((directory/'prompt.txt').read_bytes()).hexdigest(),prior_status=status)
   (archive/'retry-audit.json').write_text(json.dumps(audit,indent=2))
   for name in ['response.json','response_pending.json','response.txt','usage.json','request_settings.json','request_retry.json']:
    source=directory/name
    if source.exists():source.rename(archive/name)
   (directory/'request_retry.json').write_text(json.dumps({'id':ident,'reason':'credit balance replenished'}))
   if (run/'exit-code.txt').exists():shutil.copy2(run/'exit-code.txt',archive/'prior-exit-code.txt')
  subprocess.run(['tmux','new-session','-d','-s',session,'-c',str(run),'bash '+str(run/'launch.sh')],check=True)
  audit['session']=session;resumed.append(audit);(a.root/'billing-resume-20260924.json').write_text(json.dumps(resumed,indent=2));print(record['id'],'resumed at revision',revision,flush=True)
 print('Resumed',len(resumed),'billing failures')
if __name__=='__main__':main()
