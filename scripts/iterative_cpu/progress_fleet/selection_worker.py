"""Remote CPU workers claim independent durable jobs from the coordinator."""
from pathlib import Path
import argparse,concurrent.futures,gzip,io,json,os,socket,sys,time,traceback
import httpx
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'harness'))

def play(job):
 from mjarena.core.build_config import ObservationConfig
 from mjarena.dspy_core import create_match_runner
 from mjarena.envs.sumo import compose_sumo_model
 from mjarena.policy_spec import PolicySpec
 root=BASE/'tournament/worker_matches'/job['id'];root.mkdir(parents=True,exist_ok=True)
 h=BASE/'harness';os.chdir(h);started=time.monotonic()
 for color in ('red','blue'):(root/f'{color}.xml').write_text(job[color]['xml'])
 compose_sumo_model(env_xml=str(h/'mjarena/assets/sumo_ring_env_cinematic_3d.xml'),robot_red_xml=str(root/'red.xml'),robot_blue_xml=str(root/'blue.xml'),out_path=str(root/'composed.xml'),randomize_spawn_3d=True,spawn_seed=job['seed'],use_material_palette=True)
 r=job['red'];b=job['blue']
 runner=create_match_runner(composed_xml=root/'composed.xml',blue_policy_spec=PolicySpec.controller_code(b['code'],b['actuators']),out_dir=root,match_time=job.get('seconds',300),quiet=True,save_video_seeds=0,inactivity_timeout_seconds=10.0,inactivity_min_displacement=.5,inactivity_exempt_prefixes=[],size_limits=(2.44,2.44,3.05),max_obs_lookback=20,max_action_lookback=20,observation_config=ObservationConfig())
 record=runner.run_with_policy_spec(PolicySpec.controller_code(r['code'],r['actuators']),seed=job['seed'])
 result={'id':job['id'],'kind':job['kind'],'candidate_id':job['candidate_id'],'opponent_id':job['opponent_id'],'candidate_side':job['side'],'seed':job['seed'],'winner':record.winner,'outcome':'win' if record.winner==job['side'] else 'loss' if record.winner in ('red','blue') else 'draw','termination_reason':record.termination_reason,'duration_seconds':record.num_steps*record.control_dt,'controller_errors':record.controller_errors,'physics_unstable':record.physics_unstable,'forfeit':False,'wall_seconds':time.monotonic()-started,'worker_host':socket.getfqdn()}
 payload={'result':result,'composed_xml':'','match_data':{}}
 compressed=gzip.compress(json.dumps(payload,allow_nan=False,separators=(',',':')).encode(),compresslevel=1)
 (root/'result.json').write_text(json.dumps(result))
 return compressed

def loop(index,url,tokenfile):
 token=Path(tokenfile).read_text().strip();headers={'Authorization':'Bearer '+token};ident=f'{socket.gethostname()}-{os.getpid()}-{index}'
 with httpx.Client(headers=headers,timeout=httpx.Timeout(180,connect=15)) as client:
  while True:
   try:
    reply=client.post(url+'/claim',json={'worker':ident}).json()
    if reply.get('finished'):return
    job=reply.get('job')
    if not job:time.sleep(15);continue
   except (httpx.HTTPError,ValueError):time.sleep(30);continue
   # Heartbeats keep long simulations leased without relying on a laptop.
   import threading
   stop=threading.Event()
   def heartbeat():
    while not stop.wait(45):
     try:client.post(url+'/heartbeat',json={'job':job['id'],'worker':ident})
     except httpx.HTTPError:pass
   thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
   try:
    payload=play(job)
    for attempt in range(3):
     try:
      response=client.post(url+'/result',content=payload,headers={'Content-Type':'application/gzip'});response.raise_for_status();break
     except httpx.HTTPError:
      if attempt==2:raise
      time.sleep(20)
   except Exception as exc:
    traceback.print_exc()
    try:client.post(url+'/error',json={'job':job['id'],'worker':ident,'error':str(exc),'type':type(exc).__name__})
    except httpx.HTTPError:pass
   finally:stop.set();thread.join(timeout=2)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workers',type=int,required=True);p.add_argument('--url',required=True);p.add_argument('--token-file',required=True);a=p.parse_args()
 with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
  for future in [pool.submit(loop,i,a.url,a.token_file) for i in range(a.workers)]:future.result()
