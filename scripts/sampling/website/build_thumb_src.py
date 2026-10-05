"""thumb-src/: one pairing dir per zoo roster bot for the app's thumbnail bake (no re-simulation).

For every roster aid in bots/index.json (roles champion and run-winner) pick one real pairing dir —
a Champions Round pairing for a champion, a Top-5 Round pairing for a run-winner (the first, in
sorted order, not already claimed by another roster bot, so 105 bots → 105 distinct dirs) — and write

    <out>/matches/<siteRed>_vs_<siteBlue>/composed.xml       verbatim
    <out>/matches/<siteRed>_vs_<siteBlue>/match_data.json    ONE seed key (the pairing's first seed) with a
                                                             one-frame record: the bake reads only frame 0
                                                             (precompute-wasm-thumbnails.mjs) and a full
                                                             30,000-step JSON exceeds V8's string limit.

python scripts/sampling/website/build_thumb_src.py --rr LOGS-SH250/rr-final --bots LOGS-SH250/site/bots/index.json \
    --out LOGS-SH250/site/thumb-src
"""
from __future__ import annotations
import argparse, gzip, json, shutil, sys
from pathlib import Path
_SAMPLING = Path(__file__).resolve().parents[1]
if str(_SAMPLING) not in sys.path:
    sys.path.insert(0, str(_SAMPLING))
from website.site_ids import model_of, site_aid  # noqa: E402

ROSTER_ROLES = ("champion", "run-winner")
FRAME_KEYS = ("seed", "winner", "num_steps", "control_dt", "termination_reason", "physics_unstable")
LIST_KEYS = ("qpos", "red_positions", "blue_positions")
NAME_KEYS = ("red_actuator_names", "blue_actuator_names")


def _pairing_dirs(round_dir: Path) -> list[Path]:
    """The pairing dirs of one round's matches/ folder, sorted by harness dir name (env.xml and other files skipped)."""
    return sorted(p for p in round_dir.iterdir() if p.is_dir() and "_vs_" in p.name)


def _one_frame(d: Path) -> tuple[str, dict]:
    res = json.loads((d / "match_result.json").read_text())
    first = res["matches"][0]
    key = f"seed_{first['seed']}"
    rec = json.load(gzip.open(d / "match_data.json.gz", "rt"))[key]
    for k in ("winner", "num_steps", "seed"):
        if rec[k] != first[k]:
            raise RuntimeError(f"{d} {key}: telemetry {k}={rec[k]!r} != result {first[k]!r}")
    frame = {k: rec[k] for k in FRAME_KEYS}
    frame.update({k: [rec[k][0]] for k in LIST_KEYS})
    frame.update({k: rec[k] for k in NAME_KEYS})
    return key, frame


def build(rr: Path, bots_index: Path, out: Path) -> dict:
    roster = [b for b in json.loads(bots_index.read_text())["bots"] if b["role"] in ROSTER_ROLES]
    roster.sort(key=lambda b: (b["model"], b["tournament_id"]))
    top1 = _pairing_dirs(rr / "stage_b" / "top1" / "matches")
    top5_root = rr / "stage_b" / "top5"
    top5_cache: dict[str, list[Path]] = {}
    matches = out / "matches"; matches.mkdir(parents=True, exist_ok=True)
    claimed: set[Path] = set()
    for b in roster:
        tid = b["tournament_id"]
        if b["role"] == "champion":
            candidates = top1
        else:
            model = model_of(tid)
            if model not in top5_cache:
                mm = top5_root / model / "matches"
                top5_cache[model] = _pairing_dirs(mm) if mm.exists() else []
            candidates = top5_cache[model]
        pick = None
        for d in candidates:
            if d in claimed:
                continue
            red_tid, blue_tid = d.name.split("_vs_", 1)
            if tid in (red_tid, blue_tid):
                pick = d
                break
        if pick is None:
            raise RuntimeError(f"{tid} ({b['role']}): no unclaimed pairing dir in its round")
        claimed.add(pick)
        red_tid, blue_tid = pick.name.split("_vs_", 1)
        dst = matches / f"{site_aid(red_tid)}_vs_{site_aid(blue_tid)}"
        dst.mkdir(exist_ok=True)
        shutil.copyfile(pick / "composed.xml", dst / "composed.xml")
        key, frame = _one_frame(pick)
        (dst / "match_data.json").write_text(json.dumps({key: frame}))
    return {"roster": len(roster), "dirs": len(claimed)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rr", type=Path, required=True); ap.add_argument("--bots", type=Path, required=True, help="bots/index.json")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.rr, a.bots, a.out)))
