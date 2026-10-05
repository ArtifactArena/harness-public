"""Compare stock and accelerated MuJoCo substeps without tolerances."""
import argparse
import ctypes
import hashlib
import json
import os
import time
from pathlib import Path

import mujoco
import numpy as np


def same(left, right, step, name):
    a, b = np.asarray(left), np.asarray(right)
    if a.dtype != b.dtype or a.shape != b.shape or a.tobytes() != b.tobytes():
        raise AssertionError(f'Numerical mismatch at step {step}: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--threads', type=int, choices=[1], default=1)
    parser.add_argument('--steps', type=int, default=1000)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('steps must be positive')
    if len(os.sched_getaffinity(0)) != 1:
        parser.error('pin this paired benchmark to one CPU with taskset or scheduler affinity')
    if mujoco.__version__ != '3.10.0':
        parser.error('requires MuJoCo 3.10.0')
    lib = ctypes.CDLL(str(args.library.resolve()))
    lib.arena_enable.argtypes = [ctypes.c_int]
    lib.arena_enable.restype = None
    lib.arena_create.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.arena_create.restype = ctypes.c_void_p
    for name in ('arena_step', 'arena_destroy'):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
        getattr(lib, name).restype = None
    model = mujoco.MjModel.from_binary_path(str(args.model))
    reference, candidate = mujoco.MjData(model), mujoco.MjData(model)
    with np.load(args.state, allow_pickle=False) as saved:
        for data in (reference, candidate):
            mujoco.mj_setState(model, data, saved['state'], int(saved['spec']))
            mujoco.mj_forward(model, data)
    context = lib.arena_create(model._address, candidate._address, args.threads)
    if not context:
        raise RuntimeError('Model is outside the accelerated physics scope')
    seconds = [0.0, 0.0]
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    states = [np.empty(mujoco.mj_stateSize(model, spec)) for _ in range(2)]
    try:
        for step in range(args.steps):
            # Reverse timing order each step to reduce systematic timing bias.
            for index in ((0, 1) if step % 2 == 0 else (1, 0)):
                lib.arena_enable(index)
                start = time.perf_counter()
                if index:
                    lib.arena_step(context)
                else:
                    mujoco.mj_step(model, reference)
                seconds[index] += time.perf_counter() - start
            for data, state in zip((reference, candidate), states):
                mujoco.mj_getState(model, data, state, spec)
            same(*states, step, 'integration_state')
            for name in ('qacc', 'qfrc_constraint', 'efc_force', 'sensordata'):
                same(getattr(reference, name), getattr(candidate, name), step, name)
            for name in ('dist', 'pos', 'frame', 'geom1', 'geom2', 'efc_address'):
                same(getattr(reference.contact, name), getattr(candidate.contact, name),
                     step, 'contact.' + name)
    finally:
        lib.arena_enable(0)
        lib.arena_destroy(context)
    report = {
        'exact': True, 'steps': args.steps, 'threads': args.threads,
        'affinity': sorted(os.sched_getaffinity(0)),
        'reference_seconds': seconds[0], 'accelerated_seconds': seconds[1],
        'physics_speedup': seconds[0] / seconds[1], 'mujoco': mujoco.__version__,
        'library_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest(),
        'model_sha256': hashlib.sha256(args.model.read_bytes()).hexdigest(),
        'state_sha256': hashlib.sha256(args.state.read_bytes()).hexdigest(),
    }
    if hasattr(lib, 'arena_simd_check_counts'):
        counts = (ctypes.c_ulonglong * 2)()
        lib.arena_simd_check_counts.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        lib.arena_simd_check_counts.restype = None
        lib.arena_simd_check_counts(counts)
        report['exact_simd_gradient_checks'] = counts[0]
        report['exact_simd_distance_checks'] = counts[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
