"""Isolated real-controller CPU benchmark; never submits tournament results."""
import argparse, cProfile, dataclasses, hashlib, json, os, pstats, random, struct, sys, time
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--mode',choices=['reference','observations','native'],required=True)
p.add_argument('--a',required=True);p.add_argument('--b',required=True)
p.add_argument('--side',default='blue');p.add_argument('--seed',type=int,default=7101)
p.add_argument('--steps',type=int,default=300);p.add_argument('--cpu',type=int,required=True)
p.add_argument('--candidate',default='candidate');p.add_argument('--label',required=True);p.add_argument('--profile',action='store_true')
args=p.parse_args();root=args.root.resolve();out=root/'results'/args.label;out.mkdir(parents=True,exist_ok=True)
os.sched_setaffinity(0,{args.cpu})
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
os.environ['CUDA_VISIBLE_DEVICES']=''
h=root/('baseline' if args.mode=='reference' else args.candidate);sys.path.insert(0,str(h));os.chdir(h)
import numpy as np
import mujoco
random.seed(7101);np.random.seed(7101)
if args.mode=='observations':
    from mjarena.envs.observation_accel import install
    install()
elif args.mode=='native':
    from mjarena.envs.match_accel import install
    install(root/'native-release/arena_onecore_v3.so',threads=1,interval=True)
from mjarena.core.build_config import ObservationConfig
from mjarena.dspy_core import create_match_runner
from mjarena.envs.sumo import compose_sumo_model,SumoEnv
from mjarena.policy_spec import PolicySpec
from mjarena.runner.episode import Match
from mjarena.agents.runtime import BotRuntime
from mjarena.envs.detailed_observations import DetailedObservations

def digest(value):
    hasher=hashlib.sha256()
    def add(v):
        if isinstance(v,np.ndarray):hasher.update(str((v.dtype.str,v.shape)).encode());hasher.update(v.tobytes())
        elif isinstance(v,np.generic):hasher.update(v.dtype.str.encode());hasher.update(v.tobytes())
        elif dataclasses.is_dataclass(v):add(vars(v))
        elif isinstance(v,dict):
            for k,x in v.items():add(k);add(x)
        elif isinstance(v,(list,tuple)):
            hasher.update(str(len(v)).encode())
            for x in v:add(x)
        elif isinstance(v,float):hasher.update(struct.pack('d',v))
        else:hasher.update(repr(v).encode())
        hasher.update(b'\0')
    add(value);return hasher.hexdigest()

timers={};counts={};events=[];ticks=0;lastenv=None;max_ncon=0;cpu_start=None;start=None
def timed(owner,name):
    original=getattr(owner,name)
    def wrapper(*a,**kw):
        begin=time.perf_counter()
        try:return original(*a,**kw)
        finally:
            timers[name]=timers.get(name,0)+time.perf_counter()-begin;counts[name]=counts.get(name,0)+1
    setattr(owner,name,wrapper)
for owner,name in [(mujoco,'mj_step'),(mujoco,'mj_forward'),(BotRuntime,'act')]:timed(owner,name)
if args.mode=='reference':
    for name in ['capture_contacts','snapshot']:timed(DetailedObservations,name)
original_obs=Match.build_bot_observation
def observe(self,*a,**kw):
    begin=time.perf_counter();result=original_obs(self,*a,**kw)
    timers['build_observation']=timers.get('build_observation',0)+time.perf_counter()-begin
    events.append(['observation',digest(result)]);return result
Match.build_bot_observation=observe
class Finished(BaseException):pass
original_step=SumoEnv.step
def step(self,action):
    global ticks,lastenv,max_ncon
    lastenv=self
    begin=time.perf_counter();result=original_step(self,action)
    timers['env_step']=timers.get('env_step',0)+time.perf_counter()-begin
    ticks+=1;max_ncon=max(max_ncon,int(self.data.ncon))
    spec=mujoco.mjtState.mjSTATE_INTEGRATION
    state=np.empty(mujoco.mj_stateSize(self.model,spec));mujoco.mj_getState(self.model,self.data,state,spec)
    contacts=[getattr(self.data.contact,n) for n in ['dist','pos','frame','geom1','geom2','efc_address']]
    events.append(['step',digest((action,state,self.data.qacc,self.data.qfrc_constraint,self.data.efc_force,self.data.sensordata,contacts,result))])
    if ticks in {100,300,args.steps}:
        mujoco.mj_saveModel(self.model,str(out/f'model-{ticks}.mjb'),None)
        np.savez(out/f'state-{ticks}.npz',state=state,spec=int(spec))
    if ticks%100==0:print(json.dumps({'ticks':ticks,'wall':time.perf_counter()-start,'ncon':int(self.data.ncon),'timers':timers}),flush=True)
    if ticks>=args.steps:raise Finished()
    return result
SumoEnv.step=step

recipes={ident:json.loads((root/'selected'/ident/'recipe.json').read_text()) for ident in [args.a,args.b]}
red,blue=(args.a,args.b) if args.side=='red' else (args.b,args.a)
for side,ident in [('red',red),('blue',blue)]:(out/f'{side}.xml').write_text(recipes[ident]['xml'])
compose_sumo_model(env_xml=str(h/'mjarena/assets/sumo_ring_env_cinematic_3d.xml'),robot_red_xml=str(out/'red.xml'),robot_blue_xml=str(out/'blue.xml'),out_path=str(out/'composed.xml'),randomize_spawn_3d=True,spawn_seed=args.seed,use_material_palette=True)
def spec(ident):return PolicySpec.controller_code(recipes[ident]['code'],recipes[ident]['actuators'])
runner=create_match_runner(composed_xml=out/'composed.xml',blue_policy_spec=spec(blue),out_dir=out,match_time=300,quiet=True,save_video_seeds=0,inactivity_timeout_seconds=10.0,inactivity_min_displacement=.5,inactivity_exempt_prefixes=[],size_limits=(2.44,2.44,3.05),max_obs_lookback=20,max_action_lookback=20,observation_config=ObservationConfig())
profile=cProfile.Profile();start=time.perf_counter();cpu_start=time.process_time();finished=False
if args.profile:profile.enable()
try:
    result=runner.run_with_policy_spec(spec(red),seed=args.seed);finished=True
    events.append(['result',digest(result)])
except Finished:pass
finally:
    profile.disable()
    if args.profile:
        profile.dump_stats(str(out/'profile.pstats'))
        with (out/'profile.txt').open('w') as f:pstats.Stats(profile,stream=f).strip_dirs().sort_stats('cumtime').print_stats(45)
    report={'mode':args.mode,'pair':[args.a,args.b],'side':args.side,'seed':args.seed,'steps':ticks,'finished':finished,'wall':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu_start,'timers':timers,'counts':counts,'max_ncon':max_ncon,'events':events,'mujoco':mujoco.__version__,'numpy':np.__version__,'affinity':sorted(os.sched_getaffinity(0)),'gpus_used':0}
    if lastenv:report['model']={n:int(getattr(lastenv.model,n)) for n in ['nq','nv','ngeom','nmesh','nbody','nu']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='events'}),flush=True)
