"""
Design shop utilities — XML processing, validation helpers, config loading.

Moved from mjarena.agents.dspy_programs.verifiers.utils.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import mujoco
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Color palette for per-thread prefixes in parallel builds
_THREAD_COLORS = [
    "\033[36m",   # cyan
    "\033[35m",   # magenta
    "\033[33m",   # yellow
    "\033[34m",   # blue
    "\033[32m",   # green
    "\033[93m",   # bright yellow
]
_RESET = "\033[0m"


def _thread_log(msg: str) -> None:
    """Print with [thread_name] prefix in a consistent color."""
    if os.environ.get("MJARENA_SUPPRESS_THREAD_LOGS") == "1":
        return
    name = threading.current_thread().name
    if name == "MainThread":
        print(msg)
    else:
        color = _THREAD_COLORS[hash(name) % len(_THREAD_COLORS)]
        print(f"{color}[{name}]{_RESET} {msg}")


# =============================================================================
# Content Detection
# =============================================================================

def looks_like_xml(text: str) -> bool:
    """Check if text appears to be valid MJCF XML content."""
    stripped = text.lstrip()
    return stripped.startswith("<") and ("<mujoco" in stripped.splitlines()[0] or "<mujoco" in stripped[:500])


def looks_like_python_builder(text: str) -> bool:
    """Check if text appears to be a robot builder Python script."""
    return "def build_robot" in text and "UnimalBuilder" in text


# =============================================================================
# XML Processing
# =============================================================================

def save_xml(text: str, out_path: Path) -> None:
    """Save XML content to file, creating parent directories as needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")


def sanitize_robot_xml(text: str, forbidden_tags: Iterable[str]) -> str:
    """Remove forbidden root-level elements and joint damping (see sanitize_robot_xml_report)."""
    return sanitize_robot_xml_report(text, forbidden_tags)[0]


# Explicit values prevent robot defaults or arena defaults from changing these
# properties. Sliding friction is assigned separately from the material palette.
ROBOT_COLLISION_SETTINGS = {
    "contype": "1", "conaffinity": "1", "condim": "6", "priority": "2",
    "solmix": "1", "solref": "0.02 1", "solimp": "0.9 0.95 0.001 0.5 2",
    "margin": "0", "gap": "0",
}


def normalize_robot_collision_settings(root, *, strip_friction: bool = False) -> List[str]:
    """Ignore robot collision overrides, including defaults and contact blocks.

    Accepts either ElementTree or lxml elements. During authoring validation,
    strip friction before material assignment. During match assembly, retain
    the already assigned material sliding friction and motor/geometry masses.
    This function must only be applied to robot subtrees, never the arena.
    """
    ignored = set()
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag in ("contact", "pair", "exclude"):
                ignored.add(f"<{child.tag}>")
                parent.remove(child)
    for geom in root.iter("geom"):
        if geom.get("geom") is not None:  # Spatial tendon wrapping reference.
            continue
        for attr, value in ROBOT_COLLISION_SETTINGS.items():
            if geom.get(attr) is not None:
                ignored.add(attr)
            geom.set(attr, value)
        if strip_friction and geom.get("friction") is not None:
            ignored.add("friction")
            del geom.attrib["friction"]
        # The palette supplies sliding friction later during validation.
        sliding = geom.get("friction", "1").split()[0]
        geom.set("friction", f"{sliding} 0.005 0.0001")
    return sorted(ignored)


def sanitize_robot_xml_report(text: str, forbidden_tags: Iterable[str]) -> tuple[str, list[str], list[str]]:
    """
    Remove forbidden XML elements from robot MJCF.

    Args:
        text: Raw MJCF XML content
        forbidden_tags: XML tags to remove from the root level

    Returns:
        Sanitized XML content with forbidden tags removed
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Failed to parse MJCF XML: {exc}") from exc

    forbidden = {tag.lower() for tag in forbidden_tags}
    removed: list[str] = []
    for child in list(root):
        tag = child.tag.lower()
        if tag in forbidden:
            root.remove(child)
            removed.append(child.tag)

    if removed:
        _thread_log(f"[INFO] Removed global MJCF elements from robot XML: {sorted(set(removed))}")

    notes: list[str] = []
    # 1. units and mesh inertia are environment-owned. Every other <compiler>
    #    attribute goes with them: composition builds the match from the ARENA's
    #    <compiler> (`_extract_robot_subtrees` never carries the robot's over), so
    #    an authored one would only change the model the validators measure —
    #    `settotalmass="100"` alone rewrites a robot's compiled total mass and
    #    walks it past the mass cap while the match weighs the real thing.
    compilers = root.findall("compiler")
    if not compilers:
        compilers = [ET.SubElement(root, "compiler")]
    dropped_compiler_attrs = sorted({a for c in compilers for a in c.attrib if a != "angle"})
    authored_angles = {c.get("angle") for c in compilers if c.get("angle") not in (None, "radian")}
    for extra in compilers[1:]:
        root.remove(extra)
    compiler = compilers[0]
    compiler.attrib.clear()
    compiler.set("angle", "radian")
    if dropped_compiler_attrs:
        notes.append(
            "<compiler> attributes removed ("
            + ", ".join(a + "=" for a in dropped_compiler_attrs)
            + '): the arena owns the compiler, which sets angle="radian" and mesh inertia="exact".'
        )
    for authored in sorted(authored_angles):
        # Silently rewriting angle="degree" reinterprets every euler and joint
        # range by 57x, which is a different robot from the one that was written.
        notes.append(
            f"compiler angle='{authored}' replaced by the arena's angle='radian'; "
            "all angles in your XML are interpreted as radians."
        )
    for mesh in root.findall("asset/mesh"):
        mesh.set("inertia", "exact")
    # 2. <asset> may only carry inline meshes; palette materials are injected later
    asset = root.find("asset")
    if asset is not None:
        for child in list(asset):
            if child.tag != "mesh":
                notes.append(f"<asset><{child.tag}> removed (only inline <mesh> definitions are allowed)")
                asset.remove(child)
    # 3. armature is environment-owned everywhere (joints, motors, tendons, defaults)
    for elem in root.iter():
        if elem.tag in ("joint", "motor", "general", "spatial", "fixed") and not (
            elem.tag == "joint" and any(elem.get(k) for k in ("joint", "joint1", "joint2"))):
            if elem.get("armature") not in (None, "0"):
                notes.append(f"{elem.tag} '{elem.get('name', '(unnamed)')}': armature= ignored (fixed at 0)")
            elem.set("armature", "0")
        elif elem.tag == "tendon" and elem.get("armature") is not None:
            elem.set("armature", "0")
    # 4. root joint carries no passive terms: explicit 0 beats inherited defaults
    worldbody = root.find("worldbody")
    if worldbody is not None:
        for body in worldbody.findall("body"):
            for joint in body:
                if joint.tag not in ("joint", "freejoint"):
                    continue
                present = [a for a in ("damping", "frictionloss", "stiffness", "armature") if joint.get(a) not in (None, "0")]
                for attr in ("damping", "frictionloss", "stiffness", "armature"):
                    if joint.tag == "freejoint":
                        joint.attrib.pop(attr, None)   # freejoint ignores <default>; attrs are simply removed
                    else:
                        joint.set(attr, "0")
                if joint.tag == "joint":
                    joint.set("springdamper", "0 0")
                if present:
                    notes.append(f"ROOT joint '{joint.get('name', '(unnamed)')}': {', '.join(a + '=' for a in present)} removed automatically")
    # 5. collision settings are environment-owned (friction is re-assigned from the palette later)
    ignored = normalize_robot_collision_settings(root, strip_friction=True)
    if ignored:
        notes.append("Ignored environment-owned collision settings: " + ", ".join(ignored))
    # 6. gravity is the arena's. MuJoCo's per-body `gravcomp` cancels a body's own
    #    weight (and above 1 pushes it upward): gravcomp="1" is a robot that never
    #    reaches the floor below the platform, so `ring_out` can never fire against
    #    it, and gravcomp="5" leaves the arena entirely. Removed everywhere, so a
    #    <default> entry cannot reintroduce it either.
    for elem in root.iter():
        if elem.get("gravcomp") is None:
            continue
        try:
            compensated = float(elem.get("gravcomp")) != 0.0
        except ValueError:
            compensated = True
        if compensated:
            notes.append(
                f"{elem.tag} '{elem.get('name', '(unnamed)')}': gravcomp= removed "
                "(gravity applies fully to every body)"
            )
        del elem.attrib["gravcomp"]
    _removed_tags, _stripped_damping = sorted(set(removed)), notes

    # Strip description= from all elements — useful for LLM design reasoning
    # but MuJoCo's parser rejects unknown attributes.
    for elem in root.iter():
        if elem.get("description") is not None:
            del elem.attrib["description"]

    return ET.tostring(root, encoding="unicode"), _removed_tags, _stripped_damping


# MJCF elements that hide, move, duplicate or synthesise geometry. Every geom
# walk in this file is `root.iter("body")` -> `body.findall("geom")`, so a geom
# nested in a <frame> is invisible to validate_material_attributes and
# apply_material_properties: no "missing material=" error, no mass= computed
# from the palette and no palette friction — it compiles at MuJoCo's default
# density. <replicate>, <attach>, <composite> and <flexcomp> multiply or
# synthesise bodies after the mass and size checks have measured the XML, and
# <include> points at a file the robot does not ship.
#
# <equality> is here for a different reason: composition deliberately carries a
# robot's constraints into the match (_extract_robot_subtrees), `body2` defaults
# to the world, and no validator inspects constraints — so one <weld> or
# <connect> bolts the robot to the planet and 20 kN of shove moves it 3 cm.
#
# <pulley> is a third reason: it is the unpriced force multiplier that fixed
# tendon `coef` was. A <pulley divisor="d"/> divides the spatial tendon's length
# coordinate by d, so the same |gear| applies 1/d times the force, and d is
# unbounded below — 10 kg of motor mass bought 325 N*m through a plain spatial
# tendon and 3.25 MN*m with divisor="0.0001".
#
# Rejected, never stripped: removing a <frame> would silently move the geometry
# it positions, which is a different robot from the one the model wrote.
UNSUPPORTED_STRUCTURE_ELEMENTS = (
    "frame", "replicate", "attach", "composite", "flexcomp", "include", "equality",
    "pulley",
)

_GEOMETRY_PLACEMENT_FIX = (
    ": not accepted anywhere in the robot XML. Fix: remove it and set pos= and the "
    "orientation attribute on the bodies and geoms themselves, writing every body and "
    "geom out in this file. A geom placed by one of these elements is never seen by the "
    "material, mass and size checks."
)
_STRUCTURE_ELEMENT_FIX = {
    "equality": (
        ": equality constraints (weld, connect, joint, distance, tendon) are not allowed "
        "anywhere in the robot XML. Fix: remove the <equality> block and build the "
        "mechanism from bodies, joints and tendons. body2 defaults to the world, so an "
        "equality constraint anchors the robot to the arena itself."
    ),
    "pulley": (
        ": pulleys are not allowed in a tendon. Fix: remove the <pulley> element and "
        "route the spatial tendon through sites and wrapping geoms only. A pulley's "
        "divisor= divides the tendon-length coordinate, so it multiplies the force a "
        "motor applies through the tendon without adding any motor mass."
    ),
}


def validate_structure_elements(xml_string: str) -> Tuple[List[str], dict]:
    """Reject MJCF elements that place geometry the geom walks never reach.

    Args:
        xml_string: MJCF XML content

    Returns:
        Tuple of (errors_list, details_dict)
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        return [f"Failed to parse XML: {exc}"], {}

    counts: Dict[str, int] = {}
    for elem in root.iter():
        tag = elem.tag.lower() if isinstance(elem.tag, str) else ""
        if tag in UNSUPPORTED_STRUCTURE_ELEMENTS:
            counts[tag] = counts[tag] + 1 if tag in counts else 1

    found = [tag for tag in UNSUPPORTED_STRUCTURE_ELEMENTS if tag in counts]
    errors = [
        f"Forbidden element <{tag}>"
        + (f" ({counts[tag]} occurrences)" if counts[tag] > 1 else "")
        + (_STRUCTURE_ELEMENT_FIX[tag] if tag in _STRUCTURE_ELEMENT_FIX
           else _GEOMETRY_PLACEMENT_FIX)
        for tag in found
    ]
    return errors, {"forbidden_elements": found}


