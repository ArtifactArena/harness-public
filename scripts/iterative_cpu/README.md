# Accelerating the frozen iterative tournaments on one CPU

The September 24 iterative tournament snapshots did not contain or enable the
existing Cython observation and single-core native accelerators. This release
installs those accelerators into the **original frozen harness**, adding only
the optional native interval hook to `SumoEnv.step`. Copying a newer complete
harness would also change simulation rules and is intentionally avoided.

Each new worker is pinned to one allowed logical CPU before numerical imports;
BLAS/OpenMP thread counts are one and `CUDA_VISIBLE_DEVICES` is empty. Native
AVX-512 operates within that one CPU. No GPU or physics worker pool is used.
CPU models without the required AVX-512 flags use the Cython observation path.
Source, release file, runtime and native-library ABI checks reject mismatches.

## Measured improvement and parity

Same-core sequential comparisons on Host A, Python 3.10, MuJoCo 3.10.0, NumPy 2.1.3,
NumPy OpenBLAS 0.3.27 ILP64. Wall times include the parity instrumentation. The
first four runs are 500 controller ticks (5 simulated seconds), **not complete
matches**. Fable–Opus used the original 300-second cap and ended naturally by
ring-out at 5.83 simulated seconds, followed by the normal 120 post-win steps.

| Bots | Reference seconds | Accelerated seconds | Speedup | Checked events |
|---|---:|---:|---:|---:|
| Astra 09 / Gemini 09 | 499.879 | 72.076 | 6.94× | 1,500 |
| Codex 5.3 10 / Grok 4.5 10 | 281.331 | 18.989 | 14.82× | 1,500 |
| GPT-5.4 10 / Fable 5.1 01 | 473.518 | 16.906 | 28.01× | 1,500 |
| Fable 5.1 01 / Grok 10 | 363.947 | 26.792 | 13.58× | 1,500 |
| Fable 5.1 01 / Opus 01, complete match | 220.459 | 13.632 | 16.17× | 2,110 |

Every saved event hash matched exactly. Events cover both controller observations
and, at every controller step, actions, full `mjSTATE_INTEGRATION`, acceleration,
constraint forces, sensor values, ordered contacts and step results. The complete
match also hashes the entire final game record. This is bitwise checking of raw
values, not agreement after rounding or simply equal winners. It establishes
parity for these tested trajectories, not a proof for every possible bot.

The existing geometry/contact suites passed **28 tests** with paired reference
and accelerated queries. Native runtime size-limit checks passed **11 tests**.
See `evidence/` for raw reports and regression output, and `comparison.json` for
the table data. Verify these saved results cheaply:

```sh
python scripts/iterative_cpu/verify_evidence.py
python scripts/iterative_cpu/test_install_release.py
```

Only one complete paired match was added for final parity validation. Short
prefixes and captured-state probes were used to locate bottlenecks first.

## Why it helps

One difficult GPT-5.4/Fable prefix spent approximately 94% of reference time
building observations. Its captured state required 283 surface queries, 1,800
simplex calls and 7,085 tiny least-squares solves per pair of observations. The
paired captured-state observation benchmark improved from 0.741 to 0.014 seconds
(53.1×); this microbenchmark is not an end-to-end match speedup.

The existing Cython code removes Python overhead in GJK/simplex traversal and
reuses LAPACK workspaces while retaining the same numerical kernels and order.
The native code caches exact SDF/octree work, batches independent search points
with SIMD, and accumulates contact impulses in their original order. It disables
fast-math and floating-point contraction. Controller execution was a small
fraction of these profiles; rewriting arbitrary generated controllers with JIT
would add semantic risk without addressing the principal observed bottleneck.

Sources and build instructions:
[observation accelerator](../../mjarena/envs/observation_accel/README.md) and
[single-core match accelerator](../../mjarena/envs/match_accel/README.md).

## Build and install

Build the pinned extensions and native library using those instructions on a
compatible Linux x86-64 machine. Keep the native JSON manifest beside its `.so`.
Compiled binaries are deployment artifacts and are not committed here.

```sh
python scripts/iterative_cpu/build_release.py \
  --baseline /path/to/original/frozen/harness \
  --compiled-harness /path/to/harness/with/built/extensions \
  --library /path/to/arena_onecore_v3.so \
  --output /path/to/new/release
python scripts/iterative_cpu/install_release.py /path/to/new/release /path/to/run
```

`validated-release.json` records the exact historical baseline and deployed
artifact hashes. `native-build.json` records compiler, source and SIMD settings.
The packager verifies the frozen baseline, applies `frozen-sumo.patch`, and emits
a new complete manifest. Rebuilt binaries may have different hashes and require
parity validation before use. The installer validates all inputs before copying
and accepts repeated installation of the exact same overlay.

