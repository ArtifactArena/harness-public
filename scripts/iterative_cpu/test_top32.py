"""Small adversarial checks for pruning after the proximity list is full.

Run in the pinned environment after building the observation extensions.
"""
from types import SimpleNamespace
import unittest
import numpy as np
from mjarena.envs.observation_accel._details import DetailedObservations


class Queries:
    def __init__(self, positions):
        self.positions = positions
        self.calls = []

    def update(self, data):
        pass

    def distances(self, data, pairs):
        self.calls.extend(pairs)
        result = []
        for a, b in pairs:
            pa, pb = self.positions[a].copy(), self.positions[b].copy()
            d = float(np.linalg.norm(pb - pa))
            result.append((0. if d < 1e-10 else d, pa, pb))
        return result


class Top32Tests(unittest.TestCase):
    def check_positions(self, xs, *, fewer_queries=False):
        positions = np.zeros((len(xs) + 1, 3))
        positions[:-1, 0] = xs
        data = SimpleNamespace(qpos=np.zeros(0), qvel=np.zeros(0))
        observer = DetailedObservations.__new__(DetailedObservations)
        observer.env = SimpleNamespace(t=1, data=data)
        observer.model = SimpleNamespace(nmocap=0)
        observer.data = data
        observer.cached = None
        observer.prefixes = ['red_', 'blue_']
        observer.ids = {'red_': ([], list(range(len(xs)))),
                        'blue_': ([], [len(xs)])}
        observer.radii = np.zeros(len(positions))
        observer.queries = Queries(positions)
        observer.forward_observation = lambda: True
        observer._robot = lambda prefix: {}
        observer._point_velocity = lambda *args: np.zeros(3)
        _, actual, minimum, total = observer.snapshot()
        oracle = Queries(positions)
        pairs = [(a, len(xs)) for a in range(len(xs))]
        values = oracle.distances(data, pairs)
        expected = sorted([(d, a, b, pa, pb)
                           for (a, b), (d, pa, pb) in zip(pairs, values) if d <= 2.],
                          key=lambda p: (p[0], p[1], p[2]))
        self.assertEqual(minimum, min(v[0] for v in values))
        self.assertEqual(total > 32, len(expected) > 32)
        self.assertEqual([(r[0], r[1], r[2]) for r in actual],
                         [(r[0], r[1], r[2]) for r in expected[:32]])
        for got, want in zip(actual, expected[:32]):
            self.assertEqual(got[3].tobytes(), want[3].tobytes())
            self.assertEqual(got[4].tobytes(), want[4].tobytes())
        if fewer_queries:
            self.assertLess(len(observer.queries.calls), len(pairs))

    def test_prunes_distant_pairs_but_keeps_late_global_minimum(self):
        self.check_positions([.1] * 33 + [1.5] * 30 + [.01], fewer_queries=True)

    def test_equal_distance_ties_keep_geometry_order(self):
        self.check_positions([.25] * 64)

    def test_near_zero_distance_retains_gjk_zero_threshold(self):
        self.check_positions([0.] * 33 + [5e-11] * 31)

    def test_exactly_32_is_not_truncated(self):
        self.check_positions([.5] * 32 + [3.] * 10)

    def test_minimum_still_reported_when_all_pairs_exceed_cutoff(self):
        self.check_positions([4.] * 30 + [2.5])


if __name__ == '__main__':
    unittest.main()
