"""Compare cached leaves/weights with stock traversal at adjacent float boundaries."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path

import mujoco


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1:
        parser.error('pin this check to one CPU')
    if mujoco.__version__ != '3.10.0':
        parser.error('requires MuJoCo 3.10.0')
    model = mujoco.MjModel.from_binary_path(str(args.model))
    library = ctypes.CDLL(str(args.library.resolve()))
    check = library.arena_check_octrees
    check.argtypes = [ctypes.c_void_p]
    check.restype = ctypes.c_int
    count = check(model._address)
    if count < 0:
        raise AssertionError('Cached leaf or interpolation differs from stock traversal')
    if count == 0:
        raise RuntimeError('Model has no cached octrees to check')
    report = {
        'exact': True, 'points_checked': count,
        'checks': ['leaf', 'interpolation_weights', 'gradient_weights'],
        'sampling': 'root/split boundaries, adjacent floats, seeded other coordinates',
        'affinity': sorted(os.sched_getaffinity(0)),
        'library_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest(),
        'model_sha256': hashlib.sha256(args.model.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
