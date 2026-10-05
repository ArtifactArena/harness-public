#!/bin/bash
# Run Champions Round for ONE run group k, sharded across an array: the cross-model round robin of every
# model's run-k winner (runs.json), 11 seeds with telemetry. Array task i of NSHARDS plays the pairings with
# index % NSHARDS == i (seeds are index-based, so the games equal one unsharded run). A follow-up job with
# MODE=finalize (--dependency=afterany:<array>) plays anything still missing, writes elo.json and verifies.
# Five groups (k = 0..4) = five independent cross-model leaderboards from five disjoint 50-sample draws.
# Runs in the SAME harness tree the Champions Round used (HARNESS=~/sh250/harness-accel), so physics match.
#
#   A=$(sbatch --parsable --array=0-9 --export=ALL,GROUP=$k,NSHARDS=10,RUN_ID=<id>,PACK=$HOME/sh250/pack-all,OUT=$HOME/sh250/rr-<id>,HARNESS=$HOME/sh250/harness-accel scripts/sampling/cluster/hpc_runs_job.sh)
#   sbatch --dependency=afterany:$A --export=ALL,MODE=finalize,GROUP=$k,RUN_ID=<id>,... scripts/sampling/cluster/hpc_runs_job.sh
#
#SBATCH --job-name=sh250-runs
#SBATCH --partition=group_normal,group_low,shared_normal,shared_preemptable
#SBATCH --requeue
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=44
#SBATCH --mem=96G
#SBATCH --output=logs/runs_%A_%a.out
#SBATCH --error=logs/runs_%A_%a.err
set -uo pipefail
W=${W:-$HOME/sh250}; DATA=${SH250_DATA:-<hpc-data>/sh250}; GROUP=${GROUP:?run group k}; RUN_ID=${RUN_ID:?run id}; PACK=${PACK:-$DATA/pack-all}; OUT=${OUT:-$DATA/rr-$RUN_ID}
SEEDS=${RUNS_SEEDS:-11}; MODE=${MODE:-shard}; NSHARDS=${NSHARDS:-1}; SHARD=${SLURM_ARRAY_TASK_ID:-0}
module load miniforge >/dev/null 2>&1
mamba activate sh250 2>/dev/null || conda activate sh250
export ARENA_OBS_ACCEL=${ARENA_OBS_ACCEL:-1}   # the Champions Round ran with the validated-identical observation accelerator ON
export MUJOCO_GL=disable OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset ARENA_SKIP_MATCH_DATA
cd "${HARNESS:-$W/harness-accel}" || exit 1
STAGE="$OUT/stage_b/runs/g$GROUP"
PAR=$(( SLURM_CPUS_PER_TASK / SEEDS )); [ "$PAR" -ge 2 ] || PAR=2
echo "$(date -u +%FT%TZ) job=${SLURM_JOB_ID} array=${SLURM_ARRAY_JOB_ID:-}_${SLURM_ARRAY_TASK_ID:-} host=$(hostname -s) cpus=$SLURM_CPUS_PER_TASK mode=$MODE g$GROUP shard=$SHARD/$NSHARDS seeds=$SEEDS parallel=$PAR harness=$(pwd) sha=$(cat SHIPPED_SHA 2>/dev/null) accel=$ARENA_OBS_ACCEL"
if [ "$MODE" = shard ]; then
  python scripts/sampling/pool_finals.py --rr "$OUT" --pack "$PACK" --out "$OUT" --n-rollouts "$SEEDS" \
      --n-parallel-matches "$PAR" --n-parallel-seeds "$SEEDS" --run-id "$RUN_ID" \
      --stages b3 --groups "$GROUP" --shard "$SHARD" "$NSHARDS" || { echo "$(date -u +%FT%TZ) FAILED-SHARD g$GROUP $SHARD/$NSHARDS"; exit 4; }
  echo "$(date -u +%FT%TZ) DONE shard g$GROUP $SHARD/$NSHARDS ($(find "$STAGE/matches" -name match_result.json | wc -l) pairings present in g$GROUP)"
  exit 0
fi
# finalize: play whatever is still missing, write elo.json, verify
[ -f "$STAGE/VERIFIED" ] && { echo "already verified"; exit 0; }
python scripts/sampling/pool_finals.py --rr "$OUT" --pack "$PACK" --out "$OUT" --n-rollouts "$SEEDS" \
    --n-parallel-matches "$PAR" --n-parallel-seeds "$SEEDS" --run-id "$RUN_ID" \
    --stages b3 --groups "$GROUP" || { echo "$(date -u +%FT%TZ) FAILED-FINALIZE g$GROUP"; exit 4; }
if python scripts/sampling/verify_pool_rr.py --out "$OUT" --n-rollouts "$SEEDS" --stage b3 "g$GROUP" > "$OUT/runs.g$GROUP.verify.txt" 2>&1; then
  touch "$STAGE/VERIFIED"; rm -f "$STAGE/FAILED"; echo "$(date -u +%FT%TZ) VERIFIED Run Champions Round g$GROUP ($(find "$STAGE" -name 'match_data.json.gz' | wc -l) telemetry files)"
else
  touch "$STAGE/FAILED"; echo "$(date -u +%FT%TZ) FAILED-VERIFY Run Champions Round g$GROUP"; exit 5
fi
