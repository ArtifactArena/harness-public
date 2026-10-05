"""Read-only dashboard view assembled from per-host inventories and live telemetry."""
from pathlib import Path
import json,time
HERE=Path(__file__).resolve().parent
DATA=HERE/'live-data'
EXPECTED=['host_a','host_e','host_c','host_b','host_d','host_f','host_g','host_h','host_i']+[f'gpu-node-{i}' for i in [5,8,10,11,12,13]]
SOURCES=['iterative-length10-round-robin-20260925','iterative-high-20260924','iterative-roster-20260924','iterative-23x2-20260924','design-lab-23x2-20260924']
def read(p):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return {}
def state():
 now=time.time();hosts={};rows=[]
 for path in DATA.glob('*.json'):
  d=read(path);name=d.get('host','').split('.')[0]
  if not name:continue
  age=now-d.get('updated_at',0);hosts[name]=dict(host=name,age=age,stale=age>120,pools=len(d.get('pools',[])))
  for row in d.get('rows',[]):
   pids=[pid for pool in d.get('pools',[]) if Path(pool['root']).name==row.get('pool') for pid in pool.get('pids',[])]
   rows.append({**row,'host':name,'stale':age>120,'pool_pids':pids})
 for name in EXPECTED:
  if name not in hosts:hosts[name]=dict(host=name,age=None,stale=True,pools=None)
 live=[]
 for dirname,subdir,label in [('sdf-multicpu-20260924','rescue','Four-core SDF fleet'),('straggler-races-20260924','','Replacement fleet')]+[(source,'tournament','Progress fleet · '+source) for source in SOURCES]:
  root=HERE.parents[1]/dirname/subdir
  excluded=set(read(root/'status.json').get('excluded_bot_ids',[]))
  for path in (root/'progress').glob('*.json'):
   d=read(path)
   if excluded.intersection([d.get('candidate_id'),d.get('opponent_id')]):continue
   if not d or (root/'results'/path.name).exists() or (subdir=='tournament' and (root/'matches'/d.get('job','')/'result.json').exists()):continue
   age=now-d.get('updated_at',0)
   if age>120:continue
   host=d['host'].split('.')[0];ident=d['job']
   rows=[r for r in rows if not (r['id']==ident and r['host']==host and ('parallel4' in r.get('pool','') or 'straggler-races' in r.get('pool','')))]
   replacement=dirname=='straggler-races-20260924'
   parts=ident.split('__')
   extra=dict(replacement=True,original_id='__'.join(parts[1:-1]),original_seed=int(parts[-2].split('_')[0])) if replacement else {}
   extra['source']=dirname
   live.append(dict(d,**extra,id=ident,attempt=f"{host}:{d['pid']}:{ident}",host=host,pool=label,tracking='measured',stale=False))
 # Heartbeats confirm legacy ownership without interrupting the simulation.
 leases={}
 for source in SOURCES:
  for path in (HERE.parents[1]/source/'tournament/live_leases').glob('*.json'):
   d=read(path)
   if now-d.get('updated_at',0)>120:continue
   parts=d.get('worker','').rsplit('-',2)
   if len(parts)!=3 or not parts[1].isdigit():continue
   host=parts[0].split('.')[0]
   leases.setdefault((host,d.get('job')),[]).append((source,d,int(parts[1])))
 for row in rows:
  matches=[(source,lease,pid) for source,lease,pid in leases.get((row['host'],row['id']),[])
           if pid in row.get('pool_pids',[]) and not row['stale']]
  if matches:
   source,lease,pid=max(matches,key=lambda x:x[1]['updated_at'])
   row.update(tracking='heartbeat-confirmed',worker=lease['worker'],pid=pid,source=source)
   row['accepted_result']=(HERE.parents[1]/source/'tournament/matches'/row['id']/'result.json').exists()
 # Explicit cancellation receipts take precedence over legacy folder discovery.
 races=read(HERE.parents[1]/'straggler-races-20260924/races.json')
 cancelled={(o['host'],r['original_id'],o['pid']) for r in races.values() for o in r.get('originals',[]) if o.get('cancelled')}
 rows=[r for r in rows if (r['host'],r['id'],r.get('pid')) not in cancelled]
 # Telemetry identifies its exact worker; preserve other attempts of the same match.
 measured_attempts={(r['host'],r['pid'],r['id']) for r in live}
 rows=[r for r in rows if (r['host'],r.get('pid'),r['id']) not in measured_attempts]
 rows+=live
 for r in rows:
  r['confirmed']=r['tracking'] in ('measured','heartbeat-confirmed','process-confirmed') and not r['stale']
  if r.get('source')=='design-lab-23x2-20260924' or r.get('pool')=='design-lab-23x2-20260924':
   r['category']='tool_use';r['kind']='tool use · selection';r['pool']='Tool use · selection tournament'
  elapsed=max(0,now-r['started_at']);r['elapsed_seconds']=elapsed
  sim=r.get('sim_seconds');sample=r.get('sampled_at');limit=r.get('limit_seconds',300)
  r['progress']=min(1,max(0,sim/limit)) if sim is not None else None
  r['eta_seconds']=max(0,(limit-sim)*(sample-r['started_at'])/sim) if sim and sample and sim>=.5 and not r['stale'] and now-sample<120 else None
 rows.sort(key=lambda r:r['started_at'])
 return dict(updated_at=now,matches=rows,hosts=sorted(hosts.values(),key=lambda h:h['host']),
             races=read(HERE.parents[1]/'straggler-races-20260924/status.json'),
             measured=sum(r['tracking']=='measured' and r['confirmed'] for r in rows),
             confirmed=sum(r['confirmed'] for r in rows),unverified=sum(not r['confirmed'] for r in rows),
             note='Progress is simulated time toward the match time limit; a ring-out or other early finish can end a match sooner. ETA extrapolates observed simulation speed. Fresh telemetry, a worker heartbeat tied to a live PID, or a live sandbox process confirms activity. Older tool invocations appear as batches with progress unavailable. Unverified folders are excluded from the confirmed count. A running copy with an accepted result is marked cleanup pending.')
