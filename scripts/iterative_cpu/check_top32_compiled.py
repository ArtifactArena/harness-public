"""Compare observations at an identical captured state; all numerical values exact."""
import argparse,cProfile,json,os,pstats,sys,time
from pathlib import Path
from types import SimpleNamespace
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('capture',type=Path);p.add_argument('--tick',type=int,default=500);p.add_argument('--cpu',type=int,required=True);args=p.parse_args()
root=args.root.resolve();capture=args.capture.resolve();os.sched_setaffinity(0,{args.cpu})
os.environ['CUDA_VISIBLE_DEVICES']=''
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
sys.path.insert(0,str(root/'candidate-top32'));os.chdir(root/'candidate-top32')
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

from mjarena.envs.match_accel import install as native
native(root/'native-release/arena_onecore_v3.so',threads=1,interval=True)
from mjarena.envs.observation_accel import _details, _surface

import importlib.util,types
package=types.ModuleType('baseline_accel');package.__path__=[str(root/'candidate/mjarena/envs/observation_accel')];sys.modules['baseline_accel']=package
path=next((root/'candidate/mjarena/envs/observation_accel').glob('_details*.so'))
spec=importlib.util.spec_from_file_location('baseline_accel._details',path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
Old=module.DetailedObservations;Old.forward_observation=Fast.forward_observation
old,new=Old(env),Fast(env)
for obj in (old,new):obj.capture_contacts()
a=[old.for_robot(c) for c in ['red_','blue_']];b=[new.for_robot(c) for c in ['red_','blue_']];exact(a,b)
rows=[]
for i in range(6):
    row={}
    for label,obj in ([('v1',old),('top32',new)] if i%2==0 else [('top32',new),('v1',old)]):
        obj.cached=None;t=time.perf_counter();[obj.for_robot(c) for c in ['red_','blue_']];row[label]=time.perf_counter()-t
    rows.append(row)
report=dict(exact=True,timings=rows,speedup=float(np.median([r['v1'] for r in rows])/np.median([r['top32'] for r in rows])))
(capture/'top32-final-snapshot.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
