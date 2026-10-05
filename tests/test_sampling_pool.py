"""Two-stage sampling pool: API generation fanned out in threads, then the unchanged
build pipeline replaying each saved response under a process pool.

Pieces under test:
- `configure_lm` returns a replay LM when ARENA_REPLAY_OUTPUTS names a gen.json, so
  `run_baseline_agent.py` builds a sample without touching the network.
- `configs/tournaments/sh.yaml` runs qualification without videos (disk).
- `scripts/sampling/run_pool.py` helpers: billing detection, status table, compaction.
"""
import gzip
import json
import sys
from pathlib import Path

import dspy
import pytest

import mjarena.core.unified_builder  # noqa: F401  (import order)
from mjarena.design_shop.agents.L1_engineer_unified import build_engineer
from mjarena.design_shop.agents.signatures.sampling import make_sampling_signature
from mjarena.dspy_core import configure_lm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import run_pool  # noqa: E402

PROMPT = "Design a robot.\n\n### robot_xml\nthe xml\n\n### controller_code\nthe code\n"
OUTPUTS = {"design_rationale": "because", "name": "Replayed", "design_strategy": "d",
           "hardware_plan": "h", "combat_plan": "c", "robot_xml": "<mujoco/>",
           "controller_code": "def policy_step(obs):\n    return {}", "change_summary": "s"}


def test_configure_lm_replays_a_saved_response_when_asked(tmp_path, monkeypatch):
    gen = tmp_path / "gen.json"
    gen.write_text(json.dumps({"outputs": OUTPUTS, "model": "openai/gpt-5.5"}))
    monkeypatch.setenv("ARENA_REPLAY_OUTPUTS", str(gen))
    lm = configure_lm(str(ROOT / "configs/models/openai/gpt-5.5.yaml"), use_cache=False)
    engineer = build_engineer(make_sampling_signature(PROMPT))
    with dspy.context(lm=lm):
        result = engineer()
    assert result.name == "Replayed" and result.robot_xml == "<mujoco/>"
    assert result.design_rationale == "because"
    assert lm.history and "[[ ## design_rationale ## ]]" in str(lm.history[0]["messages"])


def test_configure_lm_is_untouched_without_the_replay_variable(monkeypatch):
    monkeypatch.delenv("ARENA_REPLAY_OUTPUTS", raising=False)
    lm = configure_lm(str(ROOT / "configs/models/openai/gpt-5.5.yaml"), use_cache=False)
    assert lm.model == "openai/gpt-5.5"


def test_sh_config_qualifies_without_videos():
    from run_baseline_agent import config_to_args, load_tournament_config
    cfg = config_to_args(load_tournament_config(ROOT / "configs/tournaments/sh.yaml"))["cfg"]
    p = cfg.controller_validation_params
    assert p.save_video is False
    assert p.match_time == 20.0 and p.n_rollouts == 3  # the rest of the block still merges


@pytest.mark.parametrize("text,expected", [
    ("AnthropicException - Your credit balance is too low to access the Anthropic API", True),
    ("openai.RateLimitError: insufficient_quota: You exceeded your current quota", True),
    ("HTTP 402 Payment Required", True),
    ("Together: this account has no remaining credits", True),
    ("litellm.RateLimitError: 429 Too Many Requests, retry after 20s", False),
    ("APIConnectionError: read timed out", False),
    ("", False),
])
def test_billing_errors_are_recognised(text, expected):
    assert run_pool.is_billing_error(text) is expected


def test_billing_errors_pause_the_lane_and_only_a_long_zero_balance_stops_it(monkeypatch):
    """Providers auto-reload: a zero balance is transient. Pause 5 min and retry; stop only when
    rejections have been continuous for BILLING_STOP_MIN minutes (NOT a count — at 100 workers a
    count of 12 trips within a second)."""
    now = [1000.0]
    monkeypatch.setattr(run_pool.time, "time", lambda: now[0])
    lane = run_pool.ModelLane("gpt-5.5")
    for _ in range(200):
        assert lane.record_error("Your credit balance is too low") == "retry"
    assert lane.stopped is None and lane.backoff_seconds() == run_pool.BILLING_PAUSE_S
    now[0] += run_pool.BILLING_STOP_MIN * 60 + 1
    assert lane.record_error("Your credit balance is too low") == "stop"
    assert lane.stopped == "credits exhausted"
    lane2 = run_pool.ModelLane("m")
    for _ in range(run_pool.MAX_CONSECUTIVE_ERRORS):
        lane2.record_error("read timed out")
    assert lane2.stopped == "errors"
    lane3 = run_pool.ModelLane("m")
    lane3.record_error("Your credit balance is too low")
    lane3.record_success()
    assert lane3.backoff_seconds() == 0 and lane3.stopped is None and lane3.billing_since is None


