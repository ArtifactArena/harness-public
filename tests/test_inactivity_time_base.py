"""Inactivity is a 10 s promise in simulated time, whatever the env step size.

`check_inactivity` runs once per env `step()`, and one env step holds the
action for `apply_n_repeated_actions` control periods (`frame_timestep`
= control_timestep x apply_n_repeated_actions). The window and the timer
the controllers read must therefore be sized in env steps of
`frame_timestep`, not in control periods — otherwise a stalled bot survives
10 s x apply_n and `my_inactivity_timer` under-reports by the same factor.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)

from pathlib import Path

import pytest

from mjarena.agents.runtime import BotRuntime
from mjarena.envs.sumo import SumoEnv, compose_sumo_model
from mjarena.envs.utils import _mj_load

ROOT = Path(__file__).resolve().parents[1]
ARENA = ROOT / "mjarena/assets/sumo_ring_env_cinematic_3d.xml"
PUSHER = ROOT / "mjarena/core/assets/baseline_bots/baseline-pusher/robot.xml"
BLOCK = ROOT / "mjarena/core/assets/stationary_block_3d.xml"

DT = 0.01          # control timestep at contact_fidelity=high
TIMEOUT = 10.0     # seconds of simulated time
MIN_DISP = 0.5


def _compose(tmp_path: Path) -> Path:
    out = tmp_path / "composed.xml"
    compose_sumo_model(env_xml=str(ARENA), robot_red_xml=str(PUSHER), robot_blue_xml=str(BLOCK),
                       out_path=str(out), randomize_spawn_3d=True, spawn_seed=0)
    return out


# ── window sizing at construction ───────────────────────────────────────────

@pytest.mark.parametrize("n_repeat", [1, 2, 3])
def test_window_is_ten_simulated_seconds_of_env_steps(tmp_path, n_repeat):
    model, data = _mj_load(_compose(tmp_path))
    red = BotRuntime(model=model, data=data, policy_callable=lambda obs: {}, prefix="red_")
    blue = BotRuntime(model=model, data=data, policy_callable=lambda obs: {}, prefix="blue_")
    env = SumoEnv(model=model, data=data, xml_path="composed.xml", red_contender=red,
                  blue_contender=blue, apply_n_repeated_actions=n_repeat,
                  inactivity_timeout_seconds=TIMEOUT, inactivity_min_displacement=MIN_DISP,
                  inactivity_exempt_prefixes=["blue_"])
    assert env.frame_timestep == pytest.approx(DT * n_repeat)
    expected_window = int(round(TIMEOUT / env.frame_timestep))
    assert env._inactivity_window_steps == expected_window, (
        f"window is {env._inactivity_window_steps} env steps = "
        f"{env._inactivity_window_steps * env.frame_timestep:.2f} s of simulated time, "
        f"expected {expected_window} = {TIMEOUT} s")
    # the history keeps both endpoints of the window
    assert env._red_com_history.maxlen == expected_window + 1
    assert env._blue_com_history.maxlen == expected_window + 1
    if n_repeat == 1:
        assert env._inactivity_window_steps == 1000  # unchanged: 10 s at 100 Hz


# ── real matches ────────────────────────────────────────────────────────────

def _run(tmp_path: Path, n_repeat: int, match_time: float):
    from mjarena.runner.episode import run_match
    return run_match(
        composed_xml=_compose(tmp_path), red_policy_py=lambda obs: {}, blue_policy_py=lambda obs: {},
        out_dir=tmp_path, max_steps=None, use_gui=False, save_video=False,
        camera_mode="tracking", quiet=True, seed=0,
        match_time=match_time, inactivity_timeout_seconds=TIMEOUT,
        inactivity_min_displacement=MIN_DISP, inactivity_exempt_prefixes=["blue_"],
        env_kwargs={"apply_n_repeated_actions": n_repeat},
    )


@pytest.mark.parametrize("n_repeat", [1, 3])
def test_motionless_bot_loses_after_ten_simulated_seconds(tmp_path, n_repeat):
    frame_dt = DT * n_repeat
    window_steps = int(round(TIMEOUT / frame_dt))     # 1000 at n=1, 333 at n=3
    # match_time -> max_steps is resolved in control periods, so the cap is far
    # beyond the window either way; inactivity must end the round first.
    rec = _run(tmp_path, n_repeat, match_time=15.0)
    assert rec.termination_reason == "inactivity"
    assert rec.winner == "blue"
    assert rec.control_dt == pytest.approx(frame_dt)
    # (a) the loss lands on the window-th env step; the record counts completed steps
    assert rec.num_steps in (window_steps - 1, window_steps), (
        f"inactivity fired after {rec.num_steps} env steps = "
        f"{rec.num_steps * frame_dt:.2f} s of simulated time (frame_timestep={frame_dt}), "
        f"expected ~{window_steps} steps = {TIMEOUT} s")
    assert rec.num_steps * frame_dt == pytest.approx(TIMEOUT, abs=2 * frame_dt)
    # (b) the timer the controller reads is simulated seconds: k env steps -> k * frame_dt
    timers = rec.red_inactivity_timers
    assert len(timers) == rec.num_steps
    for k in (10, 100, rec.num_steps - 1):
        # history is seeded at reset, so after the k-th step the segment spans k+1 samples
        assert timers[k] == pytest.approx((k + 1) * frame_dt, abs=1e-9), (
            f"timer after step {k + 1} reads {timers[k]:.3f} s, simulated time is "
            f"{(k + 1) * frame_dt:.3f} s")
    assert timers[-1] >= TIMEOUT - frame_dt - 1e-9
