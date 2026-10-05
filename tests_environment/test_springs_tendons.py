"""Real MuJoCo checks for unloaded springs, tendon motors, and arena assembly."""
from pathlib import Path

import mujoco
import numpy as np
import pytest

from mjarena.agents.runtime import BotRuntime
from mjarena.design_shop.utils import inject_motor_mass, sanitize_robot_xml, validate_passive_mechanisms
from mjarena.envs.sumo import compose_sumo_model


def robot(joint='stiffness="100" ref="0.2" springref="0.2"', tendon='', defaults=''):
    return f'''<mujoco>{defaults}<worldbody><body name="bot">
      <freejoint name="root"/><geom name="chassis" size="0.2" mass="50"/>
      <site name="a" pos="0 0 0"/>
      <body name="arm" pos="1 0 0"><joint name="slide" type="slide" axis="1 0 0" {joint}/>
        <geom name="tip" size="0.1" mass="10"/><site name="b"/>
      </body>
    </body></worldbody><tendon>
      <spatial name="cable" {tendon}><site site="a"/><site site="b"/></spatial>
      <fixed name="coupling" stiffness="20"><joint joint="slide" coef="2"/></fixed>
    </tendon><actuator><motor name="pull" tendon="cable" gear="100"/>
      <motor name="coupled" tendon="coupling" gear="-50"/>
    </actuator></mujoco>'''


def compile_robot(**kwargs):
    return mujoco.MjModel.from_xml_string(sanitize_robot_xml(robot(**kwargs), ()))


def test_unloaded_springs_restore_after_displacement():
    model = compile_robot(tendon='stiffness="200"')
    assert validate_passive_mechanisms(model) == []
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    np.testing.assert_allclose(data.qfrc_spring, 0, atol=1e-12)
    data.qpos[-1] += 0.1
    mujoco.mj_forward(model, data)
    # Joint 100 + spatial 200 + fixed 20*(coefficient 2)^2 = 380 N/m.
    assert data.qfrc_spring[-1] == pytest.approx(-38)


@pytest.mark.parametrize('kwargs', [
    {'joint': 'stiffness="100" ref="0.2" springref="0"'},
    {'tendon': 'stiffness="100" springlength="0.5"'},
    {'tendon': 'stiffness="100" springlength="0.2 0.5"'},
    {'joint': '', 'defaults': '<default><joint stiffness="100" springref="0.3"/></default>'},
])
def test_preload_is_rejected(kwargs):
    assert any('must start unloaded' in error for error in validate_passive_mechanisms(compile_robot(**kwargs)))


def test_spring_rest_interval_and_zero_stiffness():
    assert not validate_passive_mechanisms(compile_robot(tendon='stiffness="100" springlength="0.5 1.5"'))
    model = compile_robot(joint='stiffness="0" springref="0.8"')
    # Automatic tendon rest lengths use qpos_spring, even for a zero-stiffness joint.
    assert any("coupling" in error for error in validate_passive_mechanisms(model))
    model.tendon_stiffness[:] = 0
    assert not validate_passive_mechanisms(model)


def test_opposing_preloads_are_not_hidden_by_zero_net_force():
    xml = robot(joint='', tendon='stiffness="100" springlength="0.5"')
    xml = xml.replace('<fixed name="coupling" stiffness="20">', '<fixed name="coupling" stiffness="100" springlength="0.25">')
    model = mujoco.MjModel.from_xml_string(sanitize_robot_xml(xml, ()))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert data.qfrc_spring[-1] == pytest.approx(0)
    assert len(validate_passive_mechanisms(model)) == 2


@pytest.mark.parametrize('damping,passes', [(0, True), (600, True), (601, False)])
def test_tendon_damping(damping, passes):
    assert (not validate_passive_mechanisms(compile_robot(tendon=f'damping="{damping}"'))) == passes


@pytest.mark.parametrize('field', ['dof_frictionloss', 'tendon_frictionloss'])
@pytest.mark.parametrize('value,passes', [(0, True), (600, True), (601, False),
                                        (-1, False), (float('nan'), False), (float('inf'), False)])
def test_frictionloss_limits(field, value, passes):
    model = compile_robot()
    getattr(model, field)[-1] = value
    assert (not validate_passive_mechanisms(model)) == passes


