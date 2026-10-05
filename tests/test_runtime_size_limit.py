"""A robot whose root-frame extents exceed the size box during a match loses on that step."""
import mjarena.core.unified_builder  # noqa: F401  (import order: avoids the dspy_core/design_shop cycle)
from pathlib import Path

import mujoco
import numpy as np
import pytest

from mjarena.agents.runtime import BotRuntime
from mjarena.design_shop.pipelines.morphology_pipeline import validate_morphology
from mjarena.design_shop.rules.mj_validators import ModelValidationConfig
from mjarena.envs.sumo import SumoEnv, compose_sumo_model
from mjarena.policy_spec import PolicySpec
from mjarena.runner.episode import _mj_load, run_match

ROOT = Path(__file__).resolve().parents[1]
ARENA = ROOT / "mjarena/assets/sumo_ring_env_studio_3d.xml"
BLOCK = ROOT / "mjarena/core/assets/stationary_block_3d.xml"
RULES = ROOT / "configs/rules/rules.yaml"

# Legal at rest (2.0 m long), but a slide joint can push a plate 1.0 m further out.
TELESCOPE = """<mujoco>
  <worldbody>
    <body name="chassis" pos="0 0 0.3">
      <freejoint name="root"/>
      <geom name="hull" type="box" size="1.0 0.5 0.2" material="foam"/>
      <body name="ram" pos="0.9 0 0">
        <joint name="extend" type="slide" axis="1 0 0" range="0 1.0"/>
        <geom name="plate" type="box" size="0.1 0.4 0.15" material="aluminum"/>
      </body>
    </body>
  </worldbody>
  <actuator><motor name="push" joint="extend" gear="4000"/></actuator>
</mujoco>"""


def _compose(tmp_path, robot_xml=TELESCOPE):
    cfg = ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")
    res = validate_morphology(robot_xml, cfg)
    assert res.passed, res.feedback
    red = tmp_path / "robot.xml"
    red.write_text(res.processed_xml)
    out = tmp_path / "composed.xml"
    compose_sumo_model(env_xml=str(ARENA), robot_red_xml=str(red),
                       robot_blue_xml=str(BLOCK), out_path=str(out),
                       randomize_spawn_3d=True, spawn_seed=0)
    return out, cfg


def _limits(cfg):
    return (cfg.max_robot_x_span, cfg.max_robot_y_span, cfg.max_robot_z_span)


def _env(composed, limits):
    model, data = _mj_load(composed)
    red = BotRuntime(model=model, data=data, policy_callable=lambda obs: {}, prefix="red_")
    blue = BotRuntime(model=model, data=data, policy_callable=lambda obs: {}, prefix="blue_")
    return SumoEnv(model=model, data=data, xml_path=str(composed),
                   red_contender=red, blue_contender=blue, size_limits=limits)


def _push(actuator="push"):
    return PolicySpec.constant([actuator], {actuator: 1.0}).build_callable()


def _run(tmp_path, composed, red_policy, match_time, **kwargs):
    return run_match(
        composed_xml=composed, red_policy_py=red_policy, blue_policy_py=lambda obs: {},
        out_dir=tmp_path, max_steps=None, use_gui=False, save_video=False,
        camera_mode="tracking", quiet=True, seed=0, match_time=match_time,
        inactivity_exempt_prefixes=["blue_"], **kwargs,
    )


def test_extents_are_measured_in_the_root_frame_and_ignore_yaw(tmp_path):
    composed, cfg = _compose(tmp_path)
    env = _env(composed, _limits(cfg))
    env.reset(seed=0)
    rest = env.robot_extents("red_")
    root = env._root_body_ids["red_"]
    adr = env.model.jnt_qposadr[env.model.body_jntadr[root]]
    env.data.qpos[adr + 3:adr + 7] = [np.cos(np.pi / 8), 0, 0, np.sin(np.pi / 8)]   # yaw 45°
    mujoco.mj_forward(env.model, env.data)
    assert np.allclose(env.robot_extents("red_"), rest, atol=1e-6)
    # hull spans x in [-1.0, 1.0]; the retracted plate sits inside it
    assert rest[0] == pytest.approx(2.0, abs=0.05)
    assert env.check_size_limit() is None
    env.close()


def test_extending_past_the_box_is_detected_in_the_root_frame(tmp_path):
    composed, cfg = _compose(tmp_path)
    env = _env(composed, _limits(cfg))
    env.reset(seed=0)
    slide = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, "red_extend")
    env.data.qpos[env.model.jnt_qposadr[slide]] = 1.0
    mujoco.mj_forward(env.model, env.data)
    assert env.robot_extents("red_")[0] == pytest.approx(3.0, abs=0.05)
    assert env.check_size_limit() == "red"
    env.close()


