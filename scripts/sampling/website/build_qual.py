"""Qualification Round (3 x 20 s vs the stationary block) → qual/<aid>/result.json for EVERY sampled
bot, plus browser-match-trace-v1 capsules for the games whose OFFICIAL telemetry is on the laptop.

Which telemetry counts as official: a sample was qualified on exactly one platform
(bot.json.qualification.platform: laptop | hpc | gpu). Only the laptop-platform models' laptop
telemetry is official — and only when the laptop match_result.json is byte-identical (md5) to the
release's samples/<model>/cNNN/qualification/match_result.json. The laptop also holds UNOFFICIAL
re-simulations of the cluster/GPU-cluster models (arm64 physics; verdicts flip) — those are never read.
Cluster/GPU-cluster samples are therefore "pending" (official results only, no capsule) until their
telemetry is mirrored; samples that forfeited before the round are "none".

python scripts/sampling/website/build_qual.py --gen laptop=LOGS-SH250/20260918 --gen hpc=LOGS-SH250/qual-hpc \\
    --release LOGS-SH250/release-sh250-pool-5ac92bc7 --bots LOGS-SH250/site/bots \\
    --assets mjarena/assets --out LOGS-SH250/site/qual
"""
from __future__ import annotations
import argparse, base64, gzip, hashlib, json, sys
from pathlib import Path
_SAMPLING = Path(__file__).resolve().parents[1]
if str(_SAMPLING) not in sys.path:
    sys.path.insert(0, str(_SAMPLING))
from website.build_capsules import ASSET_NAMES, _capsule  # noqa: E402
from website.site_ids import RUN_ID, qual_task_id  # noqa: E402

SCHEMA = "sh250-qual-v1"
INDEX_SCHEMA = "sh250-qual-index-v1"
MUJOCO_VERSION = "3.10.0"   # miniconda3/envs/arena (the env scripts/sampling/launch.py ran) — same as the cluster env
BLOCK_AID = "stationary-block"
N_SEEDS = 3
MAX_STEPS = 2000            # 20 s at control_dt 0.01
PENDING_REASON = ("official telemetry recorded on {platform}; not yet mirrored to the laptop — "
                  "laptop replays are not used because arm64 physics diverges")
COUNT_KEYS = ("samples", "fought", "official", "pending", "none")


def _laptop_qual_dir(gen: Path, model: str, n: int) -> Path:
    # `tournament_00` pinned literally: `tournament_00.stale-*` siblings are earlier, superseded attempts.
    return gen / model / f"c{n:03d}" / "tournament_00" / "round_robin_match" / "bots" / model / "refinement" / "commit_0" / "qualification"


def _load_telemetry(qdir: Path) -> dict | None:
    gz, plain = qdir / "match_data.json.gz", qdir / "match_data.json"
    if gz.exists():
        return json.load(gzip.open(gz, "rt"))
    if plain.exists():
        return json.loads(plain.read_text())
    return None


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _wdl(res: dict) -> tuple[int, int, int]:
    ws = [m["winner"] for m in res["matches"]]
    return ws.count("red"), ws.count("tie"), ws.count("blue")


def _check_wdl(aid: str, bj: dict, res: dict, rel_result: Path) -> None:
    """bot.json W-D-L (from the pool ledger) must be what the official file says — except for the
    documented ruled-forfeit case: the round was played, a seed went physics-unstable, the harness
    scored the artifact -inf (qualification_score -1.0) and the ledger recorded forfeit:controller
    with wdl null (→ 0-0-0). Anything else is an inventory error."""
    got, want = _wdl(res), (bj["wins"], bj["draws"], bj["losses"])
    if got == want:
        return
    reason = bj.get("reason") or ""
    if reason.startswith("forfeit:") and want == (0, 0, 0):
        if any(m["physics_unstable"] for m in res["matches"]) and res["qualification_score"] == -1.0:
            return
        raise RuntimeError(f"{aid}: ruled {reason} but {rel_result} shows no physics-unstable seed / score {res['qualification_score']}")
    raise RuntimeError(f"{aid}: W-D-L {got} from {rel_result} != bot.json {want}")


def _seed_row(seed_idx: int, m: dict, capsule: str | None) -> dict:
    return {"seed_idx": seed_idx, "seed": m["seed"], "winner": m["winner"], "num_steps": m["num_steps"],
            "termination_reason": m["termination_reason"], "physics_unstable": bool(m["physics_unstable"]), "capsule": capsule}


