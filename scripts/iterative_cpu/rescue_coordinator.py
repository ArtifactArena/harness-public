"""Accelerate only unfinished existing selection and iterative representative games.

Original workers remain valid; original coordinators atomically accept the first result.
No sampling-benchmark games are created or replayed by this queue.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import argparse,fcntl,gzip,hashlib,hmac,itertools,json,os,socket,sys,threading,time,traceback
import httpx
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
LB=BASE/'iterative-leaderboard-20260924'
sys.path.insert(0,str(LB/'tournament'))
import leaderboard as lb
import source_coordinator as source
LOCK=threading.RLock();JOBS={};CURRENT=set();RECIPES={};WORKERS={};ERRORS={};TOKEN='';FINISHED=False

def recipe(model,ident,meta):
    if ident in RECIPES:return RECIPES[ident]
    path=model['root']/'runs'/model['id']/f"revision_{int(ident.rsplit('_',1)[1]):02d}"
    assert lb.sha(path/'robot.xml')==meta['source_robot_sha256']
    assert lb.sha(path/'controller.py')==meta['source_controller_sha256']
    dest=ROOT/'rescue/prepared'/ident
    cached=lb.read(dest/'recipe.json')
    if cached is None:
        cached,error=source.prepare(path,dest)
        if error:raise RuntimeError(f'{ident}: {error}')
        lb.save(dest/'recipe.json',cached)
        lb.save(dest/'source.json',{'source':str(path),'robot_sha256':meta['source_robot_sha256'],'controller_sha256':meta['source_controller_sha256']})
    RECIPES[ident]=cached;return cached

def add(job,target,result_path,priority,current):
    ident=job['id'];current.add(ident)
    with LOCK:
        if ident in JOBS:return
        JOBS[ident]={'job':job,'target':target,'result_path':str(result_path),'priority':priority,'status':'completed' if result_path.exists() else 'pending','attempts':0}

def refresh():
    global FINISHED
    models=lb.sources()
    while True:
        try:
            current=set()
            for root in {m['root'] for m in models}:
                bench=lb.read(root/'tournament/status.json',{})
                metadata={r['id']:r for r in bench.get('rows',[])}
                port=8001 if root.name=='iterative-high-20260924' else 8002
                for m in [x for x in models if x['root']==root]:
                    sel=next((x for x in bench.get('selection',[]) if x['experiment']==m['id']),{})
                    standings=sorted(sel.get('standings',[]),key=lambda x:x['revision'])
                    for a,b in itertools.combinations(standings,2):
                        for seed in lb.SEEDS:
                            for side in ('red','blue'):
                                ident=f"selection__{a['id']}__{b['id']}__{seed}_{side}"
                                result_path=root/'tournament/matches'/ident/'result.json'
                                if result_path.exists():continue
                                assert a['eligible'] and b['eligible'],ident
                                ra,rb=recipe(m,a['id'],metadata[a['id']]),recipe(m,b['id'],metadata[b['id']])
                                job=dict(id=ident,kind='selection',candidate_id=a['id'],opponent_id=b['id'],seed=seed,side=side,seconds=300,red=ra if side=='red' else rb,blue=rb if side=='red' else ra)
                                add(job,f'http://127.0.0.1:{port}',result_path,0,current)
            board=lb.read(LB/'tournament/status.json',{})
            selected=[s for s in board.get('selections',[]) if s['state'] in ('selected','provisional')]
            recipes={s['winner']:lb.read(LB/'tournament/selected'/s['winner']/'recipe.json') for s in selected}
            for ident,job in lb.make_jobs(selected,recipes).items():
                result_path=LB/'tournament/matches'/ident/'result.json'
                if not result_path.exists():add(job,'http://127.0.0.1:8003',result_path,1,current)
            with LOCK:
                CURRENT.clear();CURRENT.update(current)
                for ident,item in JOBS.items():
                    if Path(item['result_path']).exists():item['status']='completed'
                    elif item['status']=='running' and time.time()-item.get('heartbeat',0)>600:
                        item['status']='pending' if item['attempts']<2 else 'failed'
                FINISHED=board.get('status')=='completed'
                report={'updated_at':lb.now(),'finished':FINISHED,'cpu_only':True,'cpus_per_match':1,'selection_pending':sum(i in CURRENT and j['priority']==0 and j['status']=='pending' for i,j in JOBS.items()),'leaderboard_pending':sum(i in CURRENT and j['priority']==1 and j['status']=='pending' for i,j in JOBS.items()),'active':sum(j['status']=='running' for j in JOBS.values()),'completed':sum(j['status']=='completed' for j in JOBS.values()),'accelerated_results':sum(bool(j.get('accelerated_result')) for j in JOBS.values()),'workers':len([w for w in WORKERS.values() if time.time()-w<120]),'errors':ERRORS}
                lb.save(ROOT/'rescue/status.json',report)
        except Exception:traceback.print_exc()
        time.sleep(15)

class Handler(BaseHTTPRequestHandler):
    def send(self,data,code=200):
        raw=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):return self.send({'error':'unauthorized'},401)
        size=int(self.headers.get('Content-Length',0))
        if size>256*1024**2:return self.send({'error':'too large'},413)
        raw=self.rfile.read(size)
        if self.path=='/result':
            r=json.loads(gzip.decompress(raw))['result'];ident=r['id']
            with LOCK:
                item=JOBS[ident];job=item['job']
                assert r['kind'] in ('selection','iterative_top1') and r['kind']==job['kind']
                for key in ['candidate_id','opponent_id','seed']:assert r[key]==job[key]
                assert r['candidate_side']==job['side'] and r['outcome'] in ('win','loss','draw')
            with httpx.Client(timeout=600,headers={'Authorization':'Bearer '+TOKEN}) as client:
                response=client.post(item['target']+'/result',content=raw,headers={'Content-Type':'application/gzip'});response.raise_for_status()
                receipt=response.json()
            with LOCK:
                item['status']='completed';item['accelerated_result']=True
                lb.save(ROOT/'rescue/results'/f'{ident}.json',{'result':r,'receipt':receipt,'received_at':lb.now(),'cpu_only':True,'cpus_per_match':1})
                ERRORS.pop(ident,None)
            return self.send({'ok':True})
        d=json.loads(raw);worker=d.get('worker','unknown')
        with LOCK:
            WORKERS[worker]=time.time()
            if self.path=='/claim':
                # During initial recipe preparation, newly ready selection jobs can start immediately.
                pending=[(i,j) for i,j in JOBS.items() if j['status']=='pending' and (j['priority']==0 or i in CURRENT)]
                pending.sort(key=lambda x:(x[1]['priority'],x[0]))
                for ident,item in pending:
                    if Path(item['result_path']).exists():item['status']='completed';continue
                    item.update(status='running',worker=worker,heartbeat=time.time(),attempts=item['attempts']+1)
                    lb.save(ROOT/'rescue/claims'/f'{ident}.json',{'worker':worker,'at':lb.now(),'attempt':item['attempts']})
                    return self.send({'job':item['job']})
                return self.send({'job':None,'finished':FINISHED})
            if self.path=='/heartbeat':
                item=JOBS.get(d['job'])
                if item and item.get('worker')==worker:item['heartbeat']=time.time()
                return self.send({'ok':True})
            if self.path=='/error':
                item=JOBS[d['job']];item['status']='pending' if item['attempts']<2 else 'failed';ERRORS[d['job']]=d
                return self.send({'ok':True})
        self.send({},404)
    def log_message(self,*args):pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--token-file',required=True);a=p.parse_args();TOKEN=Path(a.token_file).read_text().strip()
    (ROOT/'rescue').mkdir(exist_ok=True)
    with (ROOT/'rescue/coordinator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        threading.Thread(target=refresh,daemon=True).start()
        print(lb.now(),'CPU acceleration rescue coordinator',socket.gethostname(),8004,flush=True)
        ThreadingHTTPServer(('0.0.0.0',8004),Handler).serve_forever()
