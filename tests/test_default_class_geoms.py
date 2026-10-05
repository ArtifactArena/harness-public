"""Geom attributes inherited from a `<default>` class are the ones MuJoCo uses.

`geom.get("type", "sphere")` reads what the author typed, not what the compiler
resolves. MJCF lets a `<default class="…"><geom type="box" size="…"/></default>`
supply `type`, `size`, `fromto`, `mesh` and `material` to any geom that carries
`class="…"`, or that sits under a body with `childclass="…"`. Pricing such a
geom as a sphere writes a silently wrong `mass=` — and mass is what the 800 kg
cap and every collision read.

MuJoCo's own semantics, verified against 3.10.0:
  * an explicit `class=` on the geom REPLACES the enclosing `childclass`
    entirely — the childclass is not consulted for the attributes the class
    leaves unset (such a geom fails to compile rather than borrowing them);
  * a nested `<default class="child">` inherits its parent class's values;
  * `childclass` reaches nested bodies;
  * the unnamed top-level `<default>` is the main class and applies to a geom
    with no class of its own; a top-level `<default class="main">` is that
    same class, not a distinct or rejected one.
"""
import mjarena.core.unified_builder  # noqa: F401  (import order)

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from mjarena.design_shop.utils import (
    _effective_geom_attrs,
    _geom_attr_values,
    _geom_volume,
    apply_material_properties,
    inject_motor_mass,
    validate_material_attributes,
)

ROOT = Path(__file__).resolve().parents[1]
PALETTE = yaml.safe_load((ROOT / "configs/rules/materials_store.yaml").read_text())["materials"]


def _resolve(xml: str, geom_name: str):
    """(effective attribute values, inherited flags) for one named geom."""
    root = ET.fromstring(xml)
    geom = next(g for g in root.iter("geom") if g.get("name") == geom_name)
    entry = _effective_geom_attrs(root)[id(geom)]
    return _geom_attr_values(entry), {key: flag for key, (_, flag) in entry.items()}


def _volume(xml: str, geom_name: str) -> float:
    root = ET.fromstring(xml)
    geom = next(g for g in root.iter("geom") if g.get("name") == geom_name)
    attrs = _geom_attr_values(_effective_geom_attrs(root)[id(geom)])
    return _geom_volume(attrs, {m.get("name"): m for m in root.findall("asset/mesh")})


# (a) type from the geom's own class -------------------------------------------

TYPE_FROM_CLASS = """<mujoco>
  <default><default class="plate"><geom type="box"/></default></default>
  <worldbody><body name="chassis"><freejoint/>
    <geom name="deck" class="plate" size="0.5 0.5 0.5" material="steel"/>
  </body></worldbody>
</mujoco>"""


def test_type_from_a_class_default_is_a_box_not_a_sphere():
    values, inherited = _resolve(TYPE_FROM_CLASS, "deck")
    assert values["type"] == "box"
    assert inherited["type"] is True
    assert values["size"] == "0.5 0.5 0.5"
    assert inherited["size"] is False
    # 8 x 0.5^3 = 1.0 m^3, not the 0.524 m^3 a sphere of radius 0.5 would be.
    assert _volume(TYPE_FROM_CLASS, "deck") == pytest.approx(1.0)


# (b) type AND size from a body childclass -------------------------------------

def test_type_and_size_both_come_from_a_body_childclass():
    xml = """<mujoco>
      <default><default class="armour"><geom type="box" size="0.4 0.3 0.2"/></default></default>
      <worldbody><body name="chassis" childclass="armour"><freejoint/>
        <geom name="skirt" material="steel"/>
        <body name="turret"><geom name="cap" material="steel"/></body>
      </body></worldbody>
    </mujoco>"""
    values, inherited = _resolve(xml, "skirt")
    assert (values["type"], values["size"]) == ("box", "0.4 0.3 0.2")
    assert inherited["type"] and inherited["size"]
    assert _volume(xml, "skirt") == pytest.approx(8 * 0.4 * 0.3 * 0.2)
    # childclass reaches nested bodies too.
    assert _resolve(xml, "cap")[0]["type"] == "box"


# (c) class= replaces childclass; the childclass is not consulted ---------------

