"""mapkit.walkable: categories, reachability and cut-off areas on a synthetic grid."""
import unittest

import numpy as np

from mapworkshop.formats.map import Map
from mapworkshop.mapkit import walkable
from mapworkshop.mapkit.blank import create, starts


def grid(ground, layers=()):
    return dict(ground=np.asarray(ground, np.uint32), layers=list(layers), info={})


class WalkableTests(unittest.TestCase):
    def setUp(self):
        # 100 x 60 cells; a river of cliff cells at x 48..51 with no crossing.
        self.ground = np.zeros((60, 100), np.uint32)
        self.ground[:, 48:52] = 2
        self.ground[:, 47] = 7
        self.ground[30, 20:23] = 4 | (1 << 4)          # a building; the layer bits are ignored
        self.ground[5:9, 70:74] = 1                     # shallow water
        self.m = create(100, 64, 3)
        starts(self.m, [(150, 300), (850, 300)])
        self.m = Map(self.m.encode())

    def test_categories(self):
        kinds = walkable.categories(grid(self.ground))
        self.assertEqual(kinds[0, 0], walkable.WALK)
        self.assertEqual(kinds[0, 50], walkable.BLOCKED)
        self.assertEqual(kinds[0, 47], walkable.BLOCKED)
        self.assertEqual(kinds[30, 21], walkable.BLOCKED)
        self.assertEqual(kinds[6, 71], walkable.SHALLOW)

    def test_both_banks_reached_from_their_starts(self):
        result = walkable.analyse(grid(self.ground), self.m)
        self.assertEqual(result['cut_off'], [])
        self.assertTrue(result['reached'][0, 0] and result['reached'][0, 99])

    def test_a_bank_without_start_is_cut_off_until_a_bridge_joins_it(self):
        m = create(100, 64, 3)
        starts(m, [(150, 300), (160, 100)])
        m = Map(m.encode())
        result = walkable.analyse(grid(self.ground), m)
        self.assertEqual(len(result['cut_off']), 1)
        area = result['cut_off'][0]
        self.assertEqual(area['box'][0], 520)
        self.assertEqual(area['box'][2], 1000)
        self.assertEqual(tuple(walkable.overlay(result)[0, 80]), walkable.CUT_OFF)
        # A spanned bridge's layer: deck cells (type 0) across the river at y 20..22.
        deck = np.full((3, 10), 5, np.uint32)
        deck[:, :] = 0
        layer = dict(index=2, x0=45, y0=20, width=10, height=3, bridge=True, cells=deck)
        bridged = walkable.analyse(grid(self.ground, [layer]), m)
        self.assertEqual(bridged['cut_off'], [])
        self.assertEqual(bridged['categories'][21, 50], walkable.BRIDGE)


if __name__ == '__main__':
    unittest.main()
