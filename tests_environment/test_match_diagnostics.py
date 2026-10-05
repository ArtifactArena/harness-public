"""Native failures must retain the responsible side and useful replay evidence."""
import json

import mujoco
import numpy as np
import pytest

from environment_fixtures import make_match, close_match
from mjarena.envs.sumo import SumoEnv
from mjarena.design_shop.types import MatchupResult
from mjarena.eval.match_runner import save_matchup_to_disk


@pytest.mark.parametrize('colors,winner', [(('red',),'blue'),(('blue',),'red'),
                                         (('red','blue'),'tie')])
@pytest.mark.parametrize('crash_at', [0,3])
def test_controller_crash_keeps_first_error_through_serialization(tmp_path, monkeypatch, colors, winner, crash_at):
    monkeypatch.delenv('ARENA_SKIP_MATCH_DATA', raising=False)
    calls = dict(red=0,blue=0)
    def policy(color):
        def step(obs):
            calls[color] += 1
            if color in colors and obs['t'] >= crash_at:
                raise ArithmeticError(f'{color} failed on call {calls[color]}')
            return {}
        return step
    match = make_match(policy('red'), policy('blue'), steps=10)
    try:
        record = match.run(save_video=False, quiet=True)
        expected = [dict(color=c,step=crash_at,type='ArithmeticError',
                         message=f'{c} failed on call {crash_at+1}') for c in colors]
        assert record.winner == winner and record.termination_reason == 'forfeit_crash'
        assert record.controller_errors == expected
        if len(colors) == 1:
            # A single forfeit continues the winning side's post-win animation.
            assert calls[colors[0]] > crash_at+1  # later errors must not replace first
        assert json.loads(json.dumps(record.to_dict(),allow_nan=False))['controller_errors'] == expected
        assert record.downsample(7)['controller_errors'] == expected
        matchup = MatchupResult(game_records=[record],combat_scores=[0.],seed_scores=[0.],elapsed_sec=0.)
        assert matchup.downsample().game_records[0].controller_errors == expected
        save_matchup_to_disk(matchup,tmp_path)
        saved = json.loads((tmp_path/'match_data.json').read_text())['seed_0']
        assert saved['controller_errors'] == expected
        assert saved['initial_qpos'] == record.initial_qpos
        assert saved['num_steps'] == len(saved['qpos'])
    finally:
        close_match(match)


@pytest.mark.parametrize('color', ['red','blue','unknown'])
def test_qacc_diagnostics_identify_responsible_dof_and_side(color):
    captured = {}
    class WarningAtFirstStep(SumoEnv):
        def reset(self, *args, **kwargs):
            result = super().reset(*args, **kwargs)
            dof = self.model.nv+10 if color == 'unknown' else int(
                self.model.jnt_dofadr[self.model.joint(color+'_axle').id])
            captured['dof'] = dof
            warning = self.data.warning[mujoco.mjtWarning.mjWARN_BADQACC]
            warning.number = 1; warning.lastinfo = dof
            return result
    match = make_match(env_class=WarningAtFirstStep, articulated=True)
    try:
        record = match.run(save_video=False,quiet=True)
        expected_loser = 'both' if color == 'unknown' else color
        assert record.termination_reason == 'qacc' and record.physics_unstable
        assert record.winner == {'red':'blue','blue':'red','unknown':'tie'}[color]
        assert record.qacc_loser == expected_loser
        assert record.qacc_dof_index == captured['dof']
        assert record.qacc_body_name == (None if color == 'unknown' else color+'_wheel')
        diagnostics = record.qacc_gear_diagnostics
        assert {d['color'] for d in diagnostics} == ({'red','blue'} if color == 'unknown' else {color})
        assert all(d['actuator'] == 'drive' and d['gear'] == 10 for d in diagnostics)
        assert record.downsample(3)['qacc_loser'] == expected_loser
        assert record.to_dict()['qacc_gear_diagnostics'] == diagnostics
        # Warning bookkeeping must not leak to the next round.
        SumoEnv.reset(match.env,seed=1)
        assert not match.env.physics_unstable
        assert match.env._qacc_loser is None and match.env._qacc_dof_index is None
    finally:
        close_match(match)


@pytest.mark.parametrize('repeats', [1,2,3])
def test_replay_frame_count_initial_pose_and_actual_interval(repeats):
    first = {}
    match = make_match(steps=8,apply_n_repeated_actions=repeats)
    reset = match.env.reset
    def capture_reset(*args, **kwargs):
        result = reset(*args, **kwargs)
        first['qpos'] = match.env.data.qpos.copy()
        first['time'] = match.env.data.time
        return result
    match.env.reset = capture_reset
    try:
        record = match.run(save_video=False,quiet=True)
        assert record.winner == 'tie' and record.termination_reason == 'timeout'
        assert record.controller_errors == [] and not record.physics_unstable
        np.testing.assert_array_equal(record.initial_qpos,first['qpos'])
        assert record.num_steps == len(record.qpos) == 8
        dt = (match.env.data.time-first['time'])/8
        assert record.control_dt == pytest.approx(dt,abs=1e-10)
        assert record.control_dt == pytest.approx(.01*repeats)
        for series in (record.red_positions,record.blue_positions,record.contacts,
                       record.contact_forces,record.red_actions,record.red_inactivity_timers):
            assert len(series) == record.num_steps
        replay = record.downsample(3)
        assert replay['red_positions'] == [record.red_positions[i] for i in (0,3,6,7)]
        json.dumps(record.to_dict(),allow_nan=False)
    finally:
        close_match(match)
