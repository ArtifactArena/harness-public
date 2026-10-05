"""Run with the pinned harness Python and Cython 3.1.4 available on PYTHONPATH."""
from pathlib import Path
from setuptools import Extension, setup
import numpy as np
import mujoco
from Cython.Build import cythonize

root = Path(__file__).resolve().parents[3]
names = ['_helpers', '_surface', '_contacts', '_details']
extensions = [Extension('mjarena.envs.observation_accel.' + name,
                       [str(Path(__file__).parent / (name + '.pyx'))],
                       include_dirs=[np.get_include(), str(Path(mujoco.__file__).parent / 'include')],
                       extra_compile_args=['-O3', '-fno-fast-math', '-ffp-contract=off'])
              for name in names]
setup(name='arena-exact-observation-accel',
      ext_modules=cythonize(extensions, compiler_directives={
          'language_level': 3, 'infer_types': False, 'binding': True,
      }, build_dir=str(root / 'build' / 'cython')))
