from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('detailed_checks',Path(__file__).parent/'support/detailed_observation_trace.py')
checks=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
test_concave_surface_distances=checks.check_surface_distances
test_detailed_observations=checks.check_observations
test_proximity_contract=checks.check_proximity_contract


def test_validation_uses_named_robot_state():
    from mjarena.design_shop.controller_observation import initial_controller_observation
    from mjarena.design_shop.rules.software_rules import compile_policy, execute_policy, exercise_policy
    xml = '<mujoco><worldbody><body name="root"><freejoint/><geom name="base" type="box" size=".3 .3 .1" mass="10"/><body name="arm" pos="0 0 .3"><joint name="lift" type="slide" axis="0 0 1"/><geom name="tip" size=".1" mass="1"/></body></body></worldbody><actuator><motor name="lift_motor" joint="lift"/></actuator></mujoco>'
    obs = initial_controller_observation(xml)
    assert 'lift' in obs['my_robot']['joints']
    policy, result = compile_policy('def policy_step(obs):\n    return {"lift_motor": float(obs["my_robot"]["joints"]["lift"]["position"] > 0)}')
    assert result.passed
    assert execute_policy(policy, base_observation=obs)[1].passed
    assert exercise_policy(policy, ['lift_motor'], base_observation=obs).passed


def test_validation_observation_for_passive_robot():
    from mjarena.design_shop.controller_observation import initial_controller_observation
    xml = '<mujoco><worldbody><body name="root"><freejoint/><geom name="base" type="box" size=".3 .3 .1" mass="10"/></body></worldbody></mujoco>'
    obs = initial_controller_observation(xml)
    assert obs['my_robot']['motors'] == {}
    assert obs['my_actuator_velocity'] == {}
    assert obs['my_mass'] == 10
    assert obs['t'] == 0 and obs['elapsed_time'] == 0
    assert obs['time_remaining'] == 20 and obs['max_t'] == 2000


def test_validation_observation_for_unnamed_body_tree():
    from mjarena.design_shop.controller_observation import initial_controller_observation
    xml = '<mujoco><worldbody><body><freejoint/><geom name="base" type="box" size=".3 .3 .1" mass="10"/><body pos="0 0 .3"><geom name="arm" size=".1" mass="2"/></body></body></worldbody></mujoco>'
    obs = initial_controller_observation(xml)
    robot = obs['my_robot']
    assert robot['root_body'] in robot['bodies']
    assert len(robot['bodies']) == 2 and len(robot['geoms']) == 2
    assert obs['my_mass'] == 12
