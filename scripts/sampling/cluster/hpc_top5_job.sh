#!/bin/bash
# Top-5 Round for ONE model whose run winners are already verified (for jobs that ran before the
# model job learned to do it itself): 10 pairings x 11 seeds with telemetry, verified.
#   sbatch -p group_normal --dependency=afterok:<model job> --export=ALL,MODEL=<m>,RUN_ID=<id>,PACK=<pack> scripts/sampling/cluster/hpc_top5_job.sh
#SBATCH --job-name=sh250-top5
#SBATCH --partition=group_normal
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=120G
#SBATCH --output=logs/top5_%j.out
#SBATCH --error=logs/top5_%j.err
set -uo pipefail
W=${W:-$HOME/sh250}; DATA=${SH250_DATA:-<hpc-data>/sh250}; MODEL=${MODEL:?model}; RUN_ID=${RUN_ID:?run id}; PACK=${PACK:-$DATA/20260918-pack-a}; OUT=${OUT:-$DATA/rr-$RUN_ID}
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-0}   # 1 = exact-observation accelerator (validated identical, ~10x faster)
export MUJOCO_GL=disable OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset ARENA_SKIP_MATCH_DATA
cd "${HARNESS:-$W/harness}" || exit 1
[ -f "$OUT/$MODEL/VERIFIED" ] || { echo "$MODEL run winners not verified yet"; exit 2; }
[ -f "$OUT/stage_b/top5/$MODEL/VERIFIED" ] && { echo "already verified"; exit 0; }
echo "$(date -u +%FT%TZ) job=$SLURM_JOB_ID host=$(hostname -s) cpus=$SLURM_CPUS_PER_TASK Top-5 Round for $MODEL"
python scripts/sampling/pool_finals.py --rr "$OUT" --pack "$PACK" --out "$OUT" --n-rollouts "${TOP5_SEEDS:-11}" \
    --n-parallel-matches $(( SLURM_CPUS_PER_TASK / ${TOP5_SEEDS:-11} )) --n-parallel-seeds "${TOP5_SEEDS:-11}" --run-id "$RUN_ID" --models "$MODEL" --stages b1 || exit 4
if python scripts/sampling/verify_pool_rr.py --out "$OUT" --n-rollouts "${TOP5_SEEDS:-11}" --stage b1 "$MODEL" > "$OUT/$MODEL.top5.verify.txt" 2>&1; then
  touch "$OUT/stage_b/top5/$MODEL/VERIFIED"; echo "$(date -u +%FT%TZ) VERIFIED Top-5 Round $MODEL ($(find "$OUT/stage_b/top5/$MODEL" -name 'match_data.json.gz' | wc -l) telemetry files)"
else
  touch "$OUT/stage_b/top5/$MODEL/FAILED"; echo "$(date -u +%FT%TZ) FAILED-VERIFY Top-5 Round $MODEL"; exit 5
fi
