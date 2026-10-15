"""viewer.camera: the navigation moves, without a window."""
import math
import unittest

import numpy as np

from mapworkshop.viewer.camera import MAX_DISTANCE, MIN_DISTANCE, Camera


def camera():
    return Camera(lambda x, y: np.zeros_like(np.asarray(x, float)), (1000, 800))


class CameraTests(unittest.TestCase):
    def test_pan_keeps_the_grabbed_point_under_the_cursor(self):
        c = camera()
        x, y = c.goal['x'], c.goal['y']
        c.pan(np.array([100.0, 100.0, 0.0]), np.array([110.0, 90.0, 0.0]))
        self.assertEqual((c.goal['x'], c.goal['y']), (x-10, y+10))
        self.assertEqual((c.cur['x'], c.cur['y']), (x-10, y+10))

    def test_zoom_moves_towards_the_point_under_the_cursor(self):
        c = camera()
        toward = (c.goal['x']+300, c.goal['y'])
        before = c.goal['distance']
        c.zoom(1, toward)
        k = c.goal['distance']/before
        self.assertLess(k, 1)
        # The point keeps its place on screen: its offset from the focus shrinks with the distance.
        self.assertAlmostEqual(toward[0]-c.goal['x'], 300*k)

    def test_zoom_stays_within_its_limits(self):
        c = camera()
        c.zoom(100)
        self.assertEqual(c.goal['distance'], MIN_DISTANCE)
        c.zoom(-100)
        self.assertEqual(c.goal['distance'], MAX_DISTANCE)

    def test_top_view_toggles_back_to_the_earlier_tilt(self):
        c = camera()
        c.goal['elevation'] = 40.0
        c.toggle_top()
        self.assertEqual(c.goal['elevation'], 89.5)
        c.toggle_top()
        self.assertEqual(c.goal['elevation'], 40.0)

    def test_driving_keeps_the_focus_on_the_map(self):
        c = camera()
        for _ in range(100):
            c.drive(0.1, forward=1, right=1)
        self.assertEqual((c.goal['x'], c.goal['y']), (1000, 800))

    def test_orbit_keeps_the_tilt_between_its_limits(self):
        c = camera()
        c.orbit(40, 10000)
        self.assertEqual(c.goal['elevation'], 89.5)
        self.assertEqual(c.goal['heading'], 10.0)

    def test_new_rectangles_follow_the_screen_unless_nearly_north(self):
        c = camera()
        c.cur['heading'] = 5.0
        self.assertEqual(c.screen_angle(), 0.0)
        c.cur['heading'] = 30.0
        self.assertAlmostEqual(c.screen_angle(), -math.radians(30))


if __name__ == '__main__':
    unittest.main()
