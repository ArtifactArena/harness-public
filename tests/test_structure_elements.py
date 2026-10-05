"""MJCF elements that hide, move or generate geometry are rejected.

Every geom walk in `design_shop/utils.py` is `root.iter("body")` ->
`body.findall("geom")`, so a geom nested in a `<frame>` is invisible to
`validate_material_attributes` and `apply_material_properties`: it draws no
"missing material=" error, gets no computed `mass=` and no palette friction,
and compiles at MuJoCo's default density. `<replicate>`, `<attach>`,
`<composite>` and `<flexcomp>` multiply or synthesise bodies the mass and size
checks never measured; `<include>` pulls in a file that does not exist.

The ruling is to REJECT, not to strip: removing a `<frame>` would silently move
the geometry it positions.

The same family, one level up: a robot's own `<compiler>` reaches the
validation compile but not composition (`_extract_robot_subtrees` keeps only
worldbody/actuator/sensor/asset/contact/equality/tendon), so
`settotalmass="100"` used to make an 1,684 kg robot weigh 100 kg for the mass
cap and its real mass in the match.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order)

import xml.etree.ElementTree as ET

import mujoco
import pytest
import yaml
from pathlib import Path

from mjarena.design_shop.rules.hardware_rules import (
    FORBIDDEN_ROOT_TAGS,
    validate_structure_elements,
)
from mjarena.design_shop.utils import (
    UNSUPPORTED_STRUCTURE_ELEMENTS,
    apply_material_properties,
    sanitize_robot_xml_report,
    validate_material_attributes,
    validate_structure_elements as _validate_structure_elements,
)

ROOT = Path(__file__).resolve().parents[1]
PALETTE = yaml.safe_load((ROOT / "configs/rules/materials_store.yaml").read_text())["materials"]

CLEAN = """<mujoco>
  <compiler angle="radian"/>
  <worldbody>
    <body name="chassis" pos="0 0 0.3">
      <freejoint name="root"/>
      <geom name="deck" type="box" size="0.3 0.3 0.1" material="steel"/>
      <body name="arm" pos="0 0 0.2"><joint name="hinge" axis="0 1 0"/>
        <geom name="blade" type="box" size="0.2 0.05 0.02" material="aluminum"/>
      </body>
    </body>
  </worldbody>
  <actuator><motor name="m" joint="hinge" gear="50"/></actuator>
