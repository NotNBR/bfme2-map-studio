"""formats.terrain: the playable extent the game takes from HeightMapData, and heights between its samples."""
import unittest

import numpy as np

from mapworkshop.formats.terrain import height_at, playable_extent


class PlayableExtentTests(unittest.TestCase):
    def test_a_standard_map_is_its_border_record_times_ten(self):
        # W x H samples with a border of B: the record is (W - 2B, H - 2B), not one sample less.
        self.assertEqual(playable_extent(dict(width=900, height=1010, border=30, borders=[(840, 950)])),
                         (8400.0, 9500.0))

    def test_the_largest_record_wins_on_each_axis(self):
        heights = dict(width=405, height=355, border=40, borders=[(325, 200), (100, 275)])
        self.assertEqual(playable_extent(heights), (3250.0, 2750.0))

    def test_without_records_the_samples_inside_the_border(self):
        self.assertEqual(playable_extent(dict(width=160, height=120, border=30, borders=[])), (1000.0, 600.0))


if __name__ == '__main__':
    unittest.main()


class HeightAtTests(unittest.TestCase):
    def test_bilinear_between_samples_from_the_playable_origin(self):
        heights = np.array([[0, 10, 20], [30, 40, 50], [60, 70, 80]], float)     # border 1: map (0, 0) is sample (1, 1)
        self.assertEqual(float(height_at(heights, 1, 0, 0)), 40.0)
        self.assertEqual(float(height_at(heights, 1, 5, 5)), 60.0)                # halfway to sample (2, 2)
        self.assertTrue(np.allclose(height_at(heights, 1, np.array([-10, 5]), np.array([0, 0])), [30.0, 45.0]))

    def test_points_off_the_grid_take_its_edge(self):
        heights = np.array([[0, 10], [20, 30]], float)
        self.assertAlmostEqual(float(height_at(heights, 0, 500, 500)), 30.0, places=1)
