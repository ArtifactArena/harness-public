"""Native adversarial observation tests."""
import importlib.util
from pathlib import Path
import sys

directory = Path(__file__).parent / 'support'
for name in ('observation_stress', 'observation_adversarial'):
    spec = importlib.util.spec_from_file_location(name, directory / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

test_generated_name_collisions = module.check_generated_name_collisions
test_nondefault_control_timing = module.check_nondefault_control_timing
test_mesh_grazing_containment = module.check_mesh_grazing_containment
test_mesh_winding_oracle = module.check_mesh_winding_oracle
test_mesh_surface_certificate = module.check_mesh_surface_certificate
test_generated_articulation_names = module.check_generated_articulation_names
test_extreme_shape_gaps = module.check_extreme_shape_gaps
test_long_motion_and_resets = module.check_long_motion_and_resets
