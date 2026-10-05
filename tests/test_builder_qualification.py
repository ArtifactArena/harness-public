"""End-to-end build-phase wiring: generate_unified -> validation -> qualification, with the
engineer replaced by a stub that submits a real study commit once. No LLM calls."""
import re
from pathlib import Path

import pytest

import mjarena.core.unified_builder as ub
from mjarena.design_shop.refinement_state import RefinementState
from run_baseline_agent import config_to_args, load_tournament_config

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/study_bot"


def test_generate_unified_runs_qualification_with_the_configured_rules(tmp_path, monkeypatch):
    args = config_to_args(load_tournament_config(ROOT / "configs/tournaments/arh.yaml"))
    cfg = args["cfg"]
    cfg.commit_budget = 1
    cfg.controller_validation_params.save_video = False
    robot_xml = (FIX / "robot.xml").read_text()
    controller = (FIX / "controller.py").read_text()
    seen = {}

    def stub_engineer(*, run_env_fn, output_dir, **_):
        state = RefinementState(mode="unified", output_dir=output_dir)
        env = run_env_fn(robot_xml, controller)
        seen["env"] = env
        state.update(round_num=0, score=env.score, content=robot_xml, verifier_feedback=env.feedback,
                     creator_summary="study commit", controller_code=controller,
                     validation_passed=env.score != -1.0,
                     qualification_passed=bool(env.qualification and env.qualification.passed),
                     creator_outputs={"name": "Study bot"})
        return state

    monkeypatch.setattr(ub, "run_baseline_engineer_unified", stub_engineer)
    ub.generate_unified(generator="test", lm=None, constraints_path=Path(args["constraints_path"]),
                        output_dir=tmp_path, cfg=cfg, arena_xml=Path(args["arena_xml"]))

    env = seen["env"]
    assert env.qualification is not None, env.feedback
    q = env.qualification
    assert q.matchup is not None and q.matchup.game_records
    rec = q.matchup.game_records[0]
    # 20 s qualification (rules.controller.match_time), inactivity rule armed
    assert rec.num_steps <= 2000
    assert rec.red_inactivity_timers, "inactivity timer series missing -> rule not armed"
    assert (tmp_path / "refinement/commit_0/qualification/match_result.json").exists()
    # the opponent is the palette-plastic slab, and the commit keeps the exact block it fought
    assert rec.blue_mass == pytest.approx(342.0, abs=1.0)
    assert (tmp_path / "refinement/commit_0/qualification/block.xml").exists()
    # feedback hygiene
    q_data = env.qualification.data
    assert {"wins", "n_seeds", "mean_engagement", "mean_self_stability"} <= set(q_data)
    fb = env.feedback
    assert "All ? geoms" not in fb
    assert "Density Enforcement" not in fb and "2D Physics" not in fb
    assert "0.0s]" not in fb and "[verifier:" not in fb
    assert "stage" not in fb.lower()
    assert not re.search(r"\d+\.\d{5,}", fb), "raw float noise in the report"
    assert "── Simulation Settings ── PASSED" not in fb          # passed with nothing to say
    assert fb.startswith("Morphology validation:") and "Controller validation and qualification:" in fb
    assert "Qualification score:" in fb
    assert re.search(r"Seed 0: (WIN|LOSS|DRAW) — .+ at \d+\.\ds", fb), fb
    for ceremony in ("No wrappers to strip", "Inject Motor Mass", "Apply Material Properties",
                     "Validate Moving Bodies Have Geoms", "Validate Actuator Tags"):
        assert ceremony not in fb, ceremony


def test_a_broken_qualification_setup_is_graded_feedback_not_a_silent_pass():
    """If the qualification match runner cannot be built, the commit must FAIL.

    It used to be swallowed into `logger.warning`, leaving `stationary_match_fn
    = None`; `validate_controller` then took the static-only path and returned
    passed=True, score=0.0, qualification=None — an unqualified commit that the
    ledger recorded as validated, with nothing in the feedback to say why.
    """
    from mjarena.design_shop.pipelines.unified_env import run_unified_env

    def exploding_factory(_processed_xml_path):
        raise RuntimeError("block asset went missing")

    result = run_unified_env(
        (FIX / "robot.xml").read_text(),
        (FIX / "controller.py").read_text(),
        constraints_yaml_path=ROOT / "configs/rules/rules.yaml",
        physics_mode="3d",
        stationary_match_fn_factory=exploding_factory,
        n_rollouts=1,
    )

    assert result.score == -1.0, result.feedback
    assert result.qualification is None
    assert "Qualification could not be set up: block asset went missing" in result.feedback
