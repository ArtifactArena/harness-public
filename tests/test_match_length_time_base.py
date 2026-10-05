"""A match lasts `match_time` seconds of simulated time, whatever the env step size.

`run_match` and `Match` turn `match_time` into a step cap. One env step advances
`frame_timestep` = control_timestep x apply_n_repeated_actions, so the cap must be
match_time / frame_timestep. Dividing by control_timestep alone (the old code) makes
a "300 s" match run 300 x apply_n seconds.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)

from pathlib import Path

import pytest

from mjarena.agents.runtime import BotRuntime
from mjarena.envs.sumo import SumoEnv, compose_sumo_model
from mjarena.envs.utils import _mj_load
from mjarena.runner.episode import Match, run_match

ROOT = Path(__file__).resolve().parents[1]
ARENA = ROOT / "mjarena/assets/sumo_ring_env_cinematic_3d.xml"
PUSHER = ROOT / "mjarena/core/assets/baseline_bots/baseline-pusher/robot.xml"
BLOCK = ROOT / "mjarena/core/assets/stationary_block_3d.xml"

DT = 0.01  # control timestep at contact_fidelity=high


def _compose(tmp_path: Path) -> Path:
    out = tmp_path / "composed.xml"
    compose_sumo_model(env_xml=str(ARENA), robot_red_xml=str(PUSHER), robot_blue_xml=str(BLOCK),
                       out_path=str(out), randomize_spawn_3d=True, spawn_seed=0)
    return out


@pytest.mark.parametrize("n_repeat", [1, 2, 3])
def test_match_wrapper_caps_steps_in_simulated_seconds(tmp_path, n_repeat):
    model, data = _mj_load(_compose(tmp_path))
    red = BotRuntime(model=model, data=data, policy_callable=lambda obs: {}, prefix="red_")
    blue = BotRuntime(model=model, data=data, policy_callable=lambda obs: {}, prefix="blue_")
    env = SumoEnv(model=model, data=data, xml_path="composed.xml", red_contender=red,
                  blue_contender=blue, apply_n_repeated_actions=n_repeat)
    match = Match(env, red, blue, max_steps=None, headless=True, match_time=300.0)
    expected = int(round(300.0 / env.frame_timestep))  # 30000 / 15000 / 10000
    assert match.max_steps == expected, (
        f"cap is {match.max_steps} env steps = {match.max_steps * env.frame_timestep:.0f} s "
        f"of simulated time, expected {expected} = 300 s")
    if n_repeat == 1:
        assert match.max_steps == 30000  # unchanged: 300 s at 100 Hz


@pytest.mark.parametrize("n_repeat", [1, 3])
def test_real_match_ends_after_match_time_seconds(tmp_path, n_repeat):
    match_time = 3.0
    frame_dt = DT * n_repeat
    expected_steps = int(round(match_time / frame_dt))  # 300 at n=1, 100 at n=3
    record = run_match(
        composed_xml=_compose(tmp_path), red_policy_py=lambda obs: {}, blue_policy_py=lambda obs: {},
        out_dir=tmp_path, max_steps=None, use_gui=False, save_video=False,
        camera_mode="tracking", quiet=True, seed=0,
        match_time=match_time, inactivity_timeout_seconds=None,
        env_kwargs={"apply_n_repeated_actions": n_repeat},
    )
    assert record.control_dt == pytest.approx(frame_dt)
    assert record.num_steps == expected_steps, (
        f"match ran {record.num_steps} env steps = {record.num_steps * frame_dt:.2f} s of simulated "
        f"time (frame_timestep={frame_dt}), expected {expected_steps} = {match_time} s")
    assert record.num_steps * record.control_dt == pytest.approx(match_time)