</mujoco>"""

# A 0.6 m steel box hidden from the material pipeline by one <frame>.
FRAMED = CLEAN.replace(
    '<geom name="deck" type="box" size="0.3 0.3 0.1" material="steel"/>',
    '<frame pos="0 0 0.2">'
    '<geom name="deck" type="box" size="0.3 0.3 0.1" material="steel"/>'
    '</frame>',
)


def test_a_geom_inside_a_frame_escapes_the_material_pipeline():
    """The defect this validator exists for: no error, and no mass= from the palette."""
    errors, details = validate_material_attributes(FRAMED, PALETTE, default_material=None)
    assert errors == [] and details["geoms_checked"] == 1   # 'deck' was never looked at
    priced, apply_errors, _ = apply_material_properties(FRAMED, PALETTE, default_material=None)
    assert apply_errors == []
    root = ET.fromstring(priced)
    assert root.find(".//frame/geom").get("mass") is None            # steel, priced by nobody
    assert root.find(".//body[@name='arm']/geom").get("mass") is not None


def test_a_framed_geom_is_rejected_and_the_message_names_the_element():
    errors, details = _validate_structure_elements(FRAMED)
    assert len(errors) == 1
    assert errors[0].startswith("Forbidden element <frame>")
    assert "pos=" in errors[0]                      # says where to put the placement instead
    assert details["forbidden_elements"] == ["frame"]


@pytest.mark.parametrize("tag", list(UNSUPPORTED_STRUCTURE_ELEMENTS))
def test_every_listed_element_is_rejected_wherever_it_sits(tag):
    for xml in (CLEAN.replace("<worldbody>", f"<{tag}/><worldbody>"),
                CLEAN.replace('<freejoint name="root"/>', f'<freejoint name="root"/><{tag}/>')):
        errors, details = _validate_structure_elements(xml)
        assert errors and f"<{tag}>" in errors[0], tag
        assert details["forbidden_elements"] == [tag]


def test_repeated_elements_are_one_message_with_the_count():
    errors, _ = _validate_structure_elements(FRAMED.replace("</worldbody>", "<frame/></worldbody>"))
    assert len(errors) == 1 and "2 occurrences" in errors[0]


def test_a_robot_without_them_is_unaffected():
    errors, details = _validate_structure_elements(CLEAN)
    assert errors == [] and details["forbidden_elements"] == []
    xml, result = validate_structure_elements(CLEAN)
    assert result.passed and xml == CLEAN


def test_the_pipeline_step_fails_the_framed_robot():
    from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
    from mjarena.design_shop.rules.mj_validators import ModelValidationConfig

    config = ModelValidationConfig(ROOT / "configs/rules/rules.yaml", physics_mode="3d")
    result = validate_morphology(FRAMED, config)
    assert not result.passed
    step = next(s for s in result.step_results if s.label == "Validate Structure Elements")
    assert not step.passed and "<frame>" in step.message
    assert validate_morphology(CLEAN, config).step_results[2].passed


def test_both_prompts_state_the_rule():
    clause = ("Do not use `<frame>`, `<replicate>`, `<attach>`, `<composite>`, `<flexcomp>`, "
              "or `<include>` elements; the validator rejects them.")
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        assert clause in (ROOT / "configs/rules" / name).read_text(encoding="utf-8"), name


# --- the same family: <compiler> is the environment's, not the robot's --------

def test_settotalmass_cannot_shrink_a_robot_past_the_mass_cap():
    heavy = CLEAN.replace('<compiler angle="radian"/>', '<compiler settotalmass="100"/>')
    raw = mujoco.MjModel.from_xml_string(heavy.replace(' material="steel"', ' density="7800"')
                                              .replace(' material="aluminum"', ' density="2700"'))
    assert raw.body_mass.sum() == pytest.approx(100.0)          # the exploit, before sanitization
    xml, _, notes = sanitize_robot_xml_report(heavy, FORBIDDEN_ROOT_TAGS)
    model = mujoco.MjModel.from_xml_string(xml.replace(' material="steel"', ' density="7800"')
                                              .replace(' material="aluminum"', ' density="2700"'))
    assert model.body_mass.sum() > 250.0
    assert any("settotalmass=" in note and "<compiler>" in note for note in notes)


def test_the_compiler_keeps_only_the_environments_own_settings():
    authored = CLEAN.replace(
        '<compiler angle="radian"/>',
        '<compiler angle="degree" eulerseq="zyx" inertiafromgeom="true" meshdir="/tmp"/>')
    xml, _, notes = sanitize_robot_xml_report(authored, FORBIDDEN_ROOT_TAGS)
    compiler = ET.fromstring(xml).find("compiler")
    assert compiler.attrib == {"angle": "radian"}
    dropped = [note for note in notes if "<compiler>" in note]
    assert len(dropped) == 1
    for attr in ("eulerseq=", "inertiafromgeom=", "meshdir="):
        assert attr in dropped[0]


def test_a_rewritten_compiler_angle_is_reported():
    """`angle="degree"` is not dropped, it is reinterpreted: every euler and joint
    range in the file changes by 57x. Silence there is a different robot."""
    authored = CLEAN.replace('<compiler angle="radian"/>', '<compiler angle="degree"/>')
    xml, _, notes = sanitize_robot_xml_report(authored, FORBIDDEN_ROOT_TAGS)
    assert ET.fromstring(xml).find("compiler").attrib == {"angle": "radian"}
    rewritten = [note for note in notes if "angle=" in note]
    assert len(rewritten) == 1
    assert "degree" in rewritten[0] and "interpreted as radians" in rewritten[0]


def test_an_authored_radian_compiler_is_not_reported():
    _, _, notes = sanitize_robot_xml_report(CLEAN, FORBIDDEN_ROOT_TAGS)
    assert not [note for note in notes if "angle=" in note]


def test_both_prompts_state_the_compiler_rule():
    clause = "Any other `<compiler>` attribute in your XML is removed before validation and reported."
    for name in ("autoresearch_prompt.md", "sampling_prompt.md"):
        assert clause in (ROOT / "configs/rules" / name).read_text(encoding="utf-8"), name
