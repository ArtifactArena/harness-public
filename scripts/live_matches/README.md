# Live match dashboard

Deployed at http://host-a.example.org:8000/matches.html alongside the existing
iterative bot zoo viewer. The viewer's homepage links to this separate page.

`collector.py` runs read-only, every30seconds, in the existing the GPU cluster allocations
and lab-host user sessions. It sends a small inventory to the viewer's
authenticated `/api/match-inventory` endpoint. Credentials are read from an
external protected token file; the public GET response contains only match
metadata. Collectors do not inspect controller source, credentials, or other
users' processes. `live_matches.py` combines the per-host inventories with the
four-core coordinator's progress snapshots. The browser refreshes every10seconds.

`matches.html` and `matches.js` provide search, host/mode filtering and sorting,
responsive layouts, elapsed time, both bots and sides, seed, machine, acceleration,
simulation progress, and ETA. ETA is extrapolated to the configured time limit
using simulation time divided by observed wall time, including initialization.
An early ring-out can finish sooner; stale telemetry suppresses ETA.

## Coverage limitations

Legacy worker processes do not publish their current Python job or simulation
time. Their rows are inferred from unfinished match folders under a live worker
pool, and may include abandoned attempts. They are explicitly marked inferred;
progress and ETA remain unavailable. Separate attempts of the same match remain
visible. Inaccessible machines and reports older than120seconds are marked stale.
The initial rollout reached14of15target machines; Host E's collector setup
could not complete through the existing SSH routes. No live match was interrupted.

The dashboard's existing `server.py` imports `state` from `live_matches.py`, serves
`GET /api/live-matches`, whitelists `/matches.html` and `/matches.js`, and accepts
`POST /api/match-inventory` only with the existing tournament Bearer token.
Inventories are stored atomically in its private `live-data/` directory, which
is not exposed as a static route. See `install_dashboard.py` for the exact overlay.

Desktop/mobile browser checks passed with actual live data, four-core filter,
search-empty state, progress ARIA attributes and no horizontal mobile overflow
or JavaScript errors. The page does not claim legacy discovery is precise
per-process telemetry.

## New tournament coverage and duplicate cleanup

The September 24 follow-up adds the 23×2 tournament to confirmed activity.
`23x2-coordinator.py` journals claims and heartbeats, clears finished leases,
restores active assignments during startup, and accepts durable result uploads
while its candidate scan is still rebuilding. Claims wait for a 180-second
heartbeat recovery window, then can resume while the scan continues. They do
not wait for every bot to be validated. Regression tests cover startup recovery,
duplicate result preservation, claim visibility, and completed lease removal.

On deployment, 47 additional accepted-result duplicate workers were retired
on both original source queues and stopped after fresh identity checks. Their
supervisors were already isolated, preserving unrelated sibling simulations.
Receipts are stored on Host A under
`straggler-races-20260924/remaining-duplicates/`. All 47 disappeared from fresh
active-worker inventories; the browser showed zero cleanup-pending rows and
confirmed rows from the newer tournament.

## Tool-use coverage

Tool-use selection is included through `design-lab-23x2-20260924` leases and
collectors that recognize workers running from `source/` as well as `harness/`.
The selection coordinator persists claims/heartbeats and restores fresh leases
after a service reload; active simulations are never restarted for telemetry.
`patch_tool_selection.py KIND SOURCE OUTPUT` generates the coordinator, worker,
or engine overlay. Install `tool_seed_progress.py` as
`mjarena/live_seed_progress.py` alongside each patched engine before activating
it; existing sandbox calls keep the engine code already loaded in memory.

`tool_use_inventory.py` identifies live sandbox tool processes by their bound
workspace inode and the current invocation marker. It reports `run_match`,
qualification and save-time qualification, excluding ordinary file tools and
provider requests. Old invocations appear explicitly as batches with unavailable
progress and core count. `tool_seed_progress.py` connects to the engine's existing
progress callback for future invocations, preserving the original listener and
simulation results. It saves per-seed progress at most every five seconds and on
completion, without scores. The collector maps namespace PIDs back to live host
PIDs, excludes completed/stale seeds, and the dashboard displays their measured
progress and ETA. A dead process or stale host inventory cannot confirm a match.

Deployment scripts and before/after manifests for the September 25 rollout live
under `<work-root>/tool-use-live-matches-20260925` on
Host A and Host B. The rollout reloads only collectors, the dashboard, and the
selection coordinator; workers keep their running simulations.
