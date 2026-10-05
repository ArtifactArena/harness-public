"""Gravity is the arena's, and a robot may not constrain itself to the world.

Two MJCF surfaces the 2026-09-16 whole-branch review found open:

* body ``gravcomp=`` survived sanitization *and* composition. ``gravcomp="1"``
  is a weightless robot — it never contacts the outside floor, so `ring_out`
  can never fire against it; ``gravcomp="5"`` flies 906 m up in 10 s.
* ``<equality>`` passed validation and was deliberately carried into the match
  by ``_extract_robot_subtrees``. ``body2`` defaults to the world, so
  ``<equality><weld body1="chassis"/></equality>`` welds a robot to the planet:
  20 kN sideways moves it 3 cm where a clean robot is shoved 9.2 m.

The rulings: strip ``gravcomp`` and report it; reject ``<equality>`` at
validation. Both are re-checked when the match model is built, so a
preprocessed artifact cannot reintroduce them.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order)

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
import pytest

from mjarena.agents.runtime import BotRuntime
from mjarena.design_shop.rules.hardware_rules import FORBIDDEN_ROOT_TAGS
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.design_shop.utils import (
    UNSUPPORTED_STRUCTURE_ELEMENTS,
    sanitize_robot_xml_report,
    validate_structure_elements,
)
from mjarena.envs.sumo import SumoEnv, compose_sumo_model

ROOT = Path(__file__).resolve().parents[1]
ENV_XML = str(ROOT / "mjarena/assets/sumo_ring_env_studio_3d.xml")
CONFIG = ModelValidationConfig(ROOT / "configs/rules/rules.yaml", physics_mode="3d")

ROBOT = """<mujoco>{extra}<worldbody>
  <body name="chassis" pos="0 0 0.3"{bodyattr}>
   <freejoint name="root"/>
   <geom name="hull" type="box" size="0.3 0.25 0.08" material="aluminum"/>
   <body name="arm" pos="0.35 0 0"{armattr}><joint name="arm_j" type="hinge" axis="0 1 0"/>
     <geom name="armg" type="box" size="0.3 0.1 0.05" material="aluminum"/></body>
  </body></worldbody>
 <actuator><motor name="m1" joint="arm_j" gear="500"/></actuator></mujoco>"""


def robot(extra="", bodyattr="", armattr=""):
    return ROBOT.format(extra=extra, bodyattr=bodyattr, armattr=armattr)


def processed(xml):
    from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology

    result = validate_morphology(xml, CONFIG)
    assert result.passed, result.feedback
    return result.processed_xml


def composed(red_xml, directory):
    red = Path(directory) / "red.xml"
    blue = Path(directory) / "blue.xml"
    out = Path(directory) / "composed.xml"
    red.write_text(red_xml)
    blue.write_text(processed(robot()))
    compose_sumo_model(ENV_XML, str(red), str(blue), str(out),
                       randomize_spawn_3d=True, spawn_seed=1)
    return mujoco.MjModel.from_xml_path(str(out))


def match_model(xml):
    """A minimal composed-looking model, as the runtime backstops see one."""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    red = BotRuntime(model, data, lambda obs: {}, "red_")
    blue = BotRuntime(model, data, lambda obs: {}, "blue_")
    return model, data, red, blue


PREPROCESSED = """<mujoco><worldbody>
  <geom name="sumo_ring" type="cylinder" size="7.5 1"/>
  <body name="red_root"{redattr}><freejoint name="red_free"/><geom size=".2" mass="10"/></body>
  <body name="blue_root"><freejoint name="blue_free"/><geom size=".2" mass="10"/></body>
  </worldbody>{extra}</mujoco>"""


# --- C1: gravcomp -----------------------------------------------------------

@pytest.mark.parametrize("value", ["1", "5", "0.5"])
def test_gravcomp_is_removed_from_every_body_and_reported(value):
    xml, _, notes = sanitize_robot_xml_report(
        robot(bodyattr=f' gravcomp="{value}"', armattr=f' gravcomp="{value}"'),
        FORBIDDEN_ROOT_TAGS)
    root = ET.fromstring(xml)
    assert [body.get("gravcomp") for body in root.iter("body")] == [None, None]
    named = [note for note in notes if "gravcomp" in note]
    assert len(named) == 2
    assert "chassis" in " ".join(named) and "arm" in " ".join(named)


def test_gravcomp_zero_is_not_reported_as_a_change():
    _, _, notes = sanitize_robot_xml_report(robot(bodyattr=' gravcomp="0"'), FORBIDDEN_ROOT_TAGS)
    assert not [note for note in notes if "gravcomp" in note]


def test_the_composed_match_model_has_no_gravity_compensation():
    with tempfile.TemporaryDirectory() as directory:
        model = composed(processed(robot(bodyattr=' gravcomp="5"')), directory)
    assert float(np.max(np.asarray(model.body_gravcomp))) == 0.0


def test_the_match_refuses_a_preprocessed_model_that_compensates_gravity():
    model, data, red, blue = match_model(
        PREPROCESSED.format(redattr=' gravcomp="1"', extra=""))
    with pytest.raises(ValueError, match="gravcomp"):
        SumoEnv(model, data, "", red, blue, max_steps=1)


def test_a_clean_preprocessed_model_still_builds():
    model, data, red, blue = match_model(PREPROCESSED.format(redattr="", extra=""))
    SumoEnv(model, data, "", red, blue, max_steps=1)


def test_both_prompts_state_the_gravcomp_rule():
    clause = ("Gravity applies fully to every body: any `gravcomp` attribute is removed "
              "before validation and reported.")
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        assert clause in (ROOT / "configs/rules" / name).read_text(encoding="utf-8"), name


# --- C2: <equality> ---------------------------------------------------------

@pytest.mark.parametrize("constraint", [
    '<equality><weld name="pin" body1="chassis"/></equality>',
    '<equality><connect name="tether" body1="chassis" anchor="0 0 0"/></equality>',
    '<equality><joint name="gang" joint1="arm_j"/></equality>',
])
def test_equality_constraints_are_rejected_and_the_message_names_them(constraint):
    errors, details = validate_structure_elements(robot(extra=constraint))
    assert len(errors) == 1
    assert errors[0].startswith("Forbidden element <equality>")
    assert "weld" in errors[0] and "connect" in errors[0]
    assert details["forbidden_elements"] == ["equality"]


def test_equality_is_one_of_the_rejected_structure_elements():
    assert "equality" in UNSUPPORTED_STRUCTURE_ELEMENTS


def test_the_pipeline_step_fails_a_welded_robot():
    from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology

    result = validate_morphology(
        robot(extra='<equality><weld name="pin" body1="chassis"/></equality>'), CONFIG)
    assert not result.passed
    step = next(s for s in result.step_results if s.label == "Validate Structure Elements")
    assert not step.passed and "<equality>" in step.message


def test_the_match_refuses_a_composed_model_carrying_an_equality_constraint():
    model, data, red, blue = match_model(PREPROCESSED.format(
        redattr="", extra='<equality><weld name="pin" body1="red_root"/></equality>'))
    assert model.neq == 1
    with pytest.raises(ValueError, match="equality"):
        SumoEnv(model, data, "", red, blue, max_steps=1)


def test_composition_itself_contributes_no_equality_constraints():
    """The backstop is a plain `model.neq > 0`, which is only safe if the arena adds none."""
    with tempfile.TemporaryDirectory() as directory:
        model = composed(processed(robot()), directory)
    assert model.neq == 0


def test_both_prompts_state_the_equality_rule():
    clause = "`<equality>` constraints are not allowed; the validator rejects them."
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        assert clause in (ROOT / "configs/rules" / name).read_text(encoding="utf-8"), name