def test_both_sides_over_the_box_is_a_tie(tmp_path):
    composed, _ = _compose(tmp_path)
    env = _env(composed, (0.1, 0.1, 0.1))   # a box neither robot can fit in
    env.reset(seed=0)
    assert env.check_size_limit() == "both"
    env.close()


def test_extending_past_the_box_ends_the_match_as_a_loss(tmp_path):
    composed, cfg = _compose(tmp_path)
    limits = _limits(cfg)
    rec = _run(tmp_path, composed, lambda obs: {}, match_time=5.0, size_limits=limits)
    assert rec.termination_reason == "timeout"          # idle policy: the ram stays retracted
    rec = _run(tmp_path, composed, _push(), match_time=5.0, size_limits=limits)
    assert rec.termination_reason == "size_violation" and rec.winner == "blue"
    assert rec.num_steps < 500


def test_rule_is_off_when_no_limits_are_given(tmp_path):
    composed, _ = _compose(tmp_path)
    rec = _run(tmp_path, composed, _push(), match_time=2.0)
    assert rec.termination_reason != "size_violation"


def test_two_stage_config_carries_size_limits():
    """The two-stage runners (cross_model.py, intra_model.py) must arm the same
    runtime size box as the tournament and qualification paths."""
    from mjarena.two_stage.match_config import load_tournament_config

    cfg = load_tournament_config(ROOT / "configs/tournaments/arh.yaml")
    assert cfg.size_limits == (2.44, 2.44, 3.05)


# ---------------------------------------------------------------------------
# The same box, at authoring time. `validate_size_constraints` used to measure
# ONLY the world-axis AABB, so a robot whose root <body> carried euler=/quat=
# passed authoring and then lost every seed on step 1 to `size_violation`.
# ---------------------------------------------------------------------------

def _bar(half_length: float, yaw: float = 0.0) -> str:
    """A straight bar `2 × half_length` long, optionally yawed at the root."""
    euler = f' euler="0 0 {yaw}"' if yaw else ""
    return f"""<mujoco>
  <worldbody>
    <body name="chassis" pos="0 0 0.4"{euler}>
      <freejoint name="root"/>
      <geom name="hull" type="box" size="{half_length} 0.2 0.15" material="foam"/>
      <body name="arm" pos="0 0 0.2">
        <joint name="spin" type="hinge" axis="0 0 1"/>
        <geom name="pad" type="box" size="0.1 0.1 0.05" material="aluminum"/>
      </body>
    </body>
  </worldbody>
  <actuator><motor name="turn" joint="spin" gear="100"/></actuator>
</mujoco>"""


