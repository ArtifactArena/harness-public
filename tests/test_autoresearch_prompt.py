"""Exercise the real refinement loop with scripted model responses, without API calls.

Ported from the upstream unit-tests/test_autoresearch_prompt.py and adapted to the harness:
its field names, its single consolidated-prompt path (no optional build-phase modes),
and the two run configs that use it — arh.yaml (iterative) and sh.yaml (zero-shot).
"""
import json
from dataclasses import dataclass
from pathlib import Path

import dspy
import pytest
import yaml

# Keep the production import order (the design-shop package has circular imports).
import mjarena.core.unified_builder as builder
from mjarena.core.build_config import BuildConfig, ControllerValidationParams
from mjarena.design_shop.agents.L1_engineer_unified import run_baseline_engineer_unified
from mjarena.design_shop.agents.signatures.autoresearch import make_autoresearch_signature
from mjarena.design_shop.agents.signatures.sampling import make_sampling_signature
from mjarena.design_shop.types import UnifiedEnvResult, VerifierResult

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "configs/rules/autoresearch_prompt.md"
SAMPLING_PROMPT = ROOT / "configs/rules/sampling_prompt.md"
GAME_SPEC_VARS = {"mujoco_version": "3.10.0", "commit_budget": 50}


def answer(name, xml=None):
    return dict(design_rationale="Test response", name=name, improvement_plan="Plan " + name,
                design_strategy="Concept " + name,
                hardware_plan="Mass calculation", combat_plan="Control plan",
                robot_xml=xml or f'<mujoco model="{name}"/>',
                controller_code="def policy_step(obs):\n    return {'drive': 0.0}",
                change_summary="Revision " + name)


def test_consolidated_prompt_replaces_the_four_modular_inputs():
    prompt = PROMPT.read_text()
    signature = make_autoresearch_signature(prompt)
    assert signature.instructions == prompt.strip()
    assert not {"task_spec", "rules", "mjcf_syntax", "obs_schema"} & signature.input_fields.keys()
    assert list(signature.input_fields) == [
        "commit_status", "design_ledger",
        "best_commit_robot_xml", "best_commit_controller_code",
        "last_commit_robot_xml", "last_commit_controller_code",
        "last_commit_verifier_feedback", "last_commit_match_replay"]
    assert list(signature.output_fields) == [
        "name", "improvement_plan", "design_strategy", "hardware_plan",
        "combat_plan", "robot_xml", "controller_code", "change_summary"]
    inputs = {k: "" for k in signature.input_fields}
    messages = dspy.ChatAdapter().format(signature, demos=[], inputs=inputs)
    assert messages[0]["content"].count("# Competition") == 1
    assert "holdout_match_feedback" not in signature.input_fields
    assert "stage2x_test_case_plan" not in signature.output_fields
    # Selection is whatever the document says; no field may promise a rule nobody runs.
    assert "round robin among your qualified commits" not in messages[0]["content"]
    from mjarena.design_shop.agents.signatures.baseline_unified import BaselineUnifiedEngineer
    template = BaselineUnifiedEngineer.input_fields["best_commit_robot_xml"].json_schema_extra["desc"]
    assert "round robin among your qualified commits" in template  # dropped only in the copy above
    with pytest.raises(ValueError, match="must not be empty"):
        make_autoresearch_signature("   \n")


def test_sampling_prompt_signature():
    prompt = SAMPLING_PROMPT.read_text()
    signature = make_sampling_signature(prompt)
    assert signature.instructions == prompt.strip()
    assert list(signature.input_fields) == []          # zero-shot: the prompt is the whole call
    assert list(signature.output_fields) == [
        "name", "design_strategy", "hardware_plan", "combat_plan",
        "robot_xml", "controller_code", "change_summary"]
    assert "improvement_plan" not in signature.output_fields   # six sections + the ledger summary
    messages = dspy.ChatAdapter().format(signature, demos=[], inputs={})
    assert messages[0]["content"].count("# Competition") == 1
    with pytest.raises(ValueError, match="must not be empty"):
        make_sampling_signature("")


@dataclass
class SampleReplay:
    """Stands in for MatchupResult: only what the loop asks of it."""
    termination_reason: str = "inactivity"

    def to_prompt_dict(self, replay_hz: float = 2.0):
        return {"games": [{"termination_reason": self.termination_reason}]}