def test_an_explicit_class_replaces_the_enclosing_childclass():
    xml = """<mujoco>
      <default>
        <default class="a"><geom type="capsule" size="0.1 0.5"/></default>
        <default class="b"><geom type="box" size="0.6 0.6 0.6" material="steel"/></default>
      </default>
      <worldbody><body name="chassis" childclass="b"><freejoint/>
        <geom name="arm" class="a" material="foam"/>
      </body></worldbody>
    </mujoco>"""
    values, _ = _resolve(xml, "arm")
    assert values["type"] == "capsule"
    # Nothing at all comes from "b": not the size, not the material.
    assert values["size"] == "0.1 0.5"
    assert values["material"] == "foam"
    cylinder = math.pi * 0.1 ** 2 * 1.0
    sphere = (4.0 / 3.0) * math.pi * 0.1 ** 3
    assert _volume(xml, "arm") == pytest.approx(cylinder + sphere)


# (d) nested defaults: a child class inherits its parent ------------------------

def test_a_nested_default_inherits_its_parent_class():
    xml = """<mujoco>
      <default><default class="parent"><geom type="box" size="0.5 0.5 0.5" material="steel"/>
        <default class="child"><geom size="0.25 0.25 0.25"/></default>
      </default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="block" class="child"/>
      </body></worldbody>
    </mujoco>"""
    values, inherited = _resolve(xml, "block")
    assert values["type"] == "box"            # from the parent class
    assert values["size"] == "0.25 0.25 0.25"  # overridden by the child class
    assert values["material"] == "steel"       # from the parent class
    assert inherited["type"] and inherited["size"] and inherited["material"]
    assert _volume(xml, "block") == pytest.approx(8 * 0.25 ** 3)


def test_the_unnamed_main_default_applies_to_a_geom_with_no_class():
    xml = """<mujoco>
      <default><geom type="cylinder" size="0.2 0.5"/></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="drum" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    values, _ = _resolve(xml, "drum")
    assert (values["type"], values["size"]) == ("cylinder", "0.2 0.5")
    assert _volume(xml, "drum") == pytest.approx(math.pi * 0.2 ** 2 * 1.0)


def test_fromto_and_mesh_resolve_through_a_class_as_well():
    xml = """<mujoco>
      <asset><mesh name="hull" vertex="0 0 0  1 0 0  0 1 0  0 0 1"
                   face="0 2 1  0 1 3  0 3 2  1 2 3"/></asset>
      <default>
        <default class="strut"><geom type="capsule" size="0.05" fromto="0 0 0 0 0 1"/></default>
        <default class="shell"><geom type="sdf" mesh="hull"/></default>
      </default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="spar" class="strut" material="steel"/>
        <geom name="skin" class="shell" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    assert _resolve(xml, "spar")[0]["fromto"] == "0 0 0 0 0 1"
    # radius 0.05, axial length 1 from the endpoints: cylinder + one sphere.
    assert _volume(xml, "spar") == pytest.approx(math.pi * 0.05 ** 2 * 1.0
                                                 + (4.0 / 3.0) * math.pi * 0.05 ** 3)
    assert _resolve(xml, "skin")[0]["mesh"] == "hull"
    assert _volume(xml, "skin") == pytest.approx(1.0 / 6.0)


# (e) the geom's own attribute always wins -------------------------------------

def test_an_explicit_attribute_on_the_geom_beats_every_default():
    xml = """<mujoco>
      <default><geom type="box" size="0.5 0.5 0.5" material="steel"/>
        <default class="c"><geom type="ellipsoid"/></default>
      </default>
      <worldbody><body name="chassis" childclass="c"><freejoint/>
        <geom name="ball" type="sphere" size="0.5" material="foam"/>
      </body></worldbody>
    </mujoco>"""
    values, inherited = _resolve(xml, "ball")
    assert values["type"] == "sphere" and not inherited["type"]
    assert values["material"] == "foam" and not inherited["material"]
    assert _volume(xml, "ball") == pytest.approx((4.0 / 3.0) * math.pi * 0.5 ** 3)