def validate_passive_mechanisms(
    model: mujoco.MjModel, max_damping: float = 600.0,
    max_frictionloss: float = 600.0,
) -> List[str]:
    """Check each spring at qpos0, before gravity/contact settling can load it.

    Check individual extensions, not summed generalized forces: opposing
    preloaded springs can cancel their forces while retaining stored energy.
    """
    errors: List[str] = []
    for label, values in (
        ("Joint frictionloss", model.dof_frictionloss),
        ("Tendon frictionloss", model.tendon_frictionloss),
    ):
        values = np.asarray(values)
        if not np.all(np.isfinite(values)) or np.any(values < 0) or np.any(values > max_frictionloss):
            errors.append(f"{label} must be finite and between 0 and {max_frictionloss:g}")
    for label, linear, polynomial in (
        ("Joint stiffness", model.jnt_stiffness, getattr(model, "jnt_stiffnesspoly", [])),
        ("Tendon stiffness", model.tendon_stiffness, getattr(model, "tendon_stiffnesspoly", [])),
    ):
        if not np.all(np.isfinite(linear)) or np.any(np.asarray(linear) < 0):
            errors.append(f"{label} must be finite and nonnegative")
        if np.any(np.asarray(polynomial) != 0):
            errors.append(f"{label} must be scalar; nonlinear spring coefficients must be zero")

    damping = np.asarray(model.tendon_damping)
    if not np.all(np.isfinite(damping)) or np.any(damping < 0) or np.any(damping > max_damping):
        errors.append(f"Tendon damping must be finite and between 0 and {max_damping:g}")
    if np.any(np.asarray(getattr(model, "tendon_dampingpoly", [])) != 0):
        errors.append("Use scalar linear tendon damping; nonlinear damping coefficients must be zero")

    for jid in range(model.njnt):
        if not model.jnt_stiffness[jid] > 0:
            continue
        adr = int(model.jnt_qposadr[jid])
        kind = int(model.jnt_type[jid])
        if kind == int(mujoco.mjtJoint.mjJNT_BALL):
            start = np.asarray(model.qpos0[adr:adr + 4])
            rest = np.asarray(model.qpos_spring[adr:adr + 4])
            unloaded = min(np.linalg.norm(start - rest), np.linalg.norm(start + rest)) <= 1e-10
        elif kind == int(mujoco.mjtJoint.mjJNT_FREE):
            # Root springs are removed by sanitization.
            unloaded = False
        else:
            unloaded = abs(float(model.qpos0[adr] - model.qpos_spring[adr])) <= 1e-10
        if not unloaded:
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid) or str(jid)
            errors.append(f"Joint spring '{name}' must start unloaded: set springref equal to ref")

    if model.ntendon:
        data = mujoco.MjData(model)
        try:
            mujoco.mj_kinematics(model, data)
            mujoco.mj_tendon(model, data)
            for tid in range(model.ntendon):
                if not model.tendon_stiffness[tid] > 0:
                    continue
                length = float(data.ten_length[tid])
                low, high = model.tendon_lengthspring[tid]
                if not (float(low) - 1e-10 <= length <= float(high) + 1e-10):
                    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_TENDON, tid) or str(tid)
                    errors.append(f"Tendon spring '{name}' must start unloaded: omit springlength or include the initial length in its rest interval")
        finally:
            close = getattr(data, "close", None)
            if callable(close):
                close()
    return errors


