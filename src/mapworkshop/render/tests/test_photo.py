"""render.photo and the photo keys of render.camera views, without a GL context."""
import math
import unittest

import numpy as np

from mapworkshop.render.camera import look_at, parse_view, rolled
from mapworkshop.render.photo import active, blur_pixels, focal_from_fov, fov_from_focal


class Terrain:
    def height_at(self, x, y):
        return 0.0


class LensTests(unittest.TestCase):
    def test_focal_length_and_field_of_view_agree(self):
        self.assertAlmostEqual(fov_from_focal(focal_from_fov(50.0)), 50.0)
        self.assertAlmostEqual(fov_from_focal(18.0), 90.0)              # half the 36 mm sensor: 45 degrees each side
        self.assertAlmostEqual(focal_from_fov(50.0), 38.6, places=1)

    def test_blur_is_none_at_the_focus_and_grows_away_from_it(self):
        sharp = blur_pixels(500, 500, 85, 1.4, 1920)
        near, far = blur_pixels(300, 500, 85, 1.4, 1920), blur_pixels(5000, 500, 85, 1.4, 1920)
        self.assertAlmostEqual(sharp, 0.0)
        self.assertGreater(near, 1.0)
        self.assertGreater(far, 1.0)
        # Stopping down shrinks it; focusing far away sharpens the whole map, as with a real lens.
        self.assertLess(blur_pixels(5000, 500, 85, 8, 1920), far/5)
        self.assertLess(blur_pixels(1500, 1100, 85, 1.4, 1920), 1.0)

    def test_only_an_aperture_or_an_exposure_changes_the_picture(self):
        self.assertFalse(active(dict(focal=35, aperture=None, ev=0.0)))
        self.assertTrue(active(dict(aperture=2.8)))
        self.assertTrue(active(dict(ev=-0.5)))


class ViewKeyTests(unittest.TestCase):
    def test_photo_keys_reach_the_resolved_camera(self):
        view = parse_view('eye=0,0,100 target=0,1000,0 focal=85 aperture=2.8 focus=600 ev=1 roll=5'.split())
        camera = view.resolve(Terrain(), 16/9)
        self.assertEqual(camera['photo'], dict(focal=85.0, aperture=2.8, ev=1.0, focus=600.0))
        self.assertIn('near', camera)
        self.assertGreater(camera['far'], camera['near'])

    def test_focus_defaults_to_the_target_and_focal_narrows_the_view(self):
        wide = parse_view('eye=0,0,0 target=0,1000,0'.split()).resolve(Terrain(), 1.0)
        tele = parse_view('eye=0,0,0 target=0,1000,0 focal=200'.split()).resolve(Terrain(), 1.0)
        self.assertAlmostEqual(wide['photo']['focus'], 1000.0)
        # A point 100 units to the side of the target lands further out on a longer lens.
        point = np.array([100.0, 1000.0, 0.0, 1.0])
        x = lambda cam: (cam['view_projection'] @ point)[0]/(cam['view_projection'] @ point)[3]
        self.assertGreater(x(tele), x(wide)*3)

    def test_roll_turns_the_picture_about_the_view_direction(self):
        view = look_at(np.zeros(3), np.array([0.0, 1000.0, 0.0]))
        right = rolled(view, 90) @ np.array([0.0, 1000.0, 100.0, 1.0])     # a point above the centre
        self.assertAlmostEqual(right[1], 0.0, places=6)
        self.assertGreater(abs(right[0]), 99.0)
        self.assertIs(rolled(view, 0), view)

    def test_unknown_keys_are_refused(self):
        with self.assertRaises(ValueError):
            parse_view('target=0,0 bokeh=5'.split())


if __name__ == '__main__':
    unittest.main()