def test_a_geom_that_nothing_types_is_mujocos_own_sphere():
    xml = """<mujoco><worldbody><body name="chassis"><freejoint/>
      <geom name="ball" size="0.5" material="foam"/>
    </body></worldbody></mujoco>"""
    values, inherited = _resolve(xml, "ball")
    assert values["type"] == "sphere"
    assert inherited["type"] is False


# (f) end to end through the real pipeline function ----------------------------

def test_apply_material_properties_prices_the_class_typed_box_as_a_box():
    out, errors, _ = apply_material_properties(TYPE_FROM_CLASS, PALETTE, default_material="foam")
    assert errors == []
    deck = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "deck")
    # 1.0 m^3 x 7800 kg/m^3. As a sphere it would have been 4084.07 kg.
    assert float(deck.get("mass")) == pytest.approx(1.0 * 7800.0)


def test_mujoco_itself_agrees_the_class_typed_geom_is_a_box():
    """The compiler is the authority on what the class resolved to."""
    import mujoco
    out, errors, _ = apply_material_properties(TYPE_FROM_CLASS, PALETTE, default_material="foam")
    assert errors == []
    model = mujoco.MjModel.from_xml_string(out)
    assert mujoco.mjtGeom(model.geom_type[0]).name == "mjGEOM_BOX"
    assert float(model.body_mass[model.geom_bodyid[0]]) == pytest.approx(7800.0)


def test_a_material_supplied_by_a_class_is_the_one_the_palette_applies():
    xml = """<mujoco>
      <default><default class="plate"><geom type="box" material="aluminum"/></default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="deck" class="plate" size="0.5 0.5 0.5"/>
      </body></worldbody>
    </mujoco>"""
    out, errors, info = apply_material_properties(xml, PALETTE, default_material="foam")
    assert errors == []
    assert info == []          # nothing was "missing" a material, so nothing was defaulted
    root = ET.fromstring(out)
    deck = next(g for g in root.iter("geom") if g.get("name") == "deck")
    # The class keeps supplying the material; foam was NOT stamped over it.
    assert deck.get("material") is None
    assert float(deck.get("mass")) == pytest.approx(1.0 * 2700.0)   # aluminum, not foam
    assert deck.get("friction").split()[0] == "0.45"
    # and its visual asset was injected, so material="aluminum" still resolves
    assert [m.get("name") for m in root.findall("asset/material")] == ["aluminum"]


# (g) a top-level <default class="main"> is the same class as unnamed -------

CLASS_MAIN_TOP_LEVEL = """<mujoco>
  <default class="main"><geom type="box" size="0.5 0.5 0.5"/></default>
  <worldbody><body name="chassis"><freejoint/>
    <geom name="g" material="steel"/>
  </body></worldbody>
</mujoco>"""


def test_effective_geom_attrs_resolves_top_level_class_main_to_box():
    values, _ = _resolve(CLASS_MAIN_TOP_LEVEL, "g")
    assert values["type"] == "box"
    assert values["size"] == "0.5 0.5 0.5"
    assert _volume(CLASS_MAIN_TOP_LEVEL, "g") == pytest.approx(1.0)


def test_apply_material_properties_prices_a_top_level_class_main_geom_as_a_box():
    out, errors, _ = apply_material_properties(CLASS_MAIN_TOP_LEVEL, PALETTE, default_material="foam")
    assert errors == []
    g = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "g")
    # 8 x 0.5^3 x 7800 kg/m^3. As the mispriced sphere fallback it would be
    # 4084.07 kg (and, with no size=, apply_material_properties would instead
    # reject it: "Cannot compute volume for geom 'g' (type='sphere')").
    assert float(g.get("mass")) == pytest.approx(1.0 * 7800.0)


def test_mujoco_itself_agrees_the_top_level_class_main_geom_is_a_box():
    """The compiler is the authority on what the class resolved to."""
    import mujoco
    out, errors, _ = apply_material_properties(CLASS_MAIN_TOP_LEVEL, PALETTE, default_material="foam")
    assert errors == []
    model = mujoco.MjModel.from_xml_string(out)
    assert mujoco.mjtGeom(model.geom_type[0]).name == "mjGEOM_BOX"
    assert float(model.body_mass[model.geom_bodyid[0]]) == pytest.approx(7800.0)


