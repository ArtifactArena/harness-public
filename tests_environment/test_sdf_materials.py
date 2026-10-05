"""Mesh/SDF material mass must use the actual closed surface, including concavities."""

from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from mjarena.design_shop.rules.hardware_rules import sanitize_robot_xml
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.design_shop.utils import (
    _inline_mesh_volume,
    apply_material_properties,
    inject_motor_mass,
)


REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / 'fixtures'
TETRAHEDRON = '''<mesh name="surface" inertia="exact"
    vertex="0 0 0  0.6 0 0  0 0.4 0  0 0 0.3"
    face="0 2 1  0 1 3  0 3 2  1 2 3"/>'''
PALETTE = {'aluminum': {'density_kg_m3': 2700, 'friction': 0.45}}


def robot_xml(mesh=TETRAHEDRON, gtype='sdf'):
    return f'''<mujoco><asset>{mesh}</asset><worldbody>
    <body name="robot"><freejoint/>
      <geom name="surface_geom" type="{gtype}" mesh="surface" material="aluminum"/>
    </body></worldbody></mujoco>'''


@pytest.mark.parametrize('gtype', ['mesh', 'sdf'])
def test_mesh_mass_and_friction_are_applied_and_mesh_preserved(gtype):
    xml, errors, _ = apply_material_properties(robot_xml(gtype=gtype), PALETTE)
    assert errors == []
    root = ET.fromstring(xml)
    geom = root.find('.//geom')
    assert float(geom.get('mass')) == pytest.approx(0.6 * 0.4 * 0.3 / 6 * 2700)
    assert geom.get('friction') == '0.45 0.005 0.0001'
    assert geom.get('priority') == '2'
    assert geom.get('mesh') == 'surface'
    assert geom.get('type') == gtype
    assert root.find('asset/mesh').attrib == ET.fromstring(TETRAHEDRON).attrib
    assert root.find('asset/material').get('name') == 'aluminum'
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.body_mass.sum() == pytest.approx(32.4)


@pytest.mark.parametrize('scale', ['2 3 4', '-2 3 4'])
def test_scaled_offset_mesh_volume(scale):
    mesh = ET.fromstring(TETRAHEDRON)
    vertices = np.array([float(v) for v in mesh.get('vertex').split()]).reshape(-1, 3)
    mesh.set('vertex', ' '.join(str(v) for v in (vertices + [25, -4, 10]).flat))
    mesh.set('scale', scale)
    assert _inline_mesh_volume(mesh) == pytest.approx(0.012 * 24)


@pytest.mark.parametrize('fixture', ['gyrefang.xml', 'undertow.xml'])
def test_user_meshes_match_mujoco_exact_volume_and_compile(fixture):
    config = ModelValidationConfig(constraints_yaml_path=REPO / 'configs/rules/rules.yaml', physics_mode='3d')
    source, result = sanitize_robot_xml((FIXTURES / fixture).read_text())
    assert result.passed
    xml, errors, _ = apply_material_properties(source, config.material_palette)
    assert errors == []
    root = ET.fromstring(xml)
    meshes = {m.get('name'): m for m in root.findall('asset/mesh')}
    for geom in root.findall('.//geom[@type="sdf"]'):
        mesh = meshes[geom.get('mesh')]
        # Independent oracle: MuJoCo infers mass at density 1 from exact mesh
        # inertia. Using type=mesh here avoids building another numerical SDF.
        oracle_xml = f'''<mujoco><asset>{ET.tostring(mesh, encoding='unicode')}</asset>
        <worldbody><body><freejoint/><geom type="mesh" mesh="{mesh.get('name')}"
        density="1"/></body></worldbody></mujoco>'''
        oracle = mujoco.MjModel.from_xml_string(oracle_xml)
        volume = float(oracle.body_mass.sum())
        assert _inline_mesh_volume(mesh) == pytest.approx(volume, rel=1e-5)
        density = config.material_palette[geom.get('material')]['density_kg_m3']
        assert float(geom.get('mass')) == pytest.approx(volume * density, abs=0.0002)
    processed = inject_motor_mass(xml, config.motor_mass_per_gear)
    model = mujoco.MjModel.from_xml_string(processed)
    assert model.ngeom == len(root.findall('.//geom'))
    assert np.all(np.isfinite(model.body_inertia))


def test_torus_hole_is_not_charged_as_solid_mass():
    mesh = ET.parse(FIXTURES / 'gyrefang.xml').find('asset/mesh[@name="traction_torus"]')
    exact = _inline_mesh_volume(mesh)
    mesh.set('inertia', 'convex')
    model = mujoco.MjModel.from_xml_string(f'''<mujoco><asset>{ET.tostring(mesh, encoding='unicode')}</asset>
    <worldbody><body><freejoint/><geom type="mesh" mesh="traction_torus" density="1"/>
    </body></worldbody></mujoco>''')
    assert exact < float(model.body_mass.sum()) * 0.7


