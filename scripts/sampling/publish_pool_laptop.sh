#!/bin/bash
# Build the SH-250 pool release folder ON THE LAPTOP from the pulled, verified results and publish it to a
# NEW folder in the PRIVATE bucket gs://<bucket>. Nothing is hand-edited: every object is a copy of an
# input file or the output of merge_pack_manifests.py / release_readme.py / verify_pool_rr.py /
# pack_pool.py --manifest-of. The inputs are read-only and never touched.
#
#   bash scripts/sampling/publish_pool_laptop.sh <run-id>
#
# Inputs (override with the environment variables named in brackets; defaults are the 2026-09 run):
#   $RR    [RR]    LOGS-SH250/rr-final        pool_rr.py results in the grouped layout: <model>/{runs.json, top_5_bots.json,
#                                             VERIFIED, g0..g4/{pool_ledger.json, elo.json, top_1.json?, top_5_bots.json,
#                                             VERIFIED, matches/*/match_result.json}}, stage_b/{summary.json,
#                                             top5/<model>/{elo.json | SKIPPED.json, VERIFIED, matches/...},
#                                             top1/{elo.json, skipped.json, VERIFIED, matches/...}}, *.verify.txt
#   $PACK  [PACK]  LOGS-SH250/pack-all        the union of every pack (samples/ of the release) + sampling_prompt.md
#   $GEN   [GEN]   LOGS-SH250/20260918        the sampling run root (counts the samples of models that never packed)
#   PACK_SOURCES   <platform>=<MANIFEST.json> the per-platform pack manifests the union was built from
#   CAUSE_FILES    <platform>=<json>          forfeit-cause files from the build ledgers
#   SHAS           short shas                 every harness commit the games were played from (resolved with git rev-parse)
#   CHAMPIONS_PLATFORM                        where the Champions Round ran
#   $PY    [PY]    the arena python (verify_pool_rr.py imports mjarena; MUJOCO_GL=glfw)
#   PUBLISH=0                                 rehearsal: build + verify the folder, upload nothing
# Output: $LOGS/release-<run-id>/ mirrored to gs://<bucket>/sh250/<run-id>/ and reconciled (object count +
# a 200-object md5 spot check with `gcloud storage hash --hex`). Prints "PUBLISHED <dest> objects=N" on success.
#
# Refuses when: the destination prefix exists; the release folder exists; any expected VERIFIED marker is
# missing (model, every run, every Top-5 Round, the Champions Round) or a FAILED marker is present; a verifier
# report that has to be produced here finds a violation; a raw match_data.json (ungzipped) is in stage_b;
# merge_pack_manifests.py or release_readme.py refuses; the bucket object count or any spot-checked md5 differs.
set -euo pipefail

RUN=${1:?usage: publish_pool_laptop.sh <run-id>}
HARNESS=$(cd "$(dirname "$0")/../.." && pwd)
SCRIPTS=$HARNESS/scripts/sampling
LOGS=${LOGS:-$HARNESS/LOGS-SH250}
RR=${RR:-$LOGS/rr-final}
PACK=${PACK:-$LOGS/pack-all}
GEN=${GEN:-$LOGS/20260918}
REL=${REL:-$LOGS/release-$RUN}
DEST=gs://<bucket>/sh250/$RUN
PY=${PY:-$HOME/miniconda3/envs/arena/bin/python}
CHAMPIONS_PLATFORM=${CHAMPIONS_PLATFORM:-hpc}
SPOT_CHECK=${SPOT_CHECK:-200}
PUBLISH=${PUBLISH:-1}            # PUBLISH=0: build and verify the folder, print BUILT, upload nothing (a rehearsal)
export MUJOCO_GL=${MUJOCO_GL:-glfw}
export PATH=$HOME/google-cloud-sdk/bin:$PATH

