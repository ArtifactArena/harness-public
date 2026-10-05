"""Frozen all-run round robin with durable leases and measured CPU-worker progress."""
import argparse, datetime, fcntl, gzip, hashlib, hmac, itertools, json, os, shutil, threading, time, traceback
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from rating import fit_elo
from progress_protocol import cpu_budget, record_progress

def read(p,default=None):
 try:return json.loads(p.read_text())
 except FileNotFoundError:return default

def save(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,allow_nan=False));tmp.replace(p)

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

class Tournament:
 def __init__(self,root):
  self.root=root;self.lock=threading.RLock();self.manifest=read(root/'manifest.json');self.roster=self.manifest['roster'];self.excluded={r['id'] for r in self.manifest.get('excluded_roster',[])};self.jobs={};self.results={};self.workers={};self.status={}
  recipes={r['id']:read(root/'selected'/r['id']/'recipe.json') for r in self.roster}
  for a,b in itertools.combinations(sorted(recipes),2):
   for seed,side in itertools.product(self.manifest['seeds'],['red','blue']):
    ident=f'iterative_top1__{a}__{b}__{seed}_{side}'
    j=dict(id=ident,kind='iterative_top1',candidate_id=a,opponent_id=b,seed=seed,side=side,seconds=self.manifest['seconds'],red=recipes[a if side=='red' else b],blue=recipes[b if side=='red' else a],status='pending',attempts=0)
    j['cpu_budget']=cpu_budget(j);j.update(read(root/'claims'/f'{ident}.json',{}))
    r=read(root/'matches'/ident/'result.json')
    if r:self.validate(j,r);self.results[ident]=r;j['status']='completed'
    self.jobs[ident]=j
  assert len(self.jobs)==self.manifest['total_matches']
  # Shuffle deterministically across pairs so new ratings gain field-wide coverage quickly.
  self.order=sorted(self.jobs,key=lambda k:hashlib.sha256(k.encode()).hexdigest())
  self.report()
 def persist(self,j):save(self.root/'claims'/f"{j['id']}.json",{k:j[k] for k in ['status','attempts','worker','heartbeat','error'] if k in j})
 @staticmethod
 def validate(j,r):
  for k in ['id','kind','candidate_id','opponent_id','seed']:
   if r.get(k)!=j[k]:raise ValueError('Result does not match job: '+k)
  if r.get('candidate_side')!=j['side'] or r.get('outcome') not in ['win','loss','draw']:raise ValueError('Invalid side or outcome')
 def claim(self,d,budget):
  with self.lock:
   self.workers[d['worker']]={'host':d['host'],'budget':budget,'last_seen':time.time()}
   # A lost HTTP response must not consume another lease for the same worker.
   current=next((j for j in self.jobs.values() if j['status']=='running' and j.get('worker')==d['worker']),None)
   if current:return {'job':current}
   j=next((self.jobs[k] for k in self.order if self.jobs[k]['status']=='pending' and self.jobs[k]['cpu_budget']==budget),None)
   if not j:return {'job':None,'finished':len(self.results)==len(self.jobs)}
   if shutil.disk_usage(self.root).free<20*1024**3:return {'job':None,'reason':'disk headroom'}
   j.update(status='running',worker=d['worker'],heartbeat=time.time(),attempts=j['attempts']+1);self.persist(j)
   return {'job':j}
 def heartbeat(self,d):
  with self.lock:
   j=self.jobs.get(d.get('job'))
   if j and j['status']=='running' and j.get('worker')==d.get('worker'):
    j['heartbeat']=time.time();self.persist(j);record_progress(self.root,d)
   return {'ok':True}
 def error(self,d):
  with self.lock:
   j=self.jobs.get(d.get('job'))
   if j and j['status']=='running' and j.get('worker')==d.get('worker'):
    j.update(status='pending' if j['attempts']<3 else 'failed',error=d.get('error','Worker failed'));self.persist(j)
   return {'ok':True}
 def result(self,payload,raw=None):
  r=payload['result']
  with self.lock:
   j=self.jobs.get(r.get('id'))
   if not j:
    if self.excluded.intersection([r.get('candidate_id'),r.get('opponent_id')]):
     save(self.root/'excluded_results'/str(r['id'])/'result.json',r);return {'ok':True,'excluded':True}
    raise ValueError('Unknown job')
   self.validate(j,r)
   if j['id'] in self.results:return {'ok':True,'duplicate':True}
   r={**r,'completed_at':now()};dest=self.root/'matches'/j['id']
   dest.mkdir(parents=True,exist_ok=True)
   if raw is not None:
    tmp=dest/'payload.tmp';tmp.write_bytes(raw);tmp.replace(dest/'result_payload.json.gz')
   save(dest/'result.json',r);self.results[j['id']]=r;j['status']='completed';j.pop('error',None);self.persist(j)
   return {'ok':True}
 def report(self):
  with self.lock:
   for j in self.jobs.values():
    if j['status']=='running' and time.time()-j.get('heartbeat',0)>300:
     j.update(status='pending' if j['attempts']<3 else 'failed',error='Worker heartbeat expired');self.persist(j)
   results=list(self.results.values());states=Counter(j['status'] for j in self.jobs.values());active=[dict(id=j['id'],worker=j.get('worker'),cpu_budget=j['cpu_budget']) for j in self.jobs.values() if j['status']=='running'];errors={j['id']:j.get('error','failed') for j in self.jobs.values() if j['status']=='failed'}
   pending=Counter(j['cpu_budget'] for j in self.jobs.values() if j['status']=='pending')
  ratings=fit_elo([r['id'] for r in self.roster],results);counts={r['id']:Counter() for r in self.roster}
  for r in results:
   counts[r['candidate_id']][r['outcome']]+=1;counts[r['opponent_id']][{'win':'loss','loss':'win','draw':'draw'}[r['outcome']]]+=1
  rows=[]
  for r in self.roster:
   c=counts[r['id']];n=sum(c.values());rows.append({k:r[k] for k in ['id','title','model','repeat','revision','experiment']}|dict(elo=ratings[r['id']],wins=c['win'],losses=c['loss'],draws=c['draw'],win_rate=c['win']/n if n else None,completed=n,total=6*(len(self.roster)-1)))
  rows.sort(key=lambda r:(r['elo'] is None,-(r['elo'] or 0),r['id']))
  for r in rows:r['rank']=1+sum(x['elo']>r['elo'] for x in rows if x['elo'] is not None) if r['elo'] is not None else None
  report=dict(updated_at=now(),excluded_bot_ids=sorted(self.excluded),status='completed' if len(results)==len(self.jobs) else 'needs_attention' if errors else 'running',completed_matches=len(results),total_matches=len(self.jobs),active_matches=states['running'],queued_matches=states['pending'],queued_by_cpu_budget=dict(pending),reused_matches=len(self.manifest['reused_matches']),selected_runs=len(rows),models=len({r['model'] for r in rows}),round_robin=rows,worker_hosts=sorted({a['worker'].rsplit('-',2)[0] for a in active}),active_cpus=sum(a['cpu_budget'] for a in active),active=active,errors=errors,elo_method=self.manifest['elo_method'],seeds=self.manifest['seeds'],seconds=self.manifest['seconds'])
  with self.lock:self.status=report;save(self.root/'status.json',report)
  return report
 def refresh(self):
  while True:
   try:self.report()
   except Exception:traceback.print_exc()
   time.sleep(15)

