"""Native observation contract checks."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'observation_stress', Path(__file__).parent/'support/observation_stress.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)

test_false_zero_regression = checks.check_false_zero_regression
test_primitive_distances = checks.check_primitive_distances
test_sphere_oracles = checks.check_sphere_oracles
test_state_frames_and_rates = checks.check_state_frames_and_rates
test_unnamed_parts = checks.check_unnamed_parts
test_contact_impulses = checks.check_contact_impulses
test_mesh_containment_and_frames = checks.check_mesh_containment_and_frames
test_proximity_limits_and_rates = checks.check_proximity_limits_and_rates
test_time_and_solver_isolation = checks.check_time_and_solver_isolation
test_self_contacts_and_environment = checks.check_self_contacts_and_environment
test_rotated_box_intersections = checks.check_rotated_box_intersections
test_hollow_mesh = checks.check_hollow_mesh
test_wrapped_tendons_and_defaults = checks.check_wrapped_tendons_and_defaults
