"""Bounded CPU-only top-ups; release completed four-core slots for ordinary matches."""
import argparse,fcntl,json,os,subprocess,sys,time,urllib.request
from pathlib import Path

def retire_finished_heavy(directory,locks):
 for manifest in directory.glob('*.json'):
  try:
   d=json.loads(manifest.read_text())
   if d.get('budget')!=4 or d.get('host')!=os.uname().nodename:continue
   parent=Path('/proc')/str(d['pid']);root=Path(d['root']);stat=(parent/'stat').read_text().rsplit(')',1)[1].split()
   if parent.stat().st_uid!=os.getuid() or (parent/'cwd').resolve()!=root.resolve() or 'progress_worker.py' not in (parent/'cmdline').read_text():continue
   reservation=locks/f"straggler-reservation-progress-{d['job_id']}-{d['step_id']}-4.json";r=json.loads(reservation.read_text())
   if r['pid']!=d['pid'] or r.get('start_ticks')!=stat[19]:continue
   request=root/'tournament/retire-slots.json';tmp=request.with_suffix('.tmp');tmp.write_text(json.dumps(list(range(d['workers']))));tmp.replace(request)
   released=set()
   for i in range(d['workers']):
    ack=root/'tournament/retired-slots'/str(i)
    if not ack.exists():continue
    pid=json.loads(ack.read_text())['pid'];p=Path('/proc')/str(pid)/'stat'
    if not p.exists() or p.read_text().rsplit(')',1)[1].split()[0]=='Z':released.update(d['cpus'][4*i:4*i+4])
   if released:
    with (locks/'straggler-races-20260924.lock').open('a') as lock:
     fcntl.flock(lock,fcntl.LOCK_EX);r=json.loads(reservation.read_text())
     assert r['pid']==d['pid'] and r.get('start_ticks')==stat[19]
     pairs=[(c,k) for c,k in zip(r['cpus'],r['cores']) if c not in released];r['cpus']=[c for c,k in pairs];r['cores']=[k for c,k in pairs]
     tmp=reservation.with_suffix('.tmp');tmp.write_text(json.dumps(r));tmp.replace(reservation)
  except (OSError,ValueError,KeyError):continue

def main():
 p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--locks',type=Path,required=True);p.add_argument('--token',type=Path,required=True);p.add_argument('--max-workers',type=int,required=True);p.add_argument('--legacy-deployment',type=Path);p.add_argument('--gpu',action='store_true');a=p.parse_args();a.root.mkdir(parents=True,exist_ok=True)
 children=[]
 for wave in range(1440):
  try:
   req=urllib.request.Request('http://host_a.example.org:8003/status',headers={'Authorization':'Bearer '+a.token.read_text().strip()});s=json.load(urllib.request.urlopen(req,timeout=20))
   if a.legacy_deployment and not s['queued_by_cpu_budget'].get('4',0):retire_finished_heavy(a.legacy_deployment,a.locks)
   if s['status']=='completed':break
   memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))//1024
   count=min(a.max_workers,max(0,(memory-8192)//3072))
   if s['queued_by_cpu_budget'].get('1',0) and count:
    cmd=[sys.executable,str(a.stage/'launch_worker.py'),'--budget','1','--max-workers',str(count),'--run-root',str(a.root/f'wave-{wave}'),'--lock-root',str(a.locks),'--token-file',str(a.token)]
    if not a.gpu:cmd+=['--stage-dir',str(a.stage)]
    env=os.environ.copy();env['SLURM_STEP_ID']=os.environ.get('SLURM_STEP_ID','lab')+'-fill-'+str(wave);env['CUDA_VISIBLE_DEVICES']=''
    with (a.root/f'wave-{wave}.log').open('w') as f:children.append(subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=env))
   print(time.time(),'status',s['completed_matches'],s['active_matches'],'free_mem_mb',memory,flush=True)
  except Exception as e:print(type(e).__name__,str(e),flush=True)
  time.sleep(60)
 # Drain this manager's slots even when a shared legacy worker also polls old queues.
 for deployment in (a.stage/'deployment').glob('*.json'):
  try:
   d=json.loads(deployment.read_text());r=Path(d['root'])
   if r.parent==a.root and d['host']==os.uname().nodename:
    request=r/'tournament/retire-slots.json';request.write_text(json.dumps(list(range(d['workers']))))
  except (OSError,ValueError,KeyError):pass
 for child in children:
  if child.poll() is not None:continue
  child.wait()
if __name__=='__main__':main()
