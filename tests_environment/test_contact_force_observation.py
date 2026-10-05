"""Opponent force is a sum of force magnitudes, excluding contact torques."""
from types import SimpleNamespace
from unittest.mock import patch

from mjarena.envs.sumo import SumoEnv


def test_contact_force_observation():
    env = object.__new__(SumoEnv)
    env.model = object()
    env.red_contender = SimpleNamespace(prefix='red_')
    env.blue_contender = SimpleNamespace(prefix='blue_')
    env._contender_geom_ids = {'red_': [1, 2], 'blue_': [3]}
    env._boundary_geom_id = 0
    env.data = SimpleNamespace(ncon=4, contact=[
        SimpleNamespace(geom1=1, geom2=3),
        SimpleNamespace(geom1=3, geom2=2),
        SimpleNamespace(geom1=0, geom2=1),  # Platform: excluded from opponent force.
        SimpleNamespace(geom1=1, geom2=2),  # Self-contact: excluded.
    ])
    for torque in (0.0, 1e6):
        def contact_force(model, data, index, buffer):
            assert index in (0, 1)
            sign = 1 if index == 0 else -1
            buffer[:] = [3 * sign, 4 * sign, 0, torque, -torque, torque]

        with patch('mjarena.envs.sumo.mujoco.mj_contactForce', side_effect=contact_force):
            # Opposite forces still contribute 5 N each, rather than canceling.
            assert env.get_contact_info('red_') == (True, 10.0, True)
            assert env.get_contact_info('blue_') == (True, 10.0, False)

    env.data = SimpleNamespace(ncon=1, contact=[SimpleNamespace(geom1=0, geom2=1)])
    with patch('mjarena.envs.sumo.mujoco.mj_contactForce') as force:
        assert env.get_contact_info('red_') == (False, 0.0, True)
        force.assert_not_called()


if __name__ == '__main__':
    test_contact_force_observation()
    print('PASS: opponent forces exclude torques, ground contacts, and self-contact')
