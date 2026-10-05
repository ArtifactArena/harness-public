"""Profile an isolated prefix of the requested Fable/Astra exhibition."""
import cProfile, json, os, pstats, sys, time
from pathlib import Path
REPO=Path(os.environ['MATCH_OPT_REPO'])
sys.path.insert(0,str(REPO));os.chdir(REPO)
import mjarena.core.unified_builder
from mjarena.envs.observation_accel import install

if os.environ.get("USE_OBS_ACCEL","1")=="1":install()
if os.environ.get("MATCH_ACCEL_LIBRARY"):
 from mjarena.envs.match_accel import install as install_match
 install_match(os.environ["MATCH_ACCEL_LIBRARY"],int(os.environ.get("MATCH_ACCEL_THREADS","1")),interval=os.environ.get("MATCH_ACCEL_INTERVAL")=="1")
from mjarena.envs.observation_accel._details import DetailedObservations
if int(os.environ.get('SURFACE_WORKERS','0')):
 raise ValueError('This benchmark requires one CPU core per match and no surface workers')
from mjarena.runner.episode import Match
import mujoco
out=Path(os.environ['MATCH_OPT_OUT']);out.mkdir(parents=True,exist_ok=True)
prelude=Path('<scratch>/runs/sh250-20260919/control/exhibition-fable-astra.py').read_text().split("pair = OUT")[0]
prelude=prelude.replace("REPO = LOCAL / 'harness-3c03d494'",'REPO = Path(os.environ["MATCH_OPT_REPO"])').replace("OUT = LOCAL / 'exhibitions' / NAME",'OUT = Path(os.environ["MATCH_OPT_OUT"])')
exec(compile(prelude,'exhibition-setup','exec'))
from mjarena.tournament.tournament import run_matchup
counts={};elapsed={};lastenv=None
for obj,name in [(mujoco,'mj_step'),(mujoco,'mj_forward'),(DetailedObservations,'capture_contacts'),(DetailedObservations,'snapshot')]:
 if not hasattr(obj,name):continue
 original=getattr(obj,name)
 def wrapper(*args,_fn=original,_name=name,**kw):
  t=time.perf_counter()
  try:return _fn(*args,**kw)
  finally:elapsed[_name]=elapsed.get(_name,0)+time.perf_counter()-t;counts[_name]=counts.get(_name,0)+1
 setattr(obj,name,wrapper)
class Finished(BaseException):pass
steps=0;original_step=Match.single_match_step
limit=int(os.environ.get('PROFILE_STEPS','150'))
def step(self,*a,**kw):
 global steps,lastenv
 lastenv=self.env
 result=original_step(self,*a,**kw);steps+=1
 if steps%100==0:print('PROGRESS',steps,time.perf_counter()-start,flush=True)
 if steps>=limit:raise Finished()
 return result
Match.single_match_step=step
profile=cProfile.Profile();start=time.perf_counter();cpu_start=time.process_time()
if os.environ.get("CPROFILE","0")=="1":profile.enable()
try:
 result=run_matchup(bot_a=list(bots.values())[0],bot_b=list(bots.values())[1],arena_xml=REPO/cfg.arena_xml,out_dir=out/'match',seeds=[42],match_time=300,contact_fidelity=cfg.contact_fidelity,score_function=cfg.score_function,inactivity_timeout_seconds=cfg.inactivity_timeout,inactivity_min_displacement=cfg.inactivity_min_displacement,size_limits=cfg.size_limits,spawn_seed=42)
 (out/"match_result.json").write_text(json.dumps([m.to_dict() for m in result.matches],indent=2))
 from dataclasses import asdict
 (out/"game_records.json").write_text(json.dumps([asdict(r) for r in result._ds_matchup.game_records],default=lambda x:x.tolist() if hasattr(x,"tolist") else str(x)))
except Finished:pass
finally:
 profile.disable()
 if os.environ.get('CPROFILE','0')=='1':
  profile.dump_stats(str(out/'profile.pstats'))
  with (out/'profile.txt').open('w') as f:pstats.Stats(profile,stream=f).sort_stats('cumtime').print_stats(65)
 thread_affinities={};children=set()
 for task in Path('/proc/self/task').iterdir():
  try:
   thread_affinities[task.name]=sorted(os.sched_getaffinity(int(task.name)))
   children.update((task/'children').read_text().split())
  except (ProcessLookupError,FileNotFoundError):pass
 report={'steps':steps,'wall':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu_start,'counts':counts,'seconds':elapsed,'mujoco':mujoco.__version__,'affinity':list(os.sched_getaffinity(0)),'thread_affinities':thread_affinities,'child_processes':sorted(children)}
 if lastenv:
  mujoco.mj_saveModel(lastenv.model,str(out/'model.mjb'),None)
  import numpy as np
  spec=mujoco.mjtState.mjSTATE_INTEGRATION
  state=np.zeros(mujoco.mj_stateSize(lastenv.model,spec));mujoco.mj_getState(lastenv.model,lastenv.data,state,spec)
  np.savez(out/'state.npz',state=state,spec=int(spec))
 (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