if [ -z "${PACK_SOURCES:-}" ]; then
  PACK_SOURCES="laptop=$LOGS/20260918-pack-a/MANIFEST.json hpc=$LOGS/gpu/pack-gpu-1/MANIFEST.json hpc=$LOGS/gpu/pack-gpu-2/MANIFEST.json"
  for m in gpt-5.5 gpt-5.6-sol gpt-6-astra grok-4.6-high kimi-k3-high qwen3.8-2.4t-a95b-thinking; do
    PACK_SOURCES="$PACK_SOURCES gpu=$LOGS/gpu/qp/pack-gpu-3-$m/MANIFEST.json"
  done
fi
CAUSE_FILES=${CAUSE_FILES:-"laptop=$LOGS/forfeit_causes_laptop.json hpc=$LOGS/forfeit_causes_hpc.json"}
SHAS=${SHAS:-"21388af7 6d87c649 8c28de02 3c03d494 6a681320 dedc97f0 c920187e"}

die() { echo "refusing: $*" >&2; exit 1; }
ts() { date -u +%FT%TZ; }

# ── preconditions ─────────────────────────────────────────────────────────────
[ -x "$PY" ] || die "$PY is not executable"
command -v gcloud >/dev/null || die "gcloud not on PATH"
command -v md5sum >/dev/null || die "md5sum not found"
[ -d "$RR" ] || die "$RR missing (round-robin results)"
[ -d "$RR/stage_b" ] || die "$RR/stage_b missing (stored rounds)"
[ -f "$RR/stage_b/summary.json" ] || die "$RR/stage_b/summary.json missing"
[ -d "$PACK" ] || die "$PACK missing (the union pack)"
[ -f "$PACK/sampling_prompt.md" ] || die "$PACK/sampling_prompt.md missing"
[ ! -e "$PACK/MANIFEST.json" ] || die "$PACK/MANIFEST.json exists — the union pack is manifest-less; its manifest is merged from PACK_SOURCES"
[ -d "$GEN" ] || die "$GEN missing (sampling run root)"
for spec in $PACK_SOURCES $CAUSE_FILES; do [ -f "${spec#*=}" ] || die "${spec#*=} missing"; done
for f in "$SCRIPTS/merge_pack_manifests.py" "$SCRIPTS/release_readme.py" "$SCRIPTS/verify_pool_rr.py" "$SCRIPTS/pack_pool.py"; do
  [ -f "$f" ] || die "$f missing"
done
SHA_ARGS=()
for s in $SHAS; do
  full=$(git -C "$HARNESS" rev-parse --verify "$s^{commit}" 2>/dev/null) || die "harness commit $s is not in $HARNESS"
  SHA_ARGS+=(--sha "$full")
done
if gcloud storage ls "$DEST" >/dev/null 2>&1; then die "$DEST already exists — a release folder is never overwritten"; fi
[ ! -e "$REL" ] || die "$REL already exists — remove it yourself if it is a stale attempt"

# APFS clones (cp -c) share blocks with the read-only inputs but are independent files; plain copies elsewhere.
t=$(mktemp)
if cp -c "$t" "$t.clone" 2>/dev/null; then CLONE="cp -c"; else CLONE="cp"; fi
rm -f "$t" "$t.clone"