def test_frictionloss_defaults_combine_with_damping_and_root_stays_free():
    model = compile_robot(joint='', tendon='', defaults='''<default>
      <joint frictionloss="600" damping="100"/>
      <tendon frictionloss="600" damping="100"/>
    </default>''')
    assert not validate_passive_mechanisms(model)
    np.testing.assert_array_equal(model.dof_frictionloss[:6], 0)
    assert model.dof_frictionloss[-1] == 600
    np.testing.assert_array_equal(model.tendon_frictionloss, 600)
    # Keep only joint friction for this force check, and move fast enough to
    # slide. Damping and dry friction must both oppose that motion.
    model.tendon_frictionloss[:] = 0
    model.tendon_damping[:] = 0
    data = mujoco.MjData(model)
    data.qvel[-1] = 2
    mujoco.mj_forward(model, data)
    assert data.qfrc_passive[-1] == pytest.approx(-200)
    assert data.qfrc_constraint[-1] == pytest.approx(-600)


def test_tendon_motor_mass_and_observation():
    xml = inject_motor_mass(sanitize_robot_xml(robot(), ()), 0.01)
    model = mujoco.MjModel.from_xml_string(xml)
    # Both tendon motors mount on the root: the spatial 'pull' costs |gear| x 0.01
    # = 1.0 kg, and the fixed 'coupled' costs |gear| x sum(|coef|) x 0.01 =
    # 50 x 2 x 0.01 = 1.0 kg. The coefficient is priced since the 2026-09-16
    # review (C3): a fixed tendon applies gear x coef to its joints, so `coef`
    # was an unpriced torque multiplier — gear="1" with coef="100000" delivered
    # 100 kN*m for 0.01 kg. This robot used to weigh 51.5 kg.
    assert model.body_mass[1] == pytest.approx(52.0)
    assert model.body_mass[2] == 10
    data = mujoco.MjData(model)
    data.qvel[0] = 7  # Tendon 0 must not be mistaken for root joint 0.
    data.qvel[-1] = 3
    mujoco.mj_forward(model, data)
    bot = BotRuntime(model, data, lambda obs: {}, prefix='')
    assert bot.actuator_joint_velocity() == {'pull': pytest.approx(3), 'coupled': pytest.approx(6)}
    data.ctrl[:] = [1, 0]
    mujoco.mj_forward(model, data)
    assert data.qfrc_actuator[-1] == pytest.approx(100)


def test_composition_keeps_tendons_and_scopes_defaults(tmp_path):
    source = robot(joint='class="elastic"', defaults='''<default>
      <tendon stiffness="45" damping="6"/><motor gear="13"/>
      <default class="elastic"><joint stiffness="30" damping="5"/></default>
    </default>''')
    path = tmp_path / 'robot.xml'
    path.write_text(sanitize_robot_xml(source, ()))
    env = tmp_path / 'env.xml'
    env.write_text('''<mujoco><worldbody><geom name="sumo_ring" type="cylinder" size="5 1"/>
      <site name="spawn/left" pos="-2 0 1"/><site name="spawn/right" pos="2 0 1"/>
    </worldbody></mujoco>''')
    composed = compose_sumo_model(str(env), str(path), str(path), str(tmp_path / 'arena.xml'))
    model = mujoco.MjModel.from_xml_path(composed)
    assert model.ntendon == 4 and model.nu == 4
    assert not validate_passive_mechanisms(model)
    for prefix in ('red_', 'blue_'):
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, prefix + 'slide')
        tid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_TENDON, prefix + 'cable')
        assert model.jnt_stiffness[jid] == 30
        assert model.tendon_stiffness[tid] == 45
        assert model.tendon_damping[tid] == 6


def test_environment_owns_armature_and_uses_radians():
    model = compile_robot(joint='armature="20" ref="0.3" springref="0.3"',
                          tendon='armature="30"', defaults='<default><joint armature="10"/><motor armature="40"/></default>')
    np.testing.assert_array_equal(model.dof_armature, 0)
    np.testing.assert_array_equal(model.tendon_armature, 0)
    np.testing.assert_array_equal(model.actuator_armature, 0)
    xml = robot(joint='type="hinge" ref="0.3" springref="0.3"').replace('type="slide" ', '')
    model = mujoco.MjModel.from_xml_string(sanitize_robot_xml(xml, ()))
    assert model.qpos0[-1] == pytest.approx(0.3)


@pytest.mark.parametrize('joint_tag', ['<freejoint name="root"/>', '<joint name="root" type="free"/>'])
def test_free_joint_motor_mass_is_physically_injected(joint_tag):
    xml = '<mujoco><worldbody><body>'+joint_tag+'<geom size=".2" mass="10"/></body></worldbody><actuator><motor name="force" joint="root" gear="0 300 400 0 0 0"/><motor name="torque" joint="root" gear="0 0 0 0 -200 0"/></actuator></mujoco>'
    model = mujoco.MjModel.from_xml_string(inject_motor_mass(xml, .01))
    assert model.body_mass[1] == pytest.approx(17.)
    np.testing.assert_allclose(model.body_inertia[1], [.4*17*.2**2]*3)
