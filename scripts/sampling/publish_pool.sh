#!/bin/bash
# Build the SH-250 pool release folder from the run and publish it to a NEW folder in gs://<bucket>.
# Runs ON THE CLUSTER (where the matches and its authenticated gcloud are). Nothing is hand-edited: every
# object is a hardlink to a run file or the output of release_readme.py / pack_pool.py --manifest-of.
#
#   bash publish_pool.sh <run-id>
#
# Inputs under $W (default /tmp/kush-sh250):
#   $W/harness/                 the harness tree the matches were played from (SHIPPED_SHA or a git checkout)
#   $W/venv/bin/python          its venv
#   $W/20260918-pack/           the pack (pack_pool.py): MANIFEST.json, sampling_prompt.md, <model>/cNNN/...
#   $W/rr-<run-id>/<model>/     Stage A per model (pool_rr.py) with a VERIFIED marker from run_pool_rr.sh
#   $W/rr-<run-id>/<model>.verify.txt
#   $W/rr-<run-id>/stage_b/     Stage B (pool_finals.py): top5/<model>/, top1/, summary.json
# Output: $W/release-<run-id>/ mirrored to gs://<bucket>/sh250/<run-id>/ and reconciled
# (object count + a 200-object md5 spot check). Prints "PUBLISHED <dest> objects=N" on success.
#
# Refuses when: the destination prefix exists; any Stage A model lacks VERIFIED (or carries FAILED);
# Stage B is incomplete or fails verify_pool_rr.py; a raw match_data.json (ungzipped) is in Stage B;
# release_readme.py refuses (sha / prompt / rules mismatch); the bucket object count or any spot-checked
# md5 differs from the local release folder.
set -euo pipefail

RUN=${1:?usage: publish_pool.sh <run-id>}
W=${W:-/tmp/kush-sh250}
PACK=${PACK:-$W/20260918-pack}
RR=$W/rr-$RUN
REL=$W/release-$RUN
DEST=gs://<bucket>/sh250/$RUN
PY=$W/venv/bin/python
HARNESS=$W/harness
SCRIPTS=$HARNESS/scripts/sampling
export PATH=$HOME/google-cloud-sdk/bin:$PATH

die() { echo "refusing: $*" >&2; exit 1; }
ts() { date -u +%FT%TZ; }

# ── preconditions ─────────────────────────────────────────────────────────────
[ -x "$PY" ] || die "$PY is not executable"
[ -d "$HARNESS" ] || die "$HARNESS missing"
[ -f "$PACK/MANIFEST.json" ] || die "$PACK/MANIFEST.json missing (not a pack)"
[ -f "$PACK/sampling_prompt.md" ] || die "$PACK/sampling_prompt.md missing"
[ -d "$RR" ] || die "$RR missing (Stage A output)"
[ -d "$RR/stage_b" ] || die "$RR/stage_b missing (Stage B output)"
[ -f "$RR/stage_b/summary.json" ] || die "$RR/stage_b/summary.json missing"
[ -f "$RR/stage_b/top1/skipped.json" ] || die "$RR/stage_b/top1/skipped.json missing (Stage B2 not run)"
command -v gcloud >/dev/null || die "gcloud not on PATH"
command -v shuf >/dev/null || die "shuf (GNU coreutils) not found"
command -v md5sum >/dev/null || die "md5sum not found"
cp --help 2>/dev/null | grep -q -- '--parents' || die "GNU cp required (cp -al --parents -t)"

if gcloud storage ls "$DEST" >/dev/null 2>&1; then die "$DEST already exists — a release folder is never overwritten"; fi
if [ -e "$REL" ]; then die "$REL already exists — remove it yourself if it is a stale attempt"; fi

if [ -f "$HARNESS/SHIPPED_SHA" ]; then SHA=$(tr -d '[:space:]' < "$HARNESS/SHIPPED_SHA")
else SHA=$(git -C "$HARNESS" rev-parse HEAD); fi
[ -n "$SHA" ] || die "could not determine the harness sha"

