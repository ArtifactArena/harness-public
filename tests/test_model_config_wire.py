"""Every roster model config must put its reasoning + output-budget settings ON THE WIRE.

Regression test for 2026-09-17: the OpenAI ``model_type: responses`` yamls carried the
chat-completions keys ``reasoning_effort`` / ``max_tokens``; DSPy hands them to
``litellm.responses(**request)`` which only knows ``reasoning={"effort": ...}`` /
``max_output_tokens`` and silently drops the rest — every GPT run went out at the
provider's default effort with no output cap. Likewise ``claude-opus-4-7/4-8`` need an
explicit ``thinking: {type: adaptive}``; effort alone leaves thinking off on those two.

The test drives each yaml through the real path (configure_lm -> dspy.LM -> litellm ->
provider SDK) with the HTTP client stubbed offline, and asserts on the JSON body the
provider would receive.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import httpx
import pytest
import yaml

import mjarena.core  # noqa: F401  (import order: avoids the dspy_core circular import)
from mjarena.dspy_core import configure_lm  # imports litellm BEFORE httpx is stubbed below

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "configs/models/run-roster-2026-09.yaml"
ROSTER_PATHS = yaml.safe_load(ROSTER.read_text())["llms"]

# What each config promises, expressed as the provider's own wire fields.
EXPECTED: dict[str, dict] = {
    # Anthropic Messages API — effort high; Opus 4.7/4.8 also need thinking switched on
    # (Fable 5/5.1, Opus 5, Sonnet 5 think by default).
    "claude-fable-5-1-high": {"output_config": {"effort": "high"}, "max_tokens": 128000},
    "claude-fable-5-high": {"output_config": {"effort": "high"}, "max_tokens": 128000},
    "claude-opus-5-high": {"output_config": {"effort": "high"}, "max_tokens": 128000},
    "claude-sonnet-5-high": {"output_config": {"effort": "high"}, "max_tokens": 128000},
    "claude-opus-4-7-high": {"output_config": {"effort": "high"}, "max_tokens": 128000,
                             "thinking": {"type": "adaptive"}},
    "claude-opus-4-8-high": {"output_config": {"effort": "high"}, "max_tokens": 128000,
                             "thinking": {"type": "adaptive"}},
    # OpenAI Responses API
    "gpt-6-astra": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    "gpt-5.6-luna": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    "gpt-5.6-sol": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    "gpt-5.6-terra": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    "gpt-5.5": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    "gpt-5.4": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    "gpt-5.3-codex-high": {"reasoning": {"effort": "high"}, "max_output_tokens": 128000},
    # Gemini generateContent
    "gemini-3-1-pro-high": {"generationConfig": {"thinkingConfig": {"thinkingLevel": "high"}, "max_output_tokens": 65536}},
    "gemini-3-8-flash-high": {"generationConfig": {"thinkingConfig": {"thinkingLevel": "high"}, "max_output_tokens": 65535}},
    # xAI chat completions (grok-4.20 is a native reasoning model: no effort knob)
    "grok-4.6-high": {"reasoning_effort": "high", "max_tokens": 131072},
    "grok-4.5-high": {"reasoning_effort": "high", "max_tokens": 131072},
    "grok-4.20-reasoning": {"max_tokens": 32000},
    # Together chat completions
    "deepseek-v4-pro-thinking": {"thinking": {"type": "enabled"}, "max_tokens": 65536},
    "kimi-k3-high": {"reasoning_effort": "high", "max_tokens": 1048576},
    "minimax-m3-high": {"reasoning_effort": "high", "max_tokens": 98304},
    "qwen3.8-2.4t-a95b-thinking": {"top_k": 20, "min_p": 0, "max_tokens": 81920},
    "glm-5.3-high": {"reasoning_effort": "high", "max_tokens": 131072},
    "glm-5.2-high": {"reasoning_effort": "high", "max_tokens": 131072},
}

# Keys that must NOT appear: chat-completions spellings that the Responses API drops.
FORBIDDEN_ON_RESPONSES = ("reasoning_effort", "max_tokens", "max_completion_tokens")


def _fake_response(req: httpx.Request) -> httpx.Response:
    """Minimal valid success payload for each provider, so the SDKs parse it offline."""
    host = req.url.host
    path = req.url.path
    if host == "api.openai.com" and path.endswith("/responses"):
        payload = {
            "id": "resp_test", "object": "response", "created_at": 0, "status": "completed",
            "model": "test", "error": None, "incomplete_details": None, "instructions": None,
            "metadata": {}, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "text": {"format": {"type": "text"}}, "reasoning": {"effort": None, "summary": None},
            "temperature": 1.0, "top_p": 1.0, "truncation": "disabled", "max_output_tokens": None,
            "previous_response_id": None, "user": None,
            "output": [{"type": "message", "id": "msg_test", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok", "annotations": []}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                      "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}},
        }
    elif host == "api.anthropic.com":
        payload = {
            "id": "msg_test", "type": "message", "role": "assistant", "model": "test",
            "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    elif host == "generativelanguage.googleapis.com":
        payload = {
            "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
        }
    else:  # OpenAI-compatible chat completions (xAI, Together)
        payload = {
            "id": "chatcmpl_test", "object": "chat.completion", "created": 0, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    return httpx.Response(200, json=payload, headers={"content-type": "application/json"}, request=req)


@pytest.fixture
def wire(monkeypatch):
    """Stub httpx so no request leaves the machine; return the captured JSON bodies."""
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "TOGETHER_API_KEY"):
        monkeypatch.setenv(var, "test-key")
    bodies: list[dict] = []
    lock = threading.Lock()

    def send(self, request, *args, **kwargs):
        with lock:
            bodies.append(json.loads(request.content or b"{}"))
        return _fake_response(request)

    async def asend(self, request, *args, **kwargs):
        return send(self, request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", asend)
    return bodies


def _wire_body(cfg_path: Path, bodies: list[dict]) -> dict:
    lm = configure_lm(str(cfg_path), use_cache=False)
    lm(messages=[{"role": "user", "content": "Say OK."}])
    assert len(bodies) == 1, f"expected exactly one HTTP request, saw {len(bodies)}"
    return bodies[0]


def _assert_subset(expected: dict, actual: dict, path: str = "") -> None:
    for key, want in expected.items():
        assert key in actual, f"{path}{key} missing from wire body; body keys = {sorted(actual)}"
        got = actual[key]
        if isinstance(want, dict):
            assert isinstance(got, dict), f"{path}{key} = {got!r}, expected a mapping"
            _assert_subset(want, got, f"{path}{key}.")
        else:
            assert got == want, f"{path}{key} = {got!r}, expected {want!r}"


def test_roster_is_fully_covered():
    stems = {Path(p).stem for p in ROSTER_PATHS}
    assert stems == set(EXPECTED), f"roster/EXPECTED drift: {stems ^ set(EXPECTED)}"


@pytest.mark.parametrize("cfg", ROSTER_PATHS, ids=[Path(p).stem for p in ROSTER_PATHS])
def test_config_settings_reach_the_wire(cfg, wire):
    cfg_path = ROOT / cfg
    body = _wire_body(cfg_path, wire)
    _assert_subset(EXPECTED[Path(cfg).stem], body)
    if yaml.safe_load(cfg_path.read_text()).get("model_type") == "responses":
        for key in FORBIDDEN_ON_RESPONSES:
            assert key not in body, f"{key} is a chat-completions key; Responses drops it"
