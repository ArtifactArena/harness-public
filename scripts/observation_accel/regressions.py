"""Run the existing harness suites with accelerated observations and paired queries."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
import mjarena.core.unified_builder
import mjarena.envs
mjarena.envs.__path__.insert(0, str(Path(os.environ['OBS_OVERLAY']) / 'mjarena/envs'))
from validate import exact
from mjarena.envs import surface_distance as reference
from mjarena.envs.observation_accel import _surface as fast_module
from mjarena.envs.observation_accel._surface import SurfaceQueries as FastQueries
from mjarena.envs.observation_accel import install

class ComparedQueries(reference.SurfaceQueries):
    def __init__(self, model):
        super().__init__(model)
        self.fast = FastQueries(model)
    def update(self, data):
        super().update(data)
        self.fast.update(data)
    def distance(self, data, a, b):
        result = super().distance(data, a, b)
        # The certificate adversarial test intentionally monkeypatches this
        # hook. Apply its test condition equally to both implementations.
        original = fast_module._on_mesh_surface
        fast_module._on_mesh_surface = reference._on_mesh_surface
        try:
            candidate = self.fast.distance(data, a, b)
        finally:
            fast_module._on_mesh_surface = original
        exact(result, candidate, f'geoms/{a}/{b}')
        return candidate

reference.SurfaceQueries = ComparedQueries
install()
import pytest
raise SystemExit(pytest.main(['-q',
    'tests_environment/test_detailed_observations.py',
    'tests_environment/test_observation_stress.py',
    'tests_environment/test_observation_adversarial.py',
    'tests_environment/test_contact_force_observation.py']))
