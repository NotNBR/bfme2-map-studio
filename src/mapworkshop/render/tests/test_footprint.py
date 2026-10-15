"""Model outlines (render.footprint) on boxes made here, without game data."""
import math
import unittest

import numpy as np

from mapworkshop.render.footprint import _matches, area, footprint_of, section_of, to_world


def box(x0, x1, y0, y1, z0, z1, inward=False):
    """A closed box of 12 triangles, each facing out (or in)."""
    c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    middle = c.mean(0)
    tris = []
    for a, b, d, e in quads:
        for tri in ((a, b, d), (a, d, e)):
            t = c[list(tri)]
            facing = np.cross(t[1] - t[0], t[2] - t[0]) @ (t.mean(0) - middle)
            if (facing < 0) != inward:
                t = t[::-1]
            tris.append(t)
    return np.array(tris)


def extent(points):
    p = np.asarray(points)
    return p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()


class SectionTests(unittest.TestCase):
    def test_a_box_cut_through_is_its_rectangle(self):
        outlines = section_of([box(-10, 30, 5, 25, 0, 20)], 10)
        self.assertEqual(len(outlines), 1)
        self.assertEqual(extent(outlines[0]), (-10, 30, 5, 25))
        self.assertEqual(len(outlines[0]), 4)                      # straight edges stay straight
        self.assertAlmostEqual(area(outlines[0]), 800)             # counter-clockwise: solid

    def test_above_or_below_there_is_nothing(self):
        self.assertEqual(section_of([box(0, 10, 0, 10, 0, 20)], 25), [])
        self.assertEqual(section_of([box(0, 10, 0, 10, 0, 20)], -1), [])

    def test_overlapping_solids_in_one_mesh_join(self):
        # Even-odd would cancel the overlap; the cut must be one L-shaped solid.
        part = np.concatenate([box(0, 20, 0, 10, 0, 10), box(10, 20, 0, 30, 0, 10)])
        outlines = section_of([part], 5)
        self.assertEqual(len(outlines), 1)
        self.assertAlmostEqual(area(outlines[0]), 20*10 + 10*20)

    def test_a_hollow_gives_a_clockwise_hole(self):
        part = np.concatenate([box(0, 40, 0, 40, 0, 10), box(10, 30, 10, 30, -1, 11, inward=True)])
        outlines = section_of([part], 5)
        self.assertEqual(len(outlines), 2)
        self.assertAlmostEqual(area(outlines[0]), 1600)
        self.assertAlmostEqual(area(outlines[1]), -400)

    def test_faces_turned_inwards_still_fill(self):
        outlines = section_of([box(0, 10, 0, 10, 0, 10, inward=True)], 5)
        self.assertEqual(extent(outlines[0]), (0, 10, 0, 10))


class FootprintTests(unittest.TestCase):
    def test_the_ground_covered_from_above(self):
        parts = [box(0, 10, 0, 10, 0, 5), box(20, 30, 0, 10, 0, 5)]
        outlines = footprint_of(parts)
        self.assertEqual(sorted(extent(p) for p in outlines), [(0, 10, 0, 10), (20, 30, 0, 10)])

    def test_a_band_of_heights(self):
        parts = [box(0, 10, 0, 10, 0, 5), box(0, 40, 0, 10, 20, 25)]       # a post under a beam
        self.assertEqual([extent(p) for p in footprint_of(parts, high=10)], [(0, 10, 0, 10)])
        self.assertEqual([extent(p) for p in footprint_of(parts, low=10)], [(0, 40, 0, 10)])
        self.assertEqual(footprint_of(parts, low=6, high=19), [])

    def test_a_slope_clipped_to_a_band(self):
        ramp = np.array([[[0, 0, 0], [40, 0, 40], [40, 20, 40]], [[0, 0, 0], [40, 20, 40], [0, 20, 0]]], float)
        self.assertEqual(extent(footprint_of([ramp], low=10, high=30)[0]), (10, 30, 0, 20))


class PlacingTests(unittest.TestCase):
    def test_to_world_turns_counter_clockwise_and_moves(self):
        self.assertEqual(to_world([(10, 0)], 100, 200, math.pi/2), [(100, 210)])
        self.assertEqual(to_world([(0, 10, 5)], 100, 200, math.pi/2, z=50), [(90, 200, 55)])

    def test_matching_names(self):
        self.assertTrue(_matches('bridge', 'GondorIthilienBridge2'))
        self.assertTrue(_matches('*Bridge?', 'GondorIthilienBridge2'))
        self.assertTrue(_matches('waypoint', '*Waypoints/Waypoint'))
        self.assertTrue(_matches('Waypoint', '*Waypoints/Waypoint'))
        self.assertFalse(_matches('*tree', 'GondorIthilienBridge2'))


if __name__ == '__main__':
    unittest.main()