# ── every VERIFIED marker the release needs ───────────────────────────────────
MODELS=()
for d in "$RR"/*/; do
  m=$(basename "$d")
  case "$m" in stage_b|_*) continue;; esac
  [ -f "$d/runs.json" ] || die "$m: no runs.json (not a grouped model dir)"
  [ ! -f "$d/FAILED" ] || die "$m carries a FAILED marker"
  [ -f "$d/VERIFIED" ] || die "$m is not VERIFIED"
  [ -f "$d/top_5_bots.json" ] || die "$m: top_5_bots.json missing"
  runs=$("$PY" -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["runs"]))' "$d/runs.json")
  for ((k = 0; k < runs; k++)); do
    g=$d/g$k
    [ -d "$g" ] || die "$m: run g$k missing"
    [ ! -f "$g/FAILED" ] || die "$m/g$k carries a FAILED marker"
    [ -f "$g/VERIFIED" ] || die "$m/g$k is not VERIFIED"
    for f in pool_ledger.json elo.json top_5_bots.json; do [ -f "$g/$f" ] || die "$m/g$k: $f missing"; done
  done
  sd=$RR/stage_b/top5/$m
  [ -f "$sd/VERIFIED" ] || die "stage_b/top5/$m is not VERIFIED"
  [ -f "$sd/elo.json" ] || [ -f "$sd/SKIPPED.json" ] || die "stage_b/top5/$m has neither elo.json nor SKIPPED.json"
  MODELS+=("$m")
done
[ ${#MODELS[@]} -gt 0 ] || die "no model dirs under $RR"
[ -f "$RR/stage_b/top1/VERIFIED" ] || die "stage_b/top1 (Champions Round) is not VERIFIED"
for f in elo.json skipped.json; do [ -f "$RR/stage_b/top1/$f" ] || die "stage_b/top1/$f missing"; done
if find "$RR/stage_b" -name match_data.json -print -quit | grep -q .; then
  die "raw match_data.json under $RR/stage_b — the stored rounds keep gzipped telemetry only"
fi
NB=$("$PY" -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["n_rollouts"]))' "$RR/stage_b/top1/elo.json")
NA=$("$PY" -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["n_rollouts"]))' "$RR/${MODELS[0]}/g0/pool_ledger.json")
echo "$(ts) run=$RUN models=${#MODELS[@]} run-seeds=$NA stored-seeds=$NB copy='$CLONE': ${MODELS[*]}"

# ── the merged pack manifest first: it validates the union pack against its sources ───────────────
mkdir -p "$REL"
SRC_ARGS=()
for spec in $PACK_SOURCES; do SRC_ARGS+=(--source "$spec"); done
"$PY" "$SCRIPTS/merge_pack_manifests.py" --pack-root "$PACK" --out "$REL/pack-MANIFEST.json" "${SRC_ARGS[@]}"

# ── layout ────────────────────────────────────────────────────────────────────
mkdir -p "$REL/samples" "$REL/pool_rr" "$REL/stage_b/top5" "$REL/stage_b/top1" "$REL/verify" "$REL/standings"
echo "$(ts) samples/ <- $PACK"
$CLONE -R "$PACK/." "$REL/samples/"
mv "$REL/samples/sampling_prompt.md" "$REL/sampling_prompt.md"

for m in "${MODELS[@]}"; do
  d=$RR/$m
  o=$REL/pool_rr/$m
  mkdir -p "$o"
  $CLONE "$d/runs.json" "$d/top_5_bots.json" "$d/VERIFIED" "$o/"
  if [ -f "$d/top_1.json" ]; then $CLONE "$d/top_1.json" "$o/"; fi     # a lone run winner's champion record
  runs=$("$PY" -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["runs"]))' "$d/runs.json")
  for ((k = 0; k < runs; k++)); do
    g=$d/g$k
    og=$o/g$k
    mkdir -p "$og"
    $CLONE "$g/pool_ledger.json" "$g/elo.json" "$g/top_5_bots.json" "$og/"
    if [ -f "$g/top_1.json" ]; then $CLONE "$g/top_1.json" "$og/"; fi   # absent when the run had no eligible bot
    if [ -d "$g/matches" ]; then
      rsync -a --include='*/' --include='match_result.json' --exclude='*' "$g/matches/" "$og/matches/"
    fi
  done
done

copy_stored() {   # copy_stored <src stage dir> <dst stage dir>: standings + records + gzipped telemetry, nothing else
  local src=$1 dst=$2
  mkdir -p "$dst"
  for f in elo.json SKIPPED.json skipped.json VERIFIED; do if [ -f "$src/$f" ]; then $CLONE "$src/$f" "$dst/"; fi; done
  if [ -d "$src/matches" ]; then
    find "$src/matches" -mindepth 2 -maxdepth 2 \( -name match_result.json -o -name match_data.json.gz \) | while IFS= read -r f; do
      pair=$(basename "$(dirname "$f")")
      mkdir -p "$dst/matches/$pair"
      $CLONE "$f" "$dst/matches/$pair/"
    done
  fi
}
$CLONE "$RR/stage_b/summary.json" "$REL/stage_b/summary.json"
for m in "${MODELS[@]}"; do copy_stored "$RR/stage_b/top5/$m" "$REL/stage_b/top5/$m"; done
copy_stored "$RR/stage_b/top1" "$REL/stage_b/top1"

