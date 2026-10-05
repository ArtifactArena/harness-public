"""Exact recursive comparisons and paired real-controller trajectory captures."""
import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import pickle
import struct
import sys
import time

import numpy as np

sys.path.insert(0, str(Path.cwd()))
import mjarena.core.unified_builder
import mjarena.envs

overlay = os.environ.get('OBS_OVERLAY')
if overlay:
    mjarena.envs.__path__.insert(0, str(Path(overlay) / 'mjarena/envs'))

def exact(a, b, path='root'):
    assert type(a) is type(b), (path, type(a), type(b))
    if isinstance(a, np.ndarray):
        assert a.dtype == b.dtype and a.shape == b.shape, path
        assert a.tobytes() == b.tobytes(), (path, a, b)
    elif isinstance(a, dict):
        assert list(a) == list(b), path
        for k in a: exact(a[k], b[k], path + '/' + str(k))
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)): exact(x, y, path + '/' + str(i))
    elif isinstance(a, float):
        assert struct.pack('d', a) == struct.pack('d', b), (path, a, b)
    elif isinstance(a, np.generic):
        assert a.dtype == b.dtype and a.tobytes() == b.tobytes(), (path, a, b)
    else:
        assert a == b, (path, a, b)

def digest(value):
    h = hashlib.sha256()
    def add(v):
        if isinstance(v, np.ndarray):
            h.update(str((v.dtype.str, v.shape)).encode()); h.update(v.tobytes())
        elif isinstance(v, np.generic):
            h.update(v.dtype.str.encode()); h.update(v.tobytes())
        elif dataclasses.is_dataclass(v):
            add(vars(v))
        elif isinstance(v, dict):
            for k, x in v.items(): add(k); add(x)
        elif isinstance(v, (list, tuple)):
            h.update(str(len(v)).encode())
            for x in v: add(x)
        elif isinstance(v, float): h.update(struct.pack('d', v))
        else: h.update(repr(v).encode())
        h.update(b'\x00')
    add(value)
    return h.hexdigest()

def trajectory(task, output, mode, limit, duration=None):
    from mjarena.envs.detailed_observations import DetailedObservations as Reference
    from mjarena.envs.observation_accel._details import DetailedObservations as Fast
    from mjarena.runner.episode import Match
    from mjarena.envs.sumo import SumoEnv
    import mjarena.envs.detailed_observations as details

    times = {'reference': 0., 'accelerated': 0.}
    if mode == 'compare':
        class Checked(Reference):
            def __init__(self, env):
                super().__init__(env)
                self.fast = Fast(env)
            def begin_interval(self):
                super().begin_interval()
                self.fast.begin_interval()
            def capture_contacts(self, integrate=False):
                super().capture_contacts(integrate)
                self.fast.capture_contacts(integrate)
                exact(self.impulses, self.fast.impulses, 'contact_impulses')
                exact(self.latest_contacts, self.fast.latest_contacts, 'latest_contacts')
                exact(self.interval_seconds, self.fast.interval_seconds, 'contact_interval')
            def for_robot(self, prefix):
                if self.cached is None:
                    self.fast.cached = None
                start = time.perf_counter(); a = super().for_robot(prefix)
                times['reference'] += time.perf_counter() - start
                start = time.perf_counter(); b = self.fast.for_robot(prefix)
                times['accelerated'] += time.perf_counter() - start
                exact(a, b)
                return a
        details.DetailedObservations = Checked
    elif mode == 'accelerated':
        details.DetailedObservations = Fast

    events = []
    class Finished(BaseException): pass
    original_obs = Match.build_bot_observation
    def observe(self, *a, **kw):
        result = original_obs(self, *a, **kw)
        events.append(['obs', digest(result)])
        return result
    Match.build_bot_observation = observe
    original_step = SumoEnv.step
    steps = 0
    def step(self, action):
        nonlocal steps
        result = original_step(self, action)
        events.append(['step', digest((action, self.data.qpos, self.data.qvel,
                                      self.data.qacc, self.data.ctrl, result))])
        steps += 1
        if steps % 50 == 0: print('validated ticks', steps, flush=True)
        if steps == 300:
            import mujoco
            mujoco.mj_saveModel(self.model, str(output.with_suffix('.mjb')), None)
            spec = mujoco.mjtState.mjSTATE_INTEGRATION
            state = np.empty(mujoco.mj_stateSize(self.model, spec))
            mujoco.mj_getState(self.model, self.data, state, spec)
            names = ['_boundary_geom_id', '_boundary_shape', '_contender_geom_ids',
                     '_root_body_ids', 'apply_n_repeated_actions', 'control_timestep',
                     'max_steps', 'outside_floor_gid', 'ring_half_extents',
                     'ring_radius', 'ring_top_z', 't']
            frozen = dict(attributes={k:getattr(self,k) for k in names}, state=state,
                          prefixes=[self.red_contender.prefix,self.blue_contender.prefix],
                          impulses=self.detailed_observations.impulses,
                          interval_seconds=self.detailed_observations.interval_seconds)
            output.with_suffix('.state').write_bytes(pickle.dumps(frozen))
        if steps >= limit: raise Finished()
        return result
    SumoEnv.step = step
    args = pickle.loads(Path(task).read_bytes())
    runner = dataclasses.replace(args[0], out_dir=output.parent / (output.stem + '-artifacts'),
                                 trace_label=None, save_video_seeds=0)
    if duration is not None:
        runner = dataclasses.replace(runner, match_time=duration, max_steps=round(duration/.01))
    start = time.perf_counter(); cpu_start = time.process_time(); finished = False
    try:
        result = runner.run_with_policy_spec(args[1], seed=args[2], seed_index=args[3])
        finished = True
        events.append(['result', digest(result)])
    except Finished: pass
    report = dict(label=args[5], seed=args[2], steps=steps, finished=finished,
                  mode=mode, seconds=time.perf_counter()-start, cpu_seconds=time.process_time()-cpu_start, observation_seconds=times,
                  events=events)
    output.write_text(json.dumps(report))
    print(json.dumps({k:v for k,v in report.items() if k!='events'}), flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('task'); p.add_argument('output', type=Path)
    p.add_argument('--mode', choices=['reference', 'accelerated', 'compare'], default='compare')
    p.add_argument('--steps', type=int, default=350)
    p.add_argument('--duration', type=float, help='Explicit shortened validation match; never tournament output')
    args = p.parse_args()
    trajectory(args.task, args.output, args.mode, args.steps, args.duration)
