#!/bin/bash
# SH-250 Top Bot per Run Round on the HPC cluster: ONE job per model, many cores. Plays the model's
# five runs of 50 back to back (full round robin inside each run, N seeds), verifies each run,
# then writes the model's run winners (top_5_bots.json). Resumable: resubmit and finished pairings are skipped.
#
#   sbatch -p group_low --export=ALL,MODEL=gpt-5.5,RUN_ID=<id>,PACK=~/sh250/20260918-pack-a scripts/sampling/cluster/hpc_model_job.sh
#
#SBATCH --job-name=sh250-model
#SBATCH --partition=group_low
#SBATCH --time=23:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=96
#SBATCH --mem=180G
#SBATCH --output=logs/model_%j.out
#SBATCH --error=logs/model_%j.err
set -uo pipefail
W=${W:-$HOME/sh250}
DATA=${SH250_DATA:-<hpc-data>/sh250}   # data root (packs, rr-<run>, logs): NOT $HOME — the home quota filled up on 2026-09-22
MODEL=${MODEL:?model}; RUN_ID=${RUN_ID:?run id}; SEEDS=${SEEDS:-5}; RUNS=${RUNS:-5}
PACK=${PACK:-$DATA/20260918-pack-a}; OUT=${OUT:-$DATA/rr-$RUN_ID}
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-0}   # 1 = exact-observation accelerator (validated identical, ~10x faster)
export MUJOCO_GL=disable ARENA_SKIP_MATCH_DATA=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
cd "${HARNESS:-$W/harness}" || exit 1
mkdir -p "$OUT"
echo "$(date -u +%FT%TZ) job=$SLURM_JOB_ID host=$(hostname -s) cpus=$SLURM_CPUS_PER_TASK model=$MODEL seeds=$SEEDS runs=$RUNS sha=$(cat SHIPPED_SHA)"
if [ -f "$OUT/$MODEL/VERIFIED" ]; then echo "already verified"; exit 0; fi
python scripts/sampling/pool_rr.py --root "$PACK" --layout pack --out "$OUT" --model "$MODEL" \
    --n-rollouts "$SEEDS" --n-parallel-matches $(( SLURM_CPUS_PER_TASK / SEEDS )) --n-parallel-seeds "$SEEDS" --run-id "$RUN_ID" --runs "$RUNS"
rc=$?
if [ $rc -ne 0 ]; then echo "$(date -u +%FT%TZ) FAILED-RUN $MODEL rc=$rc"; touch "$OUT/$MODEL/FAILED" 2>/dev/null; exit $rc; fi
ok=1
for k in $(seq 0 $((RUNS - 1))); do
  if python scripts/sampling/verify_pool_rr.py --out "$OUT" --model "$MODEL" --n-rollouts "$SEEDS" --group "$k" > "$OUT/$MODEL.g$k.verify.txt" 2>&1; then
    touch "$OUT/$MODEL/g$k/VERIFIED"; rm -f "$OUT/$MODEL/g$k/FAILED"
  else
    ok=0; touch "$OUT/$MODEL/g$k/FAILED" 2>/dev/null; echo "$(date -u +%FT%TZ) FAILED-VERIFY $MODEL g$k"
  fi
done
if [ $ok = 1 ]; then touch "$OUT/$MODEL/VERIFIED"; rm -f "$OUT/$MODEL/FAILED"; echo "$(date -u +%FT%TZ) VERIFIED $MODEL (all $RUNS runs)"; else touch "$OUT/$MODEL/FAILED"; exit 3; fi
# Top-5 Round for this model right away: its five run winners at 11 seeds WITH telemetry (match_data.json.gz)
unset ARENA_SKIP_MATCH_DATA
python scripts/sampling/pool_finals.py --rr "$OUT" --pack "$PACK" --out "$OUT" --n-rollouts "${TOP5_SEEDS:-11}" \
    --n-parallel-matches $(( SLURM_CPUS_PER_TASK / ${TOP5_SEEDS:-11} )) --n-parallel-seeds "${TOP5_SEEDS:-11}" --run-id "$RUN_ID" --models "$MODEL" --stages b1
rc=$?
if [ $rc -ne 0 ]; then echo "$(date -u +%FT%TZ) FAILED Top-5 Round $MODEL rc=$rc"; exit 4; fi
if python scripts/sampling/verify_pool_rr.py --out "$OUT" --n-rollouts "${TOP5_SEEDS:-11}" --stage b1 "$MODEL" > "$OUT/$MODEL.top5.verify.txt" 2>&1; then
  touch "$OUT/stage_b/top5/$MODEL/VERIFIED"; echo "$(date -u +%FT%TZ) VERIFIED Top-5 Round $MODEL ($(find "$OUT/stage_b/top5/$MODEL" -name 'match_data.json.gz' | wc -l) telemetry files)"
else
  touch "$OUT/stage_b/top5/$MODEL/FAILED"; echo "$(date -u +%FT%TZ) FAILED-VERIFY Top-5 Round $MODEL"; exit 5
fi
