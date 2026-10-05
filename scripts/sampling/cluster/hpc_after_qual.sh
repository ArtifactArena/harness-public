#!/bin/bash
# Runs on HPC AFTER the Qualification Round jobs (dependency afterok): pack the freshly
# qualified models from the generation root, append their runs to the plan, submit their tasks.
#
#   sbatch --dependency=afterok:<qual job ids> --export=ALL,RUN_ID=<id>,MODELS="a b c" scripts/sampling/cluster/hpc_after_qual.sh
#
#SBATCH --job-name=sh250-pack
#SBATCH --partition=shared_normal
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/pack_%j.out
#SBATCH --error=logs/pack_%j.err
set -euo pipefail
W=${W:-$HOME/sh250}; DATA=${SH250_DATA:-<hpc-data>/sh250}; RUN_ID=${RUN_ID:?run id}; MODELS=${MODELS:?models}; SEEDS=${SEEDS:-5}; RUNS=${RUNS:-5}
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-0}   # 1 = exact-observation accelerator (validated identical, ~10x faster)
export MUJOCO_GL=disable
cd "${HARNESS:-$W/harness}"
echo "$(date -u +%FT%TZ) packing: $MODELS"
rm -rf "$W/20260918-pack-b"
python scripts/sampling/pack_pool.py --root "$W/20260918-gen" --out "$W/20260918-pack-b" --models $MODELS
python scripts/sampling/pack_pool.py --verify "$W/20260918-pack-b" | tail -1
for m in $MODELS; do
  jid=$(sbatch --parsable -p ${PARTITION:-group_low} -o $DATA/logs/model_%j.out -e $DATA/logs/model_%j.err \
        --export=ALL,MODEL=$m,RUN_ID=$RUN_ID,SEEDS=$SEEDS,RUNS=$RUNS,PACK=$DATA/20260918-pack-b,OUT=$DATA/rr-$RUN_ID scripts/sampling/cluster/hpc_model_job.sh)
  echo "$jid $m" >> "$W/plan-m.txt"
  echo "$(date -u +%FT%TZ) submitted model job $jid for $m"
done
