"""build_bots_dir: one self-describing bundle per sampled bot from the verified tournament tree
(pack-all + rr-final + pack-MANIFEST), md5-checked against the manifest, ledger W-D-L checked
against the qualification file, rounds records (run / Top-5 Round / Champions Round) and roles."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/sampling"))
from website import build_bots_dir as B  # noqa: E402

MODEL = "toy-model"


def _sample(pack, n, name="Bot %d", qual=(3, 0, 0), forfeit=False):
    d = pack / MODEL / f"c{n:03d}"; d.mkdir(parents=True)
    (d / "robot.xml").write_text(f"<mujoco><worldbody><body name='b{n}'/></worldbody></mujoco>")
    (d / "controller.py").write_text(f"def policy_step(obs):\n    return {{}}  # {n}\n")
    (d / "gen.json").write_text(json.dumps({"stem": MODEL, "idx": n, "ts": "2026-09-18T00:00:00+00:00", "wall_s": 1.0, "llm_calls": 1,
        "git_sha": "abc", "model": "configs/models/x.yaml",
        "outputs": {"name": (name % n) if name else "", "design_rationale": "r", "design_strategy": "s", "hardware_plan": "h", "combat_plan": "c", "change_summary": "sum"}}))
    (d / "bot_artifact.json").write_text(json.dumps({"morphology_verified": True, "controller_verified": not forfeit, "forfeit": forfeit, "forfeit_stage": "controller" if forfeit else "", "forfeit_error": ""}))
    (d / "usage.jsonl").write_text(json.dumps({"prompt_tokens": 1, "completion_tokens": 2, "reasoning_tokens": 3, "total_tokens": 6, "reasoning_source": "native"}) + "\n")
    w, dr, l = qual
    (d / "qualification").mkdir()
    (d / "qualification" / "match_result.json").write_text(json.dumps({"qualification_score": 4.0, "n_seeds": 3,
        "matches": [{"winner": "red"}] * w + [{"winner": "tie"}] * dr + [{"winner": "blue"}] * l}))


def _ledger(idx, eligible, reason, wdl, score):
    return {"idx": idx, "generated": True, "qualified": eligible, "forfeit": wdl is None, "forfeit_stage": "controller" if wdl is None else "", "validation_passed": True,
            "qualification_passed": eligible, "qualification_score": score, "wdl": None if wdl is None else list(wdl), "eligible": eligible, "reason": reason,
            "artifact_id": f"{MODEL}__t{idx:02d}_c000"}


def _tree(tmp_path):
    pack = tmp_path / "pack"; rr = tmp_path / "rr"
    _sample(pack, 0); _sample(pack, 1, qual=(1, 0, 2)); _sample(pack, 2, name=None); _sample(pack, 3, forfeit=True)
    (pack / MODEL / "c003" / "qualification" / "match_result.json").unlink()   # a forfeit never fought
    g = rr / MODEL / "g0"; g.mkdir(parents=True)
    tids = [f"{MODEL}__t00_c000", f"{MODEL}__t02_c000"]
    (g / "elo.json").write_text(json.dumps({"model": MODEL, "method": "bt", "standings": {
        tids[0]: {"wins": 1, "losses": 0, "draws": 0, "elo": 1050.0, "games": 1}, tids[1]: {"wins": 0, "losses": 1, "draws": 0, "elo": 950.0, "games": 1}}}))
    (g / "pool_ledger.json").write_text(json.dumps({"model": MODEL, "group": "g0", "slot_range": [0, 4], "eligible": 2, "generated_at": "2026-09-19T00:00:00+00:00",
        "ledger": [_ledger(0, True, "eligible", (3, 0, 0), 4.0), _ledger(1, False, "qualification failed (W1 D0 L2)", (1, 0, 2), 4.0), _ledger(2, True, "eligible", (3, 0, 0), 4.0),
                   _ledger(3, False, "forfeit:controller", None, -1.0)]}))
    (rr / MODEL / "runs.json").write_text(json.dumps({"model": MODEL, "runs": 1, "run_size": 4, "groups": [{"group": "g0", "slot_range": [0, 4], "eligible": 2, "winner": tids[0], "ties_at_top": [tids[0]]}]}))
    (rr / "stage_b" / "top5" / MODEL).mkdir(parents=True)
    (rr / "stage_b" / "top5" / MODEL / "SKIPPED.json").write_text(json.dumps({"model": MODEL, "stage": "b1", "reason": "1 bot", "n_bots": 1, "bots": [tids[0]]}))
    (rr / "stage_b" / "top1").mkdir(parents=True)
    (rr / "stage_b" / "top1" / "elo.json").write_text(json.dumps({"participants": [tids[0]], "standings": {tids[0]: {"wins": 0, "losses": 0, "draws": 0, "elo": 1000.0, "games": 0}}}))
    files = {str(p.relative_to(pack)): hashlib.md5(p.read_bytes()).hexdigest() for p in pack.rglob("*") if p.is_file()}
    man = tmp_path / "pack-MANIFEST.json"
    man.write_text(json.dumps({"models": {MODEL: {"qualified_on": "laptop", "n_samples": 4}}, "files": files}))
    return rr, pack, man


def test_builds_every_sample_with_roles(tmp_path):
    rr, pack, man = _tree(tmp_path)
    out = tmp_path / "bots"
    counts = B.build(rr, pack, man, out)["counts"]
    assert counts == {"samples": 4, "qualified": 2, "run_winners": 1, "champions": 1, "unnamed": 1}
    b0 = json.loads((out / f"{MODEL}__sampling__t000_c000" / "bot.json").read_text())
    assert b0["role"] == "champion" and b0["rounds"]["run"]["winner"]
    assert b0["rounds"]["top5"] == {"size": 1, "rank": 1, "elo": None, "wins": 0, "losses": 0, "draws": 0, "games": 0, "winner": True}
    assert b0["rounds"]["champions"]["rank"] == 1
    assert b0["qualification"] == {"platform": "laptop", "wins": 3, "draws": 0, "losses": 0, "score": 4.0, "passed": True, "reason": None}
    b1 = json.loads((out / f"{MODEL}__sampling__t001_c000" / "bot.json").read_text())
    assert b1["role"] == "not-qualified" and b1["rounds"] == {"run": None, "top5": None, "champions": None}
    assert b1["qualification"]["reason"] == "qualification failed (W1 D0 L2)" and b1["qualification"]["losses"] == 2
    b2 = json.loads((out / f"{MODEL}__sampling__t002_c000" / "bot.json").read_text())
    assert b2["name"] is None and b2["role"] == "qualified" and b2["rounds"]["run"]["rank"] == 2
    assert (out / f"{MODEL}__sampling__t002_c000" / "robot.xml").read_text().startswith("<mujoco>")
    b3 = json.loads((out / f"{MODEL}__sampling__t003_c000" / "bot.json").read_text())
    assert b3["qualification"] == {"platform": "laptop", "wins": 0, "draws": 0, "losses": 0, "score": None, "passed": False, "reason": "forfeit:controller"}
    assert b3["build"]["forfeit"] is True and b3["role"] == "not-qualified"
    idx = json.loads((out / "index.json").read_text())
    assert idx["schema"] == "sh250-bots-index-v1" and len(idx["bots"]) == 4
    bym = json.loads((out / "by-model" / f"{MODEL}.json").read_text())
    assert [b["sample_index"] for b in bym["bots"]] == [0, 1, 2, 3] and bym["bots"][0]["texts"]["reasoning"] == "r"


def test_md5_must_match_manifest(tmp_path):
    rr, pack, man = _tree(tmp_path)
    (pack / MODEL / "c000" / "robot.xml").write_text("<mujoco/>")   # tamper after the manifest
    with pytest.raises(RuntimeError, match="md5"):
        B.build(rr, pack, man, tmp_path / "bots")


def test_ledger_wdl_must_match_qualification_file(tmp_path):
    rr, pack, man = _tree(tmp_path)
    led = json.loads((rr / MODEL / "g0" / "pool_ledger.json").read_text())
    led["ledger"][0]["wdl"] = [2, 1, 0]
    (rr / MODEL / "g0" / "pool_ledger.json").write_text(json.dumps(led))
    with pytest.raises(RuntimeError, match="wdl"):
        B.build(rr, pack, man, tmp_path / "bots")
