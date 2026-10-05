"""Compile real MJCF to check damping preservation and mass-rule boundaries."""
from pathlib import Path

import mujoco
import numpy as np
import pytest

from mjarena.design_shop.rules.mj_validators import (
    ModelValidationConfig,
    validate_control_constraints,
    validate_mass_constraints,
)
from mjarena.design_shop.utils import sanitize_robot_xml, validate_model_mass


RULES = Path(__file__).resolve().parents[1] / "configs/rules/rules.yaml"


def compile_robot(damping="0", root_joint='<freejoint name="root"/>', defaults=""):
    xml = f'''<mujoco>{defaults}<worldbody><body name="chassis">
      {root_joint}<geom size="0.3" mass="500"/>
      <body name="arm" pos="1 0 0"><joint name="internal" damping="{damping}"/>
        <geom size="0.1" mass="10"/>
      </body>
    </body></worldbody></mujoco>'''
    return mujoco.MjModel.from_xml_string(sanitize_robot_xml(xml, ()))


@pytest.fixture
def config():
    return ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")


@pytest.mark.parametrize("damping,passes", [(0, True), (60, True), (120, True),
                                             (600, True), (600.01, False)])
def test_scalar_damping_boundaries(config, damping, passes):
    model = compile_robot(str(damping))
    assert model.dof_damping[-1] == damping
    assert validate_control_constraints(model, config).passed == passes


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_invalid_compiled_damping_is_rejected(config, value):
    model = compile_robot()
    model.dof_damping[-1] = value
    assert not validate_control_constraints(model, config).passed


def test_nonlinear_damping_cannot_bypass_scalar_rule(config):
    model = compile_robot("0 1 0")
    assert not validate_control_constraints(model, config).passed


@pytest.mark.parametrize("root_joint", [
    '<freejoint name="root"/>',
    '<freejoint name="root" damping="12" frictionloss="13" stiffness="14"/>',
    '<joint name="root" type="free"/>',
    '<joint name="root" type="free" damping="12" frictionloss="13" stiffness="14"/>',
])
def test_root_zero_overrides_explicit_and_inherited_settings(root_joint):
    defaults = '<default><joint damping="120" frictionloss="3" stiffness="4"/></default>'
    # Removing the explicit internal setting tests actual inheritance.
    xml = f'''<mujoco>{defaults}<worldbody><body>{root_joint}
      <geom size="0.3" mass="500"/>
      <body><joint name="internal"/><geom size="0.1" mass="10"/></body>
    </body></worldbody></mujoco>'''
    model = mujoco.MjModel.from_xml_string(sanitize_robot_xml(xml, ()))
    np.testing.assert_array_equal(model.dof_damping[:6], 0)
    np.testing.assert_array_equal(model.dof_frictionloss[:6], 0)
    assert model.jnt_stiffness[0] == 0
    assert model.dof_damping[-1] == 120
    assert model.dof_frictionloss[-1] == 3
    assert model.jnt_stiffness[-1] == 4


def test_body_over_old_cap_passes_but_total_cap_still_applies(config):
    model = compile_robot()
    assert validate_mass_constraints(model, config).passed  # 500 kg chassis, 510 total
    assert validate_model_mass(model, max_total_mass=800)
    model.body_mass[1] = 800  # 810 total
    assert not validate_mass_constraints(model, config).passed
    assert not validate_model_mass(model, max_total_mass=800)
    model.body_mass[1] = 1  # 11 total
    assert not validate_mass_constraints(model, config).passed
