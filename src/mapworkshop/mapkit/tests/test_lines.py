"""Distances to polylines: the reach-limited sweep gives the full sweep's values."""

import math
import unittest

import numpy as np

from mapworkshop.mapkit.lines import nearest, polyline_distance


def grid(w=120, h=90, border=5):
    y, x = (np.mgrid[0:h, 0:w]-border)*10.0
    return x, y


LINE = [(50, 60), (300, 80), (300, 80), (420, 400), (900, 520), (1300, 200)]   # with a zero-length segment


class LineTests(unittest.TestCase):
    def test_full_sweep(self):
        x, y = grid()
        d, along = polyline_distance(LINE, x, y)
        self.assertAlmostEqual(float(d[5+6, 5+5]), 0.0)                 # on the first point, (50, 60)
        # (900, 520) is the fourth point: its arc length is the first three segments.
        self.assertAlmostEqual(float(d[5+52, 5+90]), 0.0)
        self.assertAlmostEqual(float(along[5+52, 5+90]), math.dist((50, 60), (300, 80))+math.dist((300, 80), (420, 400))
                               + math.dist((420, 400), (900, 520)), places=6)

    def test_reach_is_exact_within_it(self):
        x, y = grid()
        full_d, full_along = polyline_distance(LINE, x, y)
        for reach in (35, 120, 400):
            d, along = polyline_distance(LINE, x, y, reach)
            inside = full_d <= reach
            np.testing.assert_array_equal(d[inside], full_d[inside])
            np.testing.assert_array_equal(along[inside], full_along[inside])
            self.assertTrue(np.isinf(d[~inside]).all())

    def test_nearest_of_several(self):
        x, y = grid()
        other = [(1100, 700), (100, 650)]
        np.testing.assert_array_equal(nearest([LINE, other], x, y),
                                      np.minimum(polyline_distance(LINE, x, y)[0], polyline_distance(other, x, y)[0]))
        full = nearest([LINE, other], x, y)
        near = nearest([LINE, other], x, y, reach=200)
        np.testing.assert_array_equal(near[full <= 200], full[full <= 200])

    def test_reach_needs_a_grid(self):
        with self.assertRaises(ValueError):
            polyline_distance(LINE, np.array([1., 2.]), np.array([3., 4.]), reach=10)


if __name__ == '__main__':
    unittest.main()