@pytest.mark.parametrize('requested_mode', [None, 'convex', 'legacy', 'shell'])
def test_environment_owns_concave_mesh_inertia(requested_mode):
    mesh = ET.parse(FIXTURES / 'gyrefang.xml').find('asset/mesh[@name="traction_torus"]')
    mesh.set('name', 'surface')
    # Compile an independent exact-inertia reference with material density.
    mesh.set('inertia', 'exact')
    oracle = mujoco.MjModel.from_xml_string(f'''<mujoco><asset>{ET.tostring(mesh, encoding='unicode')}</asset>
      <worldbody><body><freejoint/><geom type="sdf" mesh="surface" density="2700"/>
      </body></worldbody></mujoco>''')
    if requested_mode is None:
        mesh.attrib.pop('inertia')
    else:
        mesh.set('inertia', requested_mode)
    source, result = sanitize_robot_xml(robot_xml(ET.tostring(mesh, encoding='unicode')))
    assert result.passed
    xml, errors, _ = apply_material_properties(source, PALETTE)
    assert not errors
    actual = mujoco.MjModel.from_xml_string(xml)
    np.testing.assert_allclose(actual.body_mass, oracle.body_mass, rtol=1e-5)
    np.testing.assert_allclose(actual.body_inertia, oracle.body_inertia, rtol=1e-5)
    np.testing.assert_allclose(actual.body_ipos, oracle.body_ipos, atol=1e-7)


@pytest.mark.parametrize('gtype', ['mesh', 'sdf'])
@pytest.mark.parametrize(('attribute', 'value', 'message'), [
    ('vertex', '', 'inline vertex and face'),
    ('vertex', '0 0 nope', 'numeric XYZ/index triples'),
    ('vertex', '0 0 nan  0.6 0 0  0 0.4 0  0 0 0.3', 'finite'),
    ('face', '0 2 1  0 1 3  0 3 2  1 2 9', 'outside the vertex array'),
    ('face', '0 2 1  0 1 3  0 3 2  0 1 3', 'closed with consistently oriented'),
    ('face', '0 1 2  0 3 1  0 2 3  1 3 2', 'positive enclosed volume'),
    ('scale', '1 0 1', 'nonzero'),
    ('scale', '1 1', 'three scale values'),
])
def test_invalid_surfaces_return_actionable_material_errors(attribute, value, message, gtype):
    mesh = ET.fromstring(TETRAHEDRON)
    mesh.set(attribute, value)
    _, errors, _ = apply_material_properties(robot_xml(ET.tostring(mesh, encoding='unicode'), gtype), PALETTE)
    assert len(errors) == 1
    assert 'surface_geom' in errors[0]
    assert message in errors[0]


@pytest.mark.parametrize('gtype', ['mesh', 'sdf'])
def test_missing_asset_is_reported_without_crashing(gtype):
    _, errors, _ = apply_material_properties(robot_xml('', gtype), PALETTE)
    assert len(errors) == 1
    assert "missing mesh asset 'surface'" in errors[0]


@pytest.mark.parametrize('gtype', ['mesh', 'sdf'])
def test_motor_mass_density_fallback_uses_mesh_volume(gtype):
    xml = f'''<mujoco><asset>{TETRAHEDRON}</asset><worldbody><body>
    <joint name="joint"/><geom type="{gtype}" mesh="surface" density="2700"/>
    </body></worldbody><actuator><motor joint="joint" gear="100"/></actuator></mujoco>'''
    geom = ET.fromstring(inject_motor_mass(xml, 0.01)).find('.//geom')
    assert float(geom.get('mass')) == pytest.approx(33.4)
    assert geom.get('density') is None


def test_scaled_mesh_instances_each_receive_material_mass():
    mesh = ET.fromstring(TETRAHEDRON)
    mesh.set('scale', '2 3 4')
    root = ET.fromstring(robot_xml(ET.tostring(mesh, encoding='unicode'), 'mesh'))
    body = root.find('.//body')
    ET.SubElement(body, 'geom', name='second', type='mesh', mesh='surface',
                  material='aluminum', pos='2 0 0')
    xml, errors, _ = apply_material_properties(ET.tostring(root, encoding='unicode'), PALETTE)
    assert errors == []
    masses = [float(g.get('mass')) for g in ET.fromstring(xml).iter('geom')]
    assert masses == pytest.approx([32.4 * 24, 32.4 * 24])
    model = mujoco.MjModel.from_xml_string(xml)
    assert float(model.body_mass.sum()) == pytest.approx(sum(masses))
