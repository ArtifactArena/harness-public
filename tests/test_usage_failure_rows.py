"""Failed LLM attempts are written to usage.jsonl too, so retries are not invisible.

2026-09-18 dry run: a kimi-k3 sample ran 14.7 min while its one recorded (successful)
call took 88 s and its prompt came back fully cache-served — earlier attempts had
failed inside litellm's retry loop with no trace anywhere. A failure row carries the
exception class and wall time so `progress.jsonl` can count attempts per sample.
"""
import datetime as dt
import json

import mjarena.core  # noqa: F401  (import order: avoids the dspy_core circular import)
from mjarena.dspy_core import USAGE_CTX, _persist_failure, _persist_usage


def _rows(tmp_path):
    return [json.loads(l) for l in (tmp_path / "refinement/usage.jsonl").read_text().splitlines()]


def test_failed_attempt_is_recorded_with_error_and_wall_time(tmp_path):
    token = USAGE_CTX.set({"bot": "b", "commit": 0, "role": "engineer", "output_dir": str(tmp_path)})
    try:
        t0 = dt.datetime(2026, 9, 18, 5, 0, 0)
        t1 = t0 + dt.timedelta(seconds=612)
        _persist_failure({"model": "together_ai/moonshotai/Kimi-K3",
                          "exception": TimeoutError("read timed out")}, None, t0, t1)
    finally:
        USAGE_CTX.reset(token)
    (row,) = _rows(tmp_path)
    assert row["bot"] == "b" and row["commit"] == 0 and row["role"] == "engineer"
    assert row["model"] == "together_ai/moonshotai/Kimi-K3"
    assert row["error"] == "TimeoutError: read timed out"
    assert row["wall_ms"] == 612000
    assert row["completion_tokens"] is None  # nothing was generated


def test_failure_rows_sit_next_to_success_rows_and_are_distinguishable(tmp_path):
    token = USAGE_CTX.set({"bot": "b", "commit": 0, "role": "engineer", "output_dir": str(tmp_path)})
    try:
        _persist_failure({"model": "m", "exception": RuntimeError("boom")}, None, 0.0, 1.0)

        class _Usage:
            def model_dump(self, exclude_none=True):
                return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

        class _Resp:
            usage = _Usage()
            choices = []

        _persist_usage({"model": "m"}, _Resp(), 0.0, 2.0)
    finally:
        USAGE_CTX.reset(token)
    rows = _rows(tmp_path)
    assert [("error" in r) for r in rows] == [True, False]
    assert rows[1]["completion_tokens"] == 5


def test_failure_outside_a_tracked_scope_writes_nothing(tmp_path):
    _persist_failure({"model": "m", "exception": RuntimeError("boom")}, None, 0.0, 1.0)
    assert not (tmp_path / "refinement").exists()