def test_explicit_class_main_on_a_geom_resolves_to_the_top_level_class():
    xml = """<mujoco>
      <default class="main"><geom type="box" size="0.5 0.5 0.5"/></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="g" class="main" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    values, _ = _resolve(xml, "g")
    assert values["type"] == "box"
    assert _volume(xml, "g") == pytest.approx(1.0)


def test_childclass_main_on_a_body_resolves_to_the_top_level_class():
    xml = """<mujoco>
      <default class="main"><geom type="box" size="0.5 0.5 0.5"/></default>
      <worldbody><body name="chassis" childclass="main"><freejoint/>
        <geom name="g" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    values, _ = _resolve(xml, "g")
    assert values["type"] == "box"
    assert _volume(xml, "g") == pytest.approx(1.0)


def test_the_volume_failure_message_names_the_inherited_type():
    xml = """<mujoco>
      <default><default class="shell"><geom type="sdf"/></default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="skin" class="shell" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    _, errors, _ = apply_material_properties(xml, PALETTE, default_material="foam")
    assert errors == ["Cannot compute volume for geom 'skin' (type='sdf', inherited from a "
                      "default class): sdf geom references missing mesh asset ''"]


# (h) mass=/density= supplied through a class are rejected like an inline one --
#
# rules.yaml line 63 / sampling_prompt.md line 382: "No mass=, density=, body
# mass=, or <inertial> on geoms." A `<default>` class that supplies mass= or
# density= reaches the exact same compiled result as writing it on the geom
# (verified against MuJoCo 3.10.0 below), so it is the same violation.

def test_mujoco_itself_applies_a_class_supplied_mass_and_density():
    """Global Constraint 5: verify against the compiler, not a belief about MJCF."""
    import mujoco

    mass_xml = """<mujoco>
      <default><default class="heavy"><geom mass="50"/></default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="g" class="heavy" type="box" size="0.1 0.1 0.1"/>
      </body></worldbody>
    </mujoco>"""
    model = mujoco.MjModel.from_xml_string(mass_xml)
    assert float(model.body_mass[model.geom_bodyid[0]]) == pytest.approx(50.0)

    density_xml = """<mujoco>
      <default><default class="dense"><geom density="2000"/></default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="g" class="dense" type="box" size="0.1 0.1 0.1"/>
      </body></worldbody>
    </mujoco>"""
    model = mujoco.MjModel.from_xml_string(density_xml)
    # 8 x 0.1^3 x 2000
    assert float(model.body_mass[model.geom_bodyid[0]]) == pytest.approx(8 * 0.1 ** 3 * 2000)


def test_a_class_supplied_mass_is_rejected_with_the_mass_error():
    xml = """<mujoco>
      <default><default class="heavy"><geom mass="50"/></default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="g" class="heavy" type="box" size="0.1 0.1 0.1" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    errors, _ = validate_material_attributes(xml, PALETTE, default_material="foam")
    assert errors == [
        "Geom 'g' has mass= attribute (inherited from a <default> class). "
        "Fix: remove mass= and use material= instead. "
        "Mass is computed automatically from volume x material density."
    ]


def test_a_class_supplied_density_is_rejected_with_the_density_error():
    xml = """<mujoco>
      <default><default class="dense"><geom density="2000"/></default></default>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="g" class="dense" type="box" size="0.1 0.1 0.1" material="steel"/>
      </body></worldbody>
    </mujoco>"""
    errors, _ = validate_material_attributes(xml, PALETTE, default_material="foam")
    assert errors == [
        "Geom 'g' has density= attribute (inherited from a <default> class). "
        "Fix: remove density= and use material= instead."
    ]


def test_an_inline_mass_is_still_rejected_unchanged():
    xml = """<mujoco>
      <worldbody><body name="chassis"><freejoint/>
        <geom name="g" type="box" size="0.1 0.1 0.1" material="steel" mass="50"/>
      </body></worldbody>
    </mujoco>"""
    errors, _ = validate_material_attributes(xml, PALETTE, default_material="foam")
    assert errors == [
        "Geom 'g' has mass= attribute. "
        "Fix: remove mass= and use material= instead. "
        "Mass is computed automatically from volume x material density."
    ]


