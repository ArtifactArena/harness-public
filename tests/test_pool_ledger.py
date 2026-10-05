"""The pool ledger decides who enters the round robin: qualified, validated, non-forfeit samples only."""
import json, sys
import pytest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import pool_ledger  # noqa: E402


def _write_qual_result(qdir, winners):
    """Three rounds against the block; the ledger derives W/D/L from these, not from the journal flag."""
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / "match_result.json").write_text(json.dumps({"red_bot": "bot", "blue_bot": "", "n_seeds": len(winners),
        "matches": [{"seed": i, "winner": w, "num_steps": 100, "termination_reason": "ring_out" if w != "tie" else "draw"} for i, w in enumerate(winners)]}))


def _slot(root, model, idx, *, generated=True, qualified=True, forfeit=False, validated=True, qual_passed=True, score=2.5,
          winners=None):
    d = root / model / f"c{idx:03d}"; d.mkdir(parents=True)
    if generated:
        (d / "gen.json").write_text("{}")
    if qualified:
        bot = d / "tournament_00/round_robin_match/bots" / model
        (bot / "refinement/commit_0").mkdir(parents=True)
        (bot / "refinement/commit_0/robot.xml").write_text("<mujoco/>")
        (bot / "refinement/commit_0/controller.py").write_text("def policy_step(obs): return {}")
        (bot / "bot_artifact.json").write_text(json.dumps({"forfeit": forfeit, "forfeit_stage": "qualification" if forfeit else ""}))
        (bot / "refinement/journal.json").write_text(json.dumps({"commits": [{"validation_passed": validated, "qualification_passed": qual_passed, "score": score}]}))
        _write_qual_result(bot / "refinement/commit_0/qualification", winners if winners is not None else (['red']*3 if qual_passed else ['blue', 'blue', 'red']))
    return d


def _pack_slot(root, model, idx, *, generated=True, qualified=True, forfeit=False, validated=True, qual_passed=True, score=2.5,
               winners=None):
    """Same slot as `_slot`, in the flat layout `pack_pool.py` writes: everything under <model>/cNNN/."""
    d = root / model / f"c{idx:03d}"; d.mkdir(parents=True)
    if generated:
        (d / "gen.json").write_text("{}")
    if qualified:
        (d / "commit_0").mkdir()
        (d / "commit_0/robot.xml").write_text("<mujoco/>")
        (d / "commit_0/controller.py").write_text("def policy_step(obs): return {}")
        (d / "bot_artifact.json").write_text(json.dumps({"forfeit": forfeit, "forfeit_stage": "qualification" if forfeit else ""}))
        (d / "journal.json").write_text(json.dumps({"commits": [{"validation_passed": validated, "qualification_passed": qual_passed, "score": score}]}))
        _write_qual_result(d / "qualification", winners if winners is not None else (['red']*3 if qual_passed else ['blue', 'blue', 'red']))
    return d


def test_only_qualified_validated_non_forfeit_samples_are_eligible(tmp_path):
    _slot(tmp_path, "m", 0)                                   # eligible
    _slot(tmp_path, "m", 1, forfeit=True)                     # forfeit
    _slot(tmp_path, "m", 2, qualified=False)                  # awaiting qualification
    _slot(tmp_path, "m", 3, generated=False, qualified=False) # never generated
    _slot(tmp_path, "m", 4, qual_passed=False)                # qualified run, failed the gate
    eligible, ledger = pool_ledger.scan_pool(tmp_path, "m", n_samples=5)
    assert [r["tournament_idx"] for r in eligible] == [0]
    assert eligible[0]["commit_dir"].endswith("m/c000/tournament_00/round_robin_match/bots/m/refinement/commit_0")
    assert eligible[0]["commit_idx"] == 0 and eligible[0]["qualification_score"] == 2.5
    reasons = {r["idx"]: r["reason"] for r in ledger}
    assert reasons == {0: "eligible", 1: "forfeit:qualification", 2: "not qualified yet", 3: "not generated", 4: "qualification failed (W1 D0 L2)"}
    assert len(ledger) == 5


def test_all_with_xml_lifts_the_gate(tmp_path):
    _slot(tmp_path, "m", 0, forfeit=True)
    _slot(tmp_path, "m", 1, qual_passed=False)
    eligible, _ = pool_ledger.scan_pool(tmp_path, "m", n_samples=2, require_qualified=False)
    assert [r["tournament_idx"] for r in eligible] == [0, 1]


def test_pack_layout_reads_the_flat_slot(tmp_path):
    _pack_slot(tmp_path, "m", 0)                                   # eligible
    _pack_slot(tmp_path, "m", 1, forfeit=True)                     # forfeit
    _pack_slot(tmp_path, "m", 2, qualified=False)                  # awaiting qualification
    _pack_slot(tmp_path, "m", 3, generated=False, qualified=False) # never generated
    _pack_slot(tmp_path, "m", 4, qual_passed=False)                # qualified run, failed the gate
    eligible, ledger = pool_ledger.scan_pool(tmp_path, "m", n_samples=5, layout="pack")
    assert [r["tournament_idx"] for r in eligible] == [0]
    assert eligible[0]["commit_dir"].endswith("m/c000/commit_0")
    assert "tournament_00" not in eligible[0]["commit_dir"]
    assert eligible[0]["commit_idx"] == 0 and eligible[0]["qualification_score"] == 2.5
    reasons = {r["idx"]: r["reason"] for r in ledger}
    assert reasons == {0: "eligible", 1: "forfeit:qualification", 2: "not qualified yet", 3: "not generated", 4: "qualification failed (W1 D0 L2)"}
    assert len(ledger) == 5


@pytest.mark.parametrize("winners,eligible", [
    (["red", "red", "red"], True),      # W3
    (["red", "red", "blue"], True),     # W2 L1: more wins than losses (user ruling 2026-09-19)
    (["tie", "tie", "tie"], True),      # no loss at all: "not losing is the minimum bar"
    (["red", "tie", "tie"], True),
    (["red", "tie", "blue"], False),    # W1 D1 L1: wins not greater than losses
    (["red", "blue", "blue"], False),   # W1 L2
    (["blue", "blue", "blue"], False),
    (["tie", "tie", "blue"], False),    # W0 D2 L1: a loss with no win to outweigh it
])
def test_entry_gate_no_loss_or_more_wins_than_losses(tmp_path, winners, eligible):
    _slot(tmp_path, "m", 0, qual_passed=False, winners=winners)   # the journal flag is ignored by the gate
    elig, led = pool_ledger.scan_pool(tmp_path, "m", n_samples=1)
    assert (len(elig) == 1) is eligible, led[0]["reason"]
    w = winners.count("red"); l = winners.count("blue"); d = winners.count("tie")
    assert led[0]["wdl"] == [w, d, l]
    if not eligible:
        assert led[0]["reason"] == f"qualification failed (W{w} D{d} L{l})"
