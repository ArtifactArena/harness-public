"""Opt-in, CPU-only acceleration for fixed-geometry native arena matches."""
import atexit
import ctypes
import operator
import os
import threading
from pathlib import Path

_INSTALLED = None
_MISSING = object()


class Accelerator:
    """Own native contexts and restore patched entry points on close.

    Model geometry must stay fixed while a context exists. Joint positions,
    velocities, controls and ordinary simulation state remain fully dynamic.
    Use one process per concurrently simulated match; calls within a process
    serialize to protect the process-wide MuJoCo collision dispatch table.
    """

    def __init__(self, library, threads, interval):
        self.path = Path(library).resolve()
        self.threads = operator.index(threads)
        if self.threads not in (1, 4):
            raise ValueError('Match acceleration supports one or four CPU cores')
        if not hasattr(os, 'sched_getaffinity'):
            raise RuntimeError('The CPU accelerator requires Linux CPU affinity')
        allowed = os.sched_getaffinity(0)
        if len(allowed) != self.threads:
            raise RuntimeError('Pin the worker to exactly the requested number of CPUs')
        if self.threads == 4:
            topology = [Path(f'/sys/devices/system/cpu/cpu{cpu}/topology') for cpu in allowed]
            cores = {(p.joinpath('physical_package_id').read_text().strip(),
                      p.joinpath('core_id').read_text().strip()) for p in topology}
            if len(cores) != 4 or len({c[0] for c in cores}) != 1:
                raise RuntimeError('Four-core workers require distinct physical cores in one socket')
        for task in Path('/proc/self/task').iterdir():
            try:
                if not os.sched_getaffinity(int(task.name)) <= allowed:
                    raise RuntimeError('Existing threads must be confined to the match CPUs')
            except ProcessLookupError:
                pass
        import mujoco
        if mujoco.__version__ != '3.10.0':
            raise RuntimeError('Match acceleration requires MuJoCo 3.10.0')
        metadata = self.path.with_suffix('.json')
        if not metadata.is_file():
            raise RuntimeError('Keep the JSON build manifest beside the accelerator library')
        if metadata.exists():
            import hashlib, json, platform
            info = json.loads(metadata.read_text())
            if info.get('backend') not in ('cpu-serial', 'cpu-pair-parallel'):
                raise RuntimeError('Expected a supported CPU accelerator build')
            if self.threads == 4 and info['backend'] != 'cpu-pair-parallel':
                raise RuntimeError('Four cores require the pair-parallel build')
            if info.get('machine') != platform.machine():
                raise RuntimeError('Accelerator build has a different CPU architecture')
            if info.get('simd_target'):
                flags = next(line.split(':', 1)[1].split() for line in
                             Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('flags'))
                if not {'avx512f', 'avx512dq', 'avx512cd', 'avx512bw', 'avx512vl'} <= set(flags):
                    raise RuntimeError('This vector build requires an AVX-512-capable CPU')
            if hashlib.sha256(self.path.read_bytes()).hexdigest() != info['library_sha256']:
                raise RuntimeError('Accelerator library does not match its build metadata')
            loaded = {line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                      if '/libmujoco.so.' in line}
            if len(loaded) != 1 or hashlib.sha256(Path(next(iter(loaded))).read_bytes()).hexdigest() != info['mujoco_library_sha256']:
                raise RuntimeError('Loaded MuJoCo differs from the accelerator build')
        self.lock = threading.RLock()
        self.contexts = {}
        self.patches = []
        self.closed = False
        self.lib = ctypes.CDLL(str(self.path))
        self.lib.arena_create.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        self.lib.arena_create.restype = ctypes.c_void_p
        for name in ['arena_step', 'arena_forward', 'arena_destroy']:
            fn = getattr(self.lib, name)
            fn.argtypes = [ctypes.c_void_p]
            fn.restype = None
        self.lib.arena_enable.argtypes = [ctypes.c_int]
        self.lib.arena_enable.restype = None
        self.original_step = mujoco.mj_step
        self.original_forward = mujoco.mj_forward
        try:
            if interval:
                # Validate the exact NumPy/BLAS ABI used by the interval and bounds kernels.
                from mjarena.envs.observation_accel import install as install_observations
                from mjarena.envs import detailed_observations as reference_observations
                original_observer = reference_observations.DetailedObservations
                install_observations()
                if reference_observations.DetailedObservations is not original_observer:
                    self.patches.append((reference_observations, 'DetailedObservations',
                                         original_observer, reference_observations.DetailedObservations))
                self._install_interval()
            self.lib.arena_enable(1)
            self._patch(mujoco, 'mj_step', self.step)
            self._patch(mujoco, 'mj_forward', self.forward)
        except BaseException:
            self.close()
            raise
        atexit.register(self.close)

    def _patch(self, owner, name, replacement):
        self.patches.append((owner, name, getattr(owner, name, _MISSING), replacement))
        setattr(owner, name, replacement)

    def _context(self, model, data):
        key = (model._address, data._address)
        if key not in self.contexts:
            # Reserve four CPUs only in explicitly configured workers. Use them for
            # models with enough SDF work to amortize the collision prepass.
            import mujoco
            sdf_geoms = int((model.geom_type == mujoco.mjtGeom.mjGEOM_SDF).sum())
            threads = self.threads if sdf_geoms >= 4 and model.opt.sdf_initpoints >= 16 else 1
            native = self.lib.arena_create(*key, threads)
            if self.threads == 4:
                import json
                print(json.dumps(dict(event='sdf_cpu_policy', pid=os.getpid(),
                                      sdf_geoms=sdf_geoms, initpoints=int(model.opt.sdf_initpoints),
                                      threads=threads if native else 0)), flush=True)
            # Strong references prevent reuse of addresses held by native code.
            self.contexts[key] = (model, data, native)
        return self.contexts[key][2]

    def release(self, model, data):
        with self.lock:
            entry = self.contexts.pop((model._address, data._address), None)
            if entry and entry[2]:
                self.lib.arena_destroy(entry[2])

    def step(self, model, data, nstep=1):
        count = operator.index(nstep)
        if count < 0:
            return self.original_step(model, data, nstep=count)
        with self.lock:
            if self.closed:
                return self.original_step(model, data, nstep=count)
            ctx = self._context(model, data)
            if not ctx:
                return self.original_step(model, data, nstep=count)
            for _ in range(count):
                self.lib.arena_step(ctx)

    def forward(self, model, data):
        with self.lock:
            if self.closed:
                return self.original_forward(model, data)
            ctx = self._context(model, data)
            if ctx:
                self.lib.arena_forward(ctx)
            else:
                self.original_forward(model, data)

    def _install_interval(self):
        from mjarena.envs.sumo import SumoEnv
        from mjarena.envs.observation_accel._details import DetailedObservations
        from ._bounds import Bounds
        from ._interval import advance
        from . import _glue
        import hashlib
        root = Path(__file__).resolve().parents[3]
        if all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
               for name, digest in _glue.SOURCE_HASHES.items()):
            from mjarena.runner.episode import Match
            self._patch(Match, 'build_bot_observation', _glue.build_bot_observation)

        def robot_extents(env, prefix):
            if not hasattr(env, '_match_bounds'):
                env._match_bounds = Bounds(env.model)
            return env._match_bounds.extents(
                env.data, env._contender_geom_ids.get(prefix, []),
                env._root_body_ids.get(prefix, -1))

        step_address = ctypes.cast(self.lib.arena_step, ctypes.c_void_p).value

        def advance_interval(observer, count):
            if count <= 0:
                return False
            with self.lock:
                ctx = self._context(observer.model, observer.env.data)
                if not ctx:
                    return False
                advance(observer, count, step_address, ctx)
                return True

        self._patch(SumoEnv, 'robot_extents', robot_extents)
        self._patch(DetailedObservations, 'advance_interval', advance_interval)
        if hasattr(self.lib, 'arena_observe'):
            self.lib.arena_observe.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.lib.arena_observe.restype = ctypes.c_int

            def forward_observation(observer):
                with self.lock:
                    return bool(self.lib.arena_observe(observer.model._address,
                                                       observer.data._address))

            self._patch(DetailedObservations, 'forward_observation', forward_observation)

        original_close = SumoEnv.close

        def close_env(env):
            try:
                return original_close(env)
            finally:
                details = getattr(env, 'detailed_observations', None)
                if details is not None:
                    self.release(env.model, details.data)
                self.release(env.model, env.data)
                env.__dict__.pop('_match_bounds', None)

        self._patch(SumoEnv, 'close', close_env)

    def close(self):
        global _INSTALLED
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for owner, name, original, replacement in reversed(self.patches):
                if getattr(owner, name, _MISSING) == replacement:
                    if original is _MISSING:
                        delattr(owner, name)
                    else:
                        setattr(owner, name, original)
            for _, _, ctx in self.contexts.values():
                if ctx:
                    self.lib.arena_destroy(ctx)
            self.contexts.clear()
            self.lib.arena_enable(0)
            atexit.unregister(self.close)
            if _INSTALLED is self:
                _INSTALLED = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def install(library, threads=1, interval=True):
    """Install once at process startup; returns a closable Accelerator handle."""
    global _INSTALLED
    if _INSTALLED is not None:
        if _INSTALLED.path != Path(library).resolve() or _INSTALLED.threads != threads:
            raise RuntimeError('Close the installed accelerator before changing its configuration')
        return _INSTALLED
    _INSTALLED = Accelerator(library, threads, interval)
    return _INSTALLED