# (i) inject_motor_mass itself sees class-supplied mass=/density= ---------------
#
# The pipeline-bypassing callers (mjarena/two_stage/artifact_loader.py,
# run_episode_viewer.py) call inject_motor_mass directly, without first
# running validate_material_attributes, so it must resolve a class-supplied
# mass=/density= on its own rather than relying on being upstream of the
# rejection above.

MOTOR_MASS_FROM_CLASS = """<mujoco>
  <default><default class="heavy"><geom mass="50"/></default></default>
  <worldbody>
    <body name="chassis"><freejoint/>
      <geom name="base" type="box" size="0.3 0.3 0.1"/>
      <body name="arm" pos="0.3 0 0">
        <joint name="hinge" type="hinge" axis="0 0 1"/>
        <geom name="g" class="heavy" type="box" size="0.1 0.1 0.1"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="m" joint="hinge" gear="2"/>
  </actuator>
</mujoco>"""


def test_inject_motor_mass_reads_a_class_supplied_mass():
    out = inject_motor_mass(MOTOR_MASS_FROM_CLASS, motor_mass_per_gear=1.0)
    geom = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "g")
    # existing mass 50 (from the "heavy" class, not the geom itself) + |gear| 2 x 1.0 kg/gear
    assert float(geom.get("mass")) == pytest.approx(52.0)
    import mujoco
    mujoco.MjModel.from_xml_string(out)   # the result still compiles


MOTOR_DENSITY_FROM_CLASS = """<mujoco>
  <default><default class="dense"><geom density="2000"/></default></default>
  <worldbody>
    <body name="chassis"><freejoint/>
      <geom name="base" type="box" size="0.3 0.3 0.1"/>
      <body name="arm" pos="0.3 0 0">
        <joint name="hinge" type="hinge" axis="0 0 1"/>
        <geom name="g" class="dense" type="box" size="0.1 0.1 0.1"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="m" joint="hinge" gear="2"/>
  </actuator>
</mujoco>"""


def test_inject_motor_mass_reads_a_class_supplied_density_without_crashing():
    """`density` lives on the "dense" class, not this geom's own attrib: the old
    `del geom.attrib['density']` would KeyError here. `.pop('density', None)`
    must not raise, and the volume x class-density mass must come out right.
    """
    out = inject_motor_mass(MOTOR_DENSITY_FROM_CLASS, motor_mass_per_gear=1.0)
    geom = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "g")
    # volume 8 x 0.1^3 = 0.008 m^3 x 2000 kg/m^3 = 16 kg, + |gear| 2 x 1.0 kg/gear
    assert float(geom.get("mass")) == pytest.approx(18.0)
    assert geom.get("density") is None   # nothing to remove from the geom itself; no crash
    import mujoco
    mujoco.MjModel.from_xml_string(out)   # the result still compiles


# Two motors sharing one geom must ACCUMULATE their mass contributions, not
# overwrite each other. `geom_attrs = _effective_geom_attrs(root)` is a
# snapshot taken once before the motor loop; if the mass/density reads inside
# the loop consult only that snapshot, the second motor to land on a shared
# geom reads the pre-injection value and clobbers the first motor's
# contribution instead of adding to it.

MOTOR_MASS_TWO_JOINTS_SHARE_A_GEOM = """<mujoco>
  <worldbody>
    <body name="chassis"><freejoint/>
      <geom name="base" type="box" size="0.3 0.3 0.1" mass="1"/>
      <body name="arm" pos="0.3 0 0">
        <joint name="hinge1" type="hinge" axis="0 0 1"/>
        <joint name="hinge2" type="hinge" axis="1 0 0"/>
        <geom name="g" type="box" size="0.1 0.1 0.1" mass="5"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="m1" joint="hinge1" gear="2"/>
    <motor name="m2" joint="hinge2" gear="3"/>
  </actuator>
</mujoco>"""


