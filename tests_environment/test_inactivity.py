"""Inactivity is the diameter of the rolling 3D COM trajectory."""

from types import SimpleNamespace

import mujoco
import numpy as np
import pytest

from mjarena.envs.sumo import SumoEnv


def make_env(**kwargs):
    # Use real environment initialization/reset, with controlled COM trajectories.
    model = mujoco.MjModel.from_xml_string(
        '<mujoco><worldbody><geom name="sumo_ring" type="cylinder" '
        'size="7.5 1"/></worldbody></mujoco>'
    )
    env = SumoEnv(
        model=model,
        data=mujoco.MjData(model),
        xml_path="unused.xml",
        red_contender=SimpleNamespace(prefix="red_", com_position=np.zeros(3)),
        blue_contender=SimpleNamespace(prefix="blue_", com_position=np.zeros(3)),
        **kwargs,
    )
    env.reset(seed=0)
    return env


def test_can_be_explicitly_disabled_for_diagnostics():
    env = make_env(inactivity_timeout_seconds=None)
    for _ in range(2001):
        assert env.check_inactivity() is None
    assert env._inactivity_timers == {"red": 0.0, "blue": 0.0}
    assert not env._red_com_history
    assert not env._blue_com_history


@pytest.mark.parametrize("dt", [0.01, 0.02])
def test_stationary_loss_at_exactly_ten_seconds(dt):
    env = make_env(control_timestep=dt)
    steps = round(10 / dt)
    for _ in range(steps - 1):
        assert env.check_inactivity() is None
    assert env._inactivity_timers["red"] == pytest.approx(10 - dt)
    assert env.check_inactivity() == "both"
    assert env._inactivity_timers == {"red": 10.0, "blue": 10.0}


@pytest.mark.parametrize("path", ["oscillation", "out_and_back"])
def test_meaningful_motion_remains_active_when_returning(path):
    env = make_env(inactivity_timeout_seconds=10, inactivity_exempt_prefixes=["blue_"])
    for step in range(1, 3001):
        t = step * env.control_timestep
        x = 0.49 * np.sin(2 * np.pi * t / 4) if path == "oscillation" else min(t % 10, 10 - t % 10) / 5
        env.red_contender.com_position[0] = x
        assert env.check_inactivity() is None
    assert env._inactivity_timers["blue"] == 0


def test_small_vibrations_do_not_count_as_activity():
    env = make_env(inactivity_timeout_seconds=10)
    for step in range(1, 1001):
        env.red_contender.com_position[0] = 0.1 * np.sin(step)
        result = env.check_inactivity()
        assert result == ("both" if step == 1000 else None)


def test_furthest_pair_need_not_include_current_position():
    env = make_env(inactivity_timeout_seconds=10, inactivity_exempt_prefixes=["blue_"])
    for step in range(1, 1003):
        env.red_contender.com_position[0] = {1: -0.49, 2: 0.49}.get(step, 0.0)
        # At 10 s the endpoints are both zero, but the path spans 0.98 m.
        # At 10.01 s both extremes are still in the inclusive window.
        result = env.check_inactivity()
        assert result == ("red" if step == 1002 else None)


@pytest.mark.parametrize("destination", [
    (0.5, 0.0, 0.0), (0.4, 0.4, 0.0), (0.0, 0.0, 0.5), (0.3, 0.3, 0.3),
])
def test_threshold_is_inclusive_and_distance_is_euclidean(destination):
    env = make_env(inactivity_timeout_seconds=10, inactivity_exempt_prefixes=["blue_"])
    for _ in range(999):
        assert env.check_inactivity() is None
    env.red_contender.com_position[:] = destination
    assert env.check_inactivity() is None
    assert env._inactivity_timers["red"] == 0
    for _ in range(999):
        assert env.check_inactivity() is None
    assert env.check_inactivity() == "red"


@pytest.mark.parametrize("height", [0.49, 0.5, 1.0])
def test_vertical_motion_counts_only_when_it_spans_the_threshold(height):
    env = make_env(inactivity_timeout_seconds=10, inactivity_exempt_prefixes=["blue_"])
    for step in range(1, 3001):
        env.red_contender.com_position[2] = (step % 2) * height
        assert env.check_inactivity() == ("red" if height < 0.5 and step >= 1000 else None)


@pytest.mark.parametrize("height,loser", [(0, "both"), (1, "blue"), (-1, "red")])
def test_existing_simultaneous_loss_resolution_is_preserved(height, loser):
    env = make_env(inactivity_timeout_seconds=10)
    env.red_contender.com_position[2] = height
    env.reset(seed=0)
    for _ in range(999):
        assert env.check_inactivity() is None
    assert env.check_inactivity() == loser


def test_reset_clears_previous_round_and_seeds_new_window():
    env = make_env(inactivity_timeout_seconds=10)
    for _ in range(1000):
        env.check_inactivity()
    env.red_contender.com_position[2] = 20
    env.reset(seed=1)
    assert env._inactivity_timers == {"red": 0.0, "blue": 0.0}
    for _ in range(999):
        assert env.check_inactivity() is None
    assert env.check_inactivity() == "blue"  # Existing height tiebreak.


@pytest.mark.parametrize("seed", range(4))
def test_matches_brute_force_window_diameter(seed):
    env = make_env(
        inactivity_timeout_seconds=10,
        control_timestep=0.25,
        inactivity_exempt_prefixes=["blue_"],
    )
    rng = np.random.default_rng(seed)
    samples = [np.zeros(3)]
    for step in range(1, 401):
        # Alternate movement and long stalls to exercise entry/exit and expiry.
        scale = 0.2 if (step // 70) % 2 == 0 else 0.001
        position = samples[-1] + rng.normal(size=3) * scale
        samples.append(position)
        env.red_contender.com_position[:] = position
        window = np.asarray(samples[-41:])
        distances = np.linalg.norm(window[:, None, :] - window[None, :, :], axis=2)
        expected = "red" if step >= 40 and distances.max() < 0.5 else None
        assert env.check_inactivity() == expected
