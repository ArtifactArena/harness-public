"""The run configs, the roster they share, the launcher's inputs, and what base.yaml no longer carries."""
from pathlib import Path

import yaml

import mjarena.core.unified_builder  # noqa: F401  (import order)
from run_baseline_agent import config_to_args, load_tournament_config

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "configs/models/run-roster-2026-09.yaml"


def _roster() -> list[str]:
    return yaml.safe_load(ROSTER.read_text())["llms"]


def test_roster_lists_24_distinct_existing_models():
    roster = _roster()
    assert len(roster) == 24 and len(set(roster)) == 24
    missing = [m for m in roster if not (ROOT / m).exists()]
    assert not missing, missing


def test_arh_sh_and_oeh_configs_use_the_roster_verbatim():
    for name in ("arh.yaml", "sh.yaml", "oeh.yaml"):
        raw = yaml.safe_load((ROOT / "configs/tournaments" / name).read_text())
        assert raw["llms"] == _roster(), name


def test_all_three_run_configs_load():
    """oeh.yaml is launched from the design-lab-harness repo, but it resolves through this
    repo's loader, so a required key added here must not silently break it."""
    for name in ("arh.yaml", "sh.yaml", "oeh.yaml"):
        args = config_to_args(load_tournament_config(ROOT / "configs/tournaments" / name))
        assert len(args["llm_config_paths"]) == 24, name
        assert args["cfg"].game_spec_vars["commit_budget"] == args["cfg"].commit_budget, name


def test_only_the_three_harness_run_configs_remain():
    names = {p.name for p in (ROOT / "configs/tournaments").glob("*.yaml")}
    assert names == {"base.yaml", "arh.yaml", "sh.yaml", "oeh.yaml"}, names


def test_model_dir_holds_only_the_roster():
    files = {str(p.relative_to(ROOT)) for p in (ROOT / "configs/models").rglob("*")
             if p.is_file() and "__pycache__" not in p.parts}
    assert files == set(_roster()) | {"configs/models/run-roster-2026-09.yaml"}, files ^ set(_roster())


def test_arh_config_has_24_distinct_models_and_50_commits():
    args = config_to_args(load_tournament_config(ROOT / "configs/tournaments/arh.yaml"))
    paths = args["llm_config_paths"]
    assert len(paths) == 24 and len(set(paths)) == 24
    cfg = args["cfg"]
    assert cfg.commit_budget == 50 and not cfg.zero_shot_mode
    assert cfg.dump_prompt is True
    assert cfg.game_spec_vars["commit_budget"] == 50
    assert cfg.controller_validation_params.inactivity_timeout == 10.0


def test_sh_config_is_zero_shot_single_commit():
    args = config_to_args(load_tournament_config(ROOT / "configs/tournaments/sh.yaml"))
    cfg = args["cfg"]
    assert cfg.zero_shot_mode and cfg.commit_budget == 1 and cfg.dump_prompt is True
    assert len(args["llm_config_paths"]) == 24


def test_base_config_carries_only_what_the_harness_reads():
    base = yaml.safe_load((ROOT / "configs/tournaments/base.yaml").read_text())
    assert "rendering" not in base
    assert "compare" not in base["elo"]
    build = base["models_as_engineers"]
    for gone in ("agent_mode", "design_shop", "tournament_iteration"):
        assert gone not in build


def test_legacy_refine_keys_are_rejected_not_ignored():
    import pytest
    from mjarena.core.build_config import BuildConfig
    with pytest.raises(ValueError, match="commit_budget"):
        BuildConfig.from_yaml({"morphology_refine_n": 50, "controller_refine_n": 50}, {})
    build = {"commit_budget": 7, "unified_generation": True,
             "autoresearch_prompt_path": "configs/rules/autoresearch_prompt.md"}
    assert BuildConfig.from_yaml(build, {}).commit_budget == 7


def test_baseline_bot_artifacts_load():
    """The post-build step loads the baseline bots' artifacts; this crashed once on a removed field."""
    from mjarena.agents.types import BotArtifact
    for d in sorted((ROOT / "mjarena/core/assets/baseline_bots").iterdir()):
        if (d / "bot_artifact.json").exists():
            a = BotArtifact.load(d)
            assert a.morphology_xml.exists(), d