def validate_internal_actuation(model: mujoco.MjModel) -> List[str]:
    """Reject external wrench sources and tendon anchors outside one robot."""
    errors = []

    def root_body(body_id):
        body_id = int(body_id)
        while body_id and int(model.body_parentid[body_id]):
            body_id = int(model.body_parentid[body_id])
        return body_id

    def internal_joint(joint_id):
        body_id = int(model.jnt_bodyid[joint_id])
        return (int(model.jnt_type[joint_id]) != int(mujoco.mjtJoint.mjJNT_FREE)
                and int(model.body_parentid[body_id]) != 0)

    for actuator_id in range(model.nu):
        name = actuator_name(model, actuator_id)
        transmission = int(model.actuator_trntype[actuator_id])
        target = int(model.actuator_trnid[actuator_id, 0])
        if transmission in (int(mujoco.mjtTrn.mjTRN_JOINT), int(mujoco.mjtTrn.mjTRN_JOINTINPARENT)):
            if not internal_joint(target):
                errors.append(
                    f"Actuator '{name}' drives root/world joint '{joint_name(model, target)}'. "
                    "Root-joint actuation is forbidden. Motor forces and torques must "
                    "act between parts of the same robot."
                )
        elif transmission in (int(mujoco.mjtTrn.mjTRN_SITE), int(mujoco.mjtTrn.mjTRN_SLIDERCRANK)):
            reference = int(model.actuator_trnid[actuator_id, 1])
            # Both sites can be on any bodies, including the chassis. A missing
            # refsite instead produces an external wrench, even on an internal body.
            roots = {root_body(model.site_bodyid[site]) for site in (target, reference)
                     if 0 <= site < model.nsite}
            if target < 0 or reference < 0 or 0 in roots or len(roots) != 1:
                errors.append(
                    f"Actuator '{name}' must have both sites within the same robot: "
                    "site= requires refsite=; cranksite= requires slidersite=. "
                    "Unreferenced site forces, world anchors, and links to other robots are forbidden."
                )
        elif transmission != int(mujoco.mjtTrn.mjTRN_TENDON):
            errors.append(
                f"Actuator '{name}' uses an unsupported transmission. Use joint= or jointinparent= for "
                "an internal joint, tendon= for an internal tendon, site= with refsite=, "
                "or cranksite= with slidersite= within the same robot."
            )

    # Include passive tendons: a spring attached to the world can supply the
    # same unsupported external force without an actuator.
    for tendon_id in range(model.ntendon):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_TENDON, tendon_id) or str(tendon_id)
        roots = set()
        invalid_joint = False
        start = int(model.tendon_adr[tendon_id])
        for wrap_id in range(start, start + int(model.tendon_num[tendon_id])):
            kind = int(model.wrap_type[wrap_id])
            obj = int(model.wrap_objid[wrap_id])
            if kind == int(mujoco.mjtWrap.mjWRAP_JOINT):
                roots.add(root_body(model.jnt_bodyid[obj]))
                invalid_joint |= not internal_joint(obj)
            elif kind == int(mujoco.mjtWrap.mjWRAP_SITE):
                roots.add(root_body(model.site_bodyid[obj]))
            elif kind in (int(mujoco.mjtWrap.mjWRAP_SPHERE), int(mujoco.mjtWrap.mjWRAP_CYLINDER)):
                roots.add(root_body(model.geom_bodyid[obj]))
                sidesite = int(model.wrap_prm[wrap_id])
                if sidesite >= 0:
                    roots.add(root_body(model.site_bodyid[sidesite]))
        if invalid_joint or 0 in roots or len(roots) != 1:
            errors.append(
                f"Tendon '{name}' must connect only joints, sites, and wrapping geoms "
                "within one robot; world anchors and links to other robots are forbidden."
            )
    return errors


def robot_body_ids(model: mujoco.MjModel, *, prefix: str = "") -> List[int]:
    """Body ids that count as part of "the robot" identified by *prefix*.

    The one definition of "the robot's bodies", shared by the structure
    validator (`validate_single_root_free_joint`) and the size validator
    (`initial_root_frame_extents`) -- and matching the exclusion
    `SumoEnv._body_belongs_to_contender` applies for the match itself:
    every `<prefix>`-named body except mocap bodies (`mocap="true"`, e.g.
    the composed model's `<prefix>beacon` COM-tracking marker), which are
    environment-owned visual infrastructure, never part of the robot's own
    structure.
    """
    def _is_robot_body(bid: int) -> bool:
        name = get_element_name(model, mujoco.mjtObj.mjOBJ_BODY, bid)
        if prefix and not name.startswith(prefix):
            return False
        try:
            if int(model.body_mocapid[bid]) >= 0:
                return False
        except Exception:
            pass
        if prefix and name == f"{prefix}beacon":
            return False
        return True

    return [bid for bid in range(1, model.nbody) if _is_robot_body(bid)]


def validate_single_root_free_joint(model: mujoco.MjModel, *, prefix: str = "") -> List[str]:
    """Exactly one free joint per robot, on the root body: no detachable parts.

    A robot is one connected assembly, so it must expose exactly one 6-DOF free
    joint, on its root body. The root body is the robot's SOLE top-level body:
    the only prefix-matching body with `body_parentid == 0` (world) -- every
    other part must be nested inside it. Root identity is never guessed from id
    order (a lower body id is not assumed to be "the real one"): if more than
    one prefix-matching body sits directly under `<worldbody>`, the robot is
    not a single connected assembly and ALL of them are named together, with no
    candidate singled out as the accused non-root -- that would risk either
    misattributing blame to the true root, or silently accepting whichever
    candidate happens to sort first when it is the one that actually carries
    the free joint. Only once exactly one top-level body exists is it checked
    for the free joint itself. A free joint on any OTHER prefix-matching body
    (nested -- though MuJoCo already refuses to compile that -- kept here for
    defense in depth) is a detachable part and is named explicitly.

    Mocap bodies (e.g. the composed model's `<prefix>beacon` COM-tracking
    marker, `mocap="true"`, placed at top level beside the real robot root) are
    environment-owned visual infrastructure, not part of the robot's own
    structure, and are excluded -- the same exclusion `SumoEnv.
    _body_belongs_to_contender` already applies for the same reason.
    """
    errors: List[str] = []

    body_ids = robot_body_ids(model, prefix=prefix)
    if not body_ids:
        return errors

    def _free_joint_names(bid: int) -> List[str]:
        return [joint_name(model, jid) for jid in range(model.njnt)
                if int(model.jnt_type[jid]) == int(mujoco.mjtJoint.mjJNT_FREE)
                and int(model.jnt_bodyid[jid]) == bid]

    top_level = [bid for bid in body_ids if int(model.body_parentid[bid]) == 0]
    nested = [bid for bid in body_ids if bid not in top_level]

    if len(top_level) != 1:
        names = [get_element_name(model, mujoco.mjtObj.mjOBJ_BODY, bid) for bid in top_level]
        with_free = [n for bid, n in zip(top_level, names) if _free_joint_names(bid)]
        without_free = [n for bid, n in zip(top_level, names) if not _free_joint_names(bid)]
        detail_bits = []
        if with_free:
            detail_bits.append(f"carrying a free joint: {', '.join(with_free)}")
        if without_free:
            detail_bits.append(f"with no free joint: {', '.join(without_free)}")
        detail = (" (" + "; ".join(detail_bits) + ")") if detail_bits else ""
        found = ", ".join(f"'{n}'" for n in names) if names else "none"
        errors.append(
            "A robot must have exactly one top-level body directly under <worldbody> -- its "
            f"root -- with every other part nested inside it; found {len(top_level)}: "
            f"{found}{detail}. Fix: nest every body but the single root as a descendant of it, "
            "connected by a hinge, slide, or ball joint, or welded. Only that one root body may "
            "have a free joint."
        )
    else:
        root_bid = top_level[0]
        root_name = get_element_name(model, mujoco.mjtObj.mjOBJ_BODY, root_bid)
        if not _free_joint_names(root_bid):
            errors.append(
                f"Root body '{root_name}' has no free joint. "
                "Fix: add <freejoint/> (or <joint type=\"free\"/>) as the first child of the root <body>."
            )

    # Nested (non-top-level) bodies can never legitimately carry a free joint --
    # a root candidate is by definition top-level, so these are unambiguously
    # detachable parts regardless of how the top-level check above came out.
    for bid in nested:
        name = get_element_name(model, mujoco.mjtObj.mjOBJ_BODY, bid)
        for jname in _free_joint_names(bid):
            errors.append(
                f"Body '{name}' has a free joint '{jname}' but is not a top-level body. Only "
                "the robot's single root body -- directly under <worldbody> -- may have a free "
                "joint; connect this body to its parent with a hinge, slide, or ball joint, or "
                "weld it."
            )
    return errors


