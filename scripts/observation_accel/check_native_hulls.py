"""Bitwise triangle/hull support queries, including mesh/primitive pairs."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import mjarena.envs
mjarena.envs.__path__.insert(0,str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
import numpy as np
from mjarena.envs import surface_distance as ref
from mjarena.envs.observation_accel import _surface as fast
from validate import exact
rng=np.random.default_rng(895243)
for i in range(1200):
    n=[1,3,4,17,64,129][i%6]
    a=rng.normal(size=(n,3));b=rng.normal(size=(3+i%7,3))+rng.normal(size=3)*3
    if i%7==0:a[:,2]=0.
    if i%11==0:a[:]=a[0]
    if i%13==0:a[:]=-0.
    if i%17==0:a=a[::-1]
    if i%19==0:a=np.asfortranarray(a)
    sa,fa=ref._triangle_support(a),fast._triangle_support(a)
    sb,fb=ref._triangle_support(b),fast._triangle_support(b)
    if i%3==0:
        kind=[2,3,4,5,6][i%5];size=rng.uniform(.01,2,3);pos=rng.normal(size=3);rotation=np.eye(3)
        sb=ref.primitive_support(kind,size,pos,rotation);fb=fast.primitive_support(kind,size,pos,rotation)
    direction=rng.normal(size=3)
    if i%23==0:direction[:]=0.
    exact(ref.convex_distance(sa,sb,direction),fast.convex_distance(fa,fb,direction),f'hull-{i}')
    if i%200==0:print('hull cases',i,flush=True)
print('PASS: 1200 exact hull/triangle/primitive queries, including degenerate and strided layouts',flush=True)
