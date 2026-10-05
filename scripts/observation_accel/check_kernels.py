"""Bitwise regression corpus for the compiled numerical fast paths."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import mjarena.envs
mjarena.envs.__path__.insert(0, str(Path(os.environ['OBS_OVERLAY']) / 'mjarena/envs'))
import numpy as np
from copy import deepcopy
from validate import exact
from mjarena.envs.observation_accel._helpers import norm, cross, clone, simplex_lstsq
from mjarena.envs import surface_distance as ref
from mjarena.envs.observation_accel import _surface as fast

rng = np.random.default_rng(94192)
for i in range(2000):
    a, b = rng.normal(size=(2, 3)) * 10. ** rng.uniform(-100, 100)
    if i % 5 == 0: a[i % 3] = -0.
    exact(np.cross(a, b), cross(a, b))
    exact(np.linalg.norm(a), norm(a))
    a = rng.normal(size=(3, 1 + i % 3))
    if i % 3 == 0: a[:, -1] = a[:, 0]
    if i % 7 == 0: a *= 0
    if i % 11 == 0: a *= 1e-100
    exact(np.linalg.lstsq(a, b, rcond=None)[0], simplex_lstsq(a, b))

for i in range(300):
    points = [(rng.normal(size=3), rng.normal(size=3), rng.normal(size=3))
              for _ in range(1 + i % 4)]
    exact(ref._closest_simplex(points), fast._closest_simplex(points))

for i in range(200):
    kinds = [2, 3, 4, 5, 6]
    ka, kb = kinds[i % 5], kinds[(i // 5) % 5]
    sizes = rng.uniform(.01, 1, size=(2, 3))
    positions = rng.normal(size=(2, 3))
    rotations = [np.linalg.qr(rng.normal(size=(3, 3)))[0] for _ in range(2)]
    reference = [ref.primitive_support(k, s, p, r)
                 for k, s, p, r in zip([ka,kb], sizes, positions, rotations)]
    candidate = [fast.primitive_support(k, s, p, r)
                 for k, s, p, r in zip([ka,kb], sizes, positions, rotations)]
    exact(ref.convex_distance(*reference, positions[1]-positions[0]),
          fast.convex_distance(*candidate, positions[1]-positions[0]))

a = np.arange(20.).reshape(4, 5).T
value = {'left': a, 'right': a, 'list': [a, 3., -0., 'body']}
value['cycle'] = value
c = clone(value)
assert c is c['cycle'] and c['left'] is c['right'] is c['list'][0]
assert not np.shares_memory(a, c['left'])
del value['cycle']; del c['cycle']
exact(deepcopy(value), c)
print('PASS: 2000 cross/norm/lstsq cases, 300 simplex cases, 200 convex-distance cases, copy isolation/aliasing', flush=True)