def test_feedback_and_best_design_survive_failed_revision(tmp_path):
    lm = dspy.utils.DummyLM([answer("invalid"), answer("best"), answer("regression"), answer("final")])
    evaluations = iter([
        UnifiedEnvResult(feedback="MASS FAILED: repair the geometry"),
        UnifiedEnvResult(feedback="Three wins", score=4.0,
                         qualification=VerifierResult(True, "Qualification", "won", score=4.0,
                                                      matchup=SampleReplay("ring_out"))),
        UnifiedEnvResult(feedback="CONTROLLER FAILED: unknown motor"),
        UnifiedEnvResult(feedback="Three wins but weaker score", score=3.0,
                         qualification=VerifierResult(True, "Qualification", "won", score=3.0)),
    ])
    state = run_baseline_engineer_unified(
        lm=lm, consolidated_prompt=PROMPT.read_text(),
        run_env_fn=lambda *a, **kw: next(evaluations),
        refine_n=4, output_dir=tmp_path, verbose=False, dump_prompt=True)
    assert state.best_commit == 1 and state.best_qualification_passed
    assert state.best_content == '<mujoco model="best"/>'
    assert state.journal[2].validation_passed is False
    assert len(lm.history) == 4
    requests = [h["messages"] for h in lm.history]
    assert all(str(messages).count("# Competition") == 1 for messages in requests)
    assert 'model="invalid"' in requests[1][-1]["content"]  # repair fallback
    assert "MASS FAILED" in requests[1][-1]["content"]
    assert '"termination_reason": "ring_out"' in requests[2][-1]["content"]
    after_regression = requests[3][-1]["content"]
    assert 'model="best"' in after_regression
    assert "CONTROLLER FAILED" in after_regression and "Revision regression" in after_regression
    assert "Improvement plan: Plan regression" in after_regression
    assert state.journal[2].improvement_plan == "Plan regression"
    saved = json.loads((tmp_path / "refinement/journal.json").read_text())
    assert saved["commits"][2]["improvement_plan"] == "Plan regression"
    assert (tmp_path / "refinement/commit_3/controller.py").is_file()


def test_a_run_without_a_consolidated_prompt_is_refused(tmp_path):
    """The modular prompt path is retired: a run must name its one document (item R)."""
    with pytest.raises(ValueError, match="autoresearch_prompt_path is required"):
        BuildConfig(unified_generation=True)
    with pytest.raises(ValueError, match="zero_shot_prompt_path is required"):
        BuildConfig(unified_generation=True, zero_shot_mode=True)
    with pytest.raises(ValueError, match="consolidated_prompt is required"):
        run_baseline_engineer_unified(
            lm=dspy.utils.DummyLM([answer("no_prompt")]), consolidated_prompt="",
            run_env_fn=lambda *a, **kw: UnifiedEnvResult(feedback="FAILED"),
            refine_n=1, output_dir=tmp_path, verbose=False)


def test_zero_shot_loop_sends_only_the_sampling_prompt(tmp_path):
    response = {k: v for k, v in answer("sample").items() if k != "improvement_plan"}
    lm = dspy.utils.DummyLM([response])
    state = run_baseline_engineer_unified(
        lm=lm, consolidated_prompt=SAMPLING_PROMPT.read_text(), zero_shot_mode=True,
        run_env_fn=lambda *a, **kw: UnifiedEnvResult(feedback="Three wins", score=4.0),
        refine_n=1, output_dir=tmp_path, verbose=False)
    sent = str(lm.history[0]["messages"])
    assert sent.count("# Competition") == 1
    assert "design_ledger" not in sent and "commit_status" not in sent
    assert state.journal[0].bot_name == "sample"


def test_run_configs_load_the_prompts_and_reject_the_wrong_mode():
    from run_baseline_agent import config_to_args, load_tournament_config
    arh = config_to_args(load_tournament_config(ROOT / "configs/tournaments/arh.yaml"))["cfg"]
    assert arh.autoresearch_prompt_path == "configs/rules/autoresearch_prompt.md"
    assert not arh.zero_shot_prompt_path and not arh.zero_shot_mode
    assert arh.commit_budget == 50 and arh.dump_prompt
    sh = config_to_args(load_tournament_config(ROOT / "configs/tournaments/sh.yaml"))["cfg"]
    assert sh.zero_shot_prompt_path == "configs/rules/sampling_prompt.md"
    assert not sh.autoresearch_prompt_path and sh.zero_shot_mode

    with pytest.raises(ValueError, match="iterative mode"):
        BuildConfig(unified_generation=True, zero_shot_mode=True, autoresearch_prompt_path=str(PROMPT))
    with pytest.raises(ValueError, match="iterative mode"):
        BuildConfig(unified_generation=False, autoresearch_prompt_path=str(PROMPT))
    with pytest.raises(ValueError, match="zero-shot mode"):
        BuildConfig(unified_generation=True, zero_shot_prompt_path=str(SAMPLING_PROMPT))

    # The rules block the prompt shows is the rules file the validator reads.
    actual = yaml.safe_load((ROOT / "configs/rules/rules.yaml").read_text())["robot"]
    quoted = yaml.safe_load(PROMPT.read_text().split("```yaml\n", 1)[1].split("```", 1)[0])["robot"]
    for section in ("mass", "control", "structure", "size"):
        assert actual[section] == quoted[section], section
    assert "bounding_box_3d" not in actual          # one size block only (item P)


