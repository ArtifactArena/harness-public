"""The per-commit engineer prompt: only fields that carry something, and both designs
(best commit + last commit) so feedback always refers to code the model can see.

The rules, MJCF syntax and observation schema are not fields — they are the run's one
consolidated prompt, which is the signature's instruction (Task 15, item R)."""
from __future__ import annotations

import dspy

import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)
from mjarena.design_shop.agents.signatures.baseline_unified import BaselineUnifiedEngineer
from mjarena.design_shop.refinement_state import RefinementState

REMOVED_WORDS = ("stage", "holdout", "screenshot", "inspire", "whitebox")


def _compiled_text(signature, inputs: dict) -> str:
    from mjarena.design_shop.agents.L1_engineer_unified import build_engineer
    engineer = build_engineer(signature)
    messages = dspy.ChatAdapter().format(engineer.signature, demos=[], inputs=inputs)
    return "\n".join(str(m["content"]) for m in messages)


def test_refine_signature_fields():
    assert list(BaselineUnifiedEngineer.input_fields) == [
        "commit_status",
        "design_ledger",
        "best_commit_robot_xml", "best_commit_controller_code",
        "last_commit_robot_xml", "last_commit_controller_code",
        "last_commit_verifier_feedback", "last_commit_match_replay",
    ]
    assert list(BaselineUnifiedEngineer.output_fields) == [
        "name", "design_strategy", "hardware_plan", "combat_plan",
        "robot_xml", "controller_code", "change_summary",
    ]


def test_refine_prompt_has_no_dead_sections_and_names_both_designs():
    inputs = {k: f"<{k}>" for k in BaselineUnifiedEngineer.input_fields}
    text = _compiled_text(BaselineUnifiedEngineer, inputs)
    low = text.lower()
    for w in REMOVED_WORDS:
        assert w not in low, w
    assert text.index("[[ ## commit_status ## ]]") < text.index("[[ ## design_ledger ## ]]")
    for retired in ("task_spec", "rules", "mjcf_syntax", "obs_schema"):
        assert f"[[ ## {retired} ## ]]" not in text, retired
    assert "[[ ## last_commit_robot_xml ## ]]" in text
    assert "[[ ## best_commit_robot_xml ## ]]" in text
    assert "[[ ## last_commit_verifier_feedback ## ]]" in text
    assert "strategy.hinting" not in text          # old duplicated description text
    assert "scoreEmpty" not in text


def test_the_zero_shot_signature_is_built_from_the_prompt_alone():
    """There is no zero-shot signature class: sampling_prompt.md is the whole call."""
    from pathlib import Path
    import mjarena.design_shop.agents.signatures as signatures
    from mjarena.design_shop.agents.signatures.sampling import make_sampling_signature

    assert not hasattr(signatures, "BaselineUnifiedEngineerZeroShot")
    assert not (Path(signatures.__file__).parent / "baseline_unified_zero_shot.py").exists()

    root = Path(__file__).resolve().parents[1]
    sig = make_sampling_signature((root / "configs/rules/sampling_prompt.md").read_text())
    assert list(sig.input_fields) == []
    low = _compiled_text(sig, {}).lower()
    for w in REMOVED_WORDS:
        assert w not in low, w


def test_state_serves_last_commit_next_to_best(tmp_path):
    st = RefinementState(mode="unified", output_dir=None)
    st.update(round_num=0, score=2.0, content="<xml0/>", verifier_feedback="ok", creator_summary="c0",
              controller_code="code0", validation_passed=True, qualification_passed=True)
    # commit 0 is best AND last: the last_commit slot must not duplicate 6 KB of XML
    assert st.current_best_for_creator == "<xml0/>"
    assert st.last_commit_xml_for_creator == "same as best_commit (commit 1)"
    assert st.last_commit_controller_for_creator == "same as best_commit (commit 1)"
    # commit 1 regresses: best stays 0, last is 1
    st.update(round_num=1, score=1.0, content="<xml1/>", verifier_feedback="worse", creator_summary="c1",
              controller_code="code1", validation_passed=True, qualification_passed=True)
    assert st.current_best_for_creator == "<xml0/>"
    assert st.last_commit_xml_for_creator == "<xml1/>"
    assert st.last_commit_controller_for_creator == "code1"


def test_journal_has_no_dead_keys():
    import json
    st = RefinementState(mode="unified", output_dir=None)
    st.update(round_num=0, score=2.0, content="<xml0/>", verifier_feedback="ok", creator_summary="c0",
              controller_code="code0", validation_passed=True, qualification_passed=True,
              creator_outputs={"name": "B", "reasoning": "r", "design_strategy": "d",
                               "hardware_plan": "h", "combat_plan": "c"})
    entry = json.loads(st.to_json())["commits"][0]
    for k in ("critic_feedback", "stage2x_test_case_plan", "stage2x_test_case_observations",
              "holdout_replay_observations"):
        assert k not in entry


def test_last_commit_collapses_when_best_is_the_same_latest_attempt():
    """Before anything validates, 'best' falls back to the latest attempt: no duplicate XML."""
    st = RefinementState(mode="unified", output_dir=None)
    st.update(round_num=0, score=-1.0, content="<xml0/>", verifier_feedback="── Qualification ── FAILED\n  Physics instability detected — match terminated as loss.",
              creator_summary="c0", controller_code="code0", validation_passed=False, qualification_passed=False)
    assert st.current_best_for_creator == "<xml0/>"
    assert st.last_commit_xml_for_creator.startswith("same as best_commit")
    ledger = st.format_journal_for_creator()
    assert "Current best: none yet" in ledger
    assert "FAIL: Qualification: Physics instability detected" in ledger



