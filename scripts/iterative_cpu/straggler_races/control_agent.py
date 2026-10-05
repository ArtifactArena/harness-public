"""Identify original workers and cancel only verified losing attempts.

Freezing the owning ProcessPoolExecutor supervisor prevents one killed child
from cascading termination to its unrelated siblings. Other matches continue.
The supervisor resumes only after its source tournament is fully drained.
"""
from pathlib import Path
import argparse,json,os,signal,socket,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--token-file',required=True);p.add_argument('--state',type=Path,required=True);a=p.parse_args()
token=Path(a.token_file).read_text().strip();host=socket.gethostname().split('.')[0];parents=json.loads(a.state.read_text()) if a.state.exists() else {};retired={}
def call(path,d):
 req=urllib.request.Request('http://host_a.example.org:8008'+path,data=json.dumps(d).encode(),headers={'Authorization':'Bearer '+token})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def info(pid):
 p=Path(f'/proc/{pid}')
 if not p.exists():return None
 if p.stat().st_uid!=os.getuid():raise RuntimeError('Worker owner mismatch')
 fields=(p/'stat').read_text().rsplit(')',1)[1].split();cmd=(p/'cmdline').read_bytes()
 return dict(pid=pid,ppid=int(fields[1]),start_ticks=int(fields[19]),state=fields[0],cwd=str((p/'cwd').resolve()),worker=any(name in cmd for name in [b'tournament/worker.py',b'tournament/fleet_worker.py']) and b'--workers' in cmd,fleet=b'tournament/fleet_worker.py' in cmd)
def save():
 a.state.parent.mkdir(exist_ok=True,parents=True);tmp=a.state.with_suffix('.tmp');tmp.write_text(json.dumps(parents,indent=2));tmp.replace(a.state)
while True:
 try:
  response=call('/control',{'host':host})
  for t in response['tasks']:
   o=t['original'];identity=o.get('identity');current=info(o['pid'])
   if not current:
    if t['cancel']:call('/cancelled',dict(key=t['key'],worker=o['worker'],reason='already exited',host=host,at=time.time()))
    continue
   expected=str(Path(o['path']).parents[2]/'harness');folder=Path(o['path'])
   if not current['worker']:continue
   if current['fleet']:
    # A migrated fleet attempt has a different folder from the original snapshot.
    # Retire on BOTH source coordinators before trusting a subsequent heartbeat.
    if Path(current['cwd']).parent.name!='iterative-leaderboard-fleet-20260924':continue
    if o['worker'] not in retired:
     for port in [8001,8002]:
      req=urllib.request.Request(f'http://host_a.example.org:{port}/retire',data=json.dumps({'workers':[o['worker']]}).encode(),headers={'Authorization':'Bearer '+token})
      with urllib.request.urlopen(req,timeout=30) as r:json.load(r)
     retired[o['worker']]=time.time()
    if t['lease'].get('updated_at',0)<=retired[o['worker']]:continue
    folder=Path(current['cwd']).parent/'tournament/worker_matches'/t['original_id']
    expected=current['cwd']
   if current['cwd']!=expected:continue
   # A fresh heartbeat is the match-to-PID identity, independent of folder inference.
   if t['lease'].get('job')!=t['original_id'] or time.time()-t['lease'].get('updated_at',0)>120:continue
   if identity is None:
    boot=time.time()-float(Path('/proc/uptime').read_text().split()[0]);born=boot+current['start_ticks']/os.sysconf('SC_CLK_TCK')
    started=(folder/'red.xml').stat().st_mtime
    if born>started+1:continue
    if not current['fleet'] and abs(started-o['started_at'])>1:continue
    call('/identity',dict(key=t['key'],worker=o['worker'],identity=current));identity=current
   if not t['cancel']:continue
   if current['start_ticks']!=identity['start_ticks'] or current['ppid']!=identity['ppid']:continue
   # A retired worker cannot claim another job from its original coordinator.
   # If it finished naturally, let it exit rather than interrupt its upload.
   if (folder/'result_payload.json.gz').exists() or (folder/'result.json').exists():continue
   parent=info(current['ppid'])
   if parent and parent['worker']:
    key=str(parent['pid'])
    if key not in parents:
     parents[key]=dict(parent,source=t['source'],fleet=current['fleet'],stopped_at=time.time());save()
     os.kill(parent['pid'],signal.SIGSTOP)
    check=info(parent['pid'])
    if not check or check['start_ticks']!=parent['start_ticks']:continue
    if check['state'] not in ('T','t'):
     time.sleep(.1);check=info(parent['pid'])
     if not check or check['state'] not in ('T','t'):continue
   again=info(current['pid'])
   if not again or again['start_ticks']!=identity['start_ticks']:continue
   os.kill(current['pid'],signal.SIGTERM)
   call('/cancelled',dict(key=t['key'],worker=o['worker'],reason='replacement result accepted',host=host,pid=current['pid'],start_ticks=current['start_ticks'],parent_stopped=bool(parent and parent['worker']),at=time.time()))
   print('cancelled',current['pid'],t['original_id'],flush=True)
  for key,entry in list(parents.items()):
   if entry.get('fleet'):
    if not all(response['drained'].values()):continue
   elif not response['drained'].get(entry['source']):continue
   parent=info(int(key))
   if parent and parent['start_ticks']==entry['start_ticks']:os.kill(int(key),signal.SIGCONT)
   del parents[key];save()
 except Exception as exc:print(type(exc).__name__,str(exc),flush=True)
 time.sleep(15)
