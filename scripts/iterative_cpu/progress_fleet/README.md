# Progress-required tournament workers

All new claims on the high (8001), roster (8002), and 23×2 (8006) queues now
require `X-Match-Progress: simulation-v1`. Each coordinator has a
`tournament/require_progress` marker. Legacy workers finish their current
simulation and receive `finished: true` on their next claim. Existing matches
are not restarted for telemetry.

`patch_coordinator.py` installs the capability check, 1/4-core job selection,
and progress recording using `progress_protocol.py`. Run it against the current
coordinator and copy the helper alongside it. Keep the existing lease recovery
and result deduplication logic. New claims resume after the 180-second recovery
window even while the candidate scan continues. The original coordinator
snapshots are preserved on Host A under `progress-workers-20260924`.

`progress_worker.py` reuses the validated `MatchProgress` observer: it samples
MuJoCo simulation time after the existing step and sends a heartbeat every ten
seconds. The initial heartbeat identifies initialization before the first step.
The dashboard merges these snapshots with legacy inventory and removes completed
jobs. Progress is simulated time divided by the match limit; ETA uses measured
simulation speed and disappears if samples become stale. Early termination can
finish before the bar reaches 100%.

`launch_worker.py` installs the existing validated SIMD/SDF/Cython release into
an isolated the GPU cluster or lab run. It reserves distinct idle physical cores through the same
host lock as the earlier race pools. The native library is unchanged. Jobs with
at least four SDF geoms use the four-core pool; other jobs use one core. All
workers disable GPU use.

Deployment root on NFS:
`<scratch>/artifactarena/progress-workers-20260924`.
Initial production pools: <job-2>.93 (12 × 4 cores), <job-2>.94 (32 × 1 core),
<job-3>.34 (12 × 4 cores), <job-3>.35 (32 × 1 core). These are CPU-only steps in
existing owned allocations; no new allocations were requested. Old completed
replacement pools were stopped first. The per-step deployment manifests record
host, CPUs, worker counts and roots. Current workers retain the initial worker
snapshot; the launcher source also removes the historical early-exit shortcut
based solely on the separate leaderboard and isolates subsequent roots by step.

Tests cover capability rejection, source lease/result recovery, one/four-core
classification, rejection of progress from the wrong worker, dashboard removal
of completed jobs, and preservation of step results by the observer. Production
telemetry and browser checks verify actual simulation progress advances.

## Recovery on 2026-09-25 (UTC)

All four initial progress pools failed with `OUT_OF_MEMORY`: their 96 GiB
step limits were exhausted and `ProcessPoolExecutor` propagated a child failure
to the whole pool. The selection coordinator had 7,204 completed matches,
5,562 pending matches and only two active matches despite two idle allocations.

The worker now supervises independent processes and recycles each child after
one match. A child crash cannot terminate its siblings; three consecutive
crashes disable that slot instead of retrying forever. Simulation, policies,
seeds, result deduplication and the validated numerical overlay are unchanged.

Initial recovery steps within the existing CPU-only allocations:

| Steps | Initial workers per step | Memory limit per step |
| --- | --- | --- |
| <job-2>.96, <job-3>.37 | 96 × 1 physical core | 768 GiB |
| <job-2>.97, <job-3>.38 | 8 × 4 physical cores | 384 GiB |

Use `--oom-kill-step=0` so a single OOM victim does not cancel the whole step.
The ordinary pools used approximately 34–37 GiB and the SDF pools 4–6 GiB
at the first sustained post-recovery sample. No GPU or new allocation was used.

As the ordinary queue drained, slots were retired between matches and their
cores reassigned to SDF pools: <job-2>.103 (12 × 4), <job-3>.44 (11 × 4),
<job-2>.107 (9 × 4), and <job-3>.48 (11 × 4). Thus the GPU cluster supports 59 concurrent
four-core SDF matches while the last ordinary matches drain. These are maximum
pool capacities, not a claim that every slot always has a runnable job.

Lab deployment root:
`<work-root>/progress-workers-20260925` on each host.
The measured-idle-core launcher selected 48 ordinary slots and one four-core
slot on Host B; 24 ordinary slots each on Host H, Host D and Host G;
26 on Host F; and four on memory-limited Host I. Lab launches use `nice -n 10`.
Host A and Host C were busy; Host E had load over 1,400 and was excluded.
New jobs remain progress-capable and the workers wait for newly generated bots.

For lab launch, specify `--stage-dir`, `--run-root`, `--lock-root` and
`--token-file`. The stage directory contains the three immutable archives,
`install_release.py`, `selection_worker.py`, `progress_worker.py`, and the
launcher. Use the validated Python 3.10 / NumPy 2.1.3 / MuJoCo 3.10.0 environment.
Host F uses a user-local copy of Host D's Python 3.10.12 and package files at
`<envs-root>/iterative-roster-mj310-portable-20260925`;
the runtime/BLAS and overlay guards passed there. CPUs without AVX-512 retain
the validated Cython observation path. Hybrid CPU sibling ranges such as `0-1`
are parsed correctly. Reservations record process start ticks and ignore zombies.

## Draining and verification

`drain_slots.py MANIFEST UPDATED_WORKER --count 48` requests retirement of 48
additional one-core slots, in four-core groups per socket. It never signals a
match: workers acknowledge retirement between jobs, exit, and only then are
their reserved cores released under the host lock. Repeated invocations extend
the request; a per-manifest lock prevents concurrent drain controllers. A
30-minute timeout preserves partial progress and reports the unfinished drain.
Inspect the `*-drain.json` report before launching another pool. Existing
pre-retirement worker processes must first finish a match to load this feature;
idle legacy children need a separately verified idle-only migration.

Operational recovery logs, deployment manifests and the lease-checked idle
migration audit are under the NFS deployment root. The latter retired only
exact owned children verified to have no lease after freezing; a rollback timer
resumed any untouched children. Active matches were preserved.

Run `python3 -m unittest discover -s scripts/iterative_cpu/progress_fleet -p
'test_*.py'`. Seven tests cover protocol gates, classification, bounded child
recovery, sibling isolation, retirement acknowledgements, and refusing to release
a still-running child's core. The Linux-only process check passed separately on
Slurm login; it is skipped on macOS. Production checks
also verified accepted results, advancing dashboard telemetry and safe memory
usage. Within the recovery session the completed total passed 12,700 with no
coordinator worker errors. Recent child IDs inflate the legacy `workers` counter;
use `active_matches` and fresh confirmed telemetry for actual concurrency.
