"""formats.terrain: the playable extent the game takes from HeightMapData."""
import unittest

from mapworkshop.formats.terrain import playable_extent


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
