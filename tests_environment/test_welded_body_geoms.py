"""Welded mass supports joints; independently moving descendants do not."""
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from mjarena.design_shop.utils import inject_motor_mass, validate_moving_bodies_have_geoms

FIXTURE = Path(__file__).resolve().parent / 'fixtures/welded_bodies.xml'


def robot():
    root = ET.fromstring(FIXTURE.read_text())
    for geom in root.iter('geom'):
        geom.attrib.pop('material')
        geom.set('mass', '10' if geom.get('name') == 'tip' else '50')
    return ET.tostring(root, encoding='unicode')


def test_welded_descendants_compile_and_receive_motor_mass():
    xml = inject_motor_mass(robot(), 0.01)
    assert validate_moving_bodies_have_geoms(xml) == ([], {
        'moving_bodies_checked': 2, 'missing_geom_errors': 0})
    root = ET.fromstring(xml)
    assert float(root.find(".//geom[@name='tip']").get('mass')) == 11
    assert float(root.find(".//geom[@name='chassis']").get('mass')) == 50.5
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.body_mass.sum() == pytest.approx(61.5)

    # Flatten only welded frames: physical mass distribution and dynamics
    # must match the same shapes attached directly to the jointed bodies.
    arm = root.find(".//body[@name='arm']")
    tip = root.find(".//geom[@name='tip']")
    tip.set('pos', '0.1 0 0')
    arm.remove(arm.find('body'))
    arm.append(tip)
    chassis = root.find(".//geom[@name='chassis']")
    bot = root.find('worldbody/body')
    bot.remove(bot.find("body[@name='chassis_frame']"))
    bot.append(chassis)
    flat = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
    a, b = mujoco.MjData(model), mujoco.MjData(flat)
    a.qpos[-1] = b.qpos[-1] = 0.4
    mujoco.mj_forward(model, a)
    mujoco.mj_forward(flat, b)
    np.testing.assert_allclose(a.qM, b.qM, atol=1e-12)
    np.testing.assert_allclose(a.qfrc_bias, b.qfrc_bias, atol=1e-12)
    np.testing.assert_allclose(a.subtree_com[1], b.subtree_com[1], atol=1e-12)


@pytest.mark.parametrize('boundary', ['<joint/>', '<freejoint/>', '<joint type="free"/>'])
def test_independent_children_cannot_supply_parent_mass(boundary):
    xml = f'<mujoco><worldbody><body name="empty"><joint/><body name="moving">{boundary}<geom size="0.1"/></body></body></worldbody></mujoco>'
    errors, details = validate_moving_bodies_have_geoms(xml)
    assert len(errors) == 1 and "'empty'" in errors[0]
    assert details['missing_geom_errors'] == 1


def test_direct_geom_preferred_and_multiple_motors_accumulate():
    root = ET.fromstring(robot())
    arm = root.find(".//body[@name='arm']")
    ET.SubElement(arm, 'geom', name='direct', size='0.1', mass='2')
    ET.SubElement(root.find('actuator'), 'motor', joint='hinge', gear='-200')
    processed = ET.fromstring(inject_motor_mass(ET.tostring(root, encoding='unicode'), 0.01))
    assert float(processed.find(".//geom[@name='direct']").get('mass')) == 5
    assert float(processed.find(".//geom[@name='tip']").get('mass')) == 10


def test_missing_motor_mount_is_rejected():
    xml = '<mujoco><worldbody><body name="empty"><joint name="j"/></body></worldbody><actuator><motor joint="j" gear="10"/></actuator></mujoco>'
    with pytest.raises(RuntimeError, match='Cannot place motor'):
        inject_motor_mass(xml, 0.01)


def test_empty_fixed_frames_are_allowed_but_massless_moving_assembly_is_not():
    assert not validate_moving_bodies_have_geoms('<mujoco><worldbody><body/></worldbody></mujoco>')[0]
    xml = '<mujoco><worldbody><body><joint/><body><geom size="0.1" mass="0"/></body></body></worldbody></mujoco>'
    assert not validate_moving_bodies_have_geoms(xml)[0]
    with pytest.raises(ValueError, match='mass and inertia'):
        mujoco.MjModel.from_xml_string(xml)
