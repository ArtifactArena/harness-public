"""Build with the harness's pinned NumPy/MuJoCo and Cython 3.1.4."""
from pathlib import Path
from setuptools import Extension,setup
from Cython.Build import cythonize
import numpy,mujoco
here=Path(__file__).parent
import runpy
runpy.run_path(str(here / "build_glue.py"))
setup(name='arena-exact-interval',ext_modules=cythonize([Extension('mjarena.envs.match_accel.'+name,[str(here/(name+'.pyx'))],include_dirs=[numpy.get_include(),str(Path(mujoco.__file__).parent/'include')],extra_compile_args=['-O3','-fno-fast-math','-ffp-contract=off']) for name in ['_interval','_bounds','_glue']],compiler_directives={'language_level':3,'binding':True},build_dir=str(here.parents[2]/'build/cython')))
