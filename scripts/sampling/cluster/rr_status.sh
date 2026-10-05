#!/bin/bash
# Progress of a Stage A run on this host: per model done/expected pairings and the driver's last lines.
# usage: rr_status.sh <out dir>
OUT=${1:?out dir}
python3 - "$OUT" <<'EOF'
import json, os, sys, glob, time
out = sys.argv[1]
rows = []
for led in sorted(glob.glob(os.path.join(out, "*", "pool_ledger.json"))):
    d = os.path.dirname(led); m = os.path.basename(d)
    L = json.load(open(led)); E = L["eligible"]; exp = E * (E - 1) // 2
    done = sum(1 for _ in glob.glob(os.path.join(d, "matches", "*", "match_result.json")))
    state = "VERIFIED" if os.path.exists(os.path.join(d, "VERIFIED")) else ("FAILED" if os.path.exists(os.path.join(d, "FAILED")) else "running" if done < exp else "done")
    rows.append((m, E, done, exp, state))
print(f"{'model':28} {'bots':>4} {'pairings':>16} state")
for m, E, done, exp, st in rows:
    print(f"{m:28} {E:4} {done:7}/{exp:<8} {st}")
print("total pairings done:", sum(r[2] for r in rows), "/", sum(r[3] for r in rows))
EOF
echo "--- driver"; ls "$OUT"/*.driver.log >/dev/null 2>&1 && tail -n 3 "$OUT"/*.driver.log
echo "--- host"; uptime; df -h "$OUT" | tail -1