# Stage A models: every model dir under $RR except stage_b / scratch; each must be VERIFIED and not FAILED.
MODELS=()
for d in "$RR"/*/; do
  m=$(basename "$d")
  case "$m" in stage_b|_*) continue;; esac
  [ -f "$d/pool_ledger.json" ] || die "$m: no pool_ledger.json (not a Stage A model dir)"
  if [ -f "$d/FAILED" ]; then die "$m carries a FAILED marker"; fi
  [ -f "$d/VERIFIED" ] || die "$m is not VERIFIED (run verify_pool_rr.py --out $RR --model $m)"
  [ -f "$RR/$m.verify.txt" ] || die "$m: $RR/$m.verify.txt missing"
  for f in elo.json top_5_bots.json; do [ -f "$d/$f" ] || die "$m: $f missing"; done
  MODELS+=("$m")
done
[ ${#MODELS[@]} -gt 0 ] || die "no Stage A model dirs under $RR"
echo "$(ts) run=$RUN sha=$SHA models=${#MODELS[@]}: ${MODELS[*]}"

# Stage B: no raw telemetry anywhere; verify B1 for every model that played and B2, keeping the reports.
if find "$RR/stage_b" -name match_data.json -print -quit | grep -q .; then
  die "raw match_data.json under $RR/stage_b — Stage B stores gzipped telemetry only (rerun pool_finals.py)"
fi
NB=$("$PY" -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["n_rollouts"]))' "$RR/stage_b/summary.json")
echo "$(ts) Stage B seeds=$NB"

# ── layout ────────────────────────────────────────────────────────────────────
mkdir -p "$REL/samples" "$REL/pool_rr" "$REL/stage_b/top5" "$REL/stage_b/top1" "$REL/standings"
cp -al "$PACK/." "$REL/samples/"                                   # hardlinks: no extra disk
mv "$REL/samples/MANIFEST.json" "$REL/pack-MANIFEST.json"
mv "$REL/samples/sampling_prompt.md" "$REL/sampling_prompt.md"

for m in "${MODELS[@]}"; do
  d=$RR/$m
  mkdir -p "$REL/pool_rr/$m"
  cp -al "$d/pool_ledger.json" "$d/elo.json" "$d/top_5_bots.json" "$REL/pool_rr/$m/"
  if [ -f "$d/top_1.json" ]; then cp -al "$d/top_1.json" "$REL/pool_rr/$m/"; fi    # absent when no bot was eligible
  cp "$RR/$m.verify.txt" "$REL/pool_rr/$m/verify.txt"
  if [ -d "$d/matches" ]; then
    mkdir -p "$REL/pool_rr/$m/matches"
    (cd "$d/matches" && find . -name match_result.json -print0 | xargs -0 -r cp -al --parents -t "$REL/pool_rr/$m/matches/")
  fi
done

copy_stage() {   # copy_stage <src stage dir> <dst stage dir>: elo.json | SKIPPED.json, skipped.json, records + gzipped telemetry
  local src=$1 dst=$2
  mkdir -p "$dst"
  for f in elo.json SKIPPED.json skipped.json; do if [ -f "$src/$f" ]; then cp -al "$src/$f" "$dst/"; fi; done
  if [ -d "$src/matches" ]; then
    mkdir -p "$dst/matches"
    (cd "$src/matches" && find . \( -name match_result.json -o -name match_data.json.gz \) -print0 \
       | xargs -0 -r cp -al --parents -t "$dst/matches/")
  fi
}
cp -al "$RR/stage_b/summary.json" "$REL/stage_b/summary.json"
for sd in "$RR"/stage_b/top5/*/; do
  m=$(basename "$sd")
  case "$m" in _*) continue;; esac
  [ -f "$sd/elo.json" ] || [ -f "$sd/SKIPPED.json" ] || die "stage_b/top5/$m has neither elo.json nor SKIPPED.json"
  copy_stage "$sd" "$REL/stage_b/top5/$m"
  if [ -f "$sd/elo.json" ]; then
    "$PY" "$SCRIPTS/verify_pool_rr.py" --out "$RR" --stage b1 "$m" --n-rollouts "$NB" > "$REL/stage_b/top5/$m/verify.txt" 2>&1 \
      || { cat "$REL/stage_b/top5/$m/verify.txt"; die "Stage B1 $m failed verification"; }
  fi
done
copy_stage "$RR/stage_b/top1" "$REL/stage_b/top1"
if [ -f "$RR/stage_b/top1/elo.json" ]; then
  "$PY" "$SCRIPTS/verify_pool_rr.py" --out "$RR" --stage b2 --n-rollouts "$NB" > "$REL/stage_b/top1/verify.txt" 2>&1 \
    || { cat "$REL/stage_b/top1/verify.txt"; die "Stage B2 failed verification"; }
fi

# ── derived documents, then the manifest of everything ────────────────────────
"$PY" "$SCRIPTS/release_readme.py" --release "$REL" --run-id "$RUN" --sha "$SHA"
"$PY" "$SCRIPTS/pack_pool.py" --manifest-of "$REL" --out "$REL/MANIFEST.json"   # md5 + size of every object
N=$(find "$REL" -type f | wc -l | tr -d ' ')
BYTES=$(du -sb "$REL" | cut -f1)
echo "$(ts) release folder ready: $N files, $BYTES bytes at $REL"

# ── publish + reconcile ───────────────────────────────────────────────────────
gcloud storage rsync -r "$REL" "$DEST"
M=$(gcloud storage ls -r "$DEST/**" | grep -c '^gs://' || true)
[ "$N" = "$M" ] || die "object count mismatch: local $N bucket $M"

# md5 spot check: 200 random objects (all of them when the release is smaller).
CHECKED=0
while IFS= read -r f; do
  r=${f#"$REL"/}
  l=$(md5sum "$f" | cut -c1-32)
  b=$(gcloud storage hash --hex "$DEST/$r" | awk '/md5_hash/{print $2}')
  [ "$l" = "$b" ] || die "md5 mismatch $r: local $l bucket ${b:-<none>}"
  CHECKED=$((CHECKED + 1))
done < <(find "$REL" -type f | shuf -n 200)
[ "$CHECKED" -gt 0 ] || die "md5 spot check verified nothing"
echo "$(ts) md5 spot check: $CHECKED objects match"

echo "PUBLISHED $DEST objects=$N"
