# Selected bots from every completed 10-iteration run

The September 25, 2026 tournament now contains 63 runs: three runs for each of
21 retained models. Grok 4.7 was removed at the user’s request; its original
selection and match files are preserved but excluded from Elo and progress.
MiniMax M3 and Claude Opus 5 are also excluded. The previous 17-model
leaderboard is preserved separately.

`prepare.py` merges historical, roster, and repeat registries (latest run path
wins), recomputes selection standings from all 270 accepted results per run,
checks source/selected-copy hashes, validates the winning robot and controller,
and freezes recipes and provenance. Authorized replacement-race seeds remain
part of the original selection record. Selection uses eligibility, points,
wins, then earlier iteration. Each of 1,953 selected-bot pairs gets seeds 7101,
7102,7103 and both colors: 11,718 games, 372 per bot, 300 simulated seconds.
630 previously completed selected-bot games remain reused after the omission;
the original 64-bot roster reused 720. Those games were reused after exact recipe,
source hash, identity, seed, and side checks.

`coordinator.py` serves port 8003 on Host A. Claims, attempt counts, heartbeat
ownership, outcomes, and compressed recordings are durable. Repeated claims
are idempotent per worker; accepted results win once. Expired leases retry at
most three times. Errors never become synthetic losses. Only the validated
simulation-progress CPU fleet may claim jobs. Expensive SDF pairs use the
existing four-core criterion; all other games use one core. The simulator and
validated CPU acceleration release are unchanged. Elo is the existing batch
Bradley–Terry MAP estimator (independent N(1000,800²) priors, draws=0.5).

Host A run root:
`<work-root>/iterative-length10-round-robin-20260925`

Coordinator tmux: `user-length10-no-grok47-20260925`.
Lab CPU managers: `user-length10-fill-20260925` on each host.
the GPU cluster managers: `user-length10-fill-<job-2>` and
`user-length10-fill-<job-3>`, inside existing CPU allocations.
No new GPU allocations or GPU computation are used.

`fill_cpus.py` checks the durable queue every minute, tops up verified-idle
physical cores through the existing host reservation lock, and caps new work
by available memory. On the GPU cluster it drains completed four-core slots once their
queue empties and releases only acknowledged, exited slots, allowing ordinary
matches to use their cores. The loop is bounded to 24 hours; launchers also
respect Slurm allocation limits. All activity is detached from the laptop.

`deploy_dashboard.py DASHBOARD_PATH` backs up and adds the all-run Elo table,
match progress bar, and measured-progress live source to the existing dashboard.
Run it with `dashboard.js` alongside the script. The new section is independent
of the existing current/historical run-group selector. Ratings are provisional
until all games finish. The existing historical and sampling tables remain.

Validation: coordinator persistence/retry/result tests, core-release ownership
test, complete 64-run selection audit, live result and measured-progress checks,
and actual desktop/mobile browser rendering with all retained rows and no JS errors.