def test_run_level_prompt_snapshot_is_written_once_beside_the_config(tmp_path):
    """Every build sends the same document, so the run dir holds one copy — not 250 per model."""
    from run_baseline_agent import save_consolidated_prompt
    arh = BuildConfig(unified_generation=True, autoresearch_prompt_path="configs/rules/autoresearch_prompt.md",
                      commit_budget=50, game_spec_vars=dict(GAME_SPEC_VARS))
    path = save_consolidated_prompt(arh, tmp_path)
    assert path == tmp_path / "autoresearch_prompt.md"
    snapshot = path.read_text()
    assert snapshot == PROMPT.read_text().replace("{mujoco_version}", "3.10.0").replace("{commit_budget}", "50")
    assert "{commit_budget}" not in snapshot and "MuJoCo 3.10.0" in snapshot

    sh = BuildConfig(unified_generation=True, zero_shot_mode=True, commit_budget=1,
                     zero_shot_prompt_path="configs/rules/sampling_prompt.md",
                     game_spec_vars=dict(GAME_SPEC_VARS))
    assert save_consolidated_prompt(sh, tmp_path) == tmp_path / "sampling_prompt.md"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["autoresearch_prompt.md", "sampling_prompt.md"]


def test_builder_uses_prompt_snapshot_and_real_validation(tmp_path):
    # The complete builder reaches the actual validator; no legacy prompt loader
    # exists any more, and malformed XML should return feedback rather than an API call.
    # The modular prompt path is retired (item R): one loader, and only the files it reads.
    assert [n for n in dir(builder) if n.startswith("load_")] == ["load_consolidated_prompt"]
    assert sorted(f.name for f in (ROOT / "configs/rules").iterdir() if f.is_file()) == [
        "autoresearch_prompt.md", "materials_store.yaml", "rules.yaml", "sampling_prompt.md"]
    lm = dspy.utils.DummyLM([answer("bad", "<mujoco>"), answer("still_bad", "<mujoco>")])
    cfg = BuildConfig(unified_generation=True, autoresearch_prompt_path="configs/rules/autoresearch_prompt.md",
                      commit_budget=2, dump_prompt=True, game_spec_vars=dict(GAME_SPEC_VARS),
                      controller_validation_params=ControllerValidationParams(save_video=False))
    with pytest.raises(RuntimeError, match="Unified generation failed"):
        builder.generate_unified(generator="scripted", lm=lm,
            constraints_path=ROOT / "configs/rules/rules.yaml", output_dir=tmp_path,
            arena_xml=ROOT / "mjarena/assets/sumo_ring_env_cinematic_3d.xml", cfg=cfg, verbose=False)
    sent = str(lm.history[0]["messages"])
    assert "# Competition" in sent and "MuJoCo 3.10.0" in sent and "{commit_budget}" not in sent
    assert not (tmp_path / "autoresearch_prompt.md").exists()   # snapshotted per run, not per bot
    assert len(lm.history) == 2
    assert "FAILED" in str(lm.history[1]["messages"])


def test_missing_placeholder_value_stops_the_run(tmp_path):
    cfg = BuildConfig(unified_generation=True, autoresearch_prompt_path="configs/rules/autoresearch_prompt.md",
                      commit_budget=1, game_spec_vars={"mujoco_version": "3.10.0"})
    with pytest.raises(ValueError, match="commit_budget"):
        builder.generate_unified(generator="scripted", lm=dspy.utils.DummyLM([answer("x")]),
            constraints_path=ROOT / "configs/rules/rules.yaml", output_dir=tmp_path,
            arena_xml=ROOT / "mjarena/assets/sumo_ring_env_cinematic_3d.xml", cfg=cfg, verbose=False)


def test_responses_api_output_is_saved_in_prompt_dump(tmp_path):
    """model_type: responses returns dict outputs; the dump must still hold the response."""
    from mjarena.design_shop.agents.L1_engineer_unified import _dump_prompt_to_commit
    _dump_prompt_to_commit(tmp_path, 0, [{"messages": [], "outputs": [{"text": "complete robot response"}]}])
    assert "=== RESPONSE ===\ncomplete robot response" in (tmp_path / "refinement/commit_0/prompt.txt").read_text()


def test_infrastructure_error_stops_without_grading_bot_or_spending_next_call(tmp_path):
    lm = dspy.utils.DummyLM([answer("first"), answer("must_not_run")])
    def broken_evaluator(*args, **kwargs):
        raise RuntimeError("simulation worker failed to import")
    with pytest.raises(RuntimeError, match="evaluation failed at commit 1"):
        run_baseline_engineer_unified(lm=lm, consolidated_prompt=PROMPT.read_text(),
            run_env_fn=broken_evaluator, refine_n=2, output_dir=tmp_path, verbose=False)
    assert len(lm.history) == 1
    assert not (tmp_path / "refinement/journal.json").exists()
