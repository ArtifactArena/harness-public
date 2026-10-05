"""Integration checks for the contact and inactivity rules used by matches."""
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from mjarena.envs.utils import enforce_contact_settings
from mjarena.design_shop.utils import sanitize_robot_xml
from mjarena.runner.episode import run_match

FIXTURE = Path(__file__).resolve().parent / 'fixtures/arena_rules.xml'


def test_contact_rules_override_geoms_defaults_and_explicit_pairs():
    xml = FIXTURE.read_text().replace('<worldbody>', '<default><geom condim="1" friction="0.3 5 6"/></default><worldbody>')
    xml = sanitize_robot_xml(xml, ())
    root = ET.fromstring(xml)
    assert all(g.get('condim') == '6' for g in root.iter('geom'))
    model = mujoco.MjModel.from_xml_string(xml)
    enforce_contact_settings(model)
    np.testing.assert_array_equal(model.geom_condim, 6)
    np.testing.assert_allclose(model.geom_friction[:, 1:], np.tile([0.005, 0.0001], (model.ngeom, 1)))
    # Robot-defined contact pairs are ignored entirely.
    assert model.npair == 0
    np.testing.assert_array_equal(model.geom_contype, 1)
    np.testing.assert_array_equal(model.geom_conaffinity, 1)


@pytest.mark.parametrize('baseline,expected', [(False, 'tie'), (True, 'blue')])
def test_match_defaults_end_stalls_and_exempt_unactuated_baseline(tmp_path, baseline, expected):
    xml = FIXTURE.read_text()
    if baseline:
        xml = xml.replace('<motor name="blue_motor" joint="blue_hinge"/>', '')
    model_path = tmp_path / 'composed.xml'
    model_path.write_text(xml)
    record = run_match(composed_xml=model_path, red_policy_py=lambda obs: {'motor': 0.0},
                       blue_policy_py=lambda obs: {} if baseline else {'motor': 0.0},
                       out_dir=tmp_path, max_steps=1100, save_video=False, quiet=True,
                       use_gui=False, camera_mode='tracking')
    assert record.termination_reason == 'inactivity'
    assert record.winner == expected
    assert record.red_inactivity_timers[-1] == pytest.approx(10)
    assert record.blue_inactivity_timers[-1] == pytest.approx(0 if baseline else 10)
