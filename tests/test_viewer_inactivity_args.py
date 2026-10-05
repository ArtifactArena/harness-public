"""run_episode_viewer's inactivity-rule arg resolution: CLI flag > config > disabled/raise.

Review finding: `--inactivity-timeout` without `--config` set inactivity_timeout
but left inactivity_min_displacement unresolved, so the displacement branch's
else-arm raised KeyError against a tournament_match of `{}` (config=None printed
literally in the message). The fix mirrors the timeout branch's existing
`elif args.config is None:` arm with a clear, actionable error instead of a
hardcoded 0.5 (see rules.yaml Global Constraint 4: no hard-coded rule numbers).
"""
import argparse

import pytest

from run_episode_viewer import resolve_inactivity_rule


def _args(**overrides):
    defaults = dict(
        skip_inactivity_check=False,
        inactivity_timeout=None,
        inactivity_min_displacement=None,
        config=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_timeout_flag_without_config_raises_clear_error_not_keyerror():
    """`--inactivity-timeout 5` alone (no --config, no --inactivity-min-displacement)."""
    args = _args(inactivity_timeout=5.0)
    with pytest.raises(Exception) as exc_info:
        resolve_inactivity_rule(args, {})
    assert not isinstance(exc_info.value, KeyError)
    message = str(exc_info.value)
    assert "None" not in message
    assert "--inactivity-min-displacement" in message or "--config" in message


def test_timeout_and_displacement_flags_together_resolve_without_config():
    """`--inactivity-timeout 5 --inactivity-min-displacement 0.5` alone."""
    args = _args(inactivity_timeout=5.0, inactivity_min_displacement=0.5)
    timeout, min_displacement = resolve_inactivity_rule(args, {})
    assert timeout == 5.0
    assert min_displacement == 0.5


def test_no_flags_no_config_disables_rule():
    args = _args()
    timeout, min_displacement = resolve_inactivity_rule(args, {})
    assert timeout is None
    assert min_displacement == 0.0


def test_skip_inactivity_check_disables_rule_even_with_flags():
    args = _args(
        skip_inactivity_check=True,
        inactivity_timeout=5.0,
        inactivity_min_displacement=0.5,
    )
    timeout, min_displacement = resolve_inactivity_rule(args, {})
    assert timeout is None
    assert min_displacement == 0.0


def test_config_present_reads_both_values_from_tournament_match():
    args = _args(config="configs/tournaments/base.yaml")
    tournament_match = {"inactivity_timeout": 12.0, "inactivity_min_displacement": 0.3}
    timeout, min_displacement = resolve_inactivity_rule(args, tournament_match)
    assert timeout == 12.0
    assert min_displacement == 0.3


def test_config_present_missing_timeout_key_raises_keyerror():
    args = _args(config="configs/tournaments/base.yaml")
    with pytest.raises(KeyError):
        resolve_inactivity_rule(args, {})


def test_config_present_missing_displacement_key_raises_keyerror():
    args = _args(config="configs/tournaments/base.yaml", inactivity_timeout=5.0)
    with pytest.raises(KeyError):
        resolve_inactivity_rule(args, {})
