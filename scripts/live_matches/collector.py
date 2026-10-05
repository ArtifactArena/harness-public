"""Low-frequency read-only inventory; never touches simulator processes."""
from pathlib import Path
import argparse,json,os,socket,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--token-file',required=True);p.add_argument('--once',action='store_true');a=p.parse_args()
token=Path(a.token_file).read_text().strip();host=socket.gethostname();done=set()
def collect():
 pools={};uid=os.getuid()
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if proc.stat().st_uid!=uid:continue
   cmd=(proc/'cmdline').read_bytes()
   if not any(x in cmd for x in [b'tournament/worker.py',b'tournament/fleet_worker.py',b'tournament/rescue_worker.py']):continue
   cwd=(proc/'cwd').resolve()
   if cwd.name not in ('harness','source'):continue
   root=cwd.parent;maps=(proc/'maps').read_text();libs=sorted({l.split()[-1] for l in maps.splitlines() if 'arena_onecore' in l or 'parallel.so' in l})
   mode='SIMD + SDF rejection' if 'cpu-sdf-' in str(root) or 'cpu-parallel4-' in str(root) else 'SIMD' if libs else 'Cython observations' if 'observation_accel' in maps else 'Unaccelerated'
   entry=pools.setdefault(str(root),dict(root=str(root),pids=[],acceleration=mode));entry['pids'].append(int(proc.name))
  except (OSError,ValueError):pass
 rows=[]
 for path,pool in pools.items():
  folders=Path(path)/'tournament/worker_matches'
  if not folders.exists():continue
  for d in folders.iterdir():
   key=str(d)
   if key in done or not d.is_dir():continue
   if (d/'result.json').exists() or (d/'result_payload.json.gz').exists():done.add(key);continue
   parts=d.name.split('__')
   if len(parts)<4:continue
   try:started=(d/'red.xml').stat().st_mtime
   except OSError:continue
   row=dict(id=d.name,attempt=host+':'+key,host=host,pool=Path(path).name,
                    started_at=started,updated_at=time.time(),candidate_id=parts[1],
                    opponent_id='__'.join(parts[2:-1]),kind=parts[0],
                    side=parts[-1].rsplit('_',1)[-1],seed=parts[-1].split('_')[0],
                    acceleration=pool['acceleration'],threads=None,sim_seconds=None,
                    limit_seconds=300,tracking='legacy-inferred')
   for progress in (d/'live-progress').glob('live-*.json'):
    try:
     sample=json.loads(progress.read_text())
     if sample.get('complete') or sample.get('pid') not in pool['pids'] or time.time()-sample.get('updated_at',0)>120:continue
     row.update({k:sample[k] for k in ('pid','started_at','updated_at','sampled_at','sim_seconds','limit_seconds')});row['tracking']='measured';break
    except (OSError,ValueError,KeyError):continue
   rows.append(row)
 try:
  from tool_use_inventory import collect_tools
  rows.extend(collect_tools())
 except ImportError:pass  # Other hosts can continue using the existing collector.
 return dict(host=host,updated_at=time.time(),rows=rows,pools=list(pools.values()),gpus_used=0)
while True:
 try:
  data=collect();req=urllib.request.Request('http://host_a.example.org:8000/api/match-inventory',data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=15) as response:response.read()
  print(json.dumps(dict(host=host,at=time.time(),matches=len(data['rows']),pools=len(data['pools']))),flush=True)
 except Exception as exc:print(type(exc).__name__,str(exc),flush=True)
 if a.once:break
 time.sleep(30)
