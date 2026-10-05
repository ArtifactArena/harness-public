#!/bin/bash
# Stage A driver for the SH-250 pool tournament on a our lab host (no scheduler): one model at a
# time, N parallel matches, resumable, a VERIFIED/FAILED marker per model.
# Run inside tmux:  tmux new -d -s sh250 "bash run_pool_rr.sh <run-id> <n-rollouts> <parallel> <pack> <out> model..."
#
# usage: [RUNS=5] run_pool_rr.sh <run-id> <n-rollouts> <n-parallel-matches> <pack dir> <out dir> [models...]
#   models default to every model dir in <pack> except claude-opus-4-7-high (killed at 27 samples).
set -uo pipefail
RUN=${1:?run id}; N=${2:?n rollouts}; PAR=${3:?n parallel matches}; PACK=${4:?pack dir}; OUT=${5:?out dir}; shift 5
RUNS=${RUNS:-5}   # the model's samples are RUNS independent runs; full round robin inside each
W=/tmp/kush-sh250
mkdir -p "$OUT"
export MUJOCO_GL=egl ARENA_SKIP_MATCH_DATA=1 PYTHONNOUSERSITE=1
PY=$W/venv/bin/python
cd "$W/harness" || { echo "no harness tree at $W/harness"; exit 1; }   # config paths (configs/rules/rules.yaml) are repo-relative
if [ $# -gt 0 ]; then MODELS="$*"; else
  MODELS=$(ls "$PACK" | grep -v -e MANIFEST -e sampling_prompt -e claude-opus-4-7-high | tr '\n' ' ')
fi
echo "$(date -u +%FT%TZ) host=$(hostname -s) run=$RUN seeds=$N parallel=$PAR sha=$(cat $W/harness/SHIPPED_SHA) models: $MODELS"
for m in $MODELS; do
  if [ -f "$OUT/$m/VERIFIED" ]; then echo "$(date -u +%FT%TZ) $m already verified, skip"; continue; fi
  echo "$(date -u +%FT%TZ) START $m"
  $PY $W/harness/scripts/sampling/pool_rr.py --root "$PACK" --layout pack --out "$OUT" --model "$m" \
      --n-rollouts "$N" --n-parallel-matches "$PAR" --run-id "$RUN" --runs "$RUNS" > "$OUT/$m.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then echo "$(date -u +%FT%TZ) FAILED-RUN $m rc=$rc (see $OUT/$m.log)"; touch "$OUT/$m/FAILED" 2>/dev/null; continue; fi
  ok=1
  for k in $(seq 0 $((RUNS - 1))); do
    if $PY $W/harness/scripts/sampling/verify_pool_rr.py --out "$OUT" --model "$m" --n-rollouts "$N" --group "$k" > "$OUT/$m.g$k.verify.txt" 2>&1; then
      touch "$OUT/$m/g$k/VERIFIED"
    else
      ok=0; touch "$OUT/$m/g$k/FAILED" 2>/dev/null; echo "$(date -u +%FT%TZ) FAILED-VERIFY $m g$k (see $OUT/$m.g$k.verify.txt)"
    fi
  done
  if [ $ok = 1 ]; then touch "$OUT/$m/VERIFIED"; rm -f "$OUT/$m/FAILED"; echo "$(date -u +%FT%TZ) DONE $m (all $RUNS runs verified)"
  else touch "$OUT/$m/FAILED"; fi
done
echo "$(date -u +%FT%TZ) ALL_MODELS_DONE host=$(hostname -s)"
