"""validate_pool.py: the post-run integrity check for a sampling pool root.

A slot is STALE when its gen.json is newer than the qualified bot_artifact.json (a late duplicate
generation overwrote it before save_result refused to). `--fix` sets such slots aside for
re-qualification (tournament_00 -> tournament_00.stale-<ts>, build bookkeeping removed) and merges
any generation usage rows that never reached the bot dir.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import validate_pool  # noqa: E402

OUT = {"robot_xml": "<mujoco/>", "controller_code": "def policy_step(obs):\n    return {}"}


def _slot(root, stem, idx, gen=True, qualified=False, gen_after=False, gen_usage=False):
    d = root / stem / f"c{idx:03d}"; d.mkdir(parents=True)
    bot = d / "tournament_00/round_robin_match/bots" / stem
    if qualified:
        (bot / "refinement/commit_0").mkdir(parents=True)
        (bot / "bot_artifact.json").write_text(json.dumps({"forfeit": False}))
        (bot / "refinement/usage.jsonl").write_text(json.dumps({"role": "verifier"}) + "\n")
        (d / "config.yaml").write_text("x"); (d / ".build_progress").mkdir(); (d / ".build_progress" / f"{stem}.json").write_text("{}")
        t = time.time() - 600
        for p in (bot / "bot_artifact.json",):
            os.utime(p, (t, t))
    if gen:
        (d / "gen.json").write_text(json.dumps({"outputs": OUT}))
        if not gen_after:
            t = time.time() - 1200
            os.utime(d / "gen.json", (t, t))
    if gen_usage:
        (d / "gen/refinement").mkdir(parents=True)
        (d / "gen/refinement/usage.jsonl").write_text(json.dumps({"role": "engineer", "completion_tokens": 3}) + "\n")
    return d


def test_report_counts_missing_stale_and_unmerged(tmp_path):
    _slot(tmp_path, "m", 0, qualified=True)                       # good
    stale = _slot(tmp_path, "m", 1, qualified=True, gen_after=True)  # regenerated after qualification
    _slot(tmp_path, "m", 2)                                        # awaiting qualification
    _slot(tmp_path, "m", 3, gen=False)                             # missing
    unmerged = _slot(tmp_path, "m", 4, qualified=True, gen_usage=True)
    rows = validate_pool.scan(tmp_path, ["m"], n_samples=5)
    r = rows["m"]
    assert r["generated"] == 4 and r["missing"] == [3] and r["qualified"] == 3
    assert r["stale"] == [1] and r["unmerged_usage"] == [4] and r["awaiting"] == 1
    md = validate_pool.render(rows, n_samples=5)
    assert "| m |" in md and "c001" in md


def test_fix_sets_stale_slots_aside_and_merges_usage(tmp_path):
    stale = _slot(tmp_path, "m", 1, qualified=True, gen_after=True)
    unmerged = _slot(tmp_path, "m", 4, qualified=True, gen_usage=True)
    rows = validate_pool.scan(tmp_path, ["m"], n_samples=5)
    validate_pool.fix(tmp_path, rows)
    assert not (stale / "tournament_00").exists() and not (stale / "config.yaml").exists()
    assert not (stale / ".build_progress").exists()
    aside = list(stale.glob("tournament_00.stale-*"))
    assert len(aside) == 1 and (aside[0] / "round_robin_match/bots/m/bot_artifact.json").exists()
    assert (stale / "gen.json").exists()
    usage = unmerged / "tournament_00/round_robin_match/bots/m/refinement/usage.jsonl"
    rows_ = [json.loads(l) for l in usage.read_text().splitlines()]
    assert [r["role"] for r in rows_] == ["engineer", "verifier"] and not (unmerged / "gen").exists()
    after = validate_pool.scan(tmp_path, ["m"], n_samples=5)["m"]
    assert after["stale"] == [] and after["unmerged_usage"] == [] and after["awaiting"] == 1