def test_two_motors_targeting_one_geom_accumulate_their_mass():
    """`g` (inline mass="5") is rigidly attached to both `hinge1` and `hinge2`;
    both motors' contributions land on it. |gear| 2 + |gear| 3, x 1.0 kg/gear,
    on top of the inline 5 kg: 5 + 2 + 3 = 10 kg, not 8 (the second motor
    overwriting instead of adding to the first).
    """
    out = inject_motor_mass(MOTOR_MASS_TWO_JOINTS_SHARE_A_GEOM, motor_mass_per_gear=1.0)
    geom = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "g")
    assert float(geom.get("mass")) == pytest.approx(10.0)
    import mujoco
    model = mujoco.MjModel.from_xml_string(out)   # the result still compiles
    # "g" is the sole geom on body "arm"; body_mass is a direct check on
    # what MuJoCo itself compiled from the injected geom mass=.
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "arm")
    assert float(model.body_mass[body_id]) == pytest.approx(10.0)


MOTOR_MASS_TWO_TENDONS_ON_ROOT_CLASS_DENSITY = """<mujoco>
  <default><default class="dense"><geom density="2000"/></default></default>
  <worldbody>
    <body name="chassis"><freejoint/>
      <geom name="base" class="dense" type="box" size="0.1 0.1 0.1"/>
      <body name="arm" pos="0.3 0 0">
        <joint name="hinge" type="hinge" axis="0 0 1"/>
        <geom name="arm_geom" type="box" size="0.05 0.05 0.05" mass="1"/>
      </body>
    </body>
  </worldbody>
  <tendon>
    <fixed name="t1"><joint joint="hinge" coef="1"/></fixed>
    <fixed name="t2"><joint joint="hinge" coef="1"/></fixed>
  </tendon>
  <actuator>
    <motor name="m1" tendon="t1" gear="2"/>
    <motor name="m2" tendon="t2" gear="3"/>
  </actuator>
</mujoco>"""


def test_two_tendon_motors_on_root_body_accumulate_with_class_density():
    """Both tendon motors mount on the root body (prompt line 328), landing on
    `base` (class "dense", density="2000", no mass=). `base` is a box of
    volume 8 x 0.1^3 = 0.008 m^3, so density x volume = 16 kg. + |gear| 2 and
    |gear| 3, x 1.0 kg/gear: 16 + 2 + 3 = 21 kg, not 19 (the second motor
    recomputing density x volume from scratch instead of adding to the mass
    the first motor already set).
    """
    out = inject_motor_mass(MOTOR_MASS_TWO_TENDONS_ON_ROOT_CLASS_DENSITY, motor_mass_per_gear=1.0)
    geom = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "base")
    assert float(geom.get("mass")) == pytest.approx(21.0)
    assert geom.get("density") is None
    import mujoco
    model = mujoco.MjModel.from_xml_string(out)   # the result still compiles
    # "base" is the sole geom on body "chassis"; body_mass is a direct check
    # on what MuJoCo itself compiled from the injected geom mass=.
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "chassis")
    assert float(model.body_mass[body_id]) == pytest.approx(21.0)


MOTOR_INLINE_DENSITY = """<mujoco>
  <worldbody>
    <body name="chassis"><freejoint/>
      <geom name="base" type="box" size="0.3 0.3 0.1" mass="1"/>
      <body name="arm" pos="0.3 0 0">
        <joint name="hinge" type="hinge" axis="0 0 1"/>
        <geom name="g" type="box" size="0.1 0.1 0.1" density="2000"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="m" joint="hinge" gear="2"/>
  </actuator>
</mujoco>"""


def test_an_inline_density_on_the_geom_itself_is_still_read_and_removed():
    """`g` carries its OWN density="2000" (not inherited from a class): the
    live read must still find it, price the volume x density mass from it,
    and remove it from the geom the same as the class-supplied case above.
    """
    out = inject_motor_mass(MOTOR_INLINE_DENSITY, motor_mass_per_gear=1.0)
    geom = next(g for g in ET.fromstring(out).iter("geom") if g.get("name") == "g")
    # volume 8 x 0.1^3 = 0.008 m^3 x 2000 kg/m^3 = 16 kg, + |gear| 2 x 1.0 kg/gear
    assert float(geom.get("mass")) == pytest.approx(18.0)
    assert geom.get("density") is None   # inline density= removed; mass= is now authoritative
    import mujoco
    mujoco.MjModel.from_xml_string(out)   # the result still compiles