# ── verifier reports: the ones the clusters wrote, plus whatever is missing, produced here on this copy ──
for f in "$RR"/*.verify.txt; do [ -f "$f" ] && $CLONE "$f" "$REL/verify/"; done
verify_here() {   # verify_here <report name> <verify_pool_rr.py args...>
  local name=$1; shift
  local out=$REL/verify/$name
  if [ ! -f "$out" ]; then
    echo "$(ts) verifying here: $name"
    { echo "# verify_pool_rr.py $* — run on the laptop ($(uname -m) $(uname -s)) at $(ts) against $(basename "$RR")"
      "$PY" "$SCRIPTS/verify_pool_rr.py" --out "$RR" "$@"; } > "$out" 2>&1 || { cat "$out"; die "$name: verification failed"; }
  fi
}
for m in "${MODELS[@]}"; do
  runs=$("$PY" -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["runs"]))' "$RR/$m/runs.json")
  for ((k = 0; k < runs; k++)); do verify_here "$m.g$k.verify.txt" --model "$m" --n-rollouts "$NA" --group "$k"; done
  verify_here "$m.top5.verify.txt" --n-rollouts "$NB" --stage b1 "$m"
done
verify_here "champions.verify.txt" --n-rollouts "$NB" --stage b2
grep -L '^OK: ' "$REL"/verify/*.verify.txt | grep . && die "verifier reports without an OK line (above)"

# ── derived documents, then the manifest of everything ────────────────────────
CAUSE_ARGS=()
for spec in $CAUSE_FILES; do CAUSE_ARGS+=(--forfeit-causes "$spec"); done
"$PY" "$SCRIPTS/release_readme.py" --release "$REL" --run-id "$RUN" "${SHA_ARGS[@]}" \
  --champions-platform "$CHAMPIONS_PLATFORM" "${CAUSE_ARGS[@]}" --gen-root "$GEN"
"$PY" "$SCRIPTS/pack_pool.py" --manifest-of "$REL" --out "$REL/MANIFEST.json"   # md5 + size of every object, last
N=$(find "$REL" -type f | wc -l | tr -d ' ')
BYTES=$("$PY" -c 'import os,sys; print(sum(os.path.getsize(os.path.join(r,f)) for r,_,fs in os.walk(sys.argv[1]) for f in fs))' "$REL")
echo "$(ts) release folder ready: $N files, $BYTES bytes at $REL"
if [ "$PUBLISH" != "1" ]; then echo "BUILT $REL files=$N bytes=$BYTES (PUBLISH=$PUBLISH: not uploaded)"; exit 0; fi

# ── publish + reconcile ───────────────────────────────────────────────────────
gcloud storage rsync -r "$REL" "$DEST"
M=$(gcloud storage ls -r "$DEST/**" | grep -c '^gs://' || true)
[ "$N" = "$M" ] || die "object count mismatch: local $N bucket $M"

# md5 spot check: $SPOT_CHECK random objects (all of them when the release is smaller).
CHECKED=0
while IFS= read -r f; do
  r=${f#"$REL"/}
  l=$(md5sum "$f" | cut -c1-32)
  b=$(gcloud storage hash --hex "$DEST/$r" | awk '/^md5_hash:/{print $2}')
  [ "$l" = "$b" ] || die "md5 mismatch $r: local $l bucket ${b:-<none>}"
  CHECKED=$((CHECKED + 1))
done < <(find "$REL" -type f | awk 'BEGIN{srand()} {print rand() "\t" $0}' | sort -n | head -n "$SPOT_CHECK" | cut -f2-)
[ "$CHECKED" -gt 0 ] || die "md5 spot check verified nothing"
echo "$(ts) md5 spot check: $CHECKED objects match"

echo "PUBLISHED $DEST objects=$N"
