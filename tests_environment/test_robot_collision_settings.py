from pathlib import Path
import runpy
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from mjarena.design_shop.utils import sanitize_robot_xml
from mjarena.envs.sumo import compose_sumo_model

REPO = Path(__file__).resolve().parents[1]


def test_native_collision_override_behavior():
    check = runpy.run_path(str(Path(__file__).parent / 'support/collision_settings_trace.py'))
    check['check_collision_settings']()


def test_tendon_wrap_references_and_joint_hardware_are_preserved():
    source = '''<mujoco><worldbody><body><freejoint/>
      <geom name="wrap" type="sphere" size=".1"/>
      <body><joint name="joint" damping="42" frictionloss="12" stiffness="300"/>
        <geom type="sphere" size=".1"/><site name="anchor"/></body>
      </body></worldbody><tendon><spatial name="cable" stiffness="300">
      <geom geom="wrap" sidesite="anchor"/></spatial></tendon></mujoco>'''
    root = ET.fromstring(sanitize_robot_xml(source, ()))
    assert root.find('tendon/spatial/geom').attrib == {'geom': 'wrap', 'sidesite': 'anchor'}
    joint = root.find(".//joint[@name='joint']")
    assert [joint.get(a) for a in ('damping', 'frictionloss', 'stiffness')] == ['42', '12', '300']


def test_match_composition_normalizes_old_processed_robots_only(tmp_path):
    robot = tmp_path / 'robot.xml'
    robot.write_text('''<mujoco><worldbody><body name="root"><freejoint/>
      <geom name="ballast" type="box" size=".2 .2 .2" mass="50"
            contype="0" conaffinity="0" solref=".5 4" margin=".1"
            friction=".6 .005 .0001"/>
      <body name="child"><joint name="hinge"/>
        <geom name="rotor" type="sphere" size=".05" mass="1"/>
      </body></body></worldbody>
      <contact><exclude body1="root" body2="child"/></contact>
      <actuator><motor name="motor" joint="hinge"/></actuator></mujoco>''')
    path = compose_sumo_model(str(REPO / 'mjarena/assets/sumo_ring_env_cinematic_3d.xml'),
                             str(robot), str(robot), str(tmp_path / 'composed.xml'))
    model = mujoco.MjModel.from_xml_path(path)
    assert model.nexclude == 0
    for prefix in ('red_', 'blue_'):
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, prefix + 'ballast')
        assert model.geom_contype[gid] == model.geom_conaffinity[gid] == 1
        assert model.geom_margin[gid] == 0
        np.testing.assert_allclose(model.geom_solref[gid], [.02, 1])
        np.testing.assert_allclose(model.geom_friction[gid], [.6, .005, .0001])
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, prefix + 'root')
        assert model.body_mass[bid] == 50
    # Arena-only decorative geoms stay non-colliding.
    arena = mujoco.MjModel.from_xml_path(str(REPO / 'mjarena/assets/sumo_ring_env_cinematic_3d.xml'))
    for gid in range(arena.ngeom):
        name = mujoco.mj_id2name(arena, mujoco.mjtObj.mjOBJ_GEOM, gid)
        if name and int(arena.geom_contype[gid]) == int(arena.geom_conaffinity[gid]) == 0:
            composed_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
            assert model.geom_contype[composed_gid] == model.geom_conaffinity[composed_gid] == 0