def test_ledger_line_carries_the_score_breakdown():
    st = RefinementState(mode="unified", output_dir=None)
    parts = {"wins": 1, "n_seeds": 3, "mean_engagement": 0.2, "mean_dominant_contact": 0.1,
             "mean_displacement": 0.05, "mean_destabilization": 0.0, "mean_self_stability": 0.9}
    st.update(round_num=0, score=1.25, content="<x/>", verifier_feedback="ok", creator_summary="c0",
              controller_code="c", validation_passed=True, qualification_passed=True, scores=parts)
    line = st.format_journal_for_creator().split("\n")[0]
    assert "1.25/6.0 = wins 1/3 · engagement 0.20 · dominant_contact 0.10" in line
    assert "self_stability 0.90" in line


def test_ledger_counts_commits_from_one():
    st = RefinementState(mode="unified", output_dir=None)
    st.update(round_num=0, score=1.0, content="<a/>", verifier_feedback="ok", creator_summary="first",
              controller_code="c", validation_passed=True, qualification_passed=True)
    st.update(round_num=1, score=0.5, content="<b/>", verifier_feedback="ok", creator_summary="second",
              controller_code="c", validation_passed=True, qualification_passed=True)
    ledger = st.format_journal_for_creator()
    assert "=== Commit 1:" in ledger and "=== Commit 2:" in ledger and "Commit 0:" not in ledger
    assert "Current best: Commit 1 (" in ledger


def test_journal_keeps_full_summaries_and_ledger_cuts_only_old_ones():
    import json
    from mjarena.design_shop.refinement_state import LEDGER_FULL_RECENT
    st = RefinementState(mode="unified", output_dir=None)
    long = ("Changed the wedge angle because the block slid under it. " * 12).strip()   # ~700 chars
    for k in range(LEDGER_FULL_RECENT + 2):
        st.update(round_num=k, score=1.0, content=f"<x{k}/>", verifier_feedback="ok",
                  creator_summary=f"[{k}] " + long, controller_code="c", validation_passed=True,
                  qualification_passed=True)
    stored = [c["creator_summary"] for c in json.loads(st.to_json())["commits"]]
    assert all(len(x) > 600 for x in stored)                       # nothing lost on disk
    ledger = st.format_journal_for_creator()
    blocks = ledger.split("=== Commit ")[1:]
    old, new = blocks[0], blocks[-1]
    assert " …" in old and len(old) < 600                          # older: sentence-boundary cut
    assert old.split("\n")[1].endswith(". …")
    assert "[6] " + long in new                                     # recent: full text



def test_duplicate_flag_ignores_comments_and_descriptions(tmp_path):
    st = RefinementState(mode="unified", output_dir=tmp_path)
    a = '<mujoco model="a"><worldbody><!-- v1 --><body name="b" description="first"><freejoint/><geom name="g" type="box" size="0.1 0.1 0.1" material="steel"/></body></worldbody></mujoco>'
    b = a.replace("v1", "v2").replace('description="first"', 'description="second"').replace('model="a"', 'model="b"')
    c = a.replace('size="0.1 0.1 0.1"', 'size="0.2 0.1 0.1"')
    for k, xml in enumerate((a, b, c)):
        st.update(round_num=k, score=1.0, content=xml, verifier_feedback="ok", creator_summary=f"c{k}",
                  controller_code="c", validation_passed=True, qualification_passed=True)
    ledger = st.format_journal_for_creator()
    assert "physically identical to commit 1" in ledger.split("=== Commit 2:")[1].split("=== Commit 3:")[0]
    assert "identical" not in ledger.split("=== Commit 3:")[1]


def test_controller_only_change_is_not_hidden_behind_the_pointer():
    st = RefinementState(mode="unified", output_dir=None)
    st.update(round_num=0, score=2.0, content="<same/>", verifier_feedback="ok", creator_summary="c0",
              controller_code="ctrl-A", validation_passed=True, qualification_passed=True)
    st.update(round_num=1, score=0.5, content="<same/>", verifier_feedback="worse", creator_summary="c1",
              controller_code="ctrl-B", validation_passed=True, qualification_passed=True)
    assert st.last_commit_xml_for_creator.startswith("same as best_commit (commit 1)")
    assert "changed only the controller" in st.last_commit_xml_for_creator
    assert st.last_commit_controller_for_creator == "ctrl-B"          # the change the feedback is about


def test_xml_only_change_is_not_hidden_behind_the_pointer():
    st = RefinementState(mode="unified", output_dir=None)
    st.update(round_num=0, score=2.0, content="<a/>", verifier_feedback="ok", creator_summary="c0",
              controller_code="same-ctrl", validation_passed=True, qualification_passed=True)
    st.update(round_num=1, score=0.5, content="<b/>", verifier_feedback="worse", creator_summary="c1",
              controller_code="same-ctrl", validation_passed=True, qualification_passed=True)
    assert st.last_commit_xml_for_creator == "<b/>"
    assert "changed only the robot_xml" in st.last_commit_controller_for_creator
