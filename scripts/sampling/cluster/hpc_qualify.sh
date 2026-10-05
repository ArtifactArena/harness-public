#!/bin/bash
# SH-250 qualification on the HPC cluster (SLURM): one job = one node, replaying every unqualified
# sample of the given models from its gen.json (the pool runner's qualification stage; no API calls).
#
#   sbatch --export=ALL,ROOT=~/sh250/20260918-gen,MODELS="gpt-5.4 gpt-5.5" scripts/sampling/cluster/hpc_qualify.sh
#
#SBATCH --job-name=sh250-qual
#SBATCH --partition=shared_normal
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=120G
#SBATCH --output=logs/qual_%j.out
#SBATCH --error=logs/qual_%j.err
set -uo pipefail
W=${W:-$HOME/sh250}; ROOT=${ROOT:?run root with gen.json slots + manifest.json}; MODELS=${MODELS:-}
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-0}   # 1 = exact-observation accelerator (validated identical, ~10x faster)
export MUJOCO_GL=disable OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PY=$(which python)          # run_pool launches each build with $PY (defaults to the laptop env path)
cd "${HARNESS:-$W/harness}" || exit 1
echo "$(date -u +%FT%TZ) host=$(hostname -s) cpus=$SLURM_CPUS_PER_TASK root=$ROOT models=${MODELS:-all}"
python scripts/sampling/run_pool.py --root "$ROOT" --n-samples 250 --per-model 1 --qual-workers "$SLURM_CPUS_PER_TASK" \
    --status-every 60 --gen-deadline-min 120 --stop-scope instance --skip-recent-min 0 --allow-sha-drift \
    --status-name "STATUS-qual-$SLURM_JOB_ID.md" ${MODELS:+--models $MODELS}
rc=$?
echo "$(date -u +%FT%TZ) qualification job finished rc=$rc"
exit $rc