class Handler(BaseHTTPRequestHandler):
 def send(self,d,code=200):
  b=json.dumps(d,allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def authorized(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.token)
 def do_GET(self):
  if not self.authorized():return self.send({'error':'unauthorized'},401)
  return self.send(self.server.tournament.status if self.path=='/status' else {},200 if self.path=='/status' else 404)
 def do_POST(self):
  if not self.authorized():return self.send({'error':'unauthorized'},401)
  try:
   size=int(self.headers.get('Content-Length',0))
   if not 0<size<=256*1024**2:return self.send({'error':'payload size'},413)
   raw=self.rfile.read(size);t=self.server.tournament
   if self.path=='/result':return self.send(t.result(json.loads(gzip.decompress(raw)),raw))
   d=json.loads(raw)
   if self.path=='/claim':
    if self.headers.get('X-Match-Progress')!='simulation-v1':return self.send({'job':None,'finished':True,'reason':'Measured-progress worker required'})
    budget=int(self.headers.get('X-Match-CPU-Budget','0'))
    if budget not in [1,4]:raise ValueError('CPU budget must be 1 or 4')
    return self.send(t.claim(d,budget))
   if self.path=='/heartbeat':return self.send(t.heartbeat(d))
   if self.path=='/error':return self.send(t.error(d))
   return self.send({},404)
  except (ValueError,KeyError,TypeError) as e:return self.send({'error':str(e)},400)
 def log_message(self,*args):pass

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--token-file',type=Path,required=True);p.add_argument('--port',type=int,default=8003);a=p.parse_args()
 with (a.root/'coordinator.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);t=Tournament(a.root);server=ThreadingHTTPServer(('0.0.0.0',a.port),Handler);server.token=a.token_file.read_text().strip();server.tournament=t
  threading.Thread(target=t.refresh,daemon=True).start();print(now(),'READY',a.port,len(t.jobs),flush=True);server.serve_forever()
