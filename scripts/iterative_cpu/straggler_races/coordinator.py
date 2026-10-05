"""Race fresh-seed optimized attempts against verified five-hour stragglers."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import argparse,gzip,hmac,json,os,re,secrets,threading,time,traceback,urllib.request,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;LOCK=threading.RLock();TOKEN='';RACES={};ERRORS=[]
SOURCES={'iterative-high-20260924':8001,'iterative-roster-20260924':8002,'iterative-23x2-20260924':8006}
def read(p,default=None):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return default
def save(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,indent=2,allow_nan=False));tmp.replace(p)
def call(port,path,d=None,headers=None,raw=None):
 req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=raw if raw is not None else json.dumps(d).encode() if d is not None else None,headers={'Authorization':'Bearer '+TOKEN,**(headers or {})})
 with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def persist():save(ROOT/'races.json',RACES)
def refresh():
 snapshot=read(ROOT/'snapshot.json',[]);by={}
 for row in snapshot:
  if row['pool'] in SOURCES:by.setdefault((row['pool'],row['id']),[]).append(row)
 while True:
  try:
   for (source,ident),rows in by.items():
    key=source+'::'+ident;target=BASE/source/'tournament/matches'/ident/'result.json'
    with LOCK:
     if key in RACES:
      race=RACES[key]
      if target.exists():
       result=read(target,{});race['winner']='replacement' if result.get('race',{}).get('attempt_id')==race['job']['id'] else 'original';race['status']='completed'
      continue
    if target.exists():continue
    leases=[read(p,{}) for p in (BASE/source/'tournament/live_leases').glob('*.json')];originals=[]
    for lease in leases:
     if lease.get('job')!=ident or time.time()-lease.get('updated_at',0)>120:continue
     host,pid,index=lease['worker'].rsplit('-',2);host=host.split('.')[0]
     row=next((r for r in rows if r['host']==host),None)
     if row:originals.append(dict(worker=lease['worker'],host=host,pid=int(pid),started_at=row['started_at'],path=row['attempt'].split(':',1)[1],identity=None,cancelled=False))
    if not originals:continue
    info=call(SOURCES[source],'/job',headers={'X-Match-ID':ident});job=info.get('job')
    if not job:continue
    seed=100000+secrets.randbelow(2**31-100000);attempt='race__'+ident+'__'+str(seed)
    new={k:job[k] for k in ['kind','candidate_id','opponent_id','side','seconds','red','blue']};new.update(id=attempt,seed=seed)
    sdf=sum(n.get('type')=='sdf' for side in ['red','blue'] for n in ET.fromstring(job[side]['xml']).iter('geom'))
    call(SOURCES[source],'/retire',{'workers':[o['worker'] for o in originals]})
    with LOCK:RACES[key]=dict(key=key,source=source,original_id=ident,original_seed=job['seed'],job=new,originals=originals,threads=4 if sdf>=4 else 1,status='pending',created_at=time.time(),winner=None,attempts=0);persist()
   with LOCK:
    for race in RACES.values():
     if race['status']=='running' and time.time()-race.get('heartbeat',0)>180:race['status']='failed';race['error']='replacement heartbeat expired; no automatic duplicate launch'
    persist();save(ROOT/'status.json',dict(updated_at=time.time(),target_ids=len(by),races=len(RACES),pending=sum(r['status']=='pending' for r in RACES.values()),running=sum(r['status']=='running' for r in RACES.values()),completed=sum(r['status']=='completed' for r in RACES.values()),replacement_wins=sum(r['winner']=='replacement' for r in RACES.values()),original_wins=sum(r['winner']=='original' for r in RACES.values()),cancelled_originals=sum(o['cancelled'] for r in RACES.values() for o in r['originals']),errors=ERRORS[-5:]))
  except Exception as exc:ERRORS.append(str(exc));traceback.print_exc()
  time.sleep(10)
class Handler(BaseHTTPRequestHandler):
 def send(self,d,code=200):
  raw=json.dumps(d).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_POST(self):
  if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):return self.send({},401)
  size=int(self.headers.get('Content-Length',0))
  if not 0<size<=256*1024**2:return self.send({},413)
  raw=self.rfile.read(size)
  if self.path=='/result':
   payload=json.loads(gzip.decompress(raw));result=payload['result']
   with LOCK:
    race=next(r for r in RACES.values() if r['job']['id']==result['id'])
    for k in ['seed','candidate_id','opponent_id','kind']:assert result[k]==race['job'][k]
    assert result['candidate_side']==race['job']['side'] and result['outcome'] in ['win','loss','draw']
    attempt=result['id'];result['id']=race['original_id'];result['race']=dict(attempt_id=attempt,original_seed=race['original_seed'],replacement_seed=result['seed'],policy='first valid accepted result; replacement requested after five hours')
    # The source coordinator owns the atomic first-result decision.
    receipt=call(SOURCES[race['source']],'/result',raw=gzip.compress(json.dumps(payload,allow_nan=False).encode(),compresslevel=1),headers={'Content-Type':'application/gzip'})
    accepted=read(BASE/race['source']/'tournament/matches'/race['original_id']/'result.json',{});race['winner']='replacement' if accepted.get('race',{}).get('attempt_id')==attempt else 'original';race['status']='completed';race['receipt']=receipt;persist();save(ROOT/'results'/f'{attempt}.json',result)
   return self.send(receipt)
  d=json.loads(raw)
  with LOCK:
   if self.path=='/claim':
    pending=sorted((r for r in RACES.values() if r['status']=='pending' and r['threads']==d['budget']),key=lambda r:min(o['started_at'] for o in r['originals']))
    for race in pending:
     if (BASE/race['source']/'tournament/matches'/race['original_id']/'result.json').exists():race['status']='completed';race['winner']='original';continue
     race.update(status='running',worker=d['worker'],heartbeat=time.time(),attempts=race['attempts']+1);persist();return self.send({'job':race['job']})
    return self.send({'job':None,'finished':False})
   if self.path=='/heartbeat':
    race=next(r for r in RACES.values() if r['job']['id']==d['job'])
    if race.get('worker')==d['worker']:
     race['heartbeat']=time.time()
     if isinstance(d.get('progress'),dict):save(ROOT/'progress'/f"{d['job']}.json",d['progress'])
    return self.send({'ok':True})
   if self.path=='/error':
    race=next(r for r in RACES.values() if r['job']['id']==d['job']);race['status']='failed';race['error']=d.get('error');persist();return self.send({'ok':True})
   if self.path=='/control':
    work=[]
    for race in RACES.values():
     for o in race['originals']:
      if o['host']==d['host'] and not o['cancelled']:
       lease=read(BASE/race['source']/'tournament/live_leases'/f"{o['worker']}.json",{})
       work.append(dict(key=race['key'],source=race['source'],original_id=race['original_id'],original=o,cancel=race['winner']=='replacement',lease=lease))
    drained={s:read(BASE/s/'tournament/status.json',{}).get('status')=='completed' for s in SOURCES}
    return self.send({'tasks':work,'drained':drained})
   if self.path=='/identity':
    race=RACES[d['key']];o=next(o for o in race['originals'] if o['worker']==d['worker']);o['identity']=d['identity'];persist();return self.send({'ok':True})
   if self.path=='/cancelled':
    race=RACES[d['key']];assert race['winner']=='replacement';o=next(o for o in race['originals'] if o['worker']==d['worker']);o['cancelled']=True;o['cancellation']=d;persist();return self.send({'ok':True})
  self.send({},404)
 def log_message(self,*args):pass
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--token-file',required=True);a=p.parse_args();TOKEN=Path(a.token_file).read_text().strip();RACES.update(read(ROOT/'races.json',{}));threading.Thread(target=refresh,daemon=True).start();ThreadingHTTPServer(('0.0.0.0',8008),Handler).serve_forever()
