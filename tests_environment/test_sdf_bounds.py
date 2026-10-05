"""SDF size validation must account for the complete transformed mesh bounds."""
from pathlib import Path

import mujoco
import numpy as np
import pytest

from mjarena.design_shop.rules.mj_validators import (
    ModelValidationConfig,
    validate_size_constraints,
)
from mjarena.design_shop.utils import compute_robot_aabb


FACES = "0 2 1 0 3 2 4 5 6 4 6 7 0 1 5 0 5 4 1 2 6 1 6 5 2 3 7 2 7 6 3 0 4 3 4 7"
CORNERS = np.array([
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
])


def cuboid_model(half_size, *, offset=(0, 0, 0), scale=(1, 1, 1),
                 rotation="0 0 0", primitive=False):
    vertices = CORNERS * half_size + offset
    vertex_text = " ".join(map(str, vertices.flat))
    scale_text = " ".join(map(str, scale))
    if primitive:
        assets = ""
        size_text = " ".join(map(str, np.asarray(half_size) * np.abs(scale)))
        pos_text = " ".join(map(str, np.asarray(offset) * scale))
        geom = f'<geom type="box" size="{size_text}" pos="{pos_text}"/>'
    else:
        assets = f'<asset><mesh name="surface" inertia="exact" vertex="{vertex_text}" face="{FACES}" scale="{scale_text}"/></asset>'
        geom = '<geom type="sdf" mesh="surface"/>'
    return mujoco.MjModel.from_xml_string(f'''<mujoco><compiler angle="radian"/>
      {assets}<worldbody><body pos=".7 -.8 1.1" euler=".2 -.3 .4"><freejoint/>
      <body pos=".3 .2 -.4" euler="{rotation}">{geom}</body>
      </body></worldbody></mujoco>''')


@pytest.mark.parametrize("offset,scale,rotation", [
    ((0, 0, 0), (1, 1, 1), "0 0 0"),
    ((4, -3, 2), (1, 1, 1), ".4 .6 -.2"),
    ((2, -1, 3), (2, 3, 4), "-.3 .8 .5"),
    ((2, -1, 3), (-2, 3, 4), ".5 -.2 -.8"),
])
def test_sdf_cuboid_matches_equivalent_box(offset, scale, rotation):
    args = dict(offset=offset, scale=scale, rotation=rotation)
    sdf = cuboid_model((1.5, .2, .1), **args)
    box = cuboid_model((1.5, .2, .1), primitive=True, **args)
    np.testing.assert_allclose(compute_robot_aabb(sdf), compute_robot_aabb(box), atol=3e-6)


@pytest.mark.parametrize("rotation", ["0 0 0", ".7 -.4 1.2"])
def test_asymmetric_sdf_bounds_contain_every_surface_vertex(rotation):
    model = mujoco.MjModel.from_xml_string(f'''<mujoco><compiler angle="radian"/>
      <asset><mesh name="surface" inertia="exact"
        vertex="0 0 0 3 0 0 0 1 0 0 0 .5" face="0 2 1 0 1 3 0 3 2 1 2 3"/></asset>
      <worldbody><body pos="2 -1 3" euler="{rotation}"><freejoint/>
        <geom type="sdf" mesh="surface" pos="1 2 -3"/>
      </body></worldbody></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    rotation_matrix = data.geom_xmat[0].reshape(3, 3)
    vertices = model.mesh_vert @ rotation_matrix.T + data.geom_xpos[0]
    lower, upper = compute_robot_aabb(model)
    assert np.any(np.abs(model.geom_aabb[0, :3]) > .1)  # COM is not box center.
    assert np.all(vertices >= lower - 1e-6)
    assert np.all(vertices <= upper + 1e-6)
    np.testing.assert_allclose(lower, vertices.min(axis=0), atol=1e-6)
    np.testing.assert_allclose(upper, vertices.max(axis=0), atol=1e-6)


@pytest.mark.parametrize("axis,span,passes", [
    (0, 2.4, True), (0, 2.5, False),
    (1, 2.4, True), (1, 2.5, False),
    (2, 3.0, True), (2, 3.1, False),    # height limit is 3.05 m, not 10 m
])
def test_size_validator_accepts_and_rejects_elongated_sdfs(axis, span, passes):
    half_size = np.array([.1, .1, .1])
    half_size[axis] = span / 2
    model = cuboid_model(half_size)
    # Use an axis-aligned initial root pose for the size-limit boundary check.
    model.qpos0[3:7] = [1, 0, 0, 0]
    config = ModelValidationConfig(
        constraints_yaml_path=Path(__file__).resolve().parents[1] / "configs/rules/rules.yaml",
        physics_mode="3d",
    )
    assert validate_size_constraints(model, config).passed == passes
