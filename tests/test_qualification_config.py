"""Qualification plays the same inactivity and size rules as the tournament, for real seconds."""
from pathlib import Path

import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)
from run_baseline_agent import _cli_default_run_args, config_to_args, load_tournament_config

ROOT = Path(__file__).resolve().parents[1]


def test_base_config_arms_inactivity_in_qualification():
    args = config_to_args(load_tournament_config(ROOT / "configs/tournaments/arh.yaml"))
    cvp = args["cfg"].controller_validation_params
    assert cvp.match_time == 20.0                     # rules.controller.match_time in base.yaml
    assert cvp.inactivity_timeout == 10.0             # copied from tournament.match
    assert cvp.inactivity_min_displacement == 0.5
    assert cvp.match_time > cvp.inactivity_timeout    # otherwise the rule can never fire
    assert args["inactivity_timeout"] == cvp.inactivity_timeout   # tournament uses the same values


def test_cli_defaults_branch_arms_inactivity_without_a_config():
    """Running with neither --config nor --continue still plays the inactivity rule.

    main()'s branch-3 run_args is hand-written rather than produced by
    config_to_args, and run_season reads both keys explicitly — so a missing key
    is a KeyError and a None would silently disable the rule for the whole run.
    """
    run_args = _cli_default_run_args()
    assert run_args["inactivity_timeout"] == 10.0
    assert run_args["inactivity_min_displacement"] == 0.5
    assert run_args["size_limits"] == (2.44, 2.44, 3.05)
    # both branches feed the same run_season call, so they must not disagree
    args = config_to_args(load_tournament_config(ROOT / "configs/tournaments/arh.yaml"))
    assert run_args["inactivity_timeout"] == args["inactivity_timeout"]
    assert run_args["inactivity_min_displacement"] == args["inactivity_min_displacement"]
    assert run_args["size_limits"] == args["size_limits"]


def test_the_build_feedback_keys_are_explicit_in_every_shipped_config():
    """`max_feedback_examples` and `use_previous_match_data_for_build` change what
    the model is shown each commit and were read with a `.get()` default that no
    shipped YAML supplied. They are required keys now (base.yaml), and the CLI
    branch must agree with them — both feed the same run."""
    import pytest
    import yaml

    run_args = _cli_default_run_args()
    for name in ("arh.yaml", "sh.yaml", "oeh.yaml"):
        args = config_to_args(load_tournament_config(ROOT / "configs/tournaments" / name))
        assert args["use_previous_match_data_for_build"] is False, name
        assert args["max_feedback_examples"] == 3, name
        for key in ("use_previous_match_data_for_build", "max_feedback_examples"):
            assert run_args[key] == args[key], (name, key)

    base = yaml.safe_load((ROOT / "configs/tournaments/base.yaml").read_text())
    for key in ("use_previous_match_data_for_build", "max_feedback_examples"):
        assert key in base["models_as_engineers"], key


def test_a_config_missing_a_build_feedback_key_fails_loudly():
    import pytest

    config = load_tournament_config(ROOT / "configs/tournaments/arh.yaml")
    del config["models_as_engineers"]["max_feedback_examples"]
    with pytest.raises(KeyError, match="max_feedback_examples"):
        config_to_args(config)


def test_qualification_config_matches_the_dictated_prose():
    """The prompts' "## Qualification Round" paragraph tells the model
    "your robot must not lose each of three 20-second rounds against a simple
    baseline block" — that prose is user-dictated text, not derived from config, so
    nothing ties it to the numbers actually played. Pin the resolved config here so
    a future change to n_rollouts/match_time fails loudly instead of silently
    diverging from what the model is told.
    """
    args = config_to_args(load_tournament_config(ROOT / "configs/tournaments/arh.yaml"))
    cvp = args["cfg"].controller_validation_params
    assert cvp.n_rollouts == 3       # "three ... rounds" in the Qualification Round paragraph
    assert cvp.match_time == 20.0    # "20-second rounds" in the same paragraph