def _validate(xml: str):
    return validate_morphology(xml, ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d"))


def _size_step(res):
    return [s for s in res.step_results if s.label == "Size Constraints"][0]


def test_the_world_axis_aabb_alone_would_wave_the_yawed_bar_through():
    """The premise of the bug: yaw shrinks the world AABB of an over-size bar."""
    from mjarena.design_shop.utils import compute_robot_aabb
    model = mujoco.MjModel.from_xml_string(
        '<mujoco><compiler angle="radian"/><worldbody>'
        '<body name="chassis" pos="0 0 0.4" euler="0 0 0.7853981633974483"><freejoint/>'
        '<geom name="hull" type="box" size="1.3 0.2 0.15" mass="60"/>'
        '</body></worldbody></mujoco>'
    )
    mins, maxs = compute_robot_aabb(model)
    assert (maxs - mins)[0] < 2.44 and (maxs - mins)[1] < 2.44, maxs - mins


def test_a_yawed_bar_that_hides_inside_the_world_aabb_fails_authoring():
    """2.6 m bar yawed 45°: world AABB 2.12 × 2.12 (legal), root frame 2.6 (not)."""
    res = _validate(_bar(1.3, yaw=np.pi / 4))
    size = _size_step(res)
    assert not res.passed, res.feedback
    assert not size.passed, size.message
    assert "root" in size.message.lower(), size.message
    assert "2.60" in size.message, size.message
    # It is the root-frame measurement that rejects it, not the world AABB.
    assert "X-span 2.60m exceeds" not in size.message, size.message


def test_a_straight_bar_inside_the_box_passes_both_measurements():
    res = _validate(_bar(1.2))
    assert res.passed, res.feedback


def test_a_yawed_bar_inside_the_box_still_passes():
    """Rotating the root is legal — it is only over-size in the root frame that loses."""
    res = _validate(_bar(1.2, yaw=np.pi / 4))
    assert res.passed, res.feedback


def test_authoring_and_runtime_measure_the_same_spans(tmp_path):
    """One helper, two callers: the authoring number is the number the match uses."""
    from mjarena.design_shop.rules.mj_validators import validate_size_constraints
    from mjarena.design_shop.utils import initial_root_frame_extents

    robot = _bar(1.2, yaw=np.pi / 4)
    cfg = ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")
    res = validate_morphology(robot, cfg)
    assert res.passed, res.feedback
    model = mujoco.MjModel.from_xml_string(res.processed_xml)
    authored = validate_size_constraints(model, cfg).details["root_frame_spans"]
    assert np.allclose(authored, initial_root_frame_extents(model), atol=1e-12)

    composed, cfg = _compose(tmp_path, robot_xml=robot)
    env = _env(composed, _limits(cfg))
    env.reset(seed=3)
    assert np.allclose(env.robot_extents("red_"), authored, atol=1e-6)
    env.close()


# ---------------------------------------------------------------------------
# One size-limit tolerance, in one place (`SIZE_LIMIT_TOLERANCE_M`). The
# world-axis branch of `validate_size_constraints` used to compare bare spans
# with no tolerance, unlike its root-frame branch and unlike the match's own
# `SumoEnv.check_size_limit`, so a robot whose compiled span was a few ULPs
# over the limit (float noise, not an actual over-size robot) was rejected at
# authoring time even though it would pass every step of the match.
# ---------------------------------------------------------------------------

def _on_axis_box(x_span: float) -> str:
    """A single-body robot whose world-axis (and root-frame) X-span is exactly *x_span*.

    Unrotated and centered on the root body, so the box's compiled span along
    world X equals `2 * size[0]` exactly, with no other body/joint to disturb
    it. `mass=` is set directly so this compiles standalone, without going
    through material validation (irrelevant to the size check).
    """
    half_x = repr(x_span / 2.0)
    return (
        '<mujoco><compiler angle="radian"/><worldbody>'
        '<body name="chassis" pos="0 0 0.4"><freejoint/>'
        f'<geom name="hull" type="box" size="{half_x} 0.1 0.1" mass="60"/>'
        '</body></worldbody></mujoco>'
    )


def test_a_world_axis_span_a_float_ulp_over_the_limit_passes():
    """`limit + 1e-9` is float noise, not a violation: the world-axis branch
    must carry the same tolerance the root-frame branch and the match do."""
    from mjarena.design_shop.rules.mj_validators import validate_size_constraints
    from mjarena.design_shop.utils import compute_robot_aabb

    cfg = ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")
    target = cfg.max_robot_x_span + 1e-9
    model = mujoco.MjModel.from_xml_string(_on_axis_box(target))

    # Confirm MuJoCo actually compiled the span we intend before judging the
    # validator's tolerance against it.
    mins, maxs = compute_robot_aabb(model)
    compiled_span = float((maxs - mins)[0])
    assert compiled_span == pytest.approx(target, abs=1e-12)
    assert compiled_span > cfg.max_robot_x_span

    res = validate_size_constraints(model, cfg)
    assert res.passed, res.errors


def test_a_world_axis_span_meaningfully_over_the_limit_fails():
    """`limit + 1e-5` is a real violation -- the tolerance must not swallow it."""
    from mjarena.design_shop.rules.mj_validators import validate_size_constraints
    from mjarena.design_shop.utils import compute_robot_aabb

    cfg = ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")
    target = cfg.max_robot_x_span + 1e-5
    model = mujoco.MjModel.from_xml_string(_on_axis_box(target))

    mins, maxs = compute_robot_aabb(model)
    compiled_span = float((maxs - mins)[0])
    assert compiled_span == pytest.approx(target, abs=1e-12)

    res = validate_size_constraints(model, cfg)
    assert not res.passed
    assert any("X-span" in e and "exceeds" in e for e in res.errors), res.errors


def test_check_size_limit_and_the_validator_share_the_same_tolerance_object(tmp_path, monkeypatch):
    """Global constraint 4: the tolerance exists in exactly one place.

    `mj_validators` binds the identical object `design_shop.utils` defines
    (import identity, not merely an equal value). `SumoEnv.check_size_limit`
    re-imports it locally on every call rather than hard-coding its own copy,
    so patching that one canonical constant flips both places' verdicts.
    """
    from mjarena.design_shop import utils as design_shop_utils
    from mjarena.design_shop.rules import mj_validators

    assert mj_validators.SIZE_LIMIT_TOLERANCE_M is design_shop_utils.SIZE_LIMIT_TOLERANCE_M

    composed, cfg = _compose(tmp_path)
    env = _env(composed, _limits(cfg))
    env.reset(seed=0)
    slide = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, "red_extend")
    env.data.qpos[env.model.jnt_qposadr[slide]] = 1.0
    mujoco.mj_forward(env.model, env.data)
    assert env.check_size_limit() == "red"          # ~3.0 m span, 0.56 m over the box

    monkeypatch.setattr(design_shop_utils, "SIZE_LIMIT_TOLERANCE_M", 10.0)
    assert env.check_size_limit() is None            # same constant, now huge
    env.close()


