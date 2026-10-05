import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,str(Path(__file__).resolve().parent))
import mjarena.envs
mjarena.envs.__path__.insert(0,str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
from mjarena.envs.observation_accel import _surface as fast
from mjarena.envs.observation_accel._helpers import simplex_weights
from mjarena.envs import surface_distance as ref
from validate import exact
import numpy as np
rng=np.random.default_rng(539127)
for i in range(10000):
 n=1+i%3; tail=rng.normal(size=n)
 if i%3==0:tail*=1e-100
 if i%7==0:tail[i%n]=-0.
 if i%11==0:tail=tail[::-1]
 weights=np.r_[1-tail.sum(),tail]
 expected=None if weights.min() < -1e-9 else np.maximum(weights,0)/np.maximum(weights,0).sum()
 exact(expected,simplex_weights(tail))
 size=rng.uniform(.01,2,3);pos=rng.normal(size=3);rot=np.linalg.qr(rng.normal(size=(3,3)))[0]
 if i%3==0:rot=np.asfortranarray(rot)
 if i%11==0:rot=rot[::-1]
 if i%17==0:rot=rot.astype(np.float32)
 direction=rng.normal(size=3)
 if i%7==0:direction[i%3]=-0.
 if i%13==0:direction*=1e-100
 if i%19==0:direction=direction[::-1]
 a=ref.primitive_support(2+i%5,size,pos,rot);b=fast.primitive_support(2+i%5,size,pos,rot)
 exact(a(direction),b(direction))
print('PASS: 10000 native support / barycentric reduction cases; C/F/strided layouts and signed zero')
