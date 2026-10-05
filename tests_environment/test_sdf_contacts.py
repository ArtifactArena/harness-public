"""Test actual MuJoCo SDF contacts, independently of proximity observations."""
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from environment_fixtures import box_mesh


@pytest.mark.parametrize('axis', [0,1,2])
@pytest.mark.parametrize('sign', [-1,1])
@pytest.mark.parametrize('distance,overlap', [(.55,True),(.65,False)])
def test_native_sdf_cube_sphere_contacts_match_analytic_clearance(axis, sign, distance, overlap):
    position = np.zeros(3); position[axis] = sign*distance
    model = mujoco.MjModel.from_xml_string(f'''<mujoco><option gravity="0 0 0"/>
      <asset>{box_mesh(half=(.5,.5,.5))}</asset><worldbody>
      <geom name="solid" type="sdf" mesh="surface"/>
      <body pos="{' '.join(map(str,position))}"><freejoint/>
        <geom name="probe" type="sphere" size=".1" mass="1"/>
      </body></worldbody></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model,data)
    contacts = [c for c in data.contact if {int(c.geom1),int(c.geom2)} == {0,1}]
    assert bool(contacts) == overlap
    analytic_gap = distance-.5-.1
    if overlap:
        # MuJoCo stores max(SDF1, SDF2) at a searched intersection point,
        # rather than the primitive pair's full separation distance. Its
        # minimum here is half the analytic overlap; finite search can stop
        # shallower. Check this geometric bound and the physical response.
        # https://github.com/google-deepmind/mujoco/blob/3.10.0/src/engine/engine_collision_sdf.c
        assert all(analytic_gap/2-.005 <= c.dist < 0 for c in contacts)
        wrench = np.zeros(6)
        net_force = np.zeros(3)
        for i, contact in enumerate(data.contact):
            mujoco.mj_contactForce(model,data,i,wrench)
            force = np.asarray(contact.frame).reshape(3,3).T @ wrench[:3]
            net_force += force if contact.geom2 == 1 else -force
        assert np.all(np.isfinite(net_force)) and net_force[axis]*sign > 0
    else:
        assert analytic_gap > .04
        np.testing.assert_allclose(data.qacc[:3],0,atol=1e-12)


def closest_triangle(point, triangle):
    """Independent face/edge projection oracle; no arena distance helpers."""
    a,b,c = triangle
    normal = np.cross(b-a,c-a)
    projected = point-normal*np.dot(point-a,normal)/np.dot(normal,normal)
    uv = np.linalg.lstsq(np.column_stack((b-a,c-a)),projected-a,rcond=None)[0]
    candidates = [projected] if min(uv) >= 0 and sum(uv) <= 1 else []
    for v,w in ((a,b),(b,c),(c,a)):
        candidates.append(v+np.clip(np.dot(point-v,w-v)/np.dot(w-v,w-v),0,1)*(w-v))
    return min(candidates,key=lambda p: np.dot(point-p,point-p))


@pytest.mark.xfail(strict=True, reason=(
    "MuJoCo 3.10.0 SDF sign-field defect: the native collision field reports "
    "false contacts across the verified 0.140068 m air gap. The defect is the "
    "engine's, not this harness's; strict=True so the day MuJoCo is repaired "
    "this turns red and the mark comes off. Do not patch octree signs here."))
def test_sdf_scoop_does_not_generate_contacts_across_verified_air_gap():
    # Known MuJoCo 3.10.0 sign-field defect. Kept as a visible regression
    # until the engine is repaired; do not patch octree signs inside the test.
    path = Path(__file__).parent/'fixtures/sdf_false_contact.xml'
    mesh = ET.parse(path).find('asset/mesh')
    vertices = np.fromstring(mesh.get('vertex'),sep=' ').reshape(-1,3)
    faces = np.fromstring(mesh.get('face'),sep=' ',dtype=int).reshape(-1,3)
    edges = [(int(a),int(b)) for face in faces for a,b in zip(face,np.roll(face,-1))]
    assert all(edges.count((a,b)) == edges.count((b,a)) == 1 for a,b in edges)
    center = np.array([.22,-.94,-.02])
    clearance = min(np.linalg.norm(center-closest_triangle(center,t)) for t in vertices[faces])-.2
    assert clearance == pytest.approx(.140068,abs=1e-6)
    model = mujoco.MjModel.from_xml_path(str(path)); data = mujoco.MjData(model)
    mujoco.mj_forward(model,data)
    assert data.ncon == 0, (
        f'Native SDF collision field reports {data.ncon} false contacts across '
        f'{clearance:.6f} m of verified air; deepest distance '
        f'{min(c.dist for c in data.contact):.6f} m'
    )
