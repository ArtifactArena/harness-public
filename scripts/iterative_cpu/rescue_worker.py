"""Shared worker fleet: drain existing queued matches, then compare iterative representatives."""
from pathlib import Path
import argparse,concurrent.futures,json,os,socket,threading,time,traceback
import httpx
import worker
URLS=['http://host_a.example.org:8004']

def loop(index,tokenfile):
    from cpu_acceleration import enable
    enable(index)
    token=Path(tokenfile).read_text().strip();host=socket.gethostname();ident=f'{host}-{os.getpid()}-{index}'
    with httpx.Client(headers={'Authorization':'Bearer '+token},timeout=httpx.Timeout(180,connect=15)) as client:
        while True:
            job=None;all_finished=True
            for url in URLS:
                try:
                    response=client.post(url+'/claim',json={'worker':ident,'host':host});response.raise_for_status();reply=response.json()
                    if not reply.get('finished'):all_finished=False
                    if reply.get('job'):job=reply['job'];break
                except (httpx.HTTPError,ValueError):all_finished=False
            if not job:
                if all_finished:return
                # Older generation coordinators may remain unfinished after a zero-bot run.
                # Release this CPU allocation when both requested leaderboard outputs are complete.
                try:
                    state=client.get(URLS[-1]+'/status');state.raise_for_status();state=state.json()
                    if state.get('status')=='completed' and all(r.get('complete') for r in state.get('sampling',[])):return
                except (httpx.HTTPError,ValueError):pass
                time.sleep(15);continue
            stop=threading.Event()
            def heartbeat():
                while not stop.wait(45):
                    try:client.post(url+'/heartbeat',json={'worker':ident,'host':host,'job':job['id']})
                    except httpx.HTTPError:pass
            thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
            try:
                payload=worker.play(job)
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

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,required=True);p.add_argument('--token-file',required=True);args=p.parse_args()
    print('FLEET',socket.gethostname(),'workers',args.workers,'PID',os.getpid(),flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in [pool.submit(loop,i,args.token_file) for i in range(args.workers)]:future.result()
