"""Unattended-run policy for the pool runner.

- A transient failure (rate limit, timeout, 5xx) does not stop a lane: the sample is
  retried later, the lane backs off exponentially, and only after MAX_GEN_ATTEMPTS the
  sample is recorded as failed. A lane stops only on two consecutive billing errors or a
  long unbroken error streak.
- The manifest pins what actually defines a sample — the rendered prompt, the run config,
  the model yamls — not the git sha, so an orchestrator-only edit never blocks a resume.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/sampling"))
import run_pool  # noqa: E402


def test_transient_errors_retry_with_backoff_and_do_not_stop_the_lane():
    lane = run_pool.ModelLane("gpt-5.5")
    decisions = [lane.record_error("litellm.RateLimitError: 429 Too Many Requests") for _ in range(4)]
    assert all(d == "retry" for d in decisions)
    assert lane.stopped is None
    assert lane.backoff_seconds() >= run_pool.BACKOFF_BASE_S * 2 ** 3
    assert lane.backoff_seconds() <= run_pool.BACKOFF_MAX_S
    lane.record_success()
    assert lane.backoff_seconds() == 0


def test_lane_stops_only_after_a_long_unbroken_streak():
    lane = run_pool.ModelLane("m")
    for _ in range(run_pool.MAX_CONSECUTIVE_ERRORS - 1):
        lane.record_error("APIConnectionError: read timed out")
    assert lane.stopped is None
    lane.record_error("APIConnectionError: read timed out")
    assert lane.stopped == "errors"
    assert run_pool.MAX_CONSECUTIVE_ERRORS >= 20


def test_sample_attempts_are_capped():
    lane = run_pool.ModelLane("m")
    assert lane.attempts_left(3) is True           # first failure -> 2 attempts used? no: 1 used
    lane.note_attempt(3)
    lane.note_attempt(3)
    assert lane.attempts_left(3) is True
    lane.note_attempt(3)
    assert lane.attempts_left(3) is False           # MAX_GEN_ATTEMPTS reached -> gen_error.json
    assert run_pool.MAX_GEN_ATTEMPTS == 3


def test_manifest_pins_prompt_config_and_models_not_the_sha(tmp_path):
    cfg = ROOT / "configs/tournaments/sh.yaml"
    models = [ROOT / "configs/models/openai/gpt-5.5.yaml"]
    run_pool.write_manifest(tmp_path, cfg, models, prompt_text="PROMPT", git_sha="a" * 40, allow_drift=False)
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["prompt_md5"] == run_pool.md5_text("PROMPT") and m["git_sha"] == "a" * 40
    # same prompt/config/models at another sha: fine, sha history is appended
    run_pool.write_manifest(tmp_path, cfg, models, prompt_text="PROMPT", git_sha="b" * 40, allow_drift=False)
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["git_sha"] == "a" * 40 and "b" * 40 in m["later_shas"]
    # a different prompt is refused
    with pytest.raises(SystemExit, match="prompt"):
        run_pool.write_manifest(tmp_path, cfg, models, prompt_text="OTHER", git_sha="b" * 40, allow_drift=False)


def test_reasoning_text_is_extracted_from_every_provider_shape():
    from types import SimpleNamespace as NS
    chat = {"response": NS(choices=[NS(message=NS(content="final", reasoning_content="I think...",
                                                  thinking_blocks=None, provider_specific_fields={}))])}
    thinking = {"response": NS(choices=[NS(message=NS(content="final", reasoning_content=None,
                                                      thinking_blocks=[{"type": "thinking", "thinking": "step 1"},
                                                                       {"type": "thinking", "thinking": "step 2"}],
                                                      provider_specific_fields={}))])}
    psf = {"response": NS(choices=[NS(message=NS(content="final", reasoning_content=None, thinking_blocks=None,
                                                 provider_specific_fields={"reasoning_content": "via psf"}))])}
    responses_api = {"outputs": [{"text": "final", "reasoning_content": "summary text"}]}
    none = {"response": NS(choices=[NS(message=NS(content="final", reasoning_content=None, thinking_blocks=None,
                                                  provider_specific_fields={}))])}
    assert run_pool.extract_reasoning(chat) == "I think..."
    assert run_pool.extract_reasoning(thinking) == "step 1\n\nstep 2"
    assert run_pool.extract_reasoning(psf) == "via psf"
    assert run_pool.extract_reasoning(responses_api) == "summary text"
    assert run_pool.extract_reasoning(none) == ""


def test_operator_stop_file_halts_a_lane(tmp_path):
    lane = run_pool.ModelLane("claude-opus-4-7-high")
    assert run_pool.operator_stop(tmp_path, lane) is False and lane.stopped is None
    (tmp_path / "STOP-claude-opus-4-7-high").write_text("")
    assert run_pool.operator_stop(tmp_path, lane) is True
    assert lane.stopped == "stopped by operator (STOP file)"


def test_call_with_deadline_abandons_a_hung_call_and_returns_the_fast_one():
    import time
    assert run_pool.call_with_deadline(lambda: "ok", deadline_s=5) == "ok"
    t0 = time.time()
    with pytest.raises(run_pool.GenerationDeadline):
        run_pool.call_with_deadline(lambda: time.sleep(30), deadline_s=1)
    assert time.time() - t0 < 5


def test_call_with_deadline_propagates_exceptions():
    with pytest.raises(ZeroDivisionError):
        run_pool.call_with_deadline(lambda: 1 / 0, deadline_s=5)


def test_in_flight_elsewhere_skips_fresh_unfinished_sample_dirs(tmp_path):
    import os, time
    d = tmp_path / "m/c007"
    assert run_pool.in_flight_elsewhere(d, minutes=60) is False          # no dir: free
    d.mkdir(parents=True)
    assert run_pool.in_flight_elsewhere(d, minutes=60) is True           # fresh dir, no result yet: someone is on it
    (d / "gen.json").write_text("{}")
    assert run_pool.in_flight_elsewhere(d, minutes=60) is False          # finished: not in flight
    e = tmp_path / "m/c008"; e.mkdir()
    old = time.time() - 3 * 3600
    os.utime(e, (old, old))
    assert run_pool.in_flight_elsewhere(e, minutes=60) is False          # stale dir: abandoned, free to take
    assert run_pool.in_flight_elsewhere(e, minutes=0) is False           # feature off


def test_stop_scope_instance_ignores_global_stop_files(tmp_path):
    lane = run_pool.ModelLane("gpt-5.4")
    (tmp_path / "STOP-gpt-5.4").write_text("")
    assert run_pool.operator_stop(tmp_path, lane, instance="openai2", scope="instance") is False
    assert lane.stopped is None
    (tmp_path / "STOP-gpt-5.4.openai2").write_text("")
    assert run_pool.operator_stop(tmp_path, lane, instance="openai2", scope="instance") is True
    lane2 = run_pool.ModelLane("gpt-5.4")
    assert run_pool.operator_stop(tmp_path, lane2, instance="openai", scope="global") is True  # global file still halts global-scope instances


def test_cleared_failure_is_not_mistaken_for_in_flight(tmp_path):
    import os
    d = tmp_path / "m/c001"; d.mkdir(parents=True)
    (d / "gen_error.json").write_text("{}")
    (d / "gen_error.json").unlink(); os.utime(d, (0, 0))   # what --retry-failed does
    assert run_pool.in_flight_elsewhere(d, minutes=60) is False


def test_rate_limit_storms_back_off_but_never_stop_a_lane_or_spend_attempts():
    lane = run_pool.ModelLane("glm-5.3-high")
    for _ in range(run_pool.MAX_CONSECUTIVE_ERRORS + 5):
        assert lane.record_error("RateLimitError: Together_aiException - Too many requests in a short window") == "retry"
    assert lane.stopped is None
    assert lane.backoff_seconds() == run_pool.BACKOFF_MAX_S
    assert run_pool.is_rate_limit("litellm.RateLimitError: 429 Too Many Requests") is True
    assert run_pool.is_rate_limit("insufficient_quota: You exceeded your current quota") is False  # billing, not rate limit
    assert run_pool.is_rate_limit("AdapterParseError: could not parse") is False


def test_calls_in_flight_when_the_balance_hits_zero_are_abandoned_at_once():
    """A provider call that is in flight when the account balance hits zero never returns (Anthropic
    leaves the socket open and silent). When any worker sees a billing rejection, every call on that
    provider that started BEFORE the rejection is abandoned immediately and re-queued instead of
    waiting for the deadline."""
    import threading, time
    run_pool.PROVIDER_DIP.clear()
    started = time.time()
    def hang():
        time.sleep(30)
    def trip():
        time.sleep(0.5); run_pool.note_balance_dip("anthropic")
    threading.Thread(target=trip, daemon=True).start()
    t0 = time.time()
    with pytest.raises(run_pool.GenerationDeadline, match="balance hit zero"):
        run_pool.call_with_deadline(hang, deadline_s=20, provider="anthropic", started=started)
    assert time.time() - t0 < 10
    # a call that STARTED after the dip is not affected by it
    run_pool.PROVIDER_DIP.clear()
    run_pool.note_balance_dip("anthropic")
    assert run_pool.call_with_deadline(lambda: "ok", deadline_s=5, provider="anthropic", started=time.time()) == "ok"


def test_last_error_carries_a_timestamp(monkeypatch):
    now = [5000.0]
    monkeypatch.setattr(run_pool.time, "time", lambda: now[0])
    lane = run_pool.ModelLane("m")
    assert lane.last_error_ts is None
    lane.record_error("boom")
    assert lane.last_error_ts == 5000.0


def test_a_late_result_never_overwrites_an_existing_gen_json(tmp_path):
    d = tmp_path / "m/c001"; d.mkdir(parents=True)
    (d / "gen.json").write_text('{"first": true}')
    kept = run_pool.save_result(d, {"second": True})
    assert kept is False
    assert json.loads((d / "gen.json").read_text()) == {"first": True}
    dups = list(d.glob("gen.dup-*.json"))
    assert len(dups) == 1 and json.loads(dups[0].read_text()) == {"second": True}
    e = tmp_path / "m/c002"; e.mkdir()
    assert run_pool.save_result(e, {"only": True}) is True
    assert json.loads((e / "gen.json").read_text()) == {"only": True}


def test_deadline_abandonments_never_stop_a_lane_or_back_it_off():
    """When a whole batch of provider calls hangs (2026-09-18 19:17Z: all 45 in-flight Claude calls),
    every one of them fails with GenerationDeadline within minutes. That is not evidence the lane is
    dead — the retries are fresh calls — so it must not count toward the error stop, and there is
    nothing to wait for before re-dispatching."""
    lane = run_pool.ModelLane("claude-fable-5-1-high")
    for _ in range(run_pool.MAX_CONSECUTIVE_ERRORS + 25):
        assert lane.record_error("GenerationDeadline: no response after 120 min; call abandoned") == "retry"
    assert lane.stopped is None
    assert lane.backoff_seconds() == 0
    assert run_pool.is_deadline("GenerationDeadline: no response after 120 min; call abandoned") is True
    assert run_pool.is_deadline("APIConnectionError: read timed out") is False


def test_git_sha_helpers_fall_back_to_shipped_sha(tmp_path, monkeypatch):
    """Cluster trees are `git archive` snapshots: no .git, a SHIPPED_SHA file instead."""
    import pack_pool
    (tmp_path / "SHIPPED_SHA").write_text("abc123\n")
    monkeypatch.setattr(run_pool, "REPO", tmp_path)
    monkeypatch.setattr(pack_pool, "REPO", tmp_path)
    assert run_pool._git_sha() == "abc123" and pack_pool._git_sha() == "abc123"
    (tmp_path / "SHIPPED_SHA").unlink()
    with pytest.raises(RuntimeError, match="SHIPPED_SHA"):
        run_pool._git_sha()


def test_time_wrapper_flag_matches_the_platform(monkeypatch):
    monkeypatch.setattr(run_pool.sys, "platform", "linux")
    assert run_pool.time_prefix() == [run_pool.TIME, "-v"]
    monkeypatch.setattr(run_pool.sys, "platform", "darwin")
    assert run_pool.time_prefix() == [run_pool.TIME, "-l"]
    monkeypatch.setattr(run_pool, "TIME", "/nonexistent/time")
    assert run_pool.time_prefix() == []
