"""viewer.camera: the navigation moves, without a window."""
import math
import unittest

import numpy as np

from mapworkshop.viewer.camera import MAX_DISTANCE, MIN_DISTANCE, Camera, FlyCamera


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


def flat(x, y):
    return np.zeros_like(np.asarray(x, float))


class FlyCameraTests(unittest.TestCase):
    def test_entering_photo_mode_keeps_the_view(self):
        c = camera()
        cam = c.matrices(1.6)
        fly = FlyCamera(flat)
        fly.place(cam['eye'], cam['target']-cam['eye'], focus=float(np.linalg.norm(cam['target']-cam['eye'])))
        self.assertAlmostEqual(fly.heading, c.cur['heading'] % 360, places=6)
        self.assertAlmostEqual(fly.pitch, -c.cur['elevation'], places=6)
        np.testing.assert_allclose(fly.matrices(1.6)['view_projection'] @ np.array([*cam['target'], 1.0]),
                                   cam['view_projection'] @ np.array([*cam['target'], 1.0]), atol=1e-3, rtol=0.02)

    def test_back_to_edit_orbits_the_ground_photo_looked_at(self):
        c = camera()
        fly = FlyCamera(flat)
        fly.place(np.array([100.0, 100.0, 500.0]), np.array([0.0, 1.0, -1.0]))
        c.aim(fly.eye, fly.forward(), fly.pick_ahead((1600, 900)))
        self.assertAlmostEqual(c.goal['x'], 100.0, places=3)
        self.assertAlmostEqual(c.goal['y'], 600.0, places=1)
        self.assertAlmostEqual(c.goal['elevation'], 45.0, places=3)
        self.assertAlmostEqual(c.goal['heading'], 0.0, places=6)

    def test_looking_at_the_sky_still_finds_ground_to_orbit(self):
        c = camera()
        fly = FlyCamera(flat)
        fly.place(np.array([0.0, 0.0, 200.0]), np.array([1.0, 0.0, 0.5]))
        self.assertIsNone(fly.pick_ahead((1600, 900)))
        c.aim(fly.eye, fly.forward(), None)
        self.assertGreater(c.goal['x'], 0.0)
        self.assertEqual(c.goal['elevation'], max(5.0, c.goal['elevation']))
        self.assertAlmostEqual(c.goal['heading'], 90.0)

    def test_the_free_camera_has_no_ground_and_no_tilt_limit_but_vertical(self):
        fly = FlyCamera(flat)
        fly.place(np.array([0.0, 0.0, 50.0]), np.array([0.0, 1.0, 0.0]))
        fly.look(0, 1e6)
        self.assertAlmostEqual(fly.pitch, -89.9)
        fly.drive(10.0, up=-1)
        self.assertLess(fly.goal[2], 0.0)         # below the ground: allowed

    def test_lens_moves_stay_in_range(self):
        fly = FlyCamera(flat)
        fly.zoom(100)
        self.assertEqual(fly.focal, 600.0)
        fly.zoom(-100)
        self.assertEqual(fly.focal, 10.0)
        before = fly.focus
        fly.refocus(1)
        self.assertGreater(fly.focus, before)


if __name__ == '__main__':
    unittest.main()
