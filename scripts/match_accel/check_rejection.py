"""Check SDF enclosures and rejected pairs against the pinned reference kernel."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path

import mujoco
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert len(os.sched_getaffinity(0)) == 1, 'pin this check to one CPU'
    model = mujoco.MjModel.from_binary_path(str(args.model))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    lib = ctypes.CDLL(str(args.library.resolve()))
    lib.arena_create.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.arena_create.restype = ctypes.c_void_p
    lib.arena_destroy.argtypes = [ctypes.c_void_p]
    lib.arena_check_rejection_field.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    lib.arena_check_rejection_pair.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    ctx = lib.arena_create(model._address, data._address, 1)
    assert ctx
    rng = np.random.default_rng(2492026)
    checked = meshes = pairs = rejected = 0
    lib.arena_enable(1)
    try:
        for mid in range(model.nmesh):
            adr = model.mesh_octadr[mid]
            if adr < 0:
                continue
            root = model.oct_aabb[adr]
            center, half = root[:3], root[3:]
            coeff = model.oct_coeff[adr:adr + model.mesh_octnum[mid]]
            outside = max(1e-5, -float(coeff.min()))
            points = [rng.uniform(-1, 1, (3000, 3)) * (half + outside) + center]
            # Root faces, projection offsets, neighboring floats and exterior
            # negative-field distances; retained leaves' boundaries as well.
            for axis in range(3):
                for sign in [-1, 1]:
                    face = center[axis] + sign * half[axis]
                    for delta in [0, 1e-8, -1e-8, 1e-6, -1e-6, outside / 2, outside]:
                        p = rng.uniform(-1, 1, (50, 3)) * half + center
                        p[:, axis] = face + sign * delta
                        points += [p, np.nextafter(p, np.inf), np.nextafter(p, -np.inf)]
            boxes = model.oct_aabb[adr:adr + model.mesh_octnum[mid]]
            selected = boxes[rng.integers(0, len(boxes), 1000)]
            corners = selected[:, :3] + rng.choice([-1., 1.], (1000, 3)) * selected[:, 3:]
            points += [corners, np.nextafter(corners, np.inf), np.nextafter(corners, -np.inf)]
            p = np.ascontiguousarray(np.concatenate(points))
            result = lib.arena_check_rejection_field(ctx, mid, len(p), p.ctypes.data)
            if result == -2:
                continue  # Unsupported scales must retain the original kernel.
            assert result == -1, (mid, result, p[result].tolist())
            checked += len(p)
            meshes += 1

        sdf_geoms = np.flatnonzero(model.geom_type == mujoco.mjtGeom.mjGEOM_SDF)
        for kind in [mujoco.mjtGeom.mjGEOM_SPHERE, mujoco.mjtGeom.mjGEOM_CAPSULE,
                     mujoco.mjtGeom.mjGEOM_CYLINDER, mujoco.mjtGeom.mjGEOM_BOX]:
            candidates = np.flatnonzero(model.geom_type == kind)
            if not len(candidates):
                continue
            g1 = int(candidates[0])
            for g2 in sdf_geoms:
                adr = model.mesh_octadr[model.geom_dataid[g2]]
                root = model.oct_aabb[adr]
                for _ in range(120):
                    # Rigid poses in the same world frame, with independent
                    # rotations and positions concentrated around the SDF.
                    for geom in [g1, int(g2)]:
                        quat = rng.normal(size=4)
                        quat /= np.linalg.norm(quat)
                        mujoco.mju_quat2Mat(data.geom_xmat[geom], quat)
                    data.geom_xpos[g2] = rng.uniform(-5, 5, 3)
                    data.geom_xpos[g1] = data.geom_xpos[g2] + rng.uniform(-1.5, 1.5, 3) * (root[3:] + 0.3)
                    result = lib.arena_check_rejection_pair(ctx, g1, int(g2))
                    assert result >= 0, (kind, g1, int(g2), pairs)
                    pairs += 1
                    rejected += result
        assert meshes and rejected, 'check did not exercise rejection'
    finally:
        lib.arena_enable(0)
        lib.arena_destroy(ctx)
    report = dict(exact=True, field_points=checked, meshes=meshes,
                  pairs=pairs, rejected_pairs_checked_against_stock=rejected,
                  affinity=sorted(os.sched_getaffinity(0)),
                  model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                  library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest())
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
