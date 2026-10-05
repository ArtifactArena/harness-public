"""bots/: one self-describing bundle per sampled bot (all 5,750), from the verified tournament tree.

python scripts/sampling/website/build_bots_dir.py --rr LOGS-SH250/rr-final --pack LOGS-SH250/pack-all \
    --manifest LOGS-SH250/release-sh250-pool-5ac92bc7/pack-MANIFEST.json --out LOGS-SH250/site/bots
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from pathlib import Path
_SAMPLING = Path(__file__).resolve().parents[1]          # scripts/sampling — same shim as pool_rr.py:52
if str(_SAMPLING) not in sys.path:
    sys.path.insert(0, str(_SAMPLING))
import pool_ledger  # noqa: E402
from website.site_ids import RUN_ID, POOL_RUN_ID, site_aid  # noqa: E402

SCHEMA = "sh250-bot-v1"
TEXT_KEYS = {"reasoning": "design_rationale", "design_strategy": "design_strategy",
             "hardware_plan": "hardware_plan", "combat_plan": "combat_plan", "change_summary": "change_summary"}
USAGE_KEYS = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens", "reasoning_source")
BUILD_KEYS = ("morphology_verified", "controller_verified", "forfeit", "forfeit_stage", "forfeit_error")


def _json(p: Path):
    return json.loads(p.read_text())


def _tidx(tid: str) -> int:
    return int(tid.rsplit("__t", 1)[1].split("_")[0])


def _ranked(standings: dict) -> dict[str, int]:
    """Rating descending, exact ties by lowest tournament index — the harness's own rank order (pool_rr.py:167-173)."""
    order = sorted(standings, key=lambda t: (-standings[t]["elo"], _tidx(t)))
    return {t: i + 1 for i, t in enumerate(order)}


def _rec(standings: dict, ranks: dict, tid: str, **extra) -> dict:
    s = standings[tid]
    return {"rank": ranks[tid], "elo": round(s["elo"], 2), "wins": s["wins"], "losses": s["losses"],
            "draws": s["draws"], "games": s["games"], **extra}


def _copy_checked(src: Path, dst: Path, manifest_md5: str | None, rel: str) -> str | None:
    if not src.exists():
        return None
    got = hashlib.md5(src.read_bytes()).hexdigest()
    if manifest_md5 is None or got != manifest_md5:
        raise RuntimeError(f"md5 mismatch for {rel}: pack {got} manifest {manifest_md5}")
    shutil.copyfile(src, dst)
    return got


