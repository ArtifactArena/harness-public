# Four-core SDF execution

The optional `build.py --parallel` backend combines the existing SIMD kernel,
conservative rejection and exact SDF cell cache with OpenMP over independent
collision pairs. Contacts are emitted in the original MuJoCo order. The cached
pair result is accepted only when both poses and the margin match exactly.
Other collision types remain serial. Unsupported models use the stock fallback.

The Python installer supports `threads=1` (default) or `threads=4`. Four-core
workers must be confined to four distinct physical cores in one socket. Within
these workers, models with at least four SDF geoms and 16 initial search points
use four threads; lighter models use one. Fewer than four candidate collision
pairs execute serially. This is an initial heuristic based on the measured
Astra cases, not a universal prediction of speedup.

Set `MATCH_CPU_BUDGET=4` before `cpu_acceleration.enable(index)`. The launcher's
CPU mask must contain four nonoverlapping physical cores per worker. The worker
sets OpenMP places and binding before loading the library. Do not use this pool
for throughput-heavy backlogs if the extra cores could run independent matches.
No GPUs are used. Existing workers are not modified or restarted.

## Validation

The prototype ran 30 comparisons: three SDF-heavy scenes, five core counts,
two repeats of 1,000 physics substeps, byte-for-byte integration state, forces
and contact fields after each step. Four-core physics speedups versus the latest
single-core SIMD/rejection backend were 1.92x, 1.51x and 1.44x. The production
build additionally passed 1,000-substep comparisons on all three scenes.

Actual controllers: Astra 02 vs Flash champion (seed 7102, red) matched all 900
recorded events over 300 ticks. Fable 51 vs Opus (seed 7101, red) matched the
frozen reference for a complete 703-tick match, including all 2,110 events and
the result; this case exercised serial fallback. No complete long SDF-heavy
match was replayed solely for validation. Full-match four-core parity remains
less thoroughly tested than the one-core backend.

Build hash: `62d58f48e139e33d061359eba0cc869d13f033f61f5f647940a73b4bca3ff694`.
Evidence is in `evidence/sdf-parallel4-*.json`. Controller timings ran on a
different host from the saved reference; do not interpret their ratio as speedup.

## Deployment on September 24

the GPU cluster node8, existing allocation <job-3>, four worker slots and 16 initially idle
physical cores. The release lives at
`<local>/artifactarena/iterative-cpu-parallel4-20260924/<job-3>`.
NFS run directory:
`<scratch>/artifactarena/sdf-multicpu-20260924`.
The rescue coordinator on Host A port8007 only queues unfinished selection and
iterative representative matches; it never creates or replays sampling games.
Original coordinators retain first-result deduplication.

All four worker processes were inspected: each loaded the expected binary hash,
used exactly four CPU affinities including helper threads, and the four masks
were disjoint. See the deployment evidence. Progress instrumentation wraps
`SumoEnv.step`, reads simulation time after the original step, and publishes
snapshots via the rescue heartbeat; it does not change physics or observations.