# =============================================================================
# MuJoCo Model Inspection
# =============================================================================

def get_element_name(model: mujoco.MjModel, element_type: int, idx: int) -> str:
    """Get human-readable name for a MuJoCo model element."""
    name = mujoco.mj_id2name(model, element_type, idx)
    element_names = {
        mujoco.mjtObj.mjOBJ_ACTUATOR: "actuator",
        mujoco.mjtObj.mjOBJ_GEOM: "geom",
        mujoco.mjtObj.mjOBJ_JOINT: "joint",
        mujoco.mjtObj.mjOBJ_BODY: "body"
    }
    prefix = element_names.get(element_type, "element")
    return name or f"{prefix}[{idx}]"


def actuator_name(model: mujoco.MjModel, idx: int) -> str:
    """Get actuator name with fallback to index-based name."""
    return get_element_name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, idx)


def geom_name(model: mujoco.MjModel, idx: int) -> str:
    """Get geometry name with fallback to index-based name."""
    return get_element_name(model, mujoco.mjtObj.mjOBJ_GEOM, idx)


def joint_name(model: mujoco.MjModel, idx: int) -> str:
    """Get joint name with fallback to index-based name."""
    return get_element_name(model, mujoco.mjtObj.mjOBJ_JOINT, idx)


# =============================================================================
# Geometry Analysis
# =============================================================================

def _geom_local_half_extents(model: mujoco.MjModel, geom_id: int) -> np.ndarray:
    """
    Calculate local half-extents for a geometry in its local frame.

    Returns the half-size along each local axis for bounding box calculation.
    """
    gtype = model.geom_type[geom_id]
    size = model.geom_size[geom_id]

    if gtype == mujoco.mjtGeom.mjGEOM_SPHERE:
        r = float(size[0])
        return np.array([r, r, r], dtype=float)
    elif gtype == mujoco.mjtGeom.mjGEOM_CAPSULE:
        r = float(size[0])
        half = float(size[1]) if size.size > 1 else 0.0
        return np.array([r, r, half + r], dtype=float)
    elif gtype == mujoco.mjtGeom.mjGEOM_CYLINDER:
        r = float(size[0])
        half = float(size[1]) if size.size > 1 else 0.0
        return np.array([r, r, half], dtype=float)
    elif gtype in (mujoco.mjtGeom.mjGEOM_BOX, mujoco.mjtGeom.mjGEOM_ELLIPSOID):
        return np.array(size[:3], dtype=float)
    else:
        # Fallback for unknown geometry types
        default_radius = float(size[0])
        return np.array([default_radius, default_radius, default_radius], dtype=float)


# Unit corners of a box, scaled per geom by its local half-extents.
_BOX_CORNER_SIGNS = np.array(
    [[sx, sy, sz] for sx in (-1.0, 1.0) for sy in (-1.0, 1.0) for sz in (-1.0, 1.0)],
    dtype=float,
)


def _geom_local_points(model: mujoco.MjModel, geom_id: int) -> np.ndarray:
    """Points in the geom's own frame whose bounds are that geom's extents."""
    if model.geom_type[geom_id] in (mujoco.mjtGeom.mjGEOM_MESH, mujoco.mjtGeom.mjGEOM_SDF):
        # Compiled vertices already carry mesh scale and principal-inertia
        # recentering; rotating a local AABB instead would inflate the surface.
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        return np.asarray(model.mesh_vert[start:start + count], dtype=float)
    return _BOX_CORNER_SIGNS * _geom_local_half_extents(model, geom_id)


# The size-box comparison tolerance: a float-noise guard against a robot whose
# compiled span lands a few ULPs over the limit, not a rule number, so it lives
# in exactly one place. `SumoEnv.check_size_limit` (the match, every control
# step) and `validate_size_constraints` (authoring, world-axis and root-frame)
# both import this rather than each spelling out their own `1e-6`.
SIZE_LIMIT_TOLERANCE_M = 1e-6


def root_frame_extents(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    geom_ids: Sequence[int],
    root_body_id: int,
) -> np.ndarray:
    """Axis spans (m) of *geom_ids*, measured in the frame of *root_body_id*.

    The ONE implementation of the size box's runtime measurement. Two callers
    share it so they can never drift apart again:

    * `SumoEnv.robot_extents` — live `data`, every control step of a match.
    * `initial_root_frame_extents` — a fresh `MjData` on the standalone robot,
      at authoring time.

    The root frame, not the world axes: a legal 2.44 m robot yawed 45° spans
    3.45 m along world X, so a world-axis box would punish turning. In the root
    frame a rigid robot's extents never change and only a mechanism that
    actually extends can grow them.
    """
    if root_body_id < 0 or len(geom_ids) == 0:
        return np.zeros(3, dtype=float)
    r_root = np.asarray(data.xmat[root_body_id], dtype=float).reshape(3, 3)
    origin = np.asarray(data.xpos[root_body_id], dtype=float)
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for gid in geom_ids:
        gid = int(gid)
        points = _geom_local_points(model, gid)
        rotation = np.asarray(data.geom_xmat[gid], dtype=float).reshape(3, 3)
        world = points @ rotation.T + np.asarray(data.geom_xpos[gid], dtype=float)
        local = (world - origin) @ r_root      # into the root frame
        lo = np.minimum(lo, local.min(axis=0))
        hi = np.maximum(hi, local.max(axis=0))
    return hi - lo


def _robot_dynamic_geom_ids(model: mujoco.MjModel) -> List[int]:
    """Geom ids on `robot_body_ids(model)`'s bodies, excluding infinite geoms.

    Shared by `compute_robot_aabb` and `initial_root_frame_extents` so both
    measure the same geometry: a mocap marker (e.g. a `<prefix>beacon`) beside
    the chassis is excluded from both, exactly as `robot_body_ids` excludes it
    from root selection.
    """
    body_ids = set(robot_body_ids(model))
    return [
        g for g in range(model.ngeom)
        if int(model.geom_bodyid[g]) in body_ids
        and model.geom_type[g] not in (mujoco.mjtGeom.mjGEOM_PLANE, mujoco.mjtGeom.mjGEOM_HFIELD)
    ]


def initial_root_frame_extents(
    model: mujoco.MjModel, data: Optional[mujoco.MjData] = None,
) -> np.ndarray:
    """Root-frame extents of a standalone robot model in its XML initial pose.

    The authoring-time twin of `SumoEnv.robot_extents`: same helper, same
    measurement, on the pose the match starts from. The root body is the
    model's sole top-level body among `robot_body_ids` -- the same body set
    `validate_single_root_free_joint` uses (and reports on if there is not
    exactly one), so a mocap marker (e.g. a `<prefix>beacon`) beside the
    chassis is excluded here exactly as it is there, and its geoms are not
    measured either.

    Args:
        model: the standalone robot model.
        data: an already-`mj_forward`-ed MjData at the pose to measure. When
            omitted, a fresh MjData is built and forwarded on `model`'s own
            initial pose -- callers measuring more than one thing on the same
            pose (`validate_size_constraints`) should build and forward once
            and pass it here and to `compute_robot_aabb`, rather than paying
            for `mj_forward` twice on the same pose.

    Raises:
        RuntimeError: if the root body or the robot's geometry cannot be found.
    """
    body_ids = set(robot_body_ids(model))
    root_ids = [b for b in body_ids if int(model.body_parentid[b]) == 0]
    if len(root_ids) != 1:
        raise RuntimeError(
            "expected exactly one top-level body directly under <worldbody> to "
            f"measure the root frame, found {len(root_ids)}"
        )
    geom_ids = _robot_dynamic_geom_ids(model)
    if not geom_ids:
        raise RuntimeError("no dynamic geoms found")
    if data is None:
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
    return root_frame_extents(model, data, geom_ids, root_ids[0])


