"""No LLM call is cut short by a tight timeout: the harness default is 100 min (the same
default in every arena harness: above any legitimate call, low enough that a hung
connection aborts and retries) and no model yaml may set a smaller one (litellm turns
timeout=None into 600 s, so the default has to be an explicit number)."""
from pathlib import Path

import yaml

import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)
from mjarena.dspy_core import NO_LLM_TIMEOUT_S, configure_lm

ROOT = Path(__file__).resolve().parents[1]
MIN_ALLOWED = 6000


def test_default_timeout_is_100_minutes():
    assert NO_LLM_TIMEOUT_S >= MIN_ALLOWED
    lm = configure_lm(str(ROOT / "configs/models/openai/gpt-5.5.yaml"), use_cache=False)
    assert lm.kwargs["timeout"] == NO_LLM_TIMEOUT_S


def test_no_model_yaml_caps_the_call():
    offenders = []
    for path in sorted((ROOT / "configs/models").rglob("*.yaml")):
        cfg = yaml.safe_load(path.read_text()) or {}
        t = cfg.get("timeout")
        if t is not None and float(t) < MIN_ALLOWED:
            offenders.append(f"{path.relative_to(ROOT)}: timeout={t}")
    assert not offenders, offenders
