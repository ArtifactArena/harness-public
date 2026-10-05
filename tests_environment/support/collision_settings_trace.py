"""Native check: forbidden masks must not create ghost geometry."""
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from mjarena.design_shop.rules.hardware_rules import sanitize_robot_xml


ROBOT_XML = '''<mujoco>
  <default>
    <geom contype="0" conaffinity="0" condim="1" priority="99"
          friction="9 8 7" solmix="5" solref="0.5 4"
          solimp="0.1 0.2 0.3" margin="0.5" gap="0.2"/>
    <pair friction="9 9 9 9 9"/>
    <default class="hidden"><geom contype="0" conaffinity="0"/></default>
  </default>
  <worldbody>
    <body name="robot"><freejoint/>
      <geom name="ballast" class="hidden" type="box" size="0.2 0.2 0.2"
            mass="50" contype="0" conaffinity="0" margin="0.015"/>
    </body>
    <body name="other" pos="3 0 0"><freejoint/>
      <geom name="other_geom" type="sphere" size="0.1" mass="1"/>
    </body>
  </worldbody>
  <contact>
    <exclude body1="robot" body2="other"/>
    <pair geom1="ballast" geom2="other_geom" friction="9 9 9 9 9"/>
  </contact>
</mujoco>'''


def check_collision_settings():
    xml, step = sanitize_robot_xml(ROBOT_XML)
    assert step.passed
    assert 'Ignored environment-owned collision settings' in step.message
    assert 'conaffinity' in step.message and '<contact>' in step.message
    root = ET.fromstring(xml)
    assert root.find('contact') is None
    assert not list(root.iter('pair'))
    m = mujoco.MjModel.from_xml_string(xml)
    assert m.npair == 0 and m.nexclude == 0
    for attr, expected in [('geom_contype', 1), ('geom_conaffinity', 1),
                           ('geom_condim', 6), ('geom_priority', 2),
                           ('geom_solmix', 1), ('geom_margin', 0), ('geom_gap', 0)]:
        np.testing.assert_array_equal(np.asarray(getattr(m, attr)), expected)
    np.testing.assert_allclose(np.asarray(m.geom_solref).reshape(-1, 2), [[.02, 1]] * m.ngeom)
    np.testing.assert_allclose(np.asarray(m.geom_solimp).reshape(-1, 5), [[.9, .95, .001, .5, 2]] * m.ngeom)
    np.testing.assert_allclose(np.asarray(m.geom_friction).reshape(-1, 3), [[1, .005, .0001]] * m.ngeom)
    # Add an arena-owned probe overlapping the ballast. A real contact must
    # exist after normalization, whereas the model's original masks hide it.
    ET.SubElement(root.find('worldbody'), 'geom', name='probe', type='sphere',
                  size='.03', pos='0 0 0')
    counts = []
    for enabled in (False, True):
        geom = root.find(".//geom[@name='ballast']")
        geom.set('contype', str(int(enabled)))
        geom.set('conaffinity', str(int(enabled)))
        model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        ids = {mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
               for name in ('probe', 'ballast')}
        counts.append(sum({c.geom1, c.geom2} == ids for c in data.contact))
    assert counts[0] == 0 and counts[1] > 0, counts
    return counts


if __name__ == '__main__':
    print(check_collision_settings())