def compute_robot_aabb(
    model: mujoco.MjModel, data: Optional[mujoco.MjData] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute axis-aligned bounding box for all robot geometry.

    World-frame min/max of `_geom_local_points` -- the same per-geom point set
    `root_frame_extents` bounds in the root frame -- transformed by each
    geom's own `geom_xmat`/`geom_xpos`. For a box (or a sphere/capsule/
    cylinder/ellipsoid, all bounded as a local box) this is the same bound as
    the old `abs(R) @ half_extents` formula: rotating the box's 8 local
    corners and taking their min/max per axis is `abs(R) @ half` by
    construction (each axis's extreme corner picks the sign that makes every
    term of that dot product positive). SDF was already vertex-based; MESH
    now is too (unreachable in the pipeline: `validate_material_attributes`
    rejects `type="mesh"` before any model is compiled).

    Args:
        model: MuJoCo model containing the robot
        data: an already-`mj_forward`-ed MjData at the pose to measure. When
            omitted, a fresh MjData is built and forwarded on `model`'s own
            initial pose.

    Returns:
        Tuple of (min_coords, max_coords) as 3D numpy arrays

    Raises:
        RuntimeError: If no dynamic geometry is found in the model
    """
    if data is None:
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)

    geom_ids = _robot_dynamic_geom_ids(model)
    if not geom_ids:
        raise RuntimeError("Could not determine robot geometry bounds (no dynamic geoms found).")

    mins = np.full(3, np.inf, dtype=float)
    maxs = np.full(3, -np.inf, dtype=float)
    for geom_id in geom_ids:
        points = _geom_local_points(model, geom_id)
        rotation = np.asarray(data.geom_xmat[geom_id], dtype=float).reshape(3, 3)
        center = np.asarray(data.geom_xpos[geom_id], dtype=float)
        world = points @ rotation.T + center
        mins = np.minimum(mins, world.min(axis=0))
        maxs = np.maximum(maxs, world.max(axis=0))

    return mins, maxs


# =============================================================================
# Model Validation
# =============================================================================

def validate_model_mass(model: mujoco.MjModel, max_total_mass: float) -> bool:
    """Total compiled mass at or under *max_total_mass*.

    Not part of any check group — the mass rule is `validate_mass_constraints` and
    `validate_motor_mass`, which read the cap from rules.yaml. Kept because the upstream
    acceptance suite imports it (`tests_environment/test_joint_damping_rules.py`);
    the default was removed so no caller can inherit a cap nobody configured.
    """
    return float(np.sum(model.body_mass[1:])) <= max_total_mass  # skip the world body


# =============================================================================
# Configuration Loading
# =============================================================================

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dicts. Override wins on conflicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_constraints_from_yaml(yaml_path: Path) -> Dict[str, Any]:
    """
    Load robot constraints from rules YAML configuration file.

    The rules file (rules.yaml) is self-contained. Materials are auto-loaded
    from materials_store.yaml in the same directory.

    Args:
        yaml_path: Path to rules.yaml

    Returns:
        Dictionary containing robot constraints

    Raises:
        RuntimeError: If PyYAML is not installed or file cannot be loaded
    """
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load constraints: pip install pyyaml"
        ) from exc

    if not yaml_path.exists():
        raise RuntimeError(f"Rules file not found: {yaml_path}")

    config_dir = yaml_path.parent

    # Load rules file directly (self-contained, no prompt.yaml merging)
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    robot = data.get("robot", {})

    # Load materials_store.yaml if present
    materials_path = config_dir / "materials_store.yaml"
    if materials_path.exists():
        with materials_path.open("r", encoding="utf-8") as f:
            materials_data = yaml.safe_load(f) or {}
        materials = materials_data.get("materials", {})
        if materials:
            robot["materials"] = materials
        default_mat = materials_data.get("default_material")
        if default_mat is not None:
            robot["default_material"] = default_mat

    if not robot:
        raise RuntimeError(f"Invalid rules file: missing 'robot' section in {yaml_path}")

    return robot


# =============================================================================
# XML Modification Utilities
# =============================================================================

def _inline_mesh_volume(mesh: ET.Element) -> float:
    """Integrate a closed inline triangle surface, preserving concave volume."""
    try:
        vertices = np.array([float(v) for v in mesh.get('vertex', '').split()]).reshape(-1, 3)
        faces = np.array([int(v) for v in mesh.get('face', '').split()], dtype=int).reshape(-1, 3)
        scale = np.array([float(v) for v in mesh.get('scale', '1 1 1').split()])
    except ValueError as exc:
        raise ValueError('mesh vertex/face data must contain numeric XYZ/index triples') from exc
    if len(vertices) < 4 or len(faces) < 4:
        raise ValueError('mesh requires inline vertex and face data defining a closed surface')
    if not np.all(np.isfinite(vertices)) or scale.shape != (3,) or not np.all(np.isfinite(scale)):
        raise ValueError('mesh vertices and three scale values must be finite')
    if np.any(scale == 0):
        raise ValueError('mesh scale must be nonzero on every axis')
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError('mesh face index is outside the vertex array')

    # Equal coordinates may be listed separately for normals/texture seams.
    vertices, remap = np.unique(vertices, axis=0, return_inverse=True)
    faces = remap[faces]
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    undirected, counts = np.unique(np.sort(edges, axis=1), axis=0, return_counts=True)
    directed = np.unique(edges, axis=0)
    if (np.any(edges[:, 0] == edges[:, 1]) or np.any(counts != 2)
            or len(directed) != 2 * len(undirected)):
        raise ValueError('mesh must be closed with consistently oriented faces (each edge shared twice)')

    # Signed tetrahedra subtract concavities and holes rather than charging for
    # a convex hull. Shift near the origin to reduce cancellation for offset meshes.
    triangles = (vertices - vertices.mean(axis=0))[faces]
    signed_volume = float(np.einsum(
        'ij,ij->i', triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
    ).sum() / 6.0)
    volume = signed_volume * abs(float(np.prod(scale)))
    if not np.isfinite(volume) or volume <= 0:
        raise ValueError('mesh must have positive enclosed volume and outward-facing triangles')
    return volume


def _geom_volume(attrs: Dict[str, Optional[str]], mesh_assets: Optional[Dict[str, ET.Element]] = None) -> float:
    """
    Compute the volume of a MuJoCo geom from its EFFECTIVE attributes.

    `attrs` is one geom's entry from `_effective_geom_attrs`, run through
    `_geom_attr_values`: the values MuJoCo will compile, with any `<default>`
    class already resolved. Reading the raw `geom.get('type', 'sphere')` here
    priced a box whose `type=` came from a class default as a sphere, and that
    wrong volume went straight into `mass=`.

    Supports primitives and mesh/SDF geoms backed by closed inline meshes.
    Returns 0.0 for unsupported types or missing primitive dimensions.
    Invalid mesh data raises ValueError with an actionable diagnostic.
    """
    import math
    gtype = attrs['type'] or 'sphere'
    if gtype in ('mesh', 'sdf'):
        mesh_name = attrs['mesh'] or ''
        mesh = (mesh_assets or {}).get(mesh_name)
        if mesh is None:
            raise ValueError(f"{gtype} geom references missing mesh asset '{mesh_name}'")
        return _inline_mesh_volume(mesh)
    size_str = attrs['size'] or ''
    if not size_str:
        return 0.0
    sizes = [float(s) for s in size_str.split()]
    fromto = attrs['fromto']
    if gtype in ('capsule', 'cylinder') and fromto is not None:
        try:
            endpoints = np.array([float(v) for v in fromto.split()])
        except ValueError as exc:
            raise ValueError('fromto must contain six finite endpoint coordinates') from exc
        if endpoints.shape != (6,) or not np.all(np.isfinite(endpoints)):
            raise ValueError('fromto must contain six finite endpoint coordinates')
        length = float(np.linalg.norm(endpoints[3:] - endpoints[:3]))
        if not np.isfinite(length) or length <= 0:
            raise ValueError('fromto endpoints must be distinct and define a finite length')
        # MuJoCo takes radius from size[0] and axial length from the endpoints;
        # any size[1] is ignored when fromto is present.
        sizes = [sizes[0], length / 2.0]

    if gtype == 'box':
        if len(sizes) >= 3:
            return 8.0 * sizes[0] * sizes[1] * sizes[2]
    elif gtype == 'sphere':
        if len(sizes) >= 1:
            return (4.0 / 3.0) * math.pi * sizes[0] ** 3
    elif gtype == 'cylinder':
        if len(sizes) >= 2:
            r, half_len = sizes[0], sizes[1]
            return math.pi * r ** 2 * 2.0 * half_len
    elif gtype == 'capsule':
        if len(sizes) >= 2:
            r, half_len = sizes[0], sizes[1]
            cyl = math.pi * r ** 2 * 2.0 * half_len
            sphere = (4.0 / 3.0) * math.pi * r ** 3
            return cyl + sphere
    elif gtype == 'ellipsoid':
        if len(sizes) >= 3:
            return (4.0 / 3.0) * math.pi * sizes[0] * sizes[1] * sizes[2]

    return 0.0


def validate_material_attributes(
    xml_string: str,
    material_palette: Dict[str, Any],
    default_material: Optional[str] = None,
) -> Tuple[List[str], dict]:
    """
    Validate that every robot geom has a valid material= from the palette.

    Rejects mass=, density=, body mass=, <inertial> on robot geoms.
    If default_material is set, missing/unknown material= is tolerated
    (will be auto-assigned later by apply_material_properties).

    Args:
        xml_string: MJCF XML content
        material_palette: Dict of material_name -> {density_kg_m3, friction, ...}
        default_material: If set, missing material= is not an error (auto-assigned later).

    Returns:
        Tuple of (errors_list, details_dict)
    """
    import re

    errors: List[str] = []
    checked = 0

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        return [f"Failed to parse XML: {exc}"], {}

    palette_names = set(material_palette.keys())
    # A `<default>` class can supply type= and material=, so judge the geom on
    # what MuJoCo will compile rather than on what the author typed on it.
    geom_attrs = _effective_geom_attrs(root)

    for body in root.iter("body"):
        for geom in body.findall("geom"):
            entry = geom_attrs[id(geom)]
            effective = _geom_attr_values(entry)
            geom_label = geom.get("name", effective["type"])
            checked += 1

            # Reject forbidden geom types: an sdf geom preserves concavity where a
            # mesh geom collides as its convex hull, so the choice must be deliberate.
            if effective["type"] == "mesh":
                errors.append(
                    f"Geom '{geom_label}': type=\"mesh\" is not accepted; express the same "
                    f"shape as an sdf geom from the same vertices and faces."
                )

            # Reject forbidden attributes -- a <default> class supplies these
            # exactly as if they were inline (Global Constraint 5), so judge
            # the effective value, not just what the geom itself typed.
            mass_val, mass_inherited = entry["mass"]
            if mass_val is not None:
                from_class = " (inherited from a <default> class)" if mass_inherited else ""
                errors.append(
                    f"Geom '{geom_label}' has mass= attribute{from_class}. "
                    f"Fix: remove mass= and use material= instead. "
                    f"Mass is computed automatically from volume x material density."
                )
            density_val, density_inherited = entry["density"]
            if density_val is not None:
                from_class = " (inherited from a <default> class)" if density_inherited else ""
                errors.append(
                    f"Geom '{geom_label}' has density= attribute{from_class}. "
                    f"Fix: remove density= and use material= instead."
                )

            # Check material attribute
            mat_name = effective["material"]
            if mat_name is None:
                if default_material:
                    # Missing material= is a warning, not error — will default later
                    pass
                else:
                    errors.append(
                        f"Geom '{geom_label}' missing material= attribute. "
                        f"Fix: add material='...' from palette: {', '.join(sorted(palette_names))}."
                    )
            elif mat_name not in palette_names:
                errors.append(
                    f"Geom '{geom_label}' has unknown material='{mat_name}'. "
                    f"'{mat_name}' does not exist. "
                    f"Pick from: {', '.join(sorted(palette_names))}."
                )

    # Also check for body mass= and <inertial>
    if re.search(r'<body[^>]*\bmass\s*=', xml_string):
        errors.append(
            "Forbidden: mass= on body. Fix: remove it. "
            "Mass is computed from geom volume x material density."
        )
    if '<inertial' in xml_string:
        errors.append(
            "Forbidden: <inertial> element. Fix: remove it. "
            "MuJoCo will infer correct inertia from geom shapes and material masses."
        )

    details = {"geoms_checked": checked, "material_errors": len(errors)}
    return errors, details


# The geom attributes a `<default>` class can supply that this file reads: the
# four that decide volume, the material the palette prices that volume at, and
# mass/density -- both forbidden on a geom (rules.yaml line 63) but which
# MuJoCo applies from a class exactly as if they were inline (verified against
# 3.10.0), so validate_material_attributes and inject_motor_mass must see the
# same effective value the compiler does, not just what the geom itself typed.
_GEOM_DEFAULT_ATTRS = ("type", "size", "fromto", "mesh", "material", "mass", "density")


def _default_class_geom_attrs(root: ET.Element) -> Dict[Optional[str], Dict[str, str]]:
    """`class` name -> the geom attributes that class supplies, parents folded in.

    MJCF's unnamed top-level `<default>` is the "main" class, keyed here as
    None. MuJoCo also accepts an explicit top-level `<default class="main">`
    as that identical class (verified against 3.10.0), so it is keyed as
    None too -- both an implicit main-class lookup and an explicit
    `class="main"` / `childclass="main"` must find the same attribute dict.
    MuJoCo rejects any other name on the top-level `<default>` ("top-level
    default class 'main' cannot be renamed") and rejects a nested
    `<default class="main">` ("repeated default class name"), so neither
    needs handling here. Every named class is nested inside the top-level
    one (MuJoCo rejects a second top-level `<default>`, named or not) and
    inherits whatever it does not restate, so each entry is already the
    whole chain.
    """
    classes: Dict[Optional[str], Dict[str, str]] = {}

    def walk(elem: ET.Element, inherited: Dict[str, str], top: bool = False) -> None:
        for default in elem.findall("default"):
            geom = default.find("geom")
            attrs = dict(inherited)
            if geom is not None:
                for attr in _GEOM_DEFAULT_ATTRS:
                    declared = geom.get(attr)
                    if declared is not None:
                        attrs[attr] = declared
            class_name = default.get("class")
            if top and class_name == "main":
                class_name = None
            classes[class_name] = attrs
            walk(default, attrs)

    walk(root, {}, top=True)
    return classes


def _effective_geom_attrs(root: ET.Element) -> Dict[int, Dict[str, Tuple[Optional[str], bool]]]:
    """Per geom element: {attribute: (value MuJoCo compiles, inherited?)}.

    `geom.get("type", "sphere")` reports `sphere` for a geom that inherits
    `type="box"` from a `<default>` class: the volume computed from it is wrong
    by the ratio of a sphere to a box, and a rejection message would name a
    shape the author never wrote. Resolve the class chain first.

    MJCF resolution, verified against MuJoCo 3.10.0:
      * the geom's own attribute wins;
      * else, if the geom carries `class=`, THAT chain and only that chain — an
        explicit class REPLACES the enclosing `childclass` rather than falling
        back to it (a geom whose class leaves `size` unset fails to compile
        instead of borrowing the childclass's size);
      * else the nearest enclosing body's `childclass=` chain, which reaches
        nested bodies;
      * else the main class; else MuJoCo's own default.
    """
    classes = _default_class_geom_attrs(root)
    main = classes[None] if None in classes else {}
    resolved: Dict[int, Dict[str, Tuple[Optional[str], bool]]] = {}

    def resolve(geom: ET.Element, childclass: Optional[str]) -> Dict[str, Tuple[Optional[str], bool]]:
        own_class = geom.get("class")
        key = own_class if own_class is not None else childclass
        # An undefined class name is MuJoCo's error to report; price the geom
        # off main rather than off a class it never named.
        supplied = classes[key] if key in classes else main
        entry: Dict[str, Tuple[Optional[str], bool]] = {}
        for attr in _GEOM_DEFAULT_ATTRS:
            declared = geom.get(attr)
            if declared is not None:
                entry[attr] = (declared, False)
            elif attr in supplied:
                entry[attr] = (supplied[attr], True)
            else:
                entry[attr] = (None, False)
        if entry["type"][0] is None:
            entry["type"] = ("sphere", False)            # MuJoCo's own default
        return entry

    def walk(elem: ET.Element, childclass: Optional[str]) -> None:
        if elem.tag == "default":
            return                        # class declarations, not robot geoms
        if elem.tag == "body":
            declared = elem.get("childclass")
            if declared is not None:
                childclass = declared
            for geom in elem.findall("geom"):
                resolved[id(geom)] = resolve(geom, childclass)
        for child in elem:
            walk(child, childclass)

    walk(root, None)
    return resolved


def _geom_attr_values(entry: Dict[str, Tuple[Optional[str], bool]]) -> Dict[str, Optional[str]]:
    """Drop the inherited-from-a-class flags, keep the values MuJoCo compiles."""
    return {attr: value for attr, (value, _) in entry.items()}


def apply_material_properties(
    xml_string: str,
    material_palette: Dict[str, Any],
    bot_geom_priority: int = 2,
    default_material: Optional[str] = None,
) -> Tuple[str, List[str], List[str]]:
    """
    Apply material palette properties to robot XML.

    Step 0: Auto-assign default_material to any body geom missing material=.
    Step 1: Inject visual <material> assets for each used material.
    Step 2: For each robot geom with material=, compute mass from volume x density,
            set friction from material, set priority for contact resolution.
    Step 3: Keep material= on geom (valid MuJoCo visual ref).

    Args:
        xml_string: MJCF XML content
        material_palette: Dict of material_name -> {density_kg_m3, friction, rgba, specular, shininess}
        bot_geom_priority: Contact priority for bot geoms (default 2, higher than arena floor)
        default_material: Material name to auto-assign to geoms missing material=.
            Must be a key in material_palette. If None, raises error on missing material.

    Returns:
        Tuple of (modified_xml, errors, info). Errors if material unknown or volume=0.
        Info contains non-fatal messages about auto-assigned materials for refine feedback.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        return xml_string, [f"Failed to parse XML: {exc}"], []

    errors: List[str] = []
    info: List[str] = []

    # type/size/fromto/mesh decide the volume and material decides the density;
    # every one of them may come from a `<default>` class rather than the geom.
    geom_attrs = _effective_geom_attrs(root)

    def effective_material(geom: ET.Element) -> Optional[str]:
        """The material MuJoCo resolves — Step 0 writes its own onto the geom."""
        own = geom.get("material")
        if own is not None:
            return own
        value, _ = geom_attrs[id(geom)]["material"]
        return value

    # Validate default_material
    if default_material is not None and default_material not in material_palette:
        raise ValueError(
            f"default_material='{default_material}' not found in material palette. "
            f"Available: {list(material_palette.keys())}"
        )

    # Step 0: Auto-assign default material to body geoms missing material=
    defaulted_geoms: List[str] = []
    if default_material:
        for body in root.iter("body"):
            for geom in body.findall("geom"):
                mat = effective_material(geom)
                if not mat or mat not in material_palette:
                    geom_label = geom.get("name", geom_attrs[id(geom)]["type"][0])
                    body_name = body.get("name", "unnamed")
                    _thread_log(
                        f"[INFO] Geom '{geom_label}' in body '{body_name}' has no valid material — "
                        f"auto-assigning material='{default_material}'"
                    )
                    geom.set("material", default_material)
                    defaulted_geoms.append(f"'{geom_label}' in body '{body_name}'")

    if defaulted_geoms:
        info.append(
            f"Geoms without material= attribute defaulted to '{default_material}': "
            f"{', '.join(defaulted_geoms)}. "
            f"Fix: explicitly set material= on each geom from the material palette."
        )

    # Collect used materials
    used_materials: set = set()
    for body in root.iter("body"):
        for geom in body.findall("geom"):
            mat = effective_material(geom)
            if mat and mat in material_palette:
                used_materials.add(mat)

    # Step 1: Inject visual <material> assets
    asset = root.find("asset")
    if asset is None:
        asset = ET.SubElement(root, "asset")

    # Check which materials already exist as MuJoCo materials
    existing_materials = {m.get("name") for m in asset.findall("material")}

    for mat_name in sorted(used_materials):
        if mat_name in existing_materials:
            continue
        mat_data = material_palette[mat_name]
        mat_elem = ET.SubElement(asset, "material")
        mat_elem.set("name", mat_name)
        mat_elem.set("rgba", str(mat_data.get("rgba", "0.5 0.5 0.5 1")))
        mat_elem.set("specular", str(mat_data.get("specular", 0.1)))
        mat_elem.set("shininess", str(mat_data.get("shininess", 0.1)))

    # Step 2: Compute physics per geom
    mesh_assets = {m.get('name'): m for m in root.findall('asset/mesh')}
    for body in root.iter("body"):
        for geom in body.findall("geom"):
            mat_name = effective_material(geom)
            if not mat_name or mat_name not in material_palette:
                continue

            mat_data = material_palette[mat_name]
            density = float(mat_data["density_kg_m3"])
            friction = float(mat_data["friction"])

            # Compute volume from the EFFECTIVE attributes: a geom inheriting
            # type="box" from a <default> class carries no type= of its own, and
            # the raw attribute would both price it as a sphere and tell the
            # author their box is one.
            attrs = geom_attrs[id(geom)]
            gtype, inherited = attrs["type"]
            from_class = ", inherited from a default class" if inherited else ""
            geom_label = geom.get("name", gtype)
            try:
                volume = _geom_volume(_geom_attr_values(attrs), mesh_assets)
            except ValueError as exc:
                errors.append(
                    f"Cannot compute volume for geom '{geom_label}' "
                    f"(type='{gtype}'{from_class}): {exc}"
                )
                continue
            if not np.isfinite(volume) or volume <= 0:
                errors.append(
                    f"Geom '{geom_label}' (type='{gtype}'{from_class}) has no volume to price: "
                    f"give it a size= with the numbers its type takes "
                    f"(capsules and cylinders need size= (radius) even when fromto= sets the length)."
                )
                continue

            # Compute mass
            mass = volume * density
            geom.set("mass", f"{mass:.4f}")

            # Set friction (sliding, torsional, rolling)
            geom.set("friction", f"{friction} 0.005 0.0001")

            # Set priority (bot geoms > arena floor for contact friction)
            geom.set("priority", str(bot_geom_priority))

    return ET.tostring(root, encoding="unicode"), errors, info


def _first_rigidly_attached_geom(body: ET.Element) -> Optional[ET.Element]:
    """Prefer direct geoms, then search welded children in XML order.

    A joint or freejoint starts a separate moving assembly, so its subtree
    cannot supply mass for this body.
    """
    geom = body.find('geom')
    if geom is not None:
        return geom
    for child in body.findall('body'):
        if child.find('joint') is not None or child.find('freejoint') is not None:
            continue
        geom = _first_rigidly_attached_geom(child)
        if geom is not None:
            return geom
    return None


def fixed_tendon_coef_sums(root) -> Dict[str, float]:
    """Map each `<fixed>` tendon name to the sum of its joints' |coef|.

    A motor on a fixed tendon applies ``gear x coef`` to every joint the tendon
    names, so ``coef`` is an unpriced torque multiplier unless it is charged for.
    Spatial tendons are absent from the map: they have no joint coefficients and
    keep the plain ``|gear|``.
    """
    sums: Dict[str, float] = {}
    for tendon in root.findall('tendon/fixed'):
        name = tendon.get('name')
        if name is None:
            continue
        total = 0.0
        for entry in tendon.findall('joint'):
            coef = entry.get('coef')
            if coef is None:
                continue          # MJCF requires coef=; MuJoCo's compiler says so
            total += abs(float(coef))
        sums[name] = total
    return sums


def inject_motor_mass(xml_string: str, motor_mass_per_gear: float) -> str:
    """
    Distribute motor mass to a geom rigidly attached to each actuated body.
    Tendon motors mount on the root assembly; relative-site motors on the site
    body; slider-crank motors on the slidersite body.

    For each <motor> actuator: reads |gear|, finds the target joint's parent
    body, locates its first direct geom (or searches welded descendants), and adds
    |gear| × motor_mass_per_gear to its existing mass. For a motor on a `<fixed>`
    tendon the priced gear is |gear| × sum(|coef|) over the tendon's joints, which
    is the torque it actually delivers (`fixed_tendon_coef_sums`).

    Geoms MUST have an explicit mass= attribute (own, or inherited from a
    <default> class). If a geom has density= instead (own or inherited), the
    mass is computed from volume × density first. The new mass= is always set
    directly on the geom, which overrides any class-supplied mass or density
    for that geom alone.

    Args:
        xml_string: MJCF XML content
        motor_mass_per_gear: kg per unit of |gear ratio|

    Returns:
        Modified XML with motor mass distributed to actuated body geoms
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        raise RuntimeError(f"Failed to parse MJCF XML: {exc}") from exc

    if motor_mass_per_gear <= 0:
        return xml_string

    actuator_section = root.find('actuator')
    if actuator_section is None:
        return ET.tostring(root, encoding='unicode')

    # Gear may be inherited from nested defaults. Materialize it so mass
    # accounting and later scoped scene assembly see the same transmission.
    default_gears = {None: '1'}
    def collect_gears(default, inherited):
        gear = inherited
        for element in default:
            if element.tag in ('general', 'motor') and element.get('gear') is not None:
                gear = element.get('gear')
        default_gears[default.get('class')] = gear
        for child in default.findall('default'):
            collect_gears(child, gear)
    for default in root.findall('default'):
        collect_gears(default, '1')

    # Build joint-name -> parent body mapping
    joint_to_body: dict[str, ET.Element] = {}
    for body in root.iter('body'):
        for joint in list(body.findall('joint')) + list(body.findall('freejoint')):
            jname = joint.get('name')
            if jname:
                joint_to_body[jname] = body

    site_to_body = {site.get('name'): body for body in root.iter('body')
                    for site in body.findall('site') if site.get('name')}

    # A <fixed> tendon applies gear x coef to each of its joints, so |coef| is a
    # torque multiplier the gear number alone does not show. Price it: the gear a
    # tendon motor is charged for is |gear| x sum(|coef|) over the tendon's joints.
    # Spatial tendons carry sites and wrapping geoms, no coefficients, so they keep
    # the plain |gear| (multiplier 1), as joint transmissions do.
    tendon_coef_sums = fixed_tendon_coef_sums(root)

    total_injected = 0.0
    mesh_assets = {m.get('name'): m for m in root.findall('asset/mesh')}
    # The density fallbacks below need the volume, so they need the same
    # `<default>`-resolved attributes apply_material_properties priced with.
    geom_attrs = _effective_geom_attrs(root)

    for motor in actuator_section:
        if motor.tag != 'motor':
            continue
        gear_str = motor.get('gear', default_gears.get(motor.get('class'), '1'))
        motor.set('gear', gear_str)
        gear_vals = [float(g) for g in gear_str.split()]
        gear_mag = abs(float(np.linalg.norm(gear_vals)))
        tendon_ref = motor.get('tendon')
        if tendon_ref is not None and tendon_ref in tendon_coef_sums:
            gear_mag *= tendon_coef_sums[tendon_ref]

        joint_ref = motor.get('joint') or motor.get('jointinparent', '')
        if motor.get('tendon'):
            parent_body = root.find('worldbody/body')
        elif motor.get('site') or motor.get('cranksite'):
            mount_site = motor.get('site') if motor.get('site') else motor.get('slidersite')
            parent_body = site_to_body.get(mount_site)
        else:
            parent_body = joint_to_body.get(joint_ref)
        if parent_body is None:
            continue

        geom = _first_rigidly_attached_geom(parent_body)
        if geom is None:
            raise RuntimeError(
                f"Cannot place motor '{motor.get('name', 'unnamed')}' mass: "
                f"body '{parent_body.get('name', 'unnamed')}' has no geom "
                "in itself or its rigidly attached descendants."
            )

        # Determine existing mass from a live read of the geom, falling back
        # to the effective (class-resolved) attrs: the geom's own attribute
        # always wins in MJCF (Global Constraint 5), and when two motors
        # share a geom, the first motor's geom.set('mass', ...) below must be
        # seen by the second — the class snapshot in `geom_attrs` never
        # changes as motors are processed.
        effective = _geom_attr_values(geom_attrs[id(geom)])
        existing_mass_str = geom.get('mass', effective['mass'])
        if existing_mass_str is not None:
            existing_mass = float(existing_mass_str)
        else:
            # Try density × volume fallback
            density_str = geom.get('density', effective['density'])
            if density_str is not None:
                density = float(density_str)
                volume = _geom_volume(effective, mesh_assets)
                existing_mass = density * volume
                # Drop an inline density (a no-op if it came from a class
                # instead); the mass= set below overrides either one.
                geom.attrib.pop('density', None)
            else:
                # No mass or density — use MuJoCo default density 1000
                volume = _geom_volume(effective, mesh_assets)
                existing_mass = 1000.0 * volume

        motor_mass = gear_mag * motor_mass_per_gear
        new_mass = existing_mass + motor_mass
        geom.set('mass', f'{new_mass:.4f}')
        total_injected += motor_mass

    if total_injected > 0:
        _thread_log(f"[INFO] Injected motor mass: {total_injected:.2f} kg distributed to actuated body geoms")

    return ET.tostring(root, encoding='unicode')


def validate_moving_bodies_have_geoms(xml_string: str) -> Tuple[List[str], dict]:
    """
    Require a geom in each jointed body's rigid assembly.

    Geoms may belong to welded descendants, but not independently moving
    children. MuJoCo compilation checks the resulting mass and inertia.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        return [f"Failed to parse XML: {exc}"], {}

    errors: List[str] = []
    checked = 0

    for body in root.iter("body"):
        joints = body.findall("joint")
        freejoints = body.findall("freejoint")
        if not joints and not freejoints:
            continue
        checked += 1

        if _first_rigidly_attached_geom(body) is None:
            body_name = body.get("name", "unnamed_body")
            joint_names = [j.get("name", "unnamed") for j in joints]
            if freejoints:
                joint_names.append("freejoint")
            errors.append(
                f"Body '{body_name}' has joint(s) {joint_names} but no geom "
                "in itself or its rigidly attached descendants. "
                "Add a geom to this rigid assembly; geoms beyond another "
                "joint or freejoint do not count."
            )

    details = {"moving_bodies_checked": checked, "missing_geom_errors": len(errors)}
    return errors, details


__all__ = [
    # Content detection
    "looks_like_xml",
    "looks_like_python_builder",

    # XML processing
    "save_xml",
    "sanitize_robot_xml",
    "sanitize_robot_xml_report",
    "ROBOT_COLLISION_SETTINGS",
    "normalize_robot_collision_settings",
    "UNSUPPORTED_STRUCTURE_ELEMENTS",
    "fixed_tendon_coef_sums",
    "validate_structure_elements",
    "inject_motor_mass",
    "validate_material_attributes",
    "apply_material_properties",
    "validate_moving_bodies_have_geoms",

    # Model inspection
    "get_element_name",
    "actuator_name",
    "geom_name",
    "joint_name",

    # Geometry analysis
    "compute_robot_aabb",
    "SIZE_LIMIT_TOLERANCE_M",

    # Model validation
    "validate_model_mass",
    "validate_passive_mechanisms",
    "validate_internal_actuation",
    "validate_single_root_free_joint",

    # Configuration loading
    "load_constraints_from_yaml",
]