def build(rr: Path, pack: Path, manifest: Path, out: Path) -> dict:
    man = _json(manifest)
    files_md5: dict = man["files"]
    champions = _json(rr / "stage_b" / "top1" / "elo.json")
    champ_ranks = _ranked(champions["standings"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "by-model").mkdir(exist_ok=True)
    index, counts = [], {"samples": 0, "qualified": 0, "run_winners": 0, "champions": 0, "unnamed": 0}
    for model_dir in sorted(p for p in rr.iterdir() if p.is_dir() and p.name != "stage_b"):
        model = model_dir.name
        platform = man["models"][model]["qualified_on"]
        runs = _json(model_dir / "runs.json")
        slot_run: dict[int, dict] = {}
        for g in runs["groups"]:
            gdir = model_dir / g["group"]
            elo = _json(gdir / "elo.json")["standings"]
            ranks = _ranked(elo)
            ledger = {e["idx"]: e for e in _json(gdir / "pool_ledger.json")["ledger"]}
            for idx in range(*g["slot_range"]):
                slot_run[idx] = {"group": g, "elo": elo, "ranks": ranks, "ledger": ledger[idx]}
        top5_dir = rr / "stage_b" / "top5" / model
        if (top5_dir / "elo.json").exists():
            t5 = _json(top5_dir / "elo.json"); t5_st = t5["standings"]; t5_ranks = _ranked(t5_st); t5_size = len(t5["participants"])
            lone_winner = None
        else:
            skipped = _json(top5_dir / "SKIPPED.json")
            if skipped["n_bots"] != 1:
                raise RuntimeError(f"{model}: Top-5 Round skipped with {skipped['n_bots']} bots")
            t5_st, t5_ranks, t5_size, lone_winner = {}, {}, 1, skipped["bots"][0]
        model_rows = []
        for cdir in sorted(pack.joinpath(model).glob("c[0-9][0-9][0-9]")):
            n = int(cdir.name[1:]); tid = f"{model}__t{n:02d}_c000"; aid = site_aid(tid)
            gen = _json(cdir / "gen.json"); outputs = gen["outputs"]
            art = _json(cdir / "bot_artifact.json") if (cdir / "bot_artifact.json").exists() else {}
            usage_lines = (cdir / "usage.jsonl").read_text().splitlines() if (cdir / "usage.jsonl").exists() else []
            calls = [json.loads(l) for l in usage_lines if l.strip()]          # >1 line = retries (591 samples); absent for the 12 GPU-cluster models
            u = {k: sum(c.get(k) or 0 for c in calls) for k in USAGE_KEYS if k != "reasoning_source"} if calls else {}
            if calls:
                u["reasoning_source"] = calls[-1].get("reasoning_source")
            sr = slot_run[n]; led = sr["ledger"]
            if led["artifact_id"] != tid:
                raise RuntimeError(f"{model} slot {n}: ledger artifact_id {led['artifact_id']} != {tid}")
            qual_p = cdir / "qualification" / "match_result.json"
            if led["wdl"] is None:            # a forfeit: never fought the block
                w, d, l, score = 0, 0, 0, None
            else:
                if qual_p.exists():
                    file_wdl = pool_ledger.qualification_wdl(qual_p)
                    if list(file_wdl) != list(led["wdl"]):
                        raise RuntimeError(f"{tid}: ledger wdl {led['wdl']} != qualification file wdl {file_wdl}")
                w, d, l = led["wdl"]; score = led["qualification_score"]
            bdir = out / aid; bdir.mkdir(exist_ok=True)
            rel = f"{model}/{cdir.name}"
            xml_md5 = _copy_checked(cdir / "robot.xml", bdir / "robot.xml", files_md5.get(f"{rel}/robot.xml"), f"{rel}/robot.xml")
            py_md5 = _copy_checked(cdir / "controller.py", bdir / "controller.py", files_md5.get(f"{rel}/controller.py"), f"{rel}/controller.py")
            run_rec = None
            if led["eligible"]:
                run_rec = {"group": sr["group"]["group"], "slot_range": sr["group"]["slot_range"], "eligible": sr["group"]["eligible"],
                           **_rec(sr["elo"], sr["ranks"], tid, winner=sr["group"]["winner"] == tid)}
            top5_rec = None
            if tid in t5_st:
                top5_rec = {"size": t5_size, **_rec(t5_st, t5_ranks, tid, winner=t5_ranks[tid] == 1)}
            elif tid == lone_winner:
                top5_rec = {"size": 1, "rank": 1, "elo": None, "wins": 0, "losses": 0, "draws": 0, "games": 0, "winner": True}
            champ_rec = _rec(champions["standings"], champ_ranks, tid) if tid in champions["standings"] else None
            role = "champion" if champ_rec else "run-winner" if top5_rec else "qualified" if run_rec else "not-qualified"
            name = (outputs.get("name") or "").strip() or None
            rec = {
                "schema": SCHEMA, "artifact_id": aid, "tournament_id": tid, "model": model, "condition": "sampling",
                "sample_index": n, "name": name,
                "texts": {k: outputs.get(src) or "" for k, src in TEXT_KEYS.items()},
                "generation": {"generated_at": gen["ts"], "wall_s": gen["wall_s"], "llm_calls": gen["llm_calls"],
                               "harness_sha": gen["git_sha"], "model_config": gen["model"], "usage": {k: u.get(k) for k in USAGE_KEYS}},   # summed over the sample's LLM calls; null when no usage.jsonl
                "files": {"robot_xml_md5": xml_md5, "controller_py_md5": py_md5},
                "build": {k: art.get(k) for k in BUILD_KEYS},
                "qualification": {"platform": platform, "wins": w, "draws": d, "losses": l, "score": score,
                                  "passed": bool(led["eligible"]), "reason": None if led["eligible"] else led["reason"]},
                "rounds": {"run": run_rec, "top5": top5_rec, "champions": champ_rec},
                "role": role,
            }
            (bdir / "bot.json").write_text(json.dumps(rec, indent=1))
            model_rows.append(rec)
            counts["samples"] += 1; counts["qualified"] += bool(run_rec); counts["run_winners"] += bool(top5_rec)
            counts["champions"] += bool(champ_rec); counts["unnamed"] += name is None
            index.append({"artifact_id": aid, "tournament_id": tid, "model": model, "sample_index": n, "name": name, "role": role,
                          "qualified": bool(run_rec), "run_group": run_rec and run_rec["group"], "run_rank": run_rec and run_rec["rank"],
                          "run_elo": run_rec and run_rec["elo"], "top5_rank": top5_rec and top5_rec["rank"], "top5_elo": top5_rec and top5_rec["elo"],
                          "champions_rank": champ_rec and champ_rec["rank"], "champions_elo": champ_rec and champ_rec["elo"], "robot_xml_md5": xml_md5})
        (out / "by-model" / f"{model}.json").write_text(json.dumps({"model": model, "run_id": RUN_ID, "bots": model_rows}, indent=1))
    header = {"schema": "sh250-bots-index-v1", "run_id": RUN_ID, "pool_run_id": POOL_RUN_ID, "counts": counts, "bots": index}
    (out / "index.json").write_text(json.dumps(header, indent=1))
    return header


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rr", type=Path, required=True); ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.rr, a.pack, a.manifest, a.out)["counts"]))
