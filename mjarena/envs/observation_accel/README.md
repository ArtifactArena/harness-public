# Exact observation accelerator

Opt-in Cython implementation of the detailed-observation and surface-distance
code at harness commit `ea50df62`. The original Python modules remain unchanged
and serve as the numerical reference. No MuJoCo integration, controller timing,
match limits, seeds, scoring, or observation schemas are changed.

Validated environment: x86-64 Linux, Python 3.10, NumPy **2.1.3**, MuJoCo **3.10.0**,
Cython **3.1.4**, and NumPy’s bundled scipy-openblas **0.3.27** with 64-bit BLAS integers. Do not replace NumPy or its BLAS/LAPACK backend to use this code.
The installer rejects a different runtime or changed reference-module hashes.

## Implementation

- Compile geometry/observation control flow and small vector loops.
- Preserve operation order and the existing NumPy matrix multiplication,
  eigensolver, dot-product, and least-squares kernels.
- Batch independent geometry queries while preserving each query's simplex
  enumeration, candidate order, convergence rules, and tie-breaking.
- Call the same BLAS kernels used by NumPy 2.1.3 directly for tiny matrix/vector
  products and norms. Preserve NumPy's layout-dependent dispatch; unsupported
  layouts use the reference path.
- Reuse DGELSD workspaces for 3-by-(1..3) least-squares problems. Call the same
  LAPACK symbol, with identical column-major inputs, cutoff, and workspace sizes.
  Nonfinite inputs and unsupported shapes retain the NumPy wrapper.
- Compile contact bookkeeping, using the original MuJoCo contact-force routine
  and the same BLAS frame transformations. Preserve contact order and the
  multiplication/addition order of accumulated forces, torques, and positions.
- Cache unchanged simplex subsets, box support corners, and exact quaternion
  inputs. Geometry caches are scoped to their query/update.
- Remove redundant internal copies while returning detached controller-facing
  snapshots with deepcopy alias and cycle behavior.
- Disable fast-math and floating-point contraction. No approximate geometry,
  relaxed tolerance, lower precision, or parallel floating-point reductions.

The compiled fast paths target the harness's float64 MuJoCo arrays. This is not
an independently supported general-purpose NumPy replacement. The NumPy/BLAS ABI is deliberately pinned. Direct native symbols are resolved
from the libraries already loaded by NumPy and MuJoCo. Missing/incompatible
symbols leave the original observer installed. Workspace calls hold the GIL;
allocate outputs before touching shared scratch so allocation-time finalizers
cannot overwrite pending results.

## Build

From the repository root, with the pinned harness environment already installed:

```sh
venv/bin/python -m pip install --target /path/to/build-deps 'Cython==3.1.4'
PYTHONPATH=/path/to/build-deps venv/bin/python \
  mjarena/envs/observation_accel/build.py build_ext --inplace
```

The build uses `-O3 -fno-fast-math -ffp-contract=off` and does not replace the
production NumPy installation. Built extensions are specific to Python 3.10
and Linux x86-64. Run the checks on the target machines before enabling.

```sh
export OBS_OVERLAY="$PWD"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export ARENA_SKIP_MATCH_DATA=1
venv/bin/python scripts/observation_accel/check_kernels.py
venv/bin/python scripts/observation_accel/check_native.py
venv/bin/python scripts/observation_accel/check_batched.py
venv/bin/python scripts/observation_accel/check_lstsq_workspace.py
venv/bin/python scripts/observation_accel/regressions.py
```

Run regression tests from a checkout containing the compiled package: the
harness test suite intentionally rejects modules imported from another checkout.

`validate.py` accepts a trusted internal seed-queue `task.pickle` and writes to
isolated validation outputs. Never load an untrusted pickle.

```sh
venv/bin/python scripts/observation_accel/validate.py /path/task.pickle \
  /path/check-reference.json --mode compare --steps 350
venv/bin/python scripts/observation_accel/validate.py /path/task.pickle \
  /path/check-fast.json --mode accelerated --steps 350
venv/bin/python scripts/observation_accel/benchmark_state.py /path/check-reference.json
```

