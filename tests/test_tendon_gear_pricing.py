"""A fixed tendon's `coef` multiplies gear, so it is priced like gear.

Review finding C3. Motor mass was `Σ|gear| × motor_mass_per_gear`, read from the
`gear` attribute alone. A `<motor tendon="…">` on a `<fixed>` tendon applies
`gear × coef` to each of the tendon's joints, and nothing priced `coef`:

    direct motor gear=1000              total_mass=  172.00 kg   torque=    1000 N·m
    tendon coef=1000, motor gear=1      total_mass=  162.01 kg   torque=    1000 N·m
    tendon coef=100000, motor gear=1    total_mass=  162.01 kg   torque=  100000 N·m

The mass cap is the only economic constraint in the game, so that is 100 kN·m
for 0.01 kg. The ruling: the priced gear of a motor on a fixed tendon is
`|gear| × Σ|coef|` over that tendon's joints. Spatial tendons (sites and
wrapping geoms, no joint coefficients) and joint transmissions are unchanged.

The price is computed twice — from the XML at injection time and from the
compiled model at validation — and the two must agree.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order)

from pathlib import Path

import mujoco
import pytest

from mjarena.design_shop.rules.mj_validators import (
    ModelValidationConfig,
    effective_actuator_gear,
    validate_motor_mass,
)
from mjarena.design_shop.utils import inject_motor_mass

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ModelValidationConfig(ROOT / "configs/rules/rules.yaml", physics_mode="3d")
PER_GEAR = CONFIG.motor_mass_per_gear

# Explicit geom mass=, so the only thing that moves between variants is motor mass.
RAW = """<mujoco><worldbody>
  <body name="chassis" pos="0 0 0.3"><freejoint name="root"/>
   <geom name="hull" type="box" size="0.3 0.25 0.08" mass="100"/>
   <body name="arm" pos="0.35 0 0"><joint name="arm_j" type="hinge" axis="0 1 0"/>
     <geom name="armg" type="box" size="0.3 0.1 0.05" mass="10"/>
     <site name="tip" pos="0 0 0"/></body>
   <site name="hub" pos="0 0 0"/>
  </body></worldbody>{tendon}<actuator>{motor}</actuator></mujoco>"""

JOINT_MOTOR = '<motor name="m1" joint="arm_j" gear="{gear}"/>'
TENDON_MOTOR = '<motor name="m1" tendon="lever" gear="{gear}"/>'
FIXED = '<tendon><fixed name="lever"><joint joint="arm_j" coef="{coef}"/></fixed></tendon>'
SPATIAL = '<tendon><spatial name="lever"><site site="hub"/><site site="tip"/></spatial></tendon>'


def raw(motor, tendon=""):
    return RAW.format(motor=motor, tendon=tendon)


def injected_mass(xml):
    """Mass the injection adds, measured by compiling before and after."""
    before = mujoco.MjModel.from_xml_string(xml)
    after = mujoco.MjModel.from_xml_string(inject_motor_mass(xml, PER_GEAR))
    return float(after.body_mass.sum() - before.body_mass.sum()), after


def compiled_price(model):
    return sum(effective_actuator_gear(model, i) for i in range(model.nu)) * PER_GEAR


# --- the two pricings agree -------------------------------------------------

@pytest.mark.parametrize("xml, expected_gear", [
    (raw(JOINT_MOTOR.format(gear=1000)), 1000.0),
    (raw(TENDON_MOTOR.format(gear=1), FIXED.format(coef=100000)), 100000.0),
    (raw(TENDON_MOTOR.format(gear=7), FIXED.format(coef=-3)), 21.0),
    (raw(TENDON_MOTOR.format(gear=5), SPATIAL), 5.0),
])
def test_the_xml_price_and_the_compiled_price_agree(xml, expected_gear):
    mass, model = injected_mass(xml)
    assert mass == pytest.approx(expected_gear * PER_GEAR, rel=1e-6)
    assert compiled_price(model) == pytest.approx(mass, rel=1e-6)
    assert effective_actuator_gear(model, 0) == pytest.approx(expected_gear, rel=1e-6)


def test_a_differential_tendon_is_priced_on_the_sum_of_absolute_coefficients():
    """+1/−1 on two joints is two joints' worth of torque, not zero."""
    xml = RAW.format(
        motor=TENDON_MOTOR.format(gear=100),
        tendon='<tendon><fixed name="lever">'
               '<joint joint="arm_j" coef="1"/><joint joint="arm_j2" coef="-1"/>'
               '</fixed></tendon>',
    ).replace('<site name="hub" pos="0 0 0"/>',
              '<site name="hub" pos="0 0 0"/>'
              '<body name="arm2" pos="-0.35 0 0"><joint name="arm_j2" type="hinge" axis="0 1 0"/>'
              '<geom name="arm2g" type="box" size="0.3 0.1 0.05" mass="10"/></body>')
    mass, model = injected_mass(xml)
    assert mass == pytest.approx(200.0 * PER_GEAR, rel=1e-6)
    assert compiled_price(model) == pytest.approx(mass, rel=1e-6)


def test_a_joint_motor_is_unchanged_by_the_rule():
    mass, model = injected_mass(raw(JOINT_MOTOR.format(gear=250)))
    assert mass == pytest.approx(250.0 * PER_GEAR, rel=1e-6)
    assert effective_actuator_gear(model, 0) == pytest.approx(250.0, rel=1e-6)


# --- the exploit, end to end ------------------------------------------------

def _validate(xml):
    from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology

    return validate_morphology(xml, CONFIG)


PALETTE_ROBOT = """<mujoco><worldbody>
  <body name="chassis" pos="0 0 0.3"><freejoint name="root"/>
   <geom name="hull" type="box" size="0.3 0.25 0.08" material="aluminum"/>
   <body name="arm" pos="0.35 0 0"><joint name="arm_j" type="hinge" axis="0 1 0"/>
     <geom name="armg" type="box" size="0.3 0.1 0.05" material="aluminum"/></body>
  </body></worldbody>{tendon}<actuator>{motor}</actuator></mujoco>"""


def test_a_tendon_motor_carries_the_same_motor_mass_as_the_joint_equivalent():
    direct = _validate(PALETTE_ROBOT.format(motor=JOINT_MOTOR.format(gear=1000), tendon=""))
    levered = _validate(PALETTE_ROBOT.format(motor=TENDON_MOTOR.format(gear=1),
                                             tendon=FIXED.format(coef=1000)))
    assert direct.passed and levered.passed
    masses = []
    for result in (direct, levered):
        model = mujoco.MjModel.from_xml_string(result.processed_xml)
        masses.append(validate_motor_mass(model, CONFIG).details["motor_mass_kg"])
    assert masses[0] == pytest.approx(masses[1])
    assert masses[0] == pytest.approx(1000.0 * PER_GEAR)


def test_the_hundred_kilonewton_lever_now_fails_the_mass_cap():
    result = _validate(PALETTE_ROBOT.format(motor=TENDON_MOTOR.format(gear=1),
                                            tendon=FIXED.format(coef=100000)))
    assert not result.passed
    assert "exceeds maximum" in result.feedback


def test_both_prompts_state_the_tendon_pricing_rule():
    clause = ("For a motor on a fixed tendon, the priced gear is |gear| multiplied by "
              "the sum of the absolute joint coefficients of that tendon.")
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        assert clause in (ROOT / "configs/rules" / name).read_text(encoding="utf-8"), name
