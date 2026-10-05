"""Robot COM must follow physical mass, including offset and articulated geoms."""

import mujoco
import numpy as np
import pytest

from mjarena.agents.runtime import _com_for_prefix


def test_offset_geom_uses_mass_position_not_body_origin():
    model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
      <body name="red_root" pos="1 2 3"><freejoint/>
        <geom type="sphere" size="0.1" pos="0.5 -0.25 0.75" mass="10"/>
      </body>
    </worldbody></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    np.testing.assert_allclose(_com_for_prefix(model, data, "red_"), [1.5, 1.75, 3.75])


@pytest.mark.parametrize("angle", [0.0, np.pi / 2])
def test_articulated_com_excludes_opponent_and_visual_markers(angle):
    model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
      <body name="red_root"><freejoint/>
        <geom size="0.1" pos="0 0 1" mass="2"/>
        <body name="red_arm"><joint name="red_hinge" axis="0 0 1"/>
          <geom size="0.1" pos="1 0 0" mass="6"/>
        </body>
      </body>
      <body name="blue_root" pos="100 0 0"><freejoint/><geom size="1" mass="800"/></body>
      <body name="red_marker" mocap="true" pos="0 100 0"><geom size="1" mass="800"/></body>
      <body name="red_beacon" pos="0 0 100"><geom size="1" mass="800"/></body>
    </worldbody></mujoco>''')
    data = mujoco.MjData(model)
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "red_hinge")
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "red_root")
    data.qpos[model.jnt_qposadr[joint]] = angle
    mujoco.mj_forward(model, data)
    com = _com_for_prefix(model, data, "red_")
    np.testing.assert_allclose(com, [0.75 * np.cos(angle), 0.75 * np.sin(angle), 0.25], atol=1e-12)
    np.testing.assert_allclose(com, data.subtree_com[root], atol=1e-12)


def test_absent_robot_returns_zero():
    model = mujoco.MjModel.from_xml_string('<mujoco/>')
    data = mujoco.MjData(model)
    np.testing.assert_array_equal(_com_for_prefix(model, data, "red_"), np.zeros(3))
