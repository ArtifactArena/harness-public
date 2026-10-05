import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mjarena.envs
mjarena.envs.__path__.insert(0,str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
from mjarena.envs.observation_accel import _surface as fast
from mjarena.envs import surface_distance as ref
from validate import exact
import numpy as np
rng=np.random.default_rng(3194)
for batch in range(30):
 supports=[];directions=[]
 for i in range(20):
  sizes=rng.uniform(.01,1,(2,3));positions=rng.normal(size=(2,3));ra=np.linalg.qr(rng.normal(size=(3,3)))[0];rb=np.linalg.qr(rng.normal(size=(3,3)))[0]
  ka,kb=(2+i%5,2+(i//5)%5)
  supports.append((ref.primitive_support(ka,sizes[0],positions[0],ra),ref.primitive_support(kb,sizes[1],positions[1],rb)))
  directions.append(positions[1]-positions[0])
 original=[ref.convex_distance(a,b,d) for (a,b),d in zip(supports,directions)]
 exact(original,fast.convex_distance_many(supports,directions))
print('600 batched primitive queries bitwise equal')