def build(gen: "Path | dict[str, Path]", release: Path, bots: Path, assets_dir: Path, out: Path) -> dict:
    """`gen` is one telemetry root per qualification platform ({"laptop": …, "hpc": …, "gpu": …});
    a bare Path means the laptop root only. A platform with a root must have every fought sample's
    official telemetry there (md5-identical match_result.json); a platform without one stays pending."""
    roots: dict[str, Path] = dict(gen) if isinstance(gen, dict) else {"laptop": Path(gen)}
    assets_b64 = {f"assets/{n}": base64.b64encode((assets_dir / n).read_bytes()).decode() for n in ASSET_NAMES}
    index = json.loads((bots / "index.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    models: dict[str, dict] = {}
    total = dict.fromkeys(COUNT_KEYS, 0)
    listing: list[str] = []
    for global_idx, row in enumerate(index["bots"]):
        aid, model, n = row["artifact_id"], row["model"], int(row["sample_index"])
        bj = json.loads((bots / aid / "bot.json").read_text())["qualification"]
        platform = bj["platform"]
        rel_result = release / "samples" / model / f"c{n:03d}" / "qualification" / "match_result.json"
        fought = rel_result.exists()
        res = json.loads(rel_result.read_text()) if fought else None
        counts = models.setdefault(model, dict.fromkeys(COUNT_KEYS, 0))
        counts["samples"] += 1
        seeds: list[dict] = []
        telemetry, pending_reason = "none", None
        if fought:
            counts["fought"] += 1
            if len(res["matches"]) != N_SEEDS:
                raise RuntimeError(f"{rel_result}: {len(res['matches'])} seeds, expected {N_SEEDS}")
            _check_wdl(aid, bj, res, rel_result)
            if platform in roots:
                qdir = _laptop_qual_dir(roots[platform], model, n)
                lap_result = qdir / "match_result.json"
                data = _load_telemetry(qdir)
                if data is None or not lap_result.exists():
                    raise RuntimeError(f"{aid}: qualified on {platform} but no telemetry under {qdir}")
                if _md5(lap_result) != _md5(rel_result):
                    raise RuntimeError(f"{aid}: {platform} {lap_result} md5 != official {rel_result} md5")
                composed = (qdir / "composed.xml").read_text()
                telemetry = "official"
                (out / aid).mkdir(exist_ok=True)
                for seed_idx, m in enumerate(res["matches"]):
                    rec = data[f"seed_{m['seed']}"]
                    for k in ("winner", "num_steps", "seed"):
                        if rec[k] != m[k]:
                            raise RuntimeError(f"{aid} seed {m['seed']}: telemetry {k}={rec[k]!r} != result {m[k]!r}")
                    tid = qual_task_id(global_idx, seed_idx)
                    cap = _capsule(rec, composed, assets_b64, aid, BLOCK_AID, m["seed"], tid, "qualification")
                    cap["mujoco_version"] = MUJOCO_VERSION
                    cap["meta"].update({"max_steps": MAX_STEPS, "blue_xml_pipeline": "sh250-block"})
                    rel_path = f"qual/{aid}/seed_{seed_idx}.json.gz"
                    with gzip.open(out / aid / f"seed_{seed_idx}.json.gz", "wt") as f:
                        json.dump(cap, f)
                    listing.append(rel_path)
                    seeds.append(_seed_row(seed_idx, m, rel_path))
            else:
                telemetry = "pending"
                pending_reason = PENDING_REASON.format(platform=platform)
                seeds = [_seed_row(i, m, None) for i, m in enumerate(res["matches"])]
        counts[telemetry] += 1
        (out / aid).mkdir(exist_ok=True)
        (out / aid / "result.json").write_text(json.dumps({
            "schema": SCHEMA, "artifact_id": aid, "model": model, "sample_index": n, "platform": platform,
            "fought": fought, "telemetry": telemetry, "pending_reason": pending_reason, "result": res,
            "wins": bj["wins"], "draws": bj["draws"], "losses": bj["losses"], "passed": bool(bj["passed"]),
            "reason": bj["reason"], "seeds": seeds}, indent=1))
    for c in models.values():
        for k in COUNT_KEYS:
            total[k] += c[k]
    summary = {"schema": INDEX_SCHEMA, "run_id": RUN_ID, "n_seeds": N_SEEDS, "total": total, "models": models}
    (out / "index.json").write_text(json.dumps(summary, indent=1))
    (out / "capsules.txt").write_text("\n".join(listing) + ("\n" if listing else ""))
    return {"total": total, "models": models}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", action="append", required=True, metavar="PLATFORM=ROOT",
                    help="telemetry root per qualification platform, e.g. laptop=LOGS-SH250/20260918 hpc=LOGS-SH250/qual-hpc (repeatable)")
    ap.add_argument("--release", type=Path, required=True, help="release folder holding samples/<model>/cNNN/qualification/match_result.json")
    ap.add_argument("--bots", type=Path, required=True, help="site bots/ dir (index.json + <aid>/bot.json)")
    ap.add_argument("--assets", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    roots = {}
    for spec in a.gen:
        if "=" not in spec:
            raise SystemExit(f"--gen expects PLATFORM=ROOT, got {spec!r}")
        platform, root = spec.split("=", 1)
        roots[platform] = Path(root)
    print(json.dumps(build(roots, a.release, a.bots, a.assets, a.out)["total"]))
