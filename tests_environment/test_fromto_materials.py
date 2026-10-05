"""Endpoint-defined capsule/cylinder masses must match MuJoCo geometry."""

import math
import xml.etree.ElementTree as ET

import mujoco
import pytest

from mjarena.design_shop.utils import apply_material_properties


PALETTE = {'aluminum': {'density_kg_m3': 2700, 'friction': 0.45}}


def source(gtype, size, endpoints):
    return f'''<mujoco><worldbody><body><freejoint/>
    <geom name="arm" type="{gtype}" size="{size}" fromto="{endpoints}"
    material="aluminum"/></body></worldbody></mujoco>'''


@pytest.mark.parametrize('gtype', ['capsule', 'cylinder'])
@pytest.mark.parametrize('size', ['0.025', '0.025 99'])
def test_fromto_mass_uses_endpoint_length(gtype, size):
    raw = source(gtype, size, '1 2 3 1.3 2.4 3')
    xml, errors, _ = apply_material_properties(raw, PALETTE)
    assert errors == []
    expected_volume = math.pi * 0.025 ** 2 * 0.5
    if gtype == 'capsule':
        expected_volume += 4 / 3 * math.pi * 0.025 ** 3
    expected_mass = expected_volume * 2700
    geom = ET.fromstring(xml).find('.//geom')
    assert float(geom.get('mass')) == pytest.approx(expected_mass, abs=0.00005)
    assert geom.get('fromto') == '1 2 3 1.3 2.4 3'
    assert geom.get('size') == size
    oracle = ET.fromstring(raw)
    oracle_geom = oracle.find('.//geom')
    oracle_geom.attrib.pop('material')
    oracle_geom.set('density', '2700')
    model = mujoco.MjModel.from_xml_string(ET.tostring(oracle, encoding='unicode'))
    assert float(model.body_mass.sum()) == pytest.approx(expected_mass)


@pytest.mark.parametrize('endpoints', ['0 0 0', '0 0 0 1 0 bad', '0 0 0 nan 0 0', '0 0 0 0 0 0'])
def test_invalid_endpoints_produce_actionable_errors(endpoints):
    _, errors, _ = apply_material_properties(source('capsule', '0.025', endpoints), PALETTE)
    assert len(errors) == 1
    assert "geom 'arm'" in errors[0]
    assert 'fromto' in errors[0]
