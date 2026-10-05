"""Exact primitive GJK checks: ties, degeneracy, repeated caches, and layouts."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import mjarena.envs
mjarena.envs.__path__.insert(0,str(Path(os.environ['OBS_OVERLAY'])/'mjarena/envs'))
import numpy as np
from mjarena.envs import surface_distance as ref
from mjarena.envs.observation_accel import _surface as fast
from validate import exact
rng=np.random.default_rng(621792)
kinds=[2,3,4,5,6]
for i in range(2500):
    scale=10.**rng.uniform(-6,3)
    sizes=rng.uniform(.001,1,size=(2,3))*scale
    positions=rng.normal(size=(2,3))*scale
    rotations=[np.linalg.qr(rng.normal(size=(3,3)))[0] for _ in range(2)]
    if i%3==0:rotations=[np.eye(3),np.eye(3)]
    if i%7==0:positions[1]=positions[0]
    if i%11==0:positions[1]=positions[0]+[sizes[0,0]+sizes[1,0],0,0]
    if i%13==0:sizes[:,2]=0.
    if i%17==0:positions[0,:]=-0.
    ka,kb=kinds[i%5],kinds[(i//5)%5]
    rs=[ref.primitive_support(k,s,p,r) for k,s,p,r in zip([ka,kb],sizes,positions,rotations)]
    fs=[fast.primitive_support(k,s,p,r) for k,s,p,r in zip([ka,kb],sizes,positions,rotations)]
    directions=[positions[1]-positions[0],np.zeros(3),rng.normal(size=3)]
    if i%19==0:directions.append(directions[0][::-1])
    for direction in directions:
        exact(ref.convex_distance(*rs,direction),fast.convex_distance(*fs,direction),f'case-{i}')
    if i%250==0:print('native GJK cases',i,flush=True)
print('PASS: 2500 shape pairs, >7500 exact queries including degeneracy and cache reuse',flush=True)
