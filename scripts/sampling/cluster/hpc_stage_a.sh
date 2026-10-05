#!/bin/bash
# SH-250 Stage A on the HPC cluster (SLURM): one array task = one model-run (50 samples, full round
# robin inside the run, N seeds). Resumable: rerun the same array and finished pairings are skipped.
#
#   PLAN=~/sh250/plan-a.txt   # lines: "<model> <run-index>"
#   sbatch --array=1-$(wc -l < $PLAN) --export=ALL,PLAN=$PLAN,RUN_ID=<id>,SEEDS=5 \
#          scripts/sampling/cluster/hpc_stage_a.sh
#
#SBATCH --job-name=sh250-a
#SBATCH --partition=shared_normal
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=120G
#SBATCH --output=logs/stage_a_%A_%a.out
#SBATCH --error=logs/stage_a_%A_%a.err
set -uo pipefail
W=${W:-$HOME/sh250}
DATA=${SH250_DATA:-<hpc-data>/sh250}   # data root (packs, rr-<run>, logs): NOT $HOME — the home quota filled up on 2026-09-22
PLAN=${PLAN:?plan file}; RUN_ID=${RUN_ID:?run id}; SEEDS=${SEEDS:-5}; RUNS=${RUNS:-5}
PACK=${PACK:-$DATA/20260918-pack}; OUT=${OUT:-$DATA/rr-$RUN_ID}
line=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$PLAN"); model=${line%% *}; k=${line##* }
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-0}   # 1 = exact-observation accelerator (validated identical, ~10x faster)
export MUJOCO_GL=disable ARENA_SKIP_MATCH_DATA=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
cd "${HARNESS:-$W/harness}" || exit 1
mkdir -p "$OUT"
echo "$(date -u +%FT%TZ) task=$SLURM_ARRAY_TASK_ID host=$(hostname -s) cpus=$SLURM_CPUS_PER_TASK model=$model run=g$k sha=$(cat SHIPPED_SHA)"
if [ -f "$OUT/$model/g$k/VERIFIED" ]; then echo "already verified"; exit 0; fi
python scripts/sampling/pool_rr.py --root "$PACK" --layout pack --out "$OUT" --model "$model" \
    --n-rollouts "$SEEDS" --n-parallel-matches $(( SLURM_CPUS_PER_TASK / SEEDS )) --n-parallel-seeds "$SEEDS" --run-id "$RUN_ID" --runs "$RUNS" --run-index "$k"
rc=$?
if [ $rc -ne 0 ]; then echo "$(date -u +%FT%TZ) FAILED-RUN $model g$k rc=$rc"; touch "$OUT/$model/g$k/FAILED" 2>/dev/null; exit $rc; fi
if python scripts/sampling/verify_pool_rr.py --out "$OUT" --model "$model" --n-rollouts "$SEEDS" --group "$k" > "$OUT/$model.g$k.verify.txt" 2>&1; then
  touch "$OUT/$model/g$k/VERIFIED"; rm -f "$OUT/$model/g$k/FAILED"; echo "$(date -u +%FT%TZ) VERIFIED $model g$k"
else
  touch "$OUT/$model/g$k/FAILED"; echo "$(date -u +%FT%TZ) FAILED-VERIFY $model g$k"; exit 3
fi
