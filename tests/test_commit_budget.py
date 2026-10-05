"""The commit budget is the loop bound: exactly refine_n engineer calls per build,
a transient LLM failure still consumes its commit, and the prompt states the same number."""
import contextlib
from pathlib import Path
from types import SimpleNamespace

import mjarena.core.unified_builder  # noqa: F401  (import order)
import mjarena.design_shop.agents.L1_engineer_unified as L1
from mjarena.design_shop.types import UnifiedEnvResult

# The iterative run's one prompt (configs/tournaments/arh.yaml: autoresearch_prompt_path).
PROMPT = (Path(__file__).resolve().parents[1] / "configs/rules/autoresearch_prompt.md").read_text()

XML = "<mujoco><worldbody><body name='b'><freejoint/><geom name='g' type='box' size='0.1 0.1 0.1' material='steel'/></body></worldbody><actuator/></mujoco>"


def _run(monkeypatch, refine_n, fail_on=(), output_dir=None):
    calls = []

    class StubEngineer:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **inputs):
            n = len(calls)
            calls.append(inputs)
            if n in fail_on:
                raise RuntimeError("timeout talking to provider")   # classified as transient
            return SimpleNamespace(robot_xml=XML, controller_code="def policy_step(obs): return {}",
                                   name=f"bot{n}", change_summary=f"c{n}", design_rationale="",
                                   design_strategy="", hardware_plan="", combat_plan="")

    monkeypatch.setattr(L1, "build_engineer", StubEngineer)
    monkeypatch.setattr(L1.dspy, "context", lambda **kw: contextlib.nullcontext())

    def run_env(robot_xml, controller_code, **_):
        return UnifiedEnvResult(feedback="ok", score=1.0, qualification=None)

    state = L1.run_baseline_engineer_unified(
        lm=SimpleNamespace(history=[]), consolidated_prompt=PROMPT,
        run_env_fn=run_env, refine_n=refine_n, output_dir=output_dir, verbose=False,
    )
    return state, calls


def test_exactly_refine_n_commits(monkeypatch):
    state, calls = _run(monkeypatch, refine_n=7)
    assert len(calls) == 7
    assert [e.commit_num for e in state.journal] == list(range(7))


def test_transient_llm_failure_still_consumes_its_commit(monkeypatch):
    state, calls = _run(monkeypatch, refine_n=5, fail_on={2})
    assert len(calls) == 5                       # no retry, no extra call
    assert len(state.journal) == 5
    assert state.journal[2].score == -1.0 and not state.journal[2].validation_passed


def test_prompt_budget_and_loop_bound_share_one_source():
    from pathlib import Path
    from run_baseline_agent import config_to_args, load_tournament_config
    root = Path(__file__).resolve().parents[1]
    cfg = config_to_args(load_tournament_config(root / "configs/tournaments/arh.yaml"))["cfg"]
    assert cfg.game_spec_vars["commit_budget"] == cfg.commit_budget == 50


def test_every_prompt_opens_with_its_position_in_the_budget(monkeypatch):
    state, calls = _run(monkeypatch, refine_n=4)
    assert [c["commit_status"] for c in calls] == [
        "Commit 1 of 4; 3 remaining after this one.",
        "Commit 2 of 4; 2 remaining after this one.",
        "Commit 3 of 4; 1 remaining after this one.",
        "Commit 4 of 4; 0 remaining after this one.",
    ]


def test_ledger_is_written_to_disk_after_every_commit(monkeypatch, tmp_path):
    state, calls = _run(monkeypatch, refine_n=3, output_dir=tmp_path)
    ledger = (tmp_path / "refinement" / "design_ledger.txt").read_text()
    assert ledger == state.format_journal_for_creator()
    assert "=== Commit 3:" in ledger and "Current best:" in ledger
