# One CPU core per match

The harness now enables this accelerator automatically around each `run_match`
call when built; see [CPU acceleration setup](../../../README.md#cpu-acceleration-setup).
The automatic path uses one simulation thread without changing process affinity,
limits numeric thread pools during the match, and releases patches and native
contexts afterward. `ARENA_MATCH_ACCEL=0` disables automatic activation.

The explicit launcher below runs **one match process on one CPU core**. It does not
start physics threads or surface worker processes and does not use a GPU. Run
independent matches on separate allocated cores to preserve tournament throughput.

The timestep, control frequency, floating-point precision, collision-search
iterations, contact order, solver, seeds, and scoring remain unchanged. Fast-math
and floating-point contraction are disabled. The 10× single-core target has not
been established; see `RESULTS.md` for measured results. The earlier 80-core
experiment is historical and does not meet the requirement.

## Build

Validated environment: Linux x86-64, Python 3.10, MuJoCo **3.10.0**, NumPy **2.1.3**,
NumPy's bundled scipy-openblas **0.3.27** ILP64, and Cython **3.1.4**. First build
or install the existing [observation accelerator](../observation_accel/README.md).

Extract the official MuJoCo
[3.10.0 source archive](https://github.com/google-deepmind/mujoco/archive/refs/tags/3.10.0.tar.gz).
From this checkout with the pinned harness environment:

```sh
export PYTHONPATH="$PWD:/path/to/build-deps"
venv/bin/python mjarena/envs/observation_accel/build.py build_ext --inplace
venv/bin/python mjarena/envs/match_accel/build_interval.py build_ext --inplace
venv/bin/python mjarena/envs/match_accel/build.py \
  /path/to/mujoco-3.10.0 /path/to/release/arena_serial.so \
  --ispc /path/to/ispc-1.31.0/bin/ispc
```

The optional ISPC **1.31.0** build uses AVX-512 vector instructions on that one
core. It batches independent search points and compacts active lanes between
line-search rounds, retaining each point's arithmetic and contact merge order.
It launches no ISPC tasks or threads. Omit `--ispc` for the slower scalar backend.
The vector build requires an AVX-512-capable CPU.

The native library has no OpenMP or worker-pool code. The builder checks pinned
MuJoCo source hashes and saves the generated C and JSON build manifest beside the
library. Keep the manifest with the library. Build on the target CPU architecture:
`-march=native` can require instructions unavailable on older processors. Never
replace a library while a process is using it.

## Run

Assign one logical CPU per match. The launcher pins itself before importing the
numeric libraries and forces BLAS/OpenMP thread counts to one. It defaults to the
first CPU allowed by the scheduler; `--cpu` selects another allowed CPU.

```sh
venv/bin/python -m mjarena.envs.match_accel \
  --library /path/to/release/arena_serial.so \
  --cpu 12 -- path/to/match_script.py [arguments]
```

It also accepts `-- -m package.module [arguments]`. Requests for more than one
physics thread or any surface worker are rejected. With Slurm, allocate one CPU
per task and let each match inherit its task's distinct affinity. When launching
several processes in one allocation yourself, explicitly assign different CPUs;
otherwise they would all default to the same first CPU.

Wrap an individual match worker, not the tournament coordinator: pinning the
coordinator would also constrain its child matches to the same core.

The embedded API defaults to `threads=1` and rejects other values. Embedders must
configure single-threaded numeric libraries and process affinity before importing
MuJoCo/NumPy; the launcher does this for you. Use one process per match because
MuJoCo's collider dispatch table is process-wide.

## Implementation and numerical checks

* Execute collision pairs in their original serial order; no parallel prepass,
  speculative physics, or extra scratch `mjData` workers.
* Reuse exact SDF work and look up octree leaves using the original IEEE split
  decisions and boundary corrections. Use the cell count for the initial index
  guess, then correct against exact cuts. Known leaves skip redundant child
  gathers. Preserve interpolation/reduction order; inline only projection and
  interpolation helpers to eliminate unused outputs.
* Reject separated primitive/SDF pairs using bounds on the interpolated
  nonpositive field, including its exterior extension. Reuse finite-difference
  leaf lookups only within identical table cells. See
  [COLLISION-BOUNDS.md](COLLISION-BOUNDS.md) for bounds, fallbacks, and checks.
* Accumulate all substep contact impulses in native code in the original order.
* Cache fixed local geometry for runtime bounds while retaining the same BLAS
  kernels and matrix-operation order.
* Calculate the private observer's kinematics and transmission rates without its
  unused second constraint solve. Exposed observations remain unchanged.
* Compile the unchanged observation assembly method and check its source hash
  before installing it. Controller sandbox code is unchanged.

Model geometry must stay fixed for the lifetime of each accelerated context.
Unsupported plugins, flexes, sleeping, custom physics callbacks, or an existing
MuJoCo thread pool retain stock physics. Numeric library versions/ABIs are pinned.
This is an optimization of this harness, not a general MuJoCo replacement.

Run the paired raw-state checker on one core, using a binary model and an NPZ
containing `state` from `mj_getState` and its integer `spec`:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  taskset -c 12 venv/bin/python scripts/match_accel/verify_physics.py \
  --library /path/to/release/arena_serial.so \
  --model /path/to/model.mjb --state /path/to/state.npz \
  --steps 1000 --output /path/to/physics-parity.json

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  taskset -c 12 venv/bin/python scripts/match_accel/check_octrees.py \
  --library /path/to/release/arena_serial.so \
  --model /path/to/model.mjb --output /path/to/octree-parity.json
```

It compares integration state, accelerations, forces, sensors, and ordered contact
geometry bytes after every substep, without numerical tolerances. Its timing is
physics-only. The octree checker compares leaf indices and interpolation/gradient
weights with stock traversal at split boundaries and their adjacent floats.
Full replay files quantize poses/actions, so comparisons of recorded
replays and raw-state byte comparisons establish different levels of parity.
A `--verify-simd` debug build independently compares every vectorized gradient,
value, and line-search distance with scalar arithmetic; use it for validation,
not timing.
The exhibition-specific scripts retain paths to the original Fable/Astra run.

MuJoCo-derived code is covered by [LICENSE.mujoco](LICENSE.mujoco).
