"""Opt-in acceleration. The unmodified Python implementation remains the oracle."""
def install():
    import hashlib
    from pathlib import Path
    import platform
    import sys
    import numpy as np
    import mujoco
    import mjarena.envs.detailed_observations as reference
    import mjarena.envs.surface_distance as surface
    if (np.__version__ != '2.1.3' or mujoco.__version__ != '3.10.0'
            or sys.version_info[:2] != (3, 10) or platform.machine() != 'x86_64'):
        raise RuntimeError('Observation acceleration requires validated x86-64 Python 3.10, NumPy 2.1.3, MuJoCo 3.10.0')
    blas = np.__config__.CONFIG.get('Build Dependencies', {}).get('blas', {})
    if (blas.get('name') != 'scipy-openblas' or blas.get('version') != '0.3.27'
            or 'USE64BITINT' not in blas.get('openblas configuration', '')):
        raise RuntimeError('Native kernels require NumPy scipy-openblas 0.3.27 with 64-bit BLAS integers')
    for module, expected in [
        (reference, '1ffd806f01dc8ec65c781ac765818628c0b5dd22bbadb44cf25a62c604f0628b'),
        (surface, 'fda3c36d56bf11d62fa5236273184d85bb7575cd3e27b62be907a42c6f0f1408'),
    ]:
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Reference observation code differs from validated ea50df62 baseline')
    from ._details import DetailedObservations
    reference.DetailedObservations = DetailedObservations
