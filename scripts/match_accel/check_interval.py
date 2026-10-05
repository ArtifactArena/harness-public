"""Compare native interval accumulation against every reference substep."""
import ctypes,sys,os,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np,mujoco
from mjarena.envs.observation_accel._contacts import capture
from mjarena.envs.match_accel._interval import advance
base=Path('<local>/gpu/sh250-20260919/match-optimization')
m=mujoco.MjModel.from_binary_path(str(base/'profile-contact/model.mjb'));z=np.load(base/'profile-contact/state.npz')
lib=ctypes.CDLL(sys.argv[1]);lib.arena_create.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int];lib.arena_create.restype=ctypes.c_void_p
lib.arena_enable.argtypes=[ctypes.c_int];lib.arena_destroy.argtypes=[ctypes.c_void_p]
observers=[]
for _ in range(2):
 d=mujoco.MjData(m);mujoco.mj_setState(m,d,z['state'],int(z['spec']));mujoco.mj_forward(m,d)
 o=SimpleNamespace(model=m,env=SimpleNamespace(data=d),owners={g:m.geom(g).name.split('_')[0] for g in range(m.ngeom) if m.geom(g).name.startswith(('red_','blue_'))},impulses={},interval_seconds=0.)
 o.capture_contacts=lambda integrate=False,o=o:capture(o,integrate);observers.append(o)
a,b=observers;ctx=lib.arena_create(m._address,b.env.data._address,1);address=ctypes.cast(lib.arena_step,ctypes.c_void_p).value
assert ctx, 'Model is outside the single-core accelerator scope'

def equal(a,b,path=''):
 if isinstance(a,np.ndarray):assert a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes(),path
 elif isinstance(a,dict):
  assert list(a)==list(b),path
  for k in a:equal(a[k],b[k],path+'.'+str(k))
 elif isinstance(a,(list,tuple)):
  assert len(a)==len(b),path
  for i,(x,y) in enumerate(zip(a,b)):equal(x,y,path+f'[{i}]')
 elif isinstance(a,float):assert np.float64(a).tobytes()==np.float64(b).tobytes(),(path,a,b)
 else:assert a==b,(path,a,b)
for k in range(25):
 for o in observers:o.impulses={};o.interval_seconds=0.
 lib.arena_enable(0)
 for _ in range(40):mujoco.mj_step(m,a.env.data);capture(a,True)
 lib.arena_enable(1);advance(b,40,address,ctx)
 for field in ['impulses','interval_seconds','latest_contacts']:equal(getattr(a,field),getattr(b,field),field)
 for field in ['qpos','qvel','qacc','qacc_warmstart','efc_force']:equal(np.asarray(getattr(a.env.data,field)),np.asarray(getattr(b.env.data,field)),field)
lib.arena_enable(0);lib.arena_destroy(ctx)
print(json.dumps({'exact':True,'intervals':25,'physics_steps':1000,'fields':'states, ordered impulses, durations, latest contacts'}),flush=True)
