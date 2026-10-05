import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,str(Path(__file__).resolve().parent))
import mjarena.envs
mjarena.envs.__path__.insert(0,str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
from mjarena.envs.observation_accel._helpers import simplex_lstsq,simplex_lstsq_batch
from validate import exact
import numpy as np
rng=np.random.default_rng(77431)
for i in range(12000):
 n=1+i%3;a=rng.normal(size=(3,n));b=rng.normal(size=3)
 if i%3==0 and n>1:a[:,-1]=a[:,0]+10.**rng.uniform(-300,-8)*a[:,-1]
 if i%7==0:a*=10.**rng.uniform(-200,200)
 if i%11==0:a[:]=0
 if i%13==0:b[i%3]=-0.
 if i%5==0:a=a[::-1];b=b[::-1]
 expected=np.linalg.lstsq(a,b,rcond=None)[0]
 exact(expected,simplex_lstsq(a,b))
 if i%31==0:
  vertices=rng.normal(size=(8,n+1,3));x=simplex_lstsq_batch(vertices)
  for j,v in enumerate(vertices):exact(np.linalg.lstsq((v[1:]-v[0]).T,-v[0],rcond=None)[0],x[j])
print('PASS: 12000 rank-deficient/scaled/strided DGELSD cases and 3104 batched cases')
