#!/bin/bash
# After a model's five run tasks (hpc_stage_a.sh) have all VERIFIED: name the run winners
# (top_5_bots.json), mark the model VERIFIED, and play its Top-5 Round (11 seeds, telemetry).
#   sbatch -p group_normal --dependency=afterok:<array job> --export=ALL,MODEL=<m>,RUN_ID=<id>,PACK=<pack> scripts/sampling/cluster/hpc_finalize_job.sh
#SBATCH --job-name=sh250-final
#SBATCH --partition=group_normal
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=120G
#SBATCH --output=logs/final_%j.out
#SBATCH --error=logs/final_%j.err
set -uo pipefail
W=${W:-$HOME/sh250}; DATA=${SH250_DATA:-<hpc-data>/sh250}; MODEL=${MODEL:?model}; RUN_ID=${RUN_ID:?run id}; SEEDS=${SEEDS:-5}; RUNS=${RUNS:-5}
PACK=${PACK:-$DATA/20260918-pack-a}; OUT=${OUT:-$DATA/rr-$RUN_ID}
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-0}
export MUJOCO_GL=disable OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
cd "${HARNESS:-$W/harness}" || exit 1
for k in $(seq 0 $((RUNS - 1))); do
  [ -f "$OUT/$MODEL/g$k/VERIFIED" ] || { echo "$MODEL g$k not verified"; exit 2; }
done
ARENA_SKIP_MATCH_DATA=1 python scripts/sampling/pool_rr.py --root "$PACK" --layout pack --out "$OUT" --model "$MODEL" \
    --n-rollouts "$SEEDS" --run-id "$RUN_ID" --runs "$RUNS" --finalize-runs || exit 3
touch "$OUT/$MODEL/VERIFIED"; echo "$(date -u +%FT%TZ) VERIFIED $MODEL (run winners named)"
unset ARENA_SKIP_MATCH_DATA
python scripts/sampling/pool_finals.py --rr "$OUT" --pack "$PACK" --out "$OUT" --n-rollouts "${TOP5_SEEDS:-11}" \
    --n-parallel-matches $(( SLURM_CPUS_PER_TASK / ${TOP5_SEEDS:-11} )) --n-parallel-seeds "${TOP5_SEEDS:-11}" --run-id "$RUN_ID" --models "$MODEL" --stages b1 || exit 4
if python scripts/sampling/verify_pool_rr.py --out "$OUT" --n-rollouts "${TOP5_SEEDS:-11}" --stage b1 "$MODEL" > "$OUT/$MODEL.top5.verify.txt" 2>&1; then
  touch "$OUT/stage_b/top5/$MODEL/VERIFIED"; echo "$(date -u +%FT%TZ) VERIFIED Top-5 Round $MODEL ($(find "$OUT/stage_b/top5/$MODEL" -name 'match_data.json.gz' | wc -l) telemetry files)"
else
  touch "$OUT/stage_b/top5/$MODEL/FAILED"; echo "$(date -u +%FT%TZ) FAILED-VERIFY Top-5 Round $MODEL"; exit 5
fi