The run must already contain the frozen harness and `tournament/worker.py` that
implements `play(job)`. It must load numerical libraries only after worker
initialization. Set thread environment variables in the parent launcher too.
`fleet_worker.py` enables acceleration before claiming any match. Its three
coordinator URLs are the existing September 24 queues; adapt them for other runs.

`probe.py` is an isolated diagnostic and never submits scores. It expects a root
with `baseline/`, `candidate/`, `native-release/arena_onecore_v3.{so,json}` and
`selected/BOT_ID/recipe.json`; recipes contain processed XML, controller code and
actuator names. Run a short reference/native pair on the same available CPU:

```sh
python scripts/iterative_cpu/probe.py --root /path/to/probe \
  --mode reference --a BOT_A --b BOT_B --cpu 12 --steps 100 --label short-reference
python scripts/iterative_cpu/probe.py --root /path/to/probe \
  --mode native --a BOT_A --b BOT_B --cpu 12 --steps 100 --label short-native
```

Compare `results/LABEL/report.json` event arrays exactly. Use a high step limit
only for the final natural-end parity check.

## Deployment to the running tournaments

The cluster-specific files in this directory reproduce the deployment:

* `rescue_coordinator.py` runs beside the existing September 24 run directories
  on Host A and imports their `leaderboard.py` and `source_coordinator.py`. It
  verifies bot source hashes and prepares bots with the frozen validator.
* The extra queue includes only unfinished within-model selection and iterative
  representative jobs. It never creates sampling-benchmark jobs. Original
  workers continue; original coordinators deduplicate by existing job ID and
  accept the first result. Completed results are retained.
* `rescue_worker.py` connects only to port 8004. `run-rescue-gpu.sh` stages the
  frozen inputs and verified overlay on node-local storage, disables GPUs and
  starts one worker per CPU, recording a durable deployment manifest on NFS.
* Initial deployment: 64 workers each in existing allocations **<job-2>** and
  **<job-3>**, on gpu-node-5 and gpu-node-8. No new allocation was requested.

These scripts depend on those existing run snapshots and protected external
token files. They are operational launch scripts, not a standalone tournament.
The rescue coordinator should stay running: it keeps leases in memory, so
restarting it while workers are active can duplicate computation (original
result submission remains deduplicated). Failed jobs get at most two attempts.

Authoritative run artifacts:
`<scratch>/artifactarena/match-parity-opt-20260924` on the GPU cluster and
`<work-root>/match-parity-opt-20260924` on Host A.
The Host A `rescue/status.json` reports active work, accelerated submissions and
errors. The existing leaderboard updates from accepted results normally.

## Follow-up: prune queries after the nearest 32 are known

The remaining queue was concentrated in Astra, Grok 4.6 and Flash 3.8 matches.
The first accelerated version still evaluated every pair whose bounding-sphere
distance could be within the 2 m proximity cutoff, even after establishing that
the public list would be truncated to 32 entries.

The new version tightens that query bound to the current 32nd distance after at
least 33 qualifying pairs have been found. A skipped pair cannot enter the
nearest list or change the global minimum. Equal-distance ties remain eligible;
conservative slack also retains near-zero and floating-point boundary cases.
The private count becomes a lower bound after pruning; the public truncation
flag, minimum, selected pairs, witnesses and closing speeds remain unchanged.
It does not approximate any returned distances or reduce solver iterations.

On the same CPU, Grok 4.6 revisions 08/10 over 500 controller ticks improved
from **53.774 to 39.157 seconds (1.37× over the first accelerator)**, including
parity instrumentation. Observation time fell from **31.825 to 17.092 seconds
(1.86×)**. All 1,500 event hashes matched. Six alternating captured-state
measurements showed **2.18×** observation speedup. These are prefix and snapshot
measurements, not an extrapolated complete-match speedup.

Final validation also matched all 2,110 events and the final game record of the
complete Fable/Opus match against the frozen reference. That run used a different
CPU, so its wall time is not used for speed claims. The 28 geometry/contact
regressions and five targeted pruning tests passed. `test_top32.py` covers late
global minima, equal-distance ordering, the GJK zero threshold, exactly 32
entries and separated robots. `top32-comparison.json` and `evidence/` retain
the results; `verify_evidence.py` checks them without rerunning matches.

Build the updated `_details` extension and package a new immutable release. The
deployed archive is `release-top32.tar.gz`, with its own manifest. The cluster
launcher `run-rescue-top32-gpu.sh` starts 32 additional workers in the existing
<job-3> allocation; its CPU mask is disjoint from the first accelerated pool.
Each worker still runs on one CPU with GPUs disabled. Existing in-flight games
continue with their original code; the new workers claim pending jobs only.

This optimization primarily helps geometry-heavy observations. A separate
200-substep sample of Astra 01/06 spent 0.450 of 0.479 seconds in sphere/SDF and
cylinder/SDF collisions, so SDF physics remains its dominant bottleneck.
