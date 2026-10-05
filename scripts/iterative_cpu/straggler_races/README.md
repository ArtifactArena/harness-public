# Fresh-seed races for five-hour stragglers

User-authorized on September 24: launch optimized replacements with different
random seeds for old matches, leave existing simulations running, accept the
first valid result, and stop the losing original only after a replacement wins.
This explicitly supersedes the earlier prohibition on new sampling games for
these unfinished stragglers. Completed benchmark matches are not replayed.

Run root on Host A:
`<work-root>/straggler-races-20260924`.
Coordinator: port 8008, tmux `user-straggler-races-20260924`.
NFS: `<scratch>/artifactarena/straggler-races-20260924`.
Workers: existing allocations <job-2> and <job-3> and 12 elements of CPU array <job-4>.
No new allocations or GPUs. Each step selects initially idle physical cores,
reserves them using a host lock, and confines each four-core group to one socket.
One-core workers take light models; four-core workers take at least four SDF
shapes, using the native backend's additional initpoint threshold.

The snapshot contained 186 distinct match IDs from 209 old attempt folders. This
inventory is inferred, not proof that every folder has a live simulator. A
replacement is prepared only when a matching fresh heartbeat is present and the
source has no accepted result. At the recorded check 86 replacements had launched;
47 other IDs already had results and 53 lacked a matching fresh heartbeat. Discovery
continues for the snapshot while originals remain untouched.

The original coordinators on 8001/8002 now journal worker heartbeats and restore
leases after restart. Claims pause for 180 seconds and until initial scanning
finishes. The roster coordinator already had bounded requests, per-result locks
and lease restoration; the same implementation was used for the high-run queue.
The code preserves existing results, including disk results before the in-memory
index is rebuilt. Bot IDs containing periods are accepted as safe filename
components. This validation was fixed after saved replacement uploads returned
400; `recover_uploads.py` resubmits those payloads without rerunning simulations.

Replacement seeds are fresh integers and persist in `races.json`. Worker output
contains the actual new seed. The accepted result retains its original logical
match ID and includes `race.original_seed`, `race.replacement_seed` and the
replacement attempt ID. The source coordinator's per-match lock and durable
result decide the first accepted valid result; duplicate uploads never overwrite
it. These are different-seed results, not numerical parity checks. They should
not be described as having all used the original 7101–7103 seeds.

## Cancellation safety

`control_agent.py` verifies the original PID, Unix owner, process start ticks,
worker command, run directory, match-file timestamp and fresh job heartbeat.
Retired original workers cannot claim another job from their source coordinator.
A worker without that identity evidence is left alone. Some fresh heartbeat
owners are newer fleet copies in a different run directory. The fleet cleanup
resolves their current match folder and retires each worker on both source
coordinators. It then requires a heartbeat newer than retirement before stopping
the verified losing attempt. A fleet supervisor stays stopped until both source
tournaments drain; ordinary supervisors wait for their own tournament.

An abruptly killed ProcessPoolExecutor child would otherwise terminate unrelated
siblings. Before cancelling a verified child, the agent stops only its verified
supervisor with SIGSTOP; sibling match processes continue. A small two-worker
Linux test demonstrated this isolation. The supervisor resumes after its source
tournament drains completely. Stopped-supervisor identities persist in the
control agent's state file. Never resume one early while other required child
matches are active, because the executor will process the broken-child event.

## Progress and validation

Replacement workers report simulation time via ten-second heartbeats. The live
matches page shows replacement badges, both seeds, bots, machine, cores, progress
and ETA. The default view counts only fresh telemetry or a fresh job heartbeat tied to
a live PID in the correct worker pool. Unverified folders have a separate filter;
they can be abandoned attempts or workers without heartbeat coverage. Accepted
results with a still-live copy are explicitly marked cleanup pending. Measured progress is time toward the cap, not a prediction of the
actual early-termination time.

Validated lease recovery, claim retirement, source-result acceptance with dotted
bot IDs, source first-result/durable deduplication, native exact parity from the
four-core release, isolated cancellation and live browser filtering/progress.
The deployed runtime has accepted replacement results and cancelled verified
original workers; this is not merely a prepared configuration.

## Repeat-selection matches

The race service also supports `iterative-23x2-20260924` on port 8006.
`patch_selection_coordinator.py SOURCE OUTPUT` adds authenticated job lookup,
lease inspection, and persistent retirement to the selection coordinator. It
restores runs with active leases first, so recovering an old match does not wait
for validation of the entire roster. Retirement leaves the current simulation
running and rejects only later claims. The selection coordinator already keeps
the first accepted result and rejects late duplicates.

Dedicated workers can use `race_worker.py --once` to exit after one attempted
match and its bounded result-upload retries, releasing their CPU reservation.
The normal fleet behavior is unchanged when this flag is omitted. Choose the
same one- or four-core budget recorded by the race coordinator; a single SDF
shape uses the validated one-core SIMD path.

On September 25, the two requested Astra stragglers were checked against live
heartbeats before launch. Repeat 2 revisions 2 versus 4 finished naturally after
26,733.55 seconds, so its original result was retained without another match.
Repeat 1 revisions 1 versus 2 received a replacement on Host B with seed
1711075644 (original seed 7101), native SIMD and Cython observations. Its original
Host H process remained running with verified cancellation identity. Audit and
launch artifacts are under `astra-straggler-races-20260925` on Host A and Host B.

The selection endpoint changes were checked with a local HTTP server: authorized
lookup, unauthorized rejection, persisted retirement, preservation of the active
job, rejection of a retired worker's next claim, first-result acceptance and late
duplicate rejection. No long physics parity test was needed because the existing
checksum-verified CPU release was used without changing the physics code.