def _sample(root, stem, idx, gen=True, artifact=None, gen_error=None):
    d = root / stem / f"c{idx:03d}"
    d.mkdir(parents=True, exist_ok=True)
    if gen:
        (d / "gen.json").write_text(json.dumps({"outputs": OUTPUTS, "wall_s": 120.0}))
    if gen_error:
        (d / "gen_error.json").write_text(json.dumps({"error": gen_error}))
    if artifact is not None:
        bot = d / "tournament_00/round_robin_match/bots" / stem
        bot.mkdir(parents=True)
        (bot / "bot_artifact.json").write_text(json.dumps({"forfeit": artifact}))
    return d


def test_status_table_counts_every_state(tmp_path):
    _sample(tmp_path, "gpt-5.5", 0, artifact=False)
    _sample(tmp_path, "gpt-5.5", 1, artifact=True)
    _sample(tmp_path, "gpt-5.5", 2)                       # generated, waiting for qualification
    _sample(tmp_path, "gpt-5.5", 3, gen=False, gen_error="credit balance is too low")
    _sample(tmp_path, "kimi-k3-high", 0, gen=False)        # nothing yet
    lanes = {"gpt-5.5": run_pool.ModelLane("gpt-5.5"), "kimi-k3-high": run_pool.ModelLane("kimi-k3-high")}
    lanes["gpt-5.5"].stopped = "credits exhausted"
    rows = run_pool.scan_status(tmp_path, ["gpt-5.5", "kimi-k3-high"], n_samples=5, lanes=lanes)
    g = rows["gpt-5.5"]
    assert g["generated"] == 3 and g["gen_failed"] == 1 and g["qualified_ok"] == 1
    assert g["forfeit"] == 1 and g["awaiting_qualification"] == 1 and g["stopped"] == "credits exhausted"
    assert g["remaining"] == 1  # 5 targets - 3 generated - 1 failed
    assert rows["kimi-k3-high"]["generated"] == 0 and rows["kimi-k3-high"]["remaining"] == 5
    md = run_pool.render_status_md(tmp_path, rows, started="2026-09-18T06:00:00Z", extra={"free_disk_gb": 9.5})
    assert "| gpt-5.5 |" in md and "credits exhausted" in md and "9.5" in md


def test_compaction_gzips_match_data_and_removes_videos(tmp_path):
    d = _sample(tmp_path, "m", 0, artifact=False)
    q = d / "tournament_00/round_robin_match/bots/m/refinement/commit_0/qualification"
    q.mkdir(parents=True)
    (q / "match_data.json").write_text(json.dumps({"frames": list(range(20000))}))
    (q / "seed_0.webm").write_bytes(b"\0" * 1000)
    run_pool.compact_sample(d, "m")
    assert not (q / "match_data.json").exists() and not (q / "seed_0.webm").exists()
    assert json.loads(gzip.open(q / "match_data.json.gz").read())["frames"][-1] == 19999


def test_generation_usage_rows_are_merged_ahead_of_the_build_rows(tmp_path):
    d = _sample(tmp_path, "m", 0, artifact=False)
    gen_usage = d / "gen/refinement/usage.jsonl"
    gen_usage.parent.mkdir(parents=True)
    gen_usage.write_text(json.dumps({"role": "engineer", "error": "TimeoutError: x"}) + "\n"
                         + json.dumps({"role": "engineer", "completion_tokens": 9}) + "\n")
    bot_usage = d / "tournament_00/round_robin_match/bots/m/refinement/usage.jsonl"
    bot_usage.parent.mkdir(parents=True)
    bot_usage.write_text(json.dumps({"role": "verifier", "completion_tokens": 1}) + "\n")
    run_pool.merge_usage(d, "m")
    rows = [json.loads(l) for l in bot_usage.read_text().splitlines()]
    assert [r.get("role") for r in rows] == ["engineer", "engineer", "verifier"]
    assert not gen_usage.exists()
