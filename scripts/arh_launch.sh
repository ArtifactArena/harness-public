#!/usr/bin/env bash
# AutoResearch redo launcher: N independent refine-50 lineages per model, build phase only.
# Each lineage is one run_baseline_agent process (1 iteration, 50 full-feedback commits).
#
# Usage: scripts/arh_launch.sh [N_LINEAGES=5] [MAX_PARALLEL=12]
#   CONFIG=configs/tournaments/arh.yaml (override with CONFIG=...)
#   PY=python interpreter (default: $HOME/miniconda3/envs/arena/bin/python)
#   MUJOCO_GL: leave unset on macOS; export MUJOCO_GL=egl on a headless Linux cluster.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HOME/miniconda3/envs/arena/bin/python}"
CONFIG="${CONFIG:-configs/tournaments/arh.yaml}"
N="${1:-5}"
MAX_PARALLEL="${2:-12}"
DATE_TAG="$(date +%Y%m%d)"
ROOT="$REPO/LOGS-ARH/$DATE_TAG/arh"
mkdir -p "$ROOT"

cd "$REPO" || exit 1
# The model list comes from the config itself, so the launcher and the run cannot drift.
MODELS=$("$PY" - "$CONFIG" <<'PYEOF'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
for p in cfg["llms"]:
    print(p)
PYEOF
)
[ -n "$MODELS" ] || { echo "[arh] no llms in $CONFIG"; exit 1; }
echo "[arh] $(echo "$MODELS" | wc -l | tr -d ' ') models x $N lineages, max $MAX_PARALLEL parallel, root=$ROOT"

launch() {  # $1 = model config path, $2 = lineage index
  local stem; stem="$(basename "$1" .yaml)"
  local out="$ROOT/$stem/c$2"
  mkdir -p "$out"
  MUJOCO_GL="${MUJOCO_GL-}" "$PY" run_baseline_agent.py \
    --config "$CONFIG" --llms "$1" \
    --iterations 1 --build-only \
    --output-dir "$out" > "$out.log" 2>&1
  echo "[arh] $stem c$2 exit=$?"
}

# Block until fewer than MAX_PARALLEL lineages are running.
#
# `wait -n` needs bash >= 4.3. macOS ships bash 3.2, where it prints
# "wait: -n: invalid option" and returns immediately (rc=2) instead of waiting:
# the cap was ignored and all 24 models x 5 lineages launched at once. Poll the
# job table there instead.
if [ "${BASH_VERSINFO[0]}" -gt 4 ] || { [ "${BASH_VERSINFO[0]}" -eq 4 ] && [ "${BASH_VERSINFO[1]}" -ge 3 ]; }; then
  throttle() { [ "$(jobs -pr | wc -l | tr -d ' ')" -ge "$MAX_PARALLEL" ] && wait -n; return 0; }
else
  throttle() {
    while [ "$(jobs -pr | wc -l | tr -d ' ')" -ge "$MAX_PARALLEL" ]; do sleep 5; done
  }
fi

for model in $MODELS; do
  j=0
  while [ "$j" -lt "$N" ]; do
    throttle
    launch "$model" "$j" &
    j=$((j+1))
  done
done
wait
echo "[arh] ALL LINEAGES DONE"