Compare the entire `events` arrays in both JSON files for equality. The compare
mode checks both observation implementations recursively, including independent
contact records and impulse accumulators after every physics substep, and returns
the reference observations to the real controllers. The independent accelerated
run checks controller outputs and simulation states as well. At step 300 the
validator saves the model and state for the paired microbenchmark.

`--duration 1 --steps 1000` additionally exercises match termination and scoring
in an explicitly shortened, isolated test. Never use this option for tournaments.

## Validation and performance, 2026-09-20 UTC

Release `exact-v1` (experimental version 8):

- 28 existing geometry/observation tests passed, with paired exact comparisons.
- 2,500 randomized/adversarial case iterations cover numerical kernels, simplex
  selection, primitive distances, and detached snapshots. Passed on all 3 the GPU cluster nodes.
- Grok: 350 real-controller ticks, 1,050 observation/action/state events identical.
- Astra and Qwen: 80 ticks and 240 identical events each on their assigned nodes.
- A completed 1-second validation match: all 301 events, including the final
  GameRecord, identical between reference and accelerated runs.
- Paired captured-state medians: 0.455464 s reference, 0.166629 s accelerated,
  **2.73x** faster observations. Previous version measured **2.64x**.
- Paired Astra/Qwen observation timings: **1.75x / 2.39x** faster.

These are representative observation benchmarks, not measured fleet throughput
or a proof covering every possible state. No full 300-second match equivalence
claim is made. Raw traces, node validation reports, compiled release checksums,
and regression output are stored with the SH-250 run's
`observation-optimization/` artifacts.

## Enable and rollback

In a fresh interpreter, before constructing environments:

```python
from mjarena.envs.observation_accel import install
install()
```

The SH-250 queue wrapper checks the immutable release's SHA-256 manifest and a
node-local activation marker before calling `install()`. Missing/incompatible
releases fall back to the reference implementation. Only new seed processes
adopt the optimization; existing matches keep their loaded code and state.
Remove the node-local `observation-acceleration.json` marker to return future
seeds to the reference implementation. Neither activation nor rollback should
kill a running seed or delete completed results.


## Further optimization: exact-v2

The second release adds cross-query batching, direct calls to the pinned BLAS
and LAPACK kernels, and compiled contact bookkeeping. The reference Python
implementation remains unchanged. The first release remains available for
rollback; do not overwrite a loaded extension library in place.

Additional exact checks cover 10,000 primitive-support/barycentric cases,
600 batched convex-distance queries, and 12,000 scaled, rank-deficient, or
strided least-squares cases plus 3,104 batch entries. Layout tests explicitly
include reversed vectors, Fortran-order matrices, and signed zero. A last-bit
difference found for reversed vectors was fixed by preserving NumPy's reference
path for that layout.

Compare against an earlier compiled release in the same process, alternating
measurement order and reporting both wall and CPU time:

```sh
export OBS_BASELINE=/path/to/exact-v1
export OBS_OVERLAY="$PWD"
venv/bin/python scripts/observation_accel/benchmark_variants.py /path/capture.json
```

Final `exact-v2` checks passed the same 28 regression tests. On all three the GPU cluster
nodes, 350 real-controller ticks produced 1,050 identical observation/action/state
events, and independent contact accumulators matched after every substep during
200-tick comparisons. The shortened completed-match check also matched all 301
events, including scoring.

Compared with deployed `exact-v1`, captured-state observations used **2.07x–2.56x**
less CPU time across Astra, Grok, and Qwen. The 350-tick replays were respectively
**1.41x, 1.92x, and 2.01x** faster by CPU time. These representative replays include
setup and are not full-length tournament throughput measurements.

