#!/bin/bash
# Mirror what is running on the HPC cluster to the laptop and rebuild the status page. Runs in a loop.
#   hpc_mirror.sh <run-id> <local dir> [interval s]
# Writes <local dir>/{slurm.json, rr/, qual/, logs/} — the inputs of scripts/sampling/rr_dashboard.py --hpc.
set -uo pipefail
RUN_ID=${1:?run id}; L=${2:?local dir}; EVERY=${3:-300}
ES="ssh -o BatchMode=yes -o ConnectTimeout=20 -S $HOME/.ssh/cm_socket/hpc user@hpc-login.example.org"
WT=<arena-checkout>/.claude/worktrees/upload-main
PY=$HOME/miniconda3/envs/arena/bin/python
mkdir -p "$L/rr" "$L/qual" "$L/logs"
while true; do
  # 1. SLURM state + the array plan, as JSON
  $ES "squeue -u user -h -o '%i|%A|%K|%j|%T|%P|%C|%N|%M|%l|%r' || echo '---SSHFAIL---'; echo '---PLAN-A---'; cat ~/sh250/plan-a.txt 2>/dev/null; echo '---PLAN-Q---'; cat ~/sh250/plan-q.txt 2>/dev/null; echo '---PLAN-M---'; cat ~/sh250/plan-m.txt 2>/dev/null; echo '---SACCT---'; sacct -u user -S \$(date -d '-3 days' +%F) -n -P -o JobID,JobName,State,Elapsed,NodeList,ExitCode 2>/dev/null | grep -E 'sh250' | grep -vE '\.(batch|extern)'" 2>/dev/null > "$L/slurm.raw"
  if [ ! -s "$L/slurm.raw" ] || grep -q -- '---SSHFAIL---' "$L/slurm.raw"; then
    echo "$(date -u +%H:%M:%SZ) cluster unreachable — keeping the previous snapshot"; sleep "$EVERY"; continue
  fi
  $PY - "$L" "$RUN_ID" <<'EOF'
import json, sys, datetime
L, run_id = sys.argv[1], sys.argv[2]
raw = open(f"{L}/slurm.raw").read()
q, plan_a, plan_q, sacct = raw.split("---PLAN-A---")[0], "", "", ""
rest = raw.split("---PLAN-A---")[1] if "---PLAN-A---" in raw else ""
if "---PLAN-Q---" in rest:
    plan_a, rest = rest.split("---PLAN-Q---")
plan_m = ""
if "---PLAN-M---" in rest:
    rest, tail = rest.split("---PLAN-M---")
    plan_q = rest
    if "---SACCT---" in tail:
        plan_m, sacct = tail.split("---SACCT---")
elif "---SACCT---" in rest:
    plan_q, sacct = rest.split("---SACCT---")
jobs = {}
for line in sacct.strip().splitlines():                      # finished jobs first (sacct), squeue overrides
    p = line.split("|")
    if len(p) < 6: continue
    jid, name, state, elapsed, node, exit_ = p[:6]
    if "[" in jid: continue                                   # sacct lists a pending array as 12345_[1-55]; squeue expands it below
    aj, _, ai = jid.partition("_")
    jobs[jid] = {"job_id": jid, "array_job": aj, "array_index": int(ai) if ai.isdigit() else None, "name": name,
                 "state": state.split()[0], "partition": "", "cpus": 0, "node": node, "elapsed": elapsed,
                 "time_limit": "", "reason": exit_}
for line in q.strip().splitlines():
    p = line.split("|")
    if len(p) < 11: continue
    jid, aj, ai, name, state, part, cpus, node, elapsed, limit, reason = p[:11]
    if "[" in jid:            # a pending array range "12345_[3-55]": expand
        base = jid.split("_")[0]; rng = jid[jid.index("[")+1:jid.index("]")]
        for chunk in rng.split(","):
            chunk = chunk.split("%")[0]
            lo, _, hi = chunk.partition("-"); hi = hi or lo
            for i in range(int(lo), int(hi) + 1):
                jobs[f"{base}_{i}"] = {"job_id": f"{base}_{i}", "array_job": base, "array_index": i, "name": name,
                                       "state": state, "partition": part, "cpus": int(cpus), "node": "", "elapsed": "00:00",
                                       "time_limit": limit, "reason": reason}
        continue
    jobs[jid] = {"job_id": jid, "array_job": aj, "array_index": int(ai) if ai.isdigit() and ai != "N/A" else None,
                 "name": name, "state": state, "partition": part, "cpus": int(cpus) if cpus.isdigit() else 0,
                 "node": node, "elapsed": elapsed, "time_limit": limit, "reason": reason}
