"""Every roster yaml rides through transient 429/5xx flaps: num_retries >= 10.

At 20 samples per model in flight the provider sees 120-140 concurrent high-effort
requests; dspy's default of 3 retries ends a sample as an ERROR (no artifact) on the
first sustained flap.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROSTER = yaml.safe_load((ROOT / "configs/models/run-roster-2026-09.yaml").read_text())["llms"]


@pytest.mark.parametrize("cfg", ROSTER, ids=[Path(p).stem for p in ROSTER])
def test_roster_model_has_a_retry_budget(cfg):
    spec = yaml.safe_load((ROOT / cfg).read_text())
    assert spec.get("num_retries", 0) >= 10, f"{cfg}: num_retries={spec.get('num_retries')} (dspy default is 3)"