CPU time helps separate compute cost from scheduling contention on shared nodes.
Captured-state benchmarks isolate observation construction; match replay timings
also include controllers, physics, contacts, and setup. Neither is a fleet-wide
throughput guarantee.

The native call conventions follow NumPy 2.1.3's
[matmul kernels](https://github.com/numpy/numpy/blob/v2.1.3/numpy/_core/src/umath/matmul.c.src),
[dot kernels](https://github.com/numpy/numpy/blob/v2.1.3/numpy/_core/src/multiarray/arraytypes.c.src),
and [least-squares wrapper](https://github.com/numpy/numpy/blob/v2.1.3/numpy/linalg/umath_linalg.cpp).

## Further optimization: exact-v3

This release removes Python allocations from the convex-distance inner loop.
Support points, simplex candidates, and cached subset solutions use fixed-size
native storage. The solver still calls the same pinned DGELSD and BLAS kernels,
with identical enumeration, tie-breaking, tolerances, and arithmetic order.

Mesh certificates reuse their point-independent triangle data within each update.
Their native loop preserves NumPy 2.1.3's two-lane SSE2 `einsum` reduction order;
a startup arithmetic check disables this path if the reduction differs. Other
array layouts retain the NumPy implementation. See the pinned
[NumPy einsum source](https://github.com/numpy/numpy/blob/v2.1.3/numpy/_core/src/multiarray/einsum_sumprod.c.src).

The observer also stops speculative far-distance queries once the updated lower
bound excludes them. Closing speeds are calculated after selecting the final 32
proximity records, because speeds do not participate in ranking. All exposed
fields, geometry witnesses, and truncation behavior are preserved.

Additional checks:

```sh
venv/bin/python scripts/observation_accel/check_native_gjk.py
venv/bin/python scripts/observation_accel/check_native_hulls.py
venv/bin/python scripts/observation_accel/check_mesh_certificate.py
```

These cover more than 7,500 primitive-distance queries, 1,200 mesh-hull/triangle
queries, and 12,952 mesh certificates, including finite intermediate values,
signed zero, degeneracy, strided arrays, read-only inputs, and tolerance edges.

`benchmark_replay.py` measures real controllers and physics without the validator's
observation/state hashing overhead. Run it in separate fresh interpreters for
each release; use `validate.py` separately to check equality:

```sh
OBS_OVERLAY=/path/to/exact-v2 venv/bin/python \
  scripts/observation_accel/benchmark_replay.py /path/task.pickle /path/baseline.json
OBS_OVERLAY=/path/to/exact-v3 venv/bin/python \
  scripts/observation_accel/benchmark_replay.py /path/task.pickle /path/candidate.json
```

The requested additional 10x end-to-end improvement has **not** been demonstrated.
Captured-state speedups and short replay speedups must not be presented as a
10x improvement to full-match or fleet throughput.

The final build passed the 28 existing regression tests and independent 350-tick
real-controller replays on all three the GPU cluster nodes (1,050 matching events each).
A shortened completed match also matched the reference GameRecord. Substep
contact comparisons were exercised for 200 ticks during development.

Captured-state observation CPU speedups versus `exact-v2` were **4.67x Grok,
5.84x Astra, and 4.85x Qwen**. These captures measure observation construction,
not full match execution. Shared-node CPU contention and frequency changes can
also affect timings; retain both wall and CPU measurements with the artifacts.

Final 350-tick replay CPU measurements (setup included, validation hashing excluded):

| Replay | Deployed exact-v2 | exact-v3 | Speedup |
| --- | ---: | ---: | ---: |
| Grok, seed 54 | 18.375 s | 9.095 s | 2.02x |
| Astra, seed 232 | 111.474 s | 74.764 s | 1.49x |
| Qwen, seed 258 | 19.839 s | 9.216 s | 2.15x |

These are short replays of three specific pairings, not measurements of all
300-second matches or fleet throughput. An earlier Grok baseline measured
16.462 CPU seconds; this variation is another reason not to promise a fixed
speedup for the shared cluster.
