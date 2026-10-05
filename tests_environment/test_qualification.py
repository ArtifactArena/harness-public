"""Qualification requires losing no round; no optional score evaluators.

The user's ruling: three 20-second rounds against the stationary block, and the
robot passes if it LOSES none of them. A draw passes; winning every round is the
goal, not the bar. The upstream suite encoded "win all three" — these cases are
rewritten to the rule this harness enforces (`qualify_round`, 2026-09-17).
"""
from pathlib import Path
import tempfile

import pytest


def _make_fake_game_record(winner="red", num_steps=100, seed=0):
    """Create a minimal GameRecord for testing."""
    from mjarena.design_shop.types import GameRecord
    red_positions = [[float(i) * 0.01, 0.0, 0.5] for i in range(num_steps)]
    blue_positions = [[0.0, 0.0, 0.5]] * num_steps
    orient = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
    zero3 = [0.0, 0.0, 0.0]
    return GameRecord(
        seed=seed,
        winner=winner,
        num_steps=num_steps,
        winner_step=num_steps if winner != "tie" else None,
        progress=0.8,
        ring_radius=7.5,
        red_mass=100.0,
        blue_mass=50.0,
        red_bounding_radius=0.5,
        blue_bounding_radius=0.3,
        red_actuator_names=["motor"],
        blue_actuator_names=[],
        red_positions=red_positions,
        blue_positions=blue_positions,
        red_orientations=[orient] * num_steps,
        blue_orientations=[orient] * num_steps,
        red_velocities=[[0.1, 0.0, 0.0]] * num_steps,
        blue_velocities=[zero3] * num_steps,
        red_angular_velocities=[zero3] * num_steps,
        blue_angular_velocities=[zero3] * num_steps,
        distances_to_opponent=[max(0.1, 5.0 - i * 0.05) for i in range(num_steps)],
        red_edge_distances=[3.0] * num_steps,
        blue_edge_distances=[3.0] * num_steps,
        contacts=[i > 50 for i in range(num_steps)],
        contact_forces=[10.0 if i > 50 else 0.0 for i in range(num_steps)],
        red_tipping=[0.0] * num_steps,
        blue_tipping=[0.0] * num_steps,
        red_ground_contacts=[True] * num_steps,
        blue_ground_contacts=[True] * num_steps,
        blue_displacements=[0.01 if i > 50 else 0.0 for i in range(num_steps)],
        red_actions=[{"motor": 0.5}] * num_steps,
        blue_actions=[{}] * num_steps,
        physics_unstable=False,
        qacc_warning_steps=[],
        initial_red_pos=[0.0, 0.0, 0.5],
        initial_blue_pos=[0.0, 0.0, 0.5],
        initial_distance=0.0,
        termination_reason="ring_out" if winner != "tie" else "timeout",
    )


def _make_fake_run_match_fn(winners=None):
    """Create a fake run_match_fn that returns preset results per seed."""
    if winners is None:
        winners = ["red", "red", "red"]
    call_count = [0]

    def fake_run_match(policy_callable, seed=0):
        idx = call_count[0] % len(winners)
        call_count[0] += 1
        return _make_fake_game_record(winner=winners[idx], seed=seed)

    return fake_run_match


def test_qualify_round_all_wins():
    from mjarena.design_shop.tools.match_tools import qualify_round

    with tempfile.TemporaryDirectory() as tmpdir:
        result = qualify_round(
            policy_callable=lambda obs: {"motor": 0.5},
            run_match_fn=_make_fake_run_match_fn(["red", "red", "red"]),
            n_rollouts=3,
            output_dir=Path(tmpdir),
            commit_num=0,
        )

    assert result.passed is True
    assert result.score > 0
    assert result.matchup is not None
    assert result.name == "qualification"


def test_qualify_round_with_loss():
    from mjarena.design_shop.tools.match_tools import qualify_round

    with tempfile.TemporaryDirectory() as tmpdir:
        result = qualify_round(
            policy_callable=lambda obs: {"motor": 0.5},
            run_match_fn=_make_fake_run_match_fn(["red", "blue", "red"]),
            n_rollouts=3,
            output_dir=Path(tmpdir),
            commit_num=1,
        )

    assert result.passed is False
    assert "Lost 1/3" in result.message


@pytest.mark.parametrize('winners', [('tie', 'tie', 'tie'), ('red', 'tie', 'red')])
def test_qualify_round_draw_passes(winners):
    """A draw is not a loss, so it qualifies — with or without wins beside it."""
    from mjarena.design_shop.tools.match_tools import qualify_round

    with tempfile.TemporaryDirectory() as tmpdir:
        result = qualify_round(
            policy_callable=lambda obs: {"motor": 0.5},
            run_match_fn=_make_fake_run_match_fn(winners),
            n_rollouts=3,
            output_dir=Path(tmpdir),
            commit_num=0,
        )

    assert result.passed is True
    assert "qualified (no losses)" in result.message


@pytest.mark.parametrize('winners,expected', [
    (['red', 'red', 'red'], True),
    (['red', 'tie', 'red'], True),      # a draw against the block passes
    (['red', 'blue', 'red'], False),    # a single loss fails
    (['blue', 'red', 'red'], False),    # …in the first round too: no early exit
    (['red', 'red', 'blue'], False),    # …and in the last, after two wins
])
def test_stationary_block_rule_requires_no_losses(winners, expected):
    # This harness has no `rules.movement_rule`; the block rule it runs is
    # `qualify_round` itself, so the rounds are counted through the match fn.
    from mjarena.design_shop.tools.match_tools import qualify_round

    records = []
    fake_run_match = _make_fake_run_match_fn(winners)

    def counting_run_match(policy_callable, seed=0):
        records.append(fake_run_match(policy_callable, seed=seed))
        return records[-1]

    result = qualify_round(
        policy_callable=lambda obs: {'motor': 0.0},
        run_match_fn=counting_run_match,
        n_rollouts=3,
    )
    assert result.passed is expected
    assert len(records) == 3


def test_qualify_round_has_matchup():
    from mjarena.design_shop.tools.match_tools import qualify_round
    from mjarena.design_shop.types import MatchupResult

    with tempfile.TemporaryDirectory() as tmpdir:
        result = qualify_round(
            policy_callable=lambda obs: {"motor": 0.5},
            run_match_fn=_make_fake_run_match_fn(["red", "red", "red"]),
            n_rollouts=3,
            output_dir=Path(tmpdir),
            commit_num=0,
        )

    assert result.matchup is not None
    assert isinstance(result.matchup, MatchupResult)
