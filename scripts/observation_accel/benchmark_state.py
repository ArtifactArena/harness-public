"""Interleave both implementations on a captured tournament state, checking every bit."""
import os
from pathlib import Path
import pickle
import statistics
import sys
import time
from types import SimpleNamespace
import numpy as np
import mujoco
sys.path.insert(0, str(Path.cwd()))
import mjarena.envs
mjarena.envs.__path__.insert(0, str(Path(os.environ['OBS_OVERLAY']) / 'mjarena/envs'))
from mjarena.envs.detailed_observations import DetailedObservations as Reference
from mjarena.envs.observation_accel import _details
from mjarena.envs.sumo import _body_belongs_to_contender
from validate import exact
import json

path = Path(sys.argv[1])
frozen = pickle.loads(path.with_suffix('.state').read_bytes())
model = mujoco.MjModel.from_binary_path(str(path.with_suffix('.mjb')))
data = mujoco.MjData(model)
mujoco.mj_setState(model, data, frozen['state'], mujoco.mjtState.mjSTATE_INTEGRATION)
mujoco.mj_forward(model, data)
env = SimpleNamespace(**frozen['attributes'], model=model, data=data,
                      red_contender=SimpleNamespace(prefix=frozen['prefixes'][0]),
                      blue_contender=SimpleNamespace(prefix=frozen['prefixes'][1]),
                      _body_belongs_to_contender=lambda i,p:_body_belongs_to_contender(model,i,p))
reference, candidate = Reference(env), _details.DetailedObservations(env)
for detail in [reference, candidate]:
    detail.impulses = frozen['impulses']
    detail.interval_seconds = frozen['interval_seconds']
    detail.capture_contacts()
timings = [[], []]
for repeat in range(9):
    results = []
    for index, detail in enumerate([reference, candidate]):
        detail.cached = None
        if index: _details._QUATERNIONS.clear()
        start = time.perf_counter()
        results.append([detail.for_robot(prefix) for prefix in frozen['prefixes']])
        timings[index].append(time.perf_counter()-start)
    exact(*results)
report = {'reference_seconds':statistics.median(timings[0][1:]),
          'accelerated_seconds':statistics.median(timings[1][1:]),
          'bitwise_equal':True, 'repeats':len(timings[0]), 'overlay':os.environ['OBS_OVERLAY']}
report['speedup'] = report['reference_seconds']/report['accelerated_seconds']
print(json.dumps(report), flush=True)
