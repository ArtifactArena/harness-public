"""Top-5 Round + Champions Round games → browser-match-trace-v1 capsules (no re-simulation).

python scripts/sampling/website/build_capsules.py --rr LOGS-SH250/rr-final --assets mjarena/assets --out LOGS-SH250/site
"""
from __future__ import annotations
import argparse, base64, gzip, hashlib, json, sys
from pathlib import Path
_SAMPLING = Path(__file__).resolve().parents[1]
if str(_SAMPLING) not in sys.path:
    sys.path.insert(0, str(_SAMPLING))
from website.site_ids import RUN_ID, capsule_sha, site_aid, task_id  # noqa: E402

ASSET_NAMES = ("octagon_platform.obj", "octagon_surface.obj")
MUJOCO_VERSION = "3.10.0"   # the cluster env (sh250) that produced every telemetry file


def _pairing_dirs(rr: Path):
    top1 = rr / "stage_b" / "top1" / "matches"
    for d in sorted(p for p in top1.iterdir() if p.is_dir()):
        yield "champions", None, d
    top5 = rr / "stage_b" / "top5"
    for mdir in sorted(p for p in top5.iterdir() if p.is_dir()):
        mm = mdir / "matches"
        if not mm.exists():
            continue
        for d in sorted(p for p in mm.iterdir() if p.is_dir()):
            yield "top5", mdir.name, d


def _capsule(rec: dict, composed: str, assets_b64: dict, red: str, blue: str, seed: int, tid: str, rnd: str) -> dict:
    cap = dict(rec)
    cap["qpos_log"] = cap.pop("qpos")
    cap.setdefault("initial_qpos", cap["qpos_log"][0])
    cap["composed_xml"] = composed
    cap["mujoco_version"] = MUJOCO_VERSION
    cap["wall_seconds"] = None
    cap.setdefault("controller_errors", [])
    for k in ("qacc_body_name", "qacc_dof_index", "qacc_loser"):
        cap.setdefault(k, None)
    cap["assets"] = assets_b64
    cap["fixture"] = "ft-" + hashlib.sha256(f"{red}|{blue}|{seed}".encode()).hexdigest()[:26]
    cap["fixture_dir"] = ""
    cap["meta"] = {"name": f"{red}_vs_{blue}", "red_bot": red, "blue_bot": blue, "seed": seed, "max_steps": 30000,
                   "red_actuators": rec.get("red_actuator_names") or [], "blue_actuators": rec.get("blue_actuator_names") or [],
                   "red_xml_pipeline": "sh250", "blue_xml_pipeline": "sh250", "assets": list(ASSET_NAMES),
                   "round": rnd, "task_id": tid}
    return cap


def build(rr: Path, assets_dir: Path, out: Path, *, n_seeds: int = 11) -> dict:
    assets_b64 = {f"assets/{n}": base64.b64encode((assets_dir / n).read_bytes()).decode() for n in ASSET_NAMES}
    replays = out / "replays"; replays.mkdir(parents=True, exist_ok=True)
    pairings, listing, games = [], [], 0
    for pair_idx, (rnd, model, d) in enumerate(_pairing_dirs(rr)):
        res = json.loads((d / "match_result.json").read_text())
        if len(res["matches"]) != n_seeds:
            raise RuntimeError(f"{d}: {len(res['matches'])} seeds, expected {n_seeds}")
        data = json.load(gzip.open(d / "match_data.json.gz", "rt"))
        composed = (d / "composed.xml").read_text()
        red_tid, blue_tid = res["red_bot"], res["blue_bot"]
        red, blue = site_aid(red_tid), site_aid(blue_tid)
        seeds = []
        for seed_idx, m in enumerate(res["matches"]):
            rec = data[f"seed_{m['seed']}"]
            for k in ("winner", "num_steps", "seed"):
                if rec[k] != m[k]:
                    raise RuntimeError(f"{d} seed {m['seed']}: telemetry {k}={rec[k]!r} != result {m[k]!r}")
            tid = task_id(pair_idx, seed_idx); sha = capsule_sha(tid)
            cap = _capsule(rec, composed, assets_b64, red, blue, m["seed"], tid, rnd)
            with gzip.open(replays / f"{sha}.json.gz", "wt") as f:
                json.dump(cap, f)
            listing.append(sha)
            seeds.append({"seed_idx": seed_idx, "seed": m["seed"], "task_id": tid, "sha": sha, "winner": m["winner"], "num_steps": m["num_steps"],
                          "termination_reason": m["termination_reason"], "physics_unstable": bool(m["physics_unstable"])})
            games += 1
        pairings.append({"pair_idx": pair_idx, "round": rnd, "model": model, "red": red, "blue": blue, "red_tid": red_tid, "blue_tid": blue_tid, "seeds": seeds})
    (out / "pairings.json").write_text(json.dumps({"run_id": RUN_ID, "n_seeds": n_seeds, "pairings": pairings}, indent=1))
    (out / f"capsules-{RUN_ID}.txt").write_text("\n".join(listing) + "\n")
    return {"pairings": len(pairings), "games": games}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rr", type=Path, required=True); ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True); ap.add_argument("--n-seeds", type=int, default=11)
    a = ap.parse_args()
    print(json.dumps(build(a.rr, a.assets, a.out, n_seeds=a.n_seeds)))
