"""Execute authoring, composition, physics, controllers, and replay together."""
import json

import mujoco
import numpy as np
import pytest

from environment_fixtures import ROOT, RULES, arena_xml, box_mesh
from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.envs.sumo import compose_sumo_model, SumoEnv
from mjarena.runner.episode import run_match


@pytest.mark.parametrize('seed', [0,1,2])
def test_twenty_second_sdf_tendon_match_with_live_detailed_observations(tmp_path, seed):
    authoring = f'''<mujoco><asset>{box_mesh()}</asset><worldbody>
      <body name="chassis"><freejoint/>
        <geom name="hull" type="sdf" mesh="surface" material="aluminum"/>
        <site name="anchor" pos="0 0 .2"/>
        <body name="arm" pos="0 0 .4"><joint name="slider" type="slide" axis="1 0 0"
          damping="10" stiffness="20" limited="true" range="-.1 .1"/>
          <geom name="tip" size=".04" material="rubber"/><site name="tip_site"/>
        </body>
      </body></worldbody><tendon><fixed name="coupler" stiffness="5" damping="2">
        <joint joint="slider" coef="2"/></fixed></tendon>
      <actuator><motor name="pull" tendon="coupler" gear="10"/></actuator></mujoco>'''
    result = validate_morphology(authoring,ModelValidationConfig(RULES,physics_mode='3d'))
    assert result.passed, result.feedback
    robot = tmp_path/'robot.xml'; robot.write_text(result.processed_xml)
    composed = tmp_path/'composed.xml'
    compose_sumo_model(str(ROOT/'mjarena/assets/sumo_ring_env_cinematic_3d.xml'),
                       str(robot),str(ROOT/'mjarena/core/assets/stationary_block_3d.xml'),
                       str(composed),randomize_spawn_3d=True,spawn_seed=seed)
    state = {'calls':0,'positions':[],'snapshot':None}
    def controller(obs):
        assert obs['t'] == state['calls']
        state['calls'] += 1
        robot_obs = obs['my_robot']
        joint = robot_obs['joints']['slider']; tendon = robot_obs['tendons']['coupler']
        position = float(np.asarray(joint['position']).reshape(-1)[0])
        state['positions'].append(position)
        assert np.isfinite(position) and abs(position) < .105
        assert tendon['length'] == pytest.approx(2*position,abs=1e-8)
        assert robot_obs['motors']['pull']['target'] == 'coupler'
        assert robot_obs['geoms']['hull']['type'] == 'sdf'
        assert obs['elapsed_time'] == pytest.approx(obs['t']*.01)
        assert obs['time_remaining'] == pytest.approx((2000-obs['t'])*.01)
        if state['snapshot'] is None:
            state['snapshot'] = robot_obs
            state['first_com'] = np.array(robot_obs['com_position'],copy=True)
        else:
            np.testing.assert_array_equal(state['snapshot']['com_position'],state['first_com'])
        return {'pull': .2*np.sin(obs['t']*.03)}
    record = run_match(composed,controller,lambda obs:{},tmp_path,2000,False,False,'tracking',
                       seed=seed,quiet=True,inactivity_timeout_seconds=None)
    assert record.termination_reason == 'timeout' and record.winner == 'tie'
    assert record.num_steps == state['calls'] == len(record.qpos) == 2000
    assert np.ptp(state['positions']) > .005  # motor really moved the mechanism
    assert not record.physics_unstable and record.controller_errors == []
    assert np.isfinite(np.asarray(record.qpos)).all()
    assert record.control_dt == pytest.approx(.01)
    saved = tmp_path/'record.json'; saved.write_text(json.dumps(record.to_dict(),allow_nan=False))
    replay = json.loads(saved.read_text())
    assert len(replay['qpos']) == 2000 and replay['initial_qpos'] == record.initial_qpos


@pytest.mark.parametrize('fidelity,dt', [('high',.01),('low',.02)])
def test_full_300_second_round_reaches_physics_and_controller_time(tmp_path, fidelity, dt):
    path = tmp_path/'arena.xml'; path.write_text(arena_xml())
    seen = {'red':0,'blue':0}; starts = {}
    def controller(color):
        def step(obs):
            assert obs['t'] == seen[color]
            seen[color] += 1
            assert obs['max_t'] == round(300/dt)
            assert obs['elapsed_time'] == pytest.approx(obs['t']*dt,abs=1e-8)
            assert obs['time_remaining'] == pytest.approx(300-obs['t']*dt,abs=1e-8)
            return {}
        return step
    class ClockedEnv(SumoEnv):
        def reset(self,*args,**kwargs):
            result = super().reset(*args,**kwargs)
            starts['clock'] = float(self.data.time); starts['env'] = self
            return result
    record = run_match(path,controller('red'),controller('blue'),tmp_path,
                       round(300/dt),False,False,'tracking',match_time=300,
                       env_cls=ClockedEnv,env_kwargs={'contact_fidelity':fidelity},quiet=True,
                       inactivity_timeout_seconds=None)
    assert record.termination_reason == 'timeout' and record.winner == 'tie'
    assert record.controller_errors == [] and not record.physics_unstable
    assert seen['red'] == seen['blue'] == record.num_steps == round(300/dt)
    assert starts['env'].data.time-starts['clock'] == pytest.approx(300,abs=2e-6)
    assert record.control_dt*record.num_steps == pytest.approx(300)


def test_match_duration_overrides_stale_environment_step_cap(tmp_path):
    # One control step is deliberately shorter than the requested 0.1 s match.
    # This preserves the org's cap-resolution fix when porting new observations.
    path = tmp_path/'arena.xml'; path.write_text(arena_xml())
    record = run_match(path,lambda obs:{},lambda obs:{},tmp_path,1,False,False,'tracking',
                       match_time=.1,quiet=True,inactivity_timeout_seconds=None)
    assert len(record.qpos) == 10, 'match_time updated Match but left an earlier SumoEnv cap active'
    assert record.num_steps == len(record.qpos), 'recorded frame count is off by one'
