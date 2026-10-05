"""Compare observations at an identical captured state; all numerical values exact."""
import argparse,cProfile,json,os,pstats,sys,time
from pathlib import Path
from types import SimpleNamespace
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('capture',type=Path);p.add_argument('--tick',type=int,default=500);p.add_argument('--cpu',type=int,required=True);args=p.parse_args()
root=args.root.resolve();capture=args.capture.resolve();os.sched_setaffinity(0,{args.cpu})
os.environ['CUDA_VISIBLE_DEVICES']=''
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
sys.path.insert(0,str(root/'candidate'));os.chdir(root/'candidate')
sys.path.insert(0,str(root/'validation'))
from validate import exact
import numpy as np,mujoco
from mjarena.envs.sumo import SumoEnv
from mjarena.envs.detailed_observations import DetailedObservations as Reference
from mjarena.envs.observation_accel import install
install()
from mjarena.envs.observation_accel._details import DetailedObservations as Fast
model=mujoco.MjModel.from_binary_path(str(capture/f'model-{args.tick}.mjb'));data=mujoco.MjData(model)
with np.load(capture/f'state-{args.tick}.npz',allow_pickle=False) as saved:mujoco.mj_setState(model,data,saved['state'],int(saved['spec']))
mujoco.mj_forward(model,data)
env=SumoEnv.__new__(SumoEnv);env.model=model;env.data=data
env.red_contender=SimpleNamespace(prefix='red_');env.blue_contender=SimpleNamespace(prefix='blue_')
env._collect_contender_geom_ids();env._collect_root_body_ids()
env.t=args.tick;env.max_steps=30000;env.control_timestep=.01;env.apply_n_repeated_actions=1
env._boundary_geom_id=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,'sumo_ring')
env.outside_floor_gid=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,'outside_floor')
gid=env._boundary_geom_id;env._boundary_shape='box' if int(model.geom_type[gid])==int(mujoco.mjtGeom.mjGEOM_BOX) else 'cylinder'
env.ring_radius=float(model.geom_size[gid,0]);env.ring_half_extents=np.array(model.geom_size[gid,:2] if env._boundary_shape=='box' else [env.ring_radius]*2,dtype=np.float32)
env.ring_top_z=float(model.geom_pos[gid,2]+model.geom_size[gid,2 if env._boundary_shape=='box' else 1])
a,b=Reference(env),Fast(env)
a.capture_contacts();b.capture_contacts();exact(a.latest_contacts,b.latest_contacts)
stats=cProfile.Profile();stats.enable();begin=time.perf_counter();ra=[a.for_robot(c) for c in ['red_','blue_']];ref_seconds=time.perf_counter()-begin;stats.disable()
with (capture/'snapshot-profile.txt').open('w') as f:pstats.Stats(stats,stream=f).strip_dirs().sort_stats('cumtime').print_stats(35)
begin=time.perf_counter();rb=[b.for_robot(c) for c in ['red_','blue_']];fast_seconds=time.perf_counter()-begin
exact(ra,rb)
times=[]
for i in range(4):
    row={}
    for label,obj in ([('reference',a),('accelerated',b)] if i%2==0 else [('accelerated',b),('reference',a)]):
        obj.cached=None;begin=time.perf_counter();[obj.for_robot(c) for c in ['red_','blue_']];row[label]=time.perf_counter()-begin
    times.append(row)
report={'exact':True,'tick':args.tick,'pair_capture':str(capture),'timings':times,'reference_median':float(np.median([x['reference'] for x in times])),'accelerated_median':float(np.median([x['accelerated'] for x in times])),'profiled_reference_seconds':ref_seconds,'initial_accelerated_seconds':fast_seconds,'gpus_used':0}
report['speedup']=report['reference_median']/report['accelerated_median']
(capture/'snapshot-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
