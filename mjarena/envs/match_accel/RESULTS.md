# One-core-per-match results — 2026-09-21

The latest release is **1.19× faster than the previous one-core accelerator** on
a 3,000-control-tick replay: **155.6848 s → 130.6822 s**, a **16.1% reduction in
wall time**. Complete final integration state is byte-identical between versions.
Every match still uses one pinned CPU core, with no worker processes or GPU.

The **10× target remains unmet**. These are replay-prefix benchmarks, not measured
full-match or fleet-throughput speedups.

## Replay measurements

All runs use the real Fable/Astra controllers, seed/spawn seed 42, the original
0.00025-second physics timestep, 0.01-second control period, and high contact
fidelity. Timing includes initialization, observations, controllers, and physics.

| 1,000 control ticks, same pinned CPU | Wall time |
| --- | ---: |
| Original harness `3c03d494`, deployed observation accelerator | 102.2323 s |
| Previous one-core accelerator `b7b6442` | 47.9618 s |
| Selected new variant | **40.5461 s** |

The selected variant is **2.52× faster than the original harness** and **1.18×
faster than the previous accelerator** on this prefix. Its complete final state
matches the original harness byte for byte.

A fresh, longer comparison of the previous and final new release:

| 3,000 control ticks, same pinned CPU | Wall time | CPU time |
| --- | ---: | ---: |
| Previous accelerator | 155.6848 s | 155.6229 s |
| Final new release | **130.6822 s** | **130.6275 s** |

Both runs had all process threads pinned to CPU 0 and **zero child processes**.
Their complete final integration states match byte for byte. The original stock
harness was not rerun for this longer prefix; the 2.52× stock comparison above
applies only to the 1,000-tick measurement.

## What changed

Native sampling identified cell lookup as the largest remaining CPU cost. Three
small changes address it:

* A table entry already identifies a leaf, so SIMD queries skip eight redundant
  child loads. Bounds checks and the uncached traversal remain in place.
* The initial lookup guess uses the number of cells (`cuts + 1`). Exact comparisons
  against the original split boundaries still correct every guess.
* Only the projection and interpolation helpers are inlined, allowing unused
  outputs to disappear without expanding the whole collision-search call tree.

Full inlining, moving whole line searches into SIMD, and eight-lane vectors were
slower and were not retained. ISPC did not support the attempted 32-lane target.
The final release retains the original 16-lane AVX-512 target, original arithmetic
and contact order, and disabled fast-math/floating-point contraction.

## Numerical verification of the final release

* Paired stock/accelerated physics checked integration state, accelerations,
  constraints, sensors, and ordered contact fields after **1,000 consecutive
  substeps**, with exact byte comparisons. Passed; physics alone was **3.22×
  faster** in this test.
* The instrumented build compared **1,615,622 gradient/value results** and
  **15,091,776 line-search distances** against scalar arithmetic. All matched
  bit for bit. Its timing includes redundant scalar work and is not a speed result.
* **72,576 boundary points** checked cached leaf indices, interpolation weights,
  and gradient weights against stock traversal, including adjacent representable
  floats on either side of root/split boundaries.
* Native interval accumulation matched ordered impulses, durations, latest
  contacts, and state over **25 intervals / 1,000 physics steps**.
* All **19 runtime size-limit tests** passed with the final accelerator installed.
* The independent real-controller comparisons above passed their final-state
  byte checks. The 3,000-tick runs cover about 120,000 physics substeps, but do not
  perform paired byte comparisons at every one of those substeps.

No timestep reduction, lower precision, relaxed tolerance, reordered reductions,
or controller-code changes are used. Validation covers this pairing and the
regression cases, not every possible bot or full-length trajectory.

## Code and artifacts

Worktree: `harness-match-opt-20260921`, branch `perf/exact-match-20260921`.
See [README.md](README.md) for the pinned environment and build/run commands.
The machine-readable report, including experiments and build hashes, is
[`onecore-v3-results.json`](../../../scripts/match_accel/results/onecore-v3-results.json).
The previous report remains in
[`onecore-results.json`](../../../scripts/match_accel/results/onecore-results.json).
The rejected 80-core experiment is documented only in
[historical results](RESULTS-manycore.md).

Completed on the GPU cluster node `gpu-node-5`, within existing job **<job-1>**. Every benchmark step requested one
CPU, used one hardware thread, and used no GPU. No benchmark remains running.
Durable artifacts:

```text
<scratch>/runs/sh250-20260919/match-optimization/
  release-onecore-v3/arena_onecore_v3.so
  release-onecore-v3/arena_onecore_v3.json
  release-onecore-v3/arena_onecore_v3.c
  release-onecore-v3/arena_onecore_v3.simd.ispc
  release-onecore-v3/mjarena/envs/     unchanged compiled observation/interval modules
  release-onecore-v3/onecore-v3-source.bundle
  release-onecore-v3/SOURCE_COMMIT
  validation-onecore-v3/onecore-v3-results.json
  validation-onecore-v3/onecore-old-3000/
  validation-onecore-v3/onecore-v3-3000/
  validation-onecore-v3/onecore-v3-physics.json
  validation-onecore-v3/onecore-v3_checked-physics.json
  validation-onecore-v3/onecore-v3-boundaries.json
  validation-onecore-v3/onecore-v3-interval.log
  validation-onecore-v3/onecore-v3-regressions.log
```