# ---------------------------------------------------------------------------
# The structure validator and the size validator must agree on which body is
# the root. `validate_single_root_free_joint` already excludes mocap bodies
# (the composed model's COM-tracking beacon) from root selection, matching
# `SumoEnv._body_belongs_to_contender`; `initial_root_frame_extents` used to
# count them, so a robot carrying a mocap marker beside its chassis passed
# Structural Limits and then failed Size Constraints with "expected exactly
# one top-level body ... found 2" -- a rejection naming the wrong rule.
# ---------------------------------------------------------------------------

def _chassis_with_mocap_marker() -> str:
    """A legal single-body chassis plus a top-level `mocap="true"` marker.

    The marker stands in for the composed model's `<prefix>beacon`
    COM-tracking body: top-level, beside the real root, never part of the
    robot's own structure.
    """
    return """<mujoco>
  <worldbody>
    <body name="chassis" pos="0 0 0.3">
      <freejoint name="root"/>
      <geom name="hull" type="box" size="1.0 0.5 0.2" mass="60"/>
    </body>
    <body name="marker" mocap="true" pos="0 0 2">
      <geom name="marker_geom" type="sphere" size="0.3" mass="1"/>
    </body>
  </worldbody>
</mujoco>"""


def test_mocap_body_passes_structure_and_does_not_break_root_frame_extents():
    from mjarena.design_shop.utils import initial_root_frame_extents, validate_single_root_free_joint

    model = mujoco.MjModel.from_xml_string(_chassis_with_mocap_marker())

    assert validate_single_root_free_joint(model) == []

    extents = initial_root_frame_extents(model)
    # hull is a 2.0 x 1.0 x 0.4 box; the marker sphere (radius 0.3, 1.7 m
    # above the chassis) must not be counted, or it would inflate Z past 2.0.
    assert extents == pytest.approx([2.0, 1.0, 0.4], abs=1e-6)


# ---------------------------------------------------------------------------
# Task 6: one geom-extent implementation, one MjData. `compute_robot_aabb` used
# to keep its own per-geom point/half-extent code (`abs(R) @ half-extents`,
# mesh vertices for SDF) next to `_geom_local_points` / `root_frame_extents` --
# two measurement paths for the same geometry that could drift apart exactly
# the way the runtime/authoring pair did before Task 2/3. This is a pinned
# contract, not a behaviour change: every value below is derived independently
# from `model`/`data` using the OLD formula (`abs(R) @ half` for box/capsule,
# raw mesh vertices for SDF) and must match `compute_robot_aabb` both before
# and after the consolidation onto `_geom_local_points`.
# ---------------------------------------------------------------------------

def test_compute_robot_aabb_matches_the_old_abs_r_half_formula_for_a_rotated_box():
    from mjarena.design_shop.utils import compute_robot_aabb

    model = mujoco.MjModel.from_xml_string(
        '<mujoco><compiler angle="radian"/><worldbody>'
        '<body name="chassis" pos="0.3 -0.2 0.5" euler="0.4 -0.6 0.9"><freejoint/>'
        '<geom name="hull" type="box" size="0.7 0.3 0.2" pos="0.1 0.05 -0.05" mass="10"/>'
        '</body></worldbody></mujoco>'
    )
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "hull")
    r = np.asarray(data.geom_xmat[gid]).reshape(3, 3)
    half = np.asarray(model.geom_size[gid, :3], dtype=float)
    center = np.asarray(data.geom_xpos[gid], dtype=float)
    world_half = np.abs(r) @ half
    expected_min, expected_max = center - world_half, center + world_half

    mins, maxs = compute_robot_aabb(model)
    np.testing.assert_allclose(mins, expected_min, atol=1e-12)
    np.testing.assert_allclose(maxs, expected_max, atol=1e-12)


