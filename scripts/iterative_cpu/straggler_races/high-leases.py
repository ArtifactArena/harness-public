"""Streaming benchmark and within-run selection; these results never enter prompts."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import resource,re
import argparse,copy,datetime,fcntl,gzip,hashlib,hmac,json,math,os,shutil,socket,sys,threading,time,traceback
BASE=Path(__file__).resolve().parents[1];HERE=BASE/'tournament';HARNESS=BASE/'harness';sys.path.insert(0,str(HARNESS))
RUNS=['grok','gemini','astra','opus'];SEEDS=[7101,7102,7103];LOCK=threading.RLock();JOBS={};RESULTS={};CANDIDATES={};OPPONENTS=[];ERRORS=[];WORKERS={};START=time.time();TOKEN=''
RETIRED=set();
RESTORED_HEARTBEATS={};RESULT_LOCKS={};INITIAL_SCAN_DONE=False;LAST_REPORT={}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p,default=None):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return default

def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(src,dest):
 from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
 from mjarena.design_shop.pipelines.controller_pipeline import validate_controller
 from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
 from mjarena.dspy_core import get_actuator_names_from_xml_string
 dest.mkdir(parents=True,exist_ok=True)
 raw=(src/'robot.xml').read_text();code=(src/'controller.py').read_text()
 if not raw.strip() or not code.strip():return None,'invalid_output'
 morph=validate_morphology(raw,ModelValidationConfig(constraints_yaml_path=HARNESS/'configs/rules/rules.yaml',physics_mode='3d'))
 (dest/'morphology_validation.txt').write_text(morph.feedback)
 if not morph.passed:return None,'invalid_morphology'
 names=get_actuator_names_from_xml_string(morph.processed_xml)
 ctrl=validate_controller(code,names,processed_robot_xml=morph.processed_xml);(dest/'controller_validation.txt').write_text(ctrl.feedback)
 if not ctrl.passed:return None,'invalid_controller'
 return {'xml':morph.processed_xml,'code':code,'actuators':names},None

def prepare_opponents():
 manifest=read(HERE/'opponents.json')
 for e in manifest['opponents']:
  src=HERE/'opponents'/e['id'];assert sha(src/'robot.xml')==e['robot_sha256'] and sha(src/'controller.py')==e['controller_sha256']
  recipe,error=prepare(src,HERE/'prepared/opponents'/e['id'])
  if error:raise RuntimeError(f"Roster bot invalid: {e['id']} {error}")
  OPPONENTS.append({**e,'recipe':recipe,'eligible':True})
 save(HERE/'roster_status.json',{'opponents':len(OPPONENTS),'status':'validated','ratings_source':manifest['roster_source'],'at':now()})

def add_job(candidate,opponent,kind,seed,side):
 ident=f"{kind}__{candidate['id']}__{opponent['id']}__{seed}_{side}"
 if ident in JOBS:return
 red=candidate if side=='red' else opponent;blue=opponent if side=='red' else candidate
 job={'id':ident,'kind':kind,'candidate_id':candidate['id'],'opponent_id':opponent['id'],'seed':seed,'side':side,'seconds':300,'red':red['recipe'],'blue':blue['recipe'],'status':'pending','attempts':0}
 previous=read(HERE/'matches'/ident/'result.json')
 if previous:RESULTS[ident]=previous;job['status']='completed'
 elif not red['eligible'] or not blue['eligible']:
  winner='tie' if not red['eligible'] and not blue['eligible'] else ('blue' if not red['eligible'] else 'red')
  r={'id':ident,'kind':kind,'candidate_id':candidate['id'],'opponent_id':opponent['id'],'seed':seed,'candidate_side':side,'outcome':'draw' if winner=='tie' else 'win' if winner==side else 'loss','winner':winner,'termination_reason':'validation_forfeit','duration_seconds':0,'forfeit':True,'wall_seconds':0,'completed_at':now()}
  save(HERE/'matches'/ident/'result.json',r);RESULTS[ident]=r;job['status']='completed'
 with LOCK:
  lease=RESTORED_HEARTBEATS.get(ident)
  if lease and ident not in RESULTS:job.update(status='running',worker=lease['worker'],heartbeat=lease['time'],attempts=1)
  if ident in RESULTS:job['status']='completed'
  JOBS[ident]=job

def scan():
 for key in RUNS:
  for p in sorted((BASE/'runs'/key).glob('revision_*')):
   if not (p/'evaluation_summary.json').exists():continue
   ident=key+'_'+p.name[-2:]
   if ident in CANDIDATES:continue
   recipe,error=prepare(p,HERE/'prepared/candidates'/ident)
   rev=int(p.name[-2:]);ev=read(p/'evaluation_summary.json')
   candidate={'id':ident,'experiment':key,'revision':rev,'eligible':not error,'invalid_reason':error,'cube_qualified':ev.get('qualification_passed',False),'recipe':recipe,'source_robot_sha256':sha(p/'robot.xml'),'source_controller_sha256':sha(p/'controller.py')}
   with LOCK:
    CANDIDATES[ident]=candidate
    for o in OPPONENTS:
     for seed in SEEDS:
      for side in ('red','blue'):add_job(candidate,o,'top1',seed,side)
    for other in list(CANDIDATES.values()):
     if other['experiment']!=key or other['id']==ident:continue
     first,second=sorted([candidate,other],key=lambda c:c['revision'])
     for seed in SEEDS:
      for side in ('red','blue'):add_job(first,second,'selection',seed,side)
   print(now(),'queued',ident,'eligible=',not error,flush=True)

def rating(results):
 if not results:return None,None
 ratings={o['id']:o['elo'] for o in OPPONENTS};k=math.log(10)/400
 # Fixed published opponent ratings; weak Gaussian prior makes all-win/loss cases finite.
 mu=1000.;variance=800.**2
 def gradient(x):return sum(k*((1 if r['outcome']=='win' else 0 if r['outcome']=='loss' else .5)-1/(1+10**((ratings[r['opponent_id']]-x)/400))) for r in results)-(x-mu)/variance
 lo,hi=-3000.,5000.
 for _ in range(80):
  mid=(lo+hi)/2
  if gradient(mid)>0:lo=mid
  else:hi=mid
 estimate=(lo+hi)/2
 info=1/variance
 for r in results:
  prob=1/(1+10**((ratings[r['opponent_id']]-estimate)/400));info+=k*k*prob*(1-prob)
 return round(estimate,1),round(1.96/math.sqrt(info),1)

def report():
 global LAST_REPORT
 with LOCK:
  results=list(RESULTS.values());candidates=list(CANDIDATES.values());jobs=list(JOBS.values());workers=copy.deepcopy(WORKERS)
 rows=[];total_per=len(OPPONENTS)*6
 for c in sorted(candidates,key=lambda c:(c['experiment'],c['revision'])):
  rs=[r for r in results if r['kind']=='top1' and r['candidate_id']==c['id']];w=sum(r['outcome']=='win' for r in rs);l=sum(r['outcome']=='loss' for r in rs);d=len(rs)-w-l
  elo,interval=rating(rs) if c['eligible'] else (None,None)
  rows.append({k:v for k,v in c.items() if k!='recipe'}|{'wins':w,'losses':l,'draws':d,'forfeits':sum(r['forfeit'] for r in rs),'completed':len(rs),'total':total_per,'complete':len(rs)==total_per,'elo':elo,'elo_95_half_width':interval,'win_rate':w/len(rs) if rs else None,'by_opponent':[{'opponent_id':o['id'],'elo':o['elo'],**{k:sum(r['opponent_id']==o['id'] and r['outcome']==out for r in rs) for k,out in [('wins','win'),('losses','loss'),('draws','draw')]}} for o in OPPONENTS]})
 selection=[]
 for key in RUNS:
  cs=[c for c in candidates if c['experiment']==key];rr=[r for r in results if r['kind']=='selection' and r['candidate_id'].startswith(key+'_')];standing=[]
  for c in cs:
   wins=losses=draws=0
   for r in rr:
    if c['id'] not in (r['candidate_id'],r['opponent_id']):continue
    outcome=r['outcome']
    if c['id']==r['opponent_id']:outcome={'win':'loss','loss':'win','draw':'draw'}[outcome]
    wins+=outcome=='win';losses+=outcome=='loss';draws+=outcome=='draw'
   standing.append({'id':c['id'],'revision':c['revision'],'wins':wins,'losses':losses,'draws':draws,'points':wins+.5*draws,'eligible':c['eligible']})
  standing.sort(key=lambda c:(not c['eligible'],-c['points'],-c['wins'],c['revision']))
  complete=len(cs)==10 and len(rr)==270
  winner=standing[0]['id'] if complete and standing and standing[0]['eligible'] else None
  if winner:
   dest=BASE/'runs'/key/'selected_bot'
   if not (dest/'selection.json').exists():
    source=BASE/'runs'/key/f"revision_{standing[0]['revision']:02d}";dest.mkdir(exist_ok=True)
    for f in ('robot.xml','controller.py','response.txt'):shutil.copy2(source/f,dest/f)
    save(dest/'selection.json',{'winner':winner,'criterion':'Round-robin points (win=1, draw=0.5), then wins, then earlier iteration','standings':standing,'matches':270})
  selection.append({'experiment':key,'completed':len(rr),'total':270,'complete':complete,'winner':winner,'standings':standing})
 failed=[j['id'] for j in jobs if j['status']=='failed'];active=sum(j['status']=='running' for j in jobs)
 done=len(candidates)==len(RUNS)*10 and len(results)==len(RUNS)*(10*total_per+270)
 actual=[r for r in results if not r['forfeit']]
 mean=sum(r['wall_seconds'] for r in actual)/len(actual) if actual else None
 working=sum(time.time()-w['last_seen']<120 for w in workers.values())
 payload={'status':'completed' if done else 'running_with_errors' if failed or ERRORS else 'running','updated_at':now(),'completed_matches':len(results),'total_matches':len(RUNS)*(10*total_per+270),'top1_completed':sum(r['kind']=='top1' for r in results),'top1_total':len(RUNS)*10*total_per,'selection_completed':sum(r['kind']=='selection' for r in results),'selection_total':len(RUNS)*270,'queued_matches':sum(j['status']=='pending' for j in jobs),'active_matches':active,'completed_bots':sum(r['complete'] for r in rows),'total_bots':len(RUNS)*10,'opponents':len(OPPONENTS),'workers':working,'worker_hosts':sorted({w['worker'].split('-')[0] for w in workers.values() if time.time()-w['last_seen']<120}),'eta_seconds':(len(RUNS)*(10*total_per+270)-len(results))*mean/working if mean and working else None,'rows':rows,'selection':selection,'failed_jobs':failed,'errors':ERRORS[-10:],'ratings_method':'Elo performance MAP against frozen published top-1 ratings; win=1 draw=0.5; N(1000,800^2) prior; 95% curvature interval; partial results provisional','forfeit_policy':'Invalid output, morphology or controller forfeits; valid bots play even if cube qualification failed','seeds':SEEDS,'seconds':300}
 save(HERE/'status.json',payload)
 LAST_REPORT=payload
 return payload

def scheduler():
 global INITIAL_SCAN_DONE
 try:prepare_opponents()
 except Exception as exc:
  ERRORS.append(str(exc));save(HERE/'status.json',{'status':'failed','error':str(exc)});traceback.print_exc();return
 while True:
  try:
   scan()
   INITIAL_SCAN_DONE=True
   with LOCK:
    for j in JOBS.values():
     if j['status']=='running' and time.time()-j.get('heartbeat',0)>600:j['status']='pending' if j['attempts']<2 else 'failed'
   if report()['status']=='completed':return
  except Exception as exc:ERRORS.append(str(exc));traceback.print_exc()
  time.sleep(10)

class BoundedHTTPServer(ThreadingHTTPServer):
 request_queue_size=256
 daemon_threads=True
 def __init__(self,*args,**kwargs):
  self.slots=threading.BoundedSemaphore(96)
  super().__init__(*args,**kwargs)
 def process_request(self,request,address):
  self.slots.acquire()
  try:super().process_request(request,address)
  except BaseException:self.slots.release();raise
 def process_request_thread(self,request,address):
  try:super().process_request_thread(request,address)
  finally:self.slots.release()
class Handler(BaseHTTPRequestHandler):
 timeout=60
 def send(self,data,code=200):
  body=json.dumps(data).encode()
  try:
   self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
 def do_GET(self):
  if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):return self.send({'error':'unauthorized'},401)
  if self.path=='/job':
   ident=self.headers.get('X-Match-ID','')
   with LOCK:job=JOBS.get(ident)
   return self.send({'ready':INITIAL_SCAN_DONE,'job':job})
  if self.path=='/leases':return self.send([read(p,{}) for p in (HERE/'live_leases').glob('*.json')])
  if self.path=='/status':return self.send(LAST_REPORT or read(HERE/'status.json',{}))
  self.send({},404)
 def do_POST(self):
  if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):return self.send({'error':'unauthorized'},401)
  length=int(self.headers.get('Content-Length',0))
  if length>256*1024**2:return self.send({'error':'too large'},413)
  body=self.rfile.read(length)
  if self.path=='/retire':
   d=json.loads(body);workers=d.get('workers',[])
   if not isinstance(workers,list) or any(not isinstance(w,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',w) for w in workers):return self.send({'error':'invalid worker'},400)
   with LOCK:
    RETIRED.update(workers);save(HERE/'retired_workers.json',sorted(RETIRED))
   return self.send({'retired':len(workers)})
  if self.path=='/result':
   payload=json.loads(gzip.decompress(body));r=payload['result'];ident=r['id']
   if not re.fullmatch(r'(?:top1|selection)__[A-Za-z0-9_.-]+',ident) or r.get('kind') not in ('top1','selection'):return self.send({'error':'invalid job'},400)
   with LOCK:result_lock=RESULT_LOCKS.setdefault(ident,threading.Lock())
   # Serialize only duplicate uploads of the same result. Large replay writes
   # never hold the shared claim/heartbeat lock.
   with result_lock:
    with LOCK:duplicate=ident in RESULTS or (HERE/'matches'/ident/'result.json').exists()
    if not duplicate:
     folder=HERE/'matches'/ident;folder.mkdir(parents=True,exist_ok=True)
     (folder/'composed.xml').write_text(payload['composed_xml'])
     with gzip.open(folder/'match_data.json.gz','wt',compresslevel=1) as f:json.dump(payload['match_data'],f,separators=(',',':'),allow_nan=False)
     r['completed_at']=now();save(folder/'result.json',r)
     with LOCK:
      RESULTS[ident]=r
      if ident in JOBS:JOBS[ident]['status']='completed'
   return self.send({'ok':True,'duplicate':duplicate})
  d=json.loads(body);worker=d.get('worker','unknown');reply={};code=200;error_path=None
  with LOCK:
   WORKERS[worker]={'worker':worker,'last_seen':time.time()}
   if self.path=='/claim':
    if worker in RETIRED:reply={'job':None,'finished':True,'reason':'worker retired after current match'}
    elif not INITIAL_SCAN_DONE or time.time()-START<180:reply={'job':None,'reason':'restoring active leases'}
    elif shutil.disk_usage(HERE).free<15*1024**3:reply={'job':None,'reason':'disk below 15 GiB'}
    else:
     pending=[j for j in JOBS.values() if j['status']=='pending']
     if pending:
      j=min(pending,key=lambda j:(j['kind']!='top1',int(j['candidate_id'].rsplit('_',1)[1]),j['seed'],j['id']))
      j.update(status='running',worker=worker,heartbeat=time.time(),attempts=j['attempts']+1);reply={'job':dict(j)}
     else:reply={'job':None,'finished':LAST_REPORT.get('status')=='completed'}
   elif self.path=='/heartbeat':
    ident=d['job'];j=JOBS.get(ident)
    RESTORED_HEARTBEATS[ident]={'worker':worker,'time':time.time()}
    if j and j.get('status')!='completed' and (j.get('worker') in (None,worker) or time.time()-START<180):j.update(status='running',worker=worker,heartbeat=time.time(),attempts=max(1,j['attempts']))
    reply={'ok':True}
   elif self.path=='/error':
    j=JOBS.get(d['job'])
    if j:
     j['status']='pending' if j['attempts']<2 else 'failed';error_path=HERE/'errors'/f"{d['job']}-{j['attempts']}.json"
    reply={'ok':True}
   else:code=404
  if self.path=='/heartbeat' and re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',worker):
   save(HERE/'live_leases'/f'{worker}.json',{'worker':worker,'job':d['job'],'updated_at':time.time()})
  if error_path:save(error_path,d)
  self.send(reply,code)
 def log_message(self,*args):pass
if __name__=='__main__':
 soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE);resource.setrlimit(resource.RLIMIT_NOFILE,(max(soft,min(65536,hard)),hard))
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8001);p.add_argument('--token-file',required=True);a=p.parse_args();TOKEN=Path(a.token_file).read_text().strip()
 with (HERE/'coordinator.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  RETIRED.update(read(HERE/'retired_workers.json',[]))
  threading.Thread(target=scheduler,daemon=True).start()
  print('Coordinator',socket.getfqdn(),a.port,flush=True);BoundedHTTPServer(('0.0.0.0',a.port),Handler).serve_forever()
