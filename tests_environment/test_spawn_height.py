"""Match composition and reset must place complete robots above the platform."""
from types import SimpleNamespace

import mujoco
import numpy as np
import pytest

from mjarena.envs.sumo import SumoEnv, compose_sumo_model


@pytest.fixture
def arena(tmp_path):
    path = tmp_path / 'env.xml'
    path.write_text('''<mujoco><worldbody>
      <geom name="sumo_ring" type="cylinder" pos="0 0 1" size="7.5 1"/>
      <site name="spawn/left" pos="-3 0 2.3"/>
      <site name="spawn/right" pos="3 0 2.3"/>
    </worldbody></mujoco>''')
    return path


@pytest.mark.parametrize('child_name', ['name="wheel_body"', ''])
@pytest.mark.parametrize('ring_type', ['cylinder', 'box'])
@pytest.mark.parametrize('root_name', ['name="chassis"', ''])
def test_materials_defaults_and_unnamed_children_are_ready_for_spawn(tmp_path, arena, child_name, ring_type, root_name):
    if ring_type == 'box':
        arena.write_text(arena.read_text().replace('type="cylinder"', 'type="box"').replace('size="7.5 1"', 'size="7.5 7.5 1"'))
    robot = tmp_path / 'robot.xml'
    robot.write_text(f'''<mujoco>
      <asset><material name="rubber" rgba=".1 .1 .1 1"/></asset>
      <default><default class="tire"><geom type="cylinder" size=".25 .075"
        euler="-1.5707963267948966 0 0" material="rubber" mass="43"/></default></default>
      <worldbody><body {root_name}><freejoint/>
        <geom type="box" size=".55 .45 .03" mass="160"/>
        <body {child_name} pos="0 0 -.25"><joint name="axle" axis="0 1 0"/>
          <geom name="wheel" class="tire"/>
        </body>
      </body></worldbody><actuator><motor name="drive" joint="axle" gear="800"/></actuator>
    </mujoco>''')
    path = compose_sumo_model(str(arena), str(robot), str(robot), str(tmp_path / 'composed.xml'),
                             randomize_spawn_3d=True, spawn_seed=0, beacon_size_m=2)
    model = mujoco.MjModel.from_xml_path(path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    for prefix in ('red_', 'blue_'):
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, prefix + 'wheel')
        assert data.geom_xpos[gid, 2] - .25 == pytest.approx(2.003, abs=1e-6)
        bid = int(model.body_rootid[model.geom_bodyid[gid]])
        assert data.xpos[bid, 2] == pytest.approx(2.503, abs=1e-6)
    # Physical contacts must not begin with deep overlap.
    assert all(contact.dist >= -1e-6 for contact in data.contact)


def test_invalid_model_does_not_silently_keep_fallback_height(tmp_path, arena):
    robot = tmp_path / 'robot.xml'
    robot.write_text('''<mujoco><worldbody><body name="bot"><freejoint/>
      <geom type="sphere" size=".5" material="missing"/>
    </body></worldbody></mujoco>''')
    with pytest.raises(ValueError, match='spawn heights'):
        compose_sumo_model(str(arena), str(robot), str(robot), str(tmp_path / 'invalid.xml'))
    assert not (tmp_path / 'invalid.xml').exists()


@pytest.mark.parametrize('taller_side', ['red', 'blue'])
def test_reset_swaps_sides_without_swapping_robot_heights(tmp_path, arena, taller_side):
    robots = []
    for side in ('red', 'blue'):
        robot = tmp_path / f'{side}.xml'
        half_height, offset = (.35, -.30) if side == taller_side else (.25, 0)
        robot.write_text(f'''<mujoco><worldbody><body name="bot"><freejoint/>
          <geom name="shape" type="box" pos="0 0 {offset}"
                size=".4 .4 {half_height}" mass="50"/>
        </body></worldbody></mujoco>''')
        robots.append(robot)
    path = compose_sumo_model(str(arena), *(str(robot) for robot in robots),
                             str(tmp_path / 'reset-arena.xml'),
                             randomize_spawn_3d=True, spawn_seed=0)
    model = mujoco.MjModel.from_xml_path(path)
    data = mujoco.MjData(model)
    env = SumoEnv(model=model, data=data, xml_path=path,
                  red_contender=SimpleNamespace(prefix='red_'),
                  blue_contender=SimpleNamespace(prefix='blue_'),
                  inactivity_timeout_seconds=None)
    spawns = np.array(env._spawn_positions, copy=True)
    try:
        # Reusing the same environment also catches accidental mutation of the
        # saved spawn positions across resets.
        for seed in (0, 1, 3, 2, 1):
            env.reset(seed=seed)
            for index, side in enumerate(('red', 'blue')):
                gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, side + '_shape')
                bid = model.geom_bodyid[gid]
                target = 1 - index if seed % 2 else index
                np.testing.assert_allclose(data.xpos[bid, :2], spawns[target, :2], atol=1e-5)
                # Real settling lowers the initial 3 mm gap slightly. Both
                # robots must still sit just above the platform on either side.
                bottom = data.geom_xpos[gid, 2] - model.geom_size[gid, 2]
                assert 2.0 < bottom < 2.003
            np.testing.assert_array_equal(env._spawn_positions, spawns)
    finally:
        env.close()


@pytest.mark.parametrize('kind', ['mesh', 'sdf', 'ellipsoid'])
def test_spawn_clearance_uses_complete_geometry_bounds(tmp_path, arena, kind):
    # Distinct mesh assets expose incorrect indexing into MuJoCo's Nx3 vertex array.
    vertices = np.array([[x, y, z] for x in (-.12, .12) for y in (-.2, .2) for z in (-.7, .7)])
    vertex_text = ' '.join(map(str, vertices.flat))
    assets = f'''<asset>
      <mesh name="unused" vertex="0 0 0 1 0 0 0 1 0 0 0 1"/>
      <mesh name="surface" vertex="{vertex_text}"/>
    </asset>'''
    if kind == 'ellipsoid':
        assets = ''
        geom = '<geom name="shape" type="ellipsoid" size=".12 .2 .7" euler=".3 .4 .2"/>'
    else:
        geom = f'<geom name="shape" type="{kind}" mesh="surface" euler=".3 .4 .2"/>'
    robot = tmp_path / 'shaped.xml'
    robot.write_text(f'<mujoco>{assets}<worldbody><body name="bot"><freejoint/>{geom}</body></worldbody></mujoco>')
    path = compose_sumo_model(str(arena), str(robot), str(robot), str(tmp_path / 'shaped-arena.xml'))
    model = mujoco.MjModel.from_xml_path(path)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    for prefix in ('red_', 'blue_'):
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, prefix + 'shape')
        rotation = data.geom_xmat[gid].reshape(3, 3)
        if kind == 'ellipsoid':
            bottom = data.geom_xpos[gid, 2] - np.linalg.norm(rotation[2] * model.geom_size[gid])
        else:
            mesh_id = model.geom_dataid[gid]
            start, count = model.mesh_vertadr[mesh_id], model.mesh_vertnum[mesh_id]
            world = model.mesh_vert[start:start + count] @ rotation.T + data.geom_xpos[gid]
            bottom = world[:, 2].min()
        assert bottom == pytest.approx(2.003, abs=1e-6)