def test_compute_robot_aabb_matches_the_old_abs_r_half_formula_for_a_rotated_capsule():
    from mjarena.design_shop.utils import compute_robot_aabb

    model = mujoco.MjModel.from_xml_string(
        '<mujoco><compiler angle="radian"/><worldbody>'
        '<body name="chassis" pos="-0.4 0.6 0.8" euler="-0.5 1.1 0.3"><freejoint/>'
        '<geom name="limb" type="capsule" size="0.15 0.5" pos="-0.1 0.2 0.05" mass="4"/>'
        '</body></worldbody></mujoco>'
    )
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "limb")
    r = np.asarray(data.geom_xmat[gid]).reshape(3, 3)
    radius, half_len = float(model.geom_size[gid, 0]), float(model.geom_size[gid, 1])
    half = np.array([radius, radius, half_len + radius])
    center = np.asarray(data.geom_xpos[gid], dtype=float)
    world_half = np.abs(r) @ half
    expected_min, expected_max = center - world_half, center + world_half

    mins, maxs = compute_robot_aabb(model)
    np.testing.assert_allclose(mins, expected_min, atol=1e-12)
    np.testing.assert_allclose(maxs, expected_max, atol=1e-12)


def test_compute_robot_aabb_matches_raw_mesh_vertex_bounds_for_an_sdf_robot():
    from mjarena.design_shop.utils import compute_robot_aabb

    vertex = "0 0 0  2 0 0  0 1 0  0 0 .6  1.3 .4 .2"
    face = "0 2 1  0 3 2  0 1 3  1 2 4  2 3 4  3 1 4"
    model = mujoco.MjModel.from_xml_string(f'''<mujoco><compiler angle="radian"/>
      <asset><mesh name="surface" inertia="exact" vertex="{vertex}" face="{face}"/></asset>
      <worldbody><body pos="0.5 -0.3 0.9" euler="0.3 -0.7 1.0"><freejoint/>
        <geom name="hull" type="sdf" mesh="surface" pos="0.2 -0.1 0.05"/>
      </body></worldbody></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "hull")
    r = np.asarray(data.geom_xmat[gid]).reshape(3, 3)
    center = np.asarray(data.geom_xpos[gid], dtype=float)
    mesh_id = int(model.geom_dataid[gid])
    start, count = int(model.mesh_vertadr[mesh_id]), int(model.mesh_vertnum[mesh_id])
    vertices = np.asarray(model.mesh_vert[start:start + count], dtype=float)
    world_vertices = vertices @ r.T + center
    expected_min, expected_max = world_vertices.min(axis=0), world_vertices.max(axis=0)

    mins, maxs = compute_robot_aabb(model)
    np.testing.assert_allclose(mins, expected_min, atol=1e-12)
    np.testing.assert_allclose(maxs, expected_max, atol=1e-12)


def test_validate_size_constraints_details_are_unchanged_by_the_aabb_consolidation():
    """Pinned contract: consolidating `compute_robot_aabb` onto `_geom_local_points`
    and sharing one `MjData` with `initial_root_frame_extents` must not move any
    number `validate_size_constraints` reports. Values below were captured from a
    run on HEAD (before this refactor) of the same yawed-bar robot used above."""
    from mjarena.design_shop.rules.mj_validators import validate_size_constraints

    cfg = ModelValidationConfig(constraints_yaml_path=RULES, physics_mode="3d")
    robot = _bar(1.2, yaw=np.pi / 4)
    res = validate_morphology(robot, cfg)
    assert res.passed, res.feedback
    model = mujoco.MjModel.from_xml_string(res.processed_xml)

    details = validate_size_constraints(model, cfg).details
    assert details["x_span"] == pytest.approx(1.979898987322333, abs=1e-9)
    assert details["y_span"] == pytest.approx(1.9798989873223332, abs=1e-9)
    assert details["z_span"] == pytest.approx(0.40000000000000013, abs=1e-9)
    assert details["bounding_box_min"] == pytest.approx(
        [-0.9899494936611665, -0.9899494936611666, 0.25], abs=1e-9)
    assert details["bounding_box_max"] == pytest.approx(
        [0.9899494936611665, 0.9899494936611666, 0.6500000000000001], abs=1e-9)
    assert details["root_frame_spans"] == pytest.approx(
        [2.4, 0.4, 0.40000000000000013], abs=1e-9)