plan = {"stage_a": [], "qual": [], "model": []}
for line in plan_m.strip().splitlines():
    jid, _, m = line.strip().partition(" ")
    if jid: plan["model"].append({"job_id": jid, "model": m.strip()})
for i, line in enumerate(plan_a.strip().splitlines(), start=1):
    m, _, k = line.strip().partition(" ")
    if m: plan["stage_a"].append({"index": i, "model": m, "run": int(k)})
for line in plan_q.strip().splitlines():
    jid, _, models = line.strip().partition(" ")
    if jid: plan["qual"].append({"job_id": jid, "models": models.split()})
# keep only live attempts: anything in the queue, plus finished jobs that belong to the current plans;
# cancelled or superseded attempts are history, not status
live = {j["job_id"] for j in plan["model"]} | {j["job_id"] for j in plan["qual"]}
def keep(j):
    if j["state"].startswith("CANCELLED"): return False
    if j["job_id"] in live: return True
    if j["name"] == "sh250-a": return j["array_job"] in {x["job_id"].split("_")[0] for x in plan["model"]} or j["state"] in ("PENDING", "RUNNING")
    return j["state"] in ("PENDING", "RUNNING")
jobs = {k: j for k, j in jobs.items() if keep(j)}
json.dump({"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "user": "user", "run_id": run_id, "jobs": sorted(jobs.values(), key=lambda j: (j["name"], j["array_index"] or 0)),
           "plan": plan}, open(f"{L}/slurm.json", "w"), indent=1)
EOF
  # 2. results + status files (small files only; telemetry stays on the cluster until the final pull)
  rsync -az --timeout=120 -e "ssh -o BatchMode=yes -S $HOME/.ssh/cm_socket/hpc" \
    --include='*/' --include='*.json' --include='VERIFIED' --include='FAILED' --include='SHIPPED_SHA' --include='*.txt' --exclude='*' \
    --delete "user@hpc-login.example.org:${REMOTE_DATA:-<hpc-data>/sh250}/rr-$RUN_ID/" "$L/rr/" 2>/dev/null     # --delete: cleared markers disappear here too
  rsync -az --timeout=60 -e "ssh -o BatchMode=yes -S $HOME/.ssh/cm_socket/hpc" \
    "user@hpc-login.example.org:sh250/harness/SHIPPED_SHA" "$L/rr/SHIPPED_SHA" 2>/dev/null
  rsync -az --timeout=120 -e "ssh -o BatchMode=yes -S $HOME/.ssh/cm_socket/hpc" \
    --include='STATUS-qual-*.md' --include='progress.jsonl' --exclude='*' \
    "user@hpc-login.example.org:sh250/20260918-gen/" "$L/qual/" 2>/dev/null
  rsync -az --timeout=120 -e "ssh -o BatchMode=yes -S $HOME/.ssh/cm_socket/hpc" \
    "user@hpc-login.example.org:${REMOTE_DATA:-<hpc-data>/sh250}/logs/" "$L/logs/" 2>/dev/null
  # 3. the page
  (cd "$WT" && $PY scripts/sampling/rr_dashboard.py --hpc "$L" --pack LOGS-SH250/20260918-pack-a --out SH250_RR.html --md SH250_RR.md >/dev/null 2>&1) \
    && echo "$(date -u +%H:%M:%SZ) page rebuilt ($(wc -l < "$L/slurm.raw") slurm lines)" || echo "$(date -u +%H:%M:%SZ) dashboard render failed"
  sleep "$EVERY"
done
