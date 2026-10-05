"""Shared worker fleet: drain existing queued matches, then compare iterative representatives."""
from pathlib import Path
import argparse,json,os,signal,socket,subprocess,sys,threading,time,traceback
import httpx
import worker
URLS=['http://host_a.example.org:'+str(p) for p in [8006,8001,8002,8003]]

def loop(index,tokenfile,single_job=False):
    from cpu_acceleration import enable
    enable(index)
    token=Path(tokenfile).read_text().strip();host=socket.gethostname();ident=f'{host}-{os.getpid()}-{index}'
    with httpx.Client(headers={'Authorization':'Bearer '+token,'X-Match-Progress':'simulation-v1','X-Match-CPU-Budget':os.environ.get('MATCH_CPU_BUDGET','1')},timeout=httpx.Timeout(180,connect=15)) as client:
        while True:
            if retiring(index):return 75
            job=None;all_finished=True
            for url in URLS:
                try:
                    response=client.post(url+'/claim',json={'worker':ident,'host':host,'budget':int(os.environ.get('MATCH_CPU_BUDGET','1'))});response.raise_for_status();reply=response.json()
                    if not reply.get('finished'):all_finished=False
                    if reply.get('job'):job=reply['job'];break
                except (httpx.HTTPError,ValueError):all_finished=False
            if not job:
                if all_finished:return 75
                time.sleep(15);continue
            from match_progress import MatchProgress
            progress=MatchProgress(job)
            try:client.post(url+'/heartbeat',json={'worker':ident,'host':host,'job':job['id'],'progress':progress.snapshot()}).raise_for_status()
            except httpx.HTTPError:pass
            stop=threading.Event()
            def heartbeat():
                while not stop.wait(10):
                    try:client.post(url+'/heartbeat',json={'worker':ident,'host':host,'job':job['id'],'progress':progress.snapshot()})
                    except httpx.HTTPError:pass
            thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
            try:
                with progress:
                    if url.endswith(':8006'):
                        import selection_worker
                        payload=selection_worker.play(job)
                    else:payload=worker.play(job)
                for attempt in range(3):
                    try:
                        response=client.post(url+'/result',content=payload,headers={'Content-Type':'application/gzip'});response.raise_for_status();break
                    except httpx.HTTPError:
                        if attempt==2:raise
                        time.sleep(20)
            except Exception as exc:
                traceback.print_exc()
                try:client.post(url+'/error',json={'worker':ident,'host':host,'job':job['id'],'error':str(exc),'type':type(exc).__name__})
                except httpx.HTTPError:pass
            finally:stop.set();thread.join(timeout=2)
            if single_job:return 0

def retiring(index):
    """Drain selected slots between matches before reallocating their cores."""
    path=Path(__file__).with_name('retire-slots.json')
    try:requested=index in json.loads(path.read_text())
    except FileNotFoundError:return False
    if requested:
        directory=path.with_name('retired-slots');directory.mkdir(exist_ok=True)
        (directory/str(index)).write_text(json.dumps({'pid':os.getpid(),'at':time.time()}))
    return requested

def supervise(workers,tokenfile):
    """Recycle after each match; a child crash must not kill sibling matches."""
    def start(index):
        return subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),
                                 '--slot-index',str(index),'--token-file',tokenfile])
    children={i:start(i) for i in range(workers)};failures={i:0 for i in children};disabled=0
    try:
        while children:
            for index,child in list(children.items()):
                code=child.poll()
                if code is None:continue
                if code==75:
                    del children[index];continue
                failures[index]=0 if code==0 else failures[index]+1
                if failures[index]>=3:
                    print('SLOT DISABLED after three consecutive child failures',index,code,flush=True)
                    del children[index];disabled+=1;continue
                if code!=0:print('Restarting failed slot',index,'exit',code,flush=True)
                children[index]=start(index)
            if children:time.sleep(2)
    finally:
        for child in children.values():
            if child.poll() is None:child.terminate()
    return 1 if disabled else 0

if __name__=='__main__':
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--workers',type=int);mode.add_argument('--slot-index',type=int);p.add_argument('--token-file',required=True);args=p.parse_args()
    if args.slot_index is not None:
        if retiring(args.slot_index):sys.exit(75)
        sys.exit(loop(args.slot_index,args.token_file,single_job=True))
    def interrupted(*_):raise SystemExit(143)
    signal.signal(signal.SIGTERM,interrupted)
    print('FLEET',socket.gethostname(),'workers',args.workers,'PID',os.getpid(),flush=True)
    sys.exit(supervise(args.workers,args.token_file))
