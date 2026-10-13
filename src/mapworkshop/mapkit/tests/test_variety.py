"""Per-object random numbers depend only on the seed and the object."""
import unittest

from mapworkshop.mapkit.variety import spot_random


class VarietyTests(unittest.TestCase):
    def test_same_object_same_numbers(self):
        self.assertEqual(spot_random(7, 'TreeA', 100.04, 200).random(), spot_random(7, 'TreeA', 100, 200.0).random())
        # A fixed value: the numbers must not depend on the process (no Python hash()).
        self.assertAlmostEqual(spot_random(7, 'TreeA', 100, 200).random(), 0.7486401559464096)

    def test_seed_template_and_place_each_matter(self):
        base = spot_random(7, 'TreeA', 100, 200).random()
        for other in (spot_random(8, 'TreeA', 100, 200), spot_random(7, 'TreeB', 100, 200),
                      spot_random(7, 'TreeA', 100.5, 200)):
            self.assertNotEqual(other.random(), base)


if __name__ == '__main__':
    unittest.main()
