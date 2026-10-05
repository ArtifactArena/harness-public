"""`<pulley>` is the unpriced force multiplier that `coef` was.

Follow-up 3 re-review, D1. A motor on a *fixed* tendon is priced on
`|gear| x sum|coef|` since `255845f9`, but a motor on a *spatial* tendon is
priced on plain `|gear|` — correct, because the force it applies is a force
along the tendon and the lever arm is geometry the robot has to carry. A
`<pulley divisor="d"/>` divides the tendon's length coordinate by `d`, which
multiplies the force by `1/d` for the same gear, and `d` is unbounded below:
on the reviewer's robot, 10 kg of motor mass bought 325 N*m through a plain
spatial tendon, 32.5 kN*m with `divisor="0.01"` and 3.25 MN*m with
`divisor="0.0001"`.

The ruling is to reject the element at validation, the same as `<equality>`.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order)

from pathlib import Path

import yaml

from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
from mjarena.design_shop.rules.hardware_rules import validate_structure_elements
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.design_shop.utils import UNSUPPORTED_STRUCTURE_ELEMENTS

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "configs/rules/rules.yaml"

# The reviewer's robot (scratchpad/rr_pulley.py), with the tendon interpolated.
BASE = """<mujoco>
 <worldbody>
  <body name="chassis" pos="0 0 0.3">
   <freejoint name="root"/>
   <geom name="hull" type="box" size="0.3 0.25 0.08" material="aluminum"/>
   <site name="a1" pos="0 0 0.4"/>
   <site name="a2" pos="0.1 0 0.4"/>
   <body name="arm" pos="0.5 0 0">
     <joint name="arm_j" type="hinge" axis="0 1 0"/>
     <geom name="armg" type="box" size="0.3 0.1 0.05" material="aluminum"/>
     <site name="b1" pos="0.2 0 0.3"/>
   </body>
  </body>
 </worldbody>
 <tendon>{tendon}</tendon>
 <actuator><motor name="m1" tendon="sp" gear="1000"/></actuator>
</mujoco>"""

PLAIN_SPATIAL = '<spatial name="sp"><site site="a1"/><site site="b1"/></spatial>'
PULLEY = (
    '<spatial name="sp"><site site="a1"/><site site="a2"/>'
    '<pulley divisor="0.0001"/><site site="a1"/><site site="b1"/></spatial>'
)


def _config():
    return ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")


def test_pulley_is_one_of_the_rejected_structure_elements():
    assert "pulley" in UNSUPPORTED_STRUCTURE_ELEMENTS


def test_the_reviewers_pulley_robot_is_rejected_by_the_pipeline_step():
    xml, result = validate_structure_elements(BASE.format(tendon=PULLEY))
    assert not result.passed
    assert "pulley" in result.message.lower()


def test_the_reviewers_pulley_robot_is_rejected_by_morphology_validation():
    result = validate_morphology(BASE.format(tendon=PULLEY), _config())
    assert not result.passed
    assert "pulley" in result.feedback.lower()


def test_the_same_robot_without_the_pulley_still_validates():
    result = validate_morphology(BASE.format(tendon=PLAIN_SPATIAL), _config())
    assert result.passed, result.feedback


def test_a_pulley_anywhere_in_the_file_is_found():
    """The walk is `root.iter()`, so nesting does not hide it."""
    nested = BASE.format(tendon=PLAIN_SPATIAL).replace(
        "<tendon>", '<default><pulley divisor="0.1"/></default><tendon>')
    _xml, result = validate_structure_elements(nested)
    assert not result.passed
    assert "pulley" in result.message.lower()


def test_the_pass_message_lists_pulley():
    _xml, result = validate_structure_elements(BASE.format(tendon=PLAIN_SPATIAL))
    assert result.passed
    assert "pulley" in result.message.lower()


def test_both_prompts_state_the_pulley_rule_and_the_spatial_tendon_price():
    clauses = (
        "`<pulley>` elements are not allowed either.",
        "A motor on a spatial tendon is priced at |gear|, the force it applies "
        "along the tendon.",
    )
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        text = (ROOT / "configs/rules" / name).read_text(encoding="utf-8")
        for clause in clauses:
            assert clause in text, (name, clause)


def test_neither_prompt_still_offers_pulley_branching():
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        text = (ROOT / "configs/rules" / name).read_text(encoding="utf-8")
        assert "branch using" not in text, name


def test_the_materials_palette_is_unchanged_by_this_wave():
    """Guards the fixture above: `aluminum` must stay in the palette."""
    palette = yaml.safe_load((ROOT / "configs/rules/materials_store.yaml").read_text())
    assert "aluminum" in palette["materials"]
