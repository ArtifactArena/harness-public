> Historical experiment, rejected: it used 80 cores for one match.
> These timings do not satisfy the one-core-per-match requirement.

# CPU match results — 2026-09-21

The requested **10× end-to-end target has not been achieved**. The current
CPU-only implementation completed the original Fable/Astra exhibition in
**348.6505 seconds (5m49s)**, versus the original **2659.7 seconds (44m20s)**:
**7.63×** faster. An earlier CPU version completed it in **317.8289 seconds
(5m18s), 8.37×** faster. Shared-node scheduling and concurrent workloads affected
timings; these are observed single-match wall times, not a throughput guarantee.

The final full run had no competing optimization builds or benchmarks. Other
user workloads continued on the node. All versions used the original seed 42,
spawn seed 42, high contact fidelity, 0.00025-second physics timestep,
0.01-second control interval, and 300-second match cap. The accelerator uses
**64 CPU physics workers plus 16 CPU surface workers**; it does not use GPUs.

## Numerical checks

* **All 49 common GameRecord fields matched** the original full replay,
  including every recorded pose, action, velocity, contact, force, score-related
  series, and termination field. Astra still wins the same ring-out at 225.81
  simulated seconds. Recorded poses/actions are quantized by the existing
  recorder; this comparison alone does not establish full raw-state bit equality.
* A separate paired test checked **1,000 consecutive physics substeps byte for
  byte**, including the complete integration state, accelerations, constraint
  forces, sensors, and ordered contact geometry/frames. Passed. This test measured
  **13.73× faster physics** (2.56023 seconds versus 0.18651 seconds); it excludes
  controllers and observation construction and is not a full-match speedup.
* Independent 1,000-tick closed-loop prefixes matched raw integration state.
* Native interval accumulation matched ordered impulses, durations, contact
  records, and states over 25 intervals / 1,000 physics substeps.
* Exact helper checks covered 72,576 octree boundary cases, 2,000 runtime bounds
  comparisons at real replay poses, and 1,000 randomized observer states.
* **19 runtime size-limit tests and 28 observation regression tests passed**.

The benchmark wrapper counts 22,701 calls, including the harness's existing 120
post-win steps; the recorded match contains 22,581 steps.

## Artifacts and reproduction

Worktree: `harness-match-opt-20260921`, branch `perf/exact-match-20260921`, based
on harness `3c03d494bf002846c86e1ab8e6c46726ac856816`. The primary harness checkout
and official tournament outputs were not modified.

Cluster: the GPU cluster, node `gpu-node-5`, existing allocation **<job-1>**. Durable files:

```text
<scratch>/runs/sh250-20260919/match-optimization/
  source/                    reproducible source snapshot
  release/arena_cpu.so        verified CPU library
  release/arena_cpu.c         generated native source
  release/arena_cpu.json      compiler/dependency/source/library hashes
  release/mjarena/envs/       compiled Cython extensions
  validation/cpu-results.json
  validation/final-physics-parity.json
  validation/final-regressions.log
  validation/observation-regressions.log
  validation/full-final/     complete final replay, state, timing, parity report
  validation/full-v18/       earlier fastest completed CPU run
```

The portable physics checker and build/run commands are in [README.md](README.md).
The exhibition-specific benchmark is `scripts/match_accel/benchmark_match.py`.
Do not launch overlapping benchmarks or compile on their CPU cores when timing.
Use a fresh interpreter and pinned NumPy/BLAS/MuJoCo versions for comparisons.

Other tested CPU schedules, compiler options, SIMD search implementations,
pthread pools, and lower spin counts did not improve the complete configuration
enough to establish 10×. They are not enabled in this release. GPU experiments
were removed from the active implementation after the CPU-only instruction.
