"""render.photo and the photo keys of render.camera views, without a GL context."""
import math
import unittest

import numpy as np

from mapworkshop.render.camera import look_at, parse_view, rolled
from mapworkshop.render.photo import (active, blur_pixels, focal_from_fov, fov_from_focal, image_size, sensor,
                                      sharp_range)


class Terrain:
    def height_at(self, x, y):
        return 0.0


class LensTests(unittest.TestCase):
    def test_focal_length_and_field_of_view_agree(self):
        self.assertAlmostEqual(fov_from_focal(focal_from_fov(50.0)), 50.0)
        self.assertAlmostEqual(fov_from_focal(18.0), 90.0)              # half the 36 mm sensor: 45 degrees each side
        self.assertAlmostEqual(focal_from_fov(50.0), 38.6, places=1)
        self.assertAlmostEqual(fov_from_focal(12.0, 24.0), 90.0)

    def test_each_frame_is_the_largest_crop_of_the_full_frame_sensor(self):
        self.assertEqual(sensor(1.5), (36.0, 24.0))
        self.assertEqual(sensor(16/9), (36.0, 20.25))
        self.assertEqual(sensor(1.0), (24.0, 24.0))
        self.assertEqual(sensor(4/3), (32.0, 24.0))
        self.assertAlmostEqual(sensor(0.8)[1], 24.0)                     # portrait: 24 mm tall
        # A window shows its frame at the sensor's scale and more around it.
        self.assertEqual(image_size(16/9, 1.0), (24.0*16/9, 24.0))
        self.assertEqual(image_size(1.0, 16/9), (36.0, 36.0))
        self.assertEqual(image_size(16/9), sensor(16/9))

    def test_the_sharp_range_closes_in_on_the_focus_as_the_aperture_opens(self):
        near, far = sharp_range(500, 50, 2.8)
        self.assertLess(near, 500)
        self.assertGreater(far, 500)
        wide = sharp_range(500, 50, 1.4)
        self.assertLess(wide[1]-wide[0], far-near)
        # 50 mm at f/8 on full frame: hyperfocal about 10.9 m, so focused at 11 m all is sharp to infinity...
        self.assertEqual(sharp_range(110, 50, 8)[1], math.inf)
        # ...and from half the hyperfocal distance.
        self.assertAlmostEqual(sharp_range(110, 50, 8)[0], 54, delta=2)

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

    def test_a_roll_to_the_right_turns_the_picture_to_the_left(self):
        view = look_at(np.zeros(3), np.array([0.0, 1000.0, 0.0]))
        above = np.array([0.0, 1000.0, 100.0, 1.0])                         # a point above the centre
        right = rolled(view, 90) @ above
        self.assertAlmostEqual(right[1], 0.0, places=6)
        self.assertLess(right[0], -99.0)                                   # the sky is now on the left
        self.assertLess((rolled(view, 10) @ above)[0], 0.0)
        self.assertIs(rolled(view, 0), view)

    def test_a_focal_length_frames_the_same_crop_at_every_aspect(self):
        view = parse_view('eye=0,0,0 target=0,1000,0 focal=50'.split())
        for aspect in (16/9, 1.5, 4/3, 1.0):
            camera = view.resolve(Terrain(), aspect)
            width, height = sensor(aspect)
            self.assertAlmostEqual(camera['sensor'], width)
            # The top edge of the picture is 12 mm (or half the crop's height) off the axis at 50 mm.
            edge = math.atan(height/2/50)
            p = camera['view_projection'] @ np.array([0.0, 1000.0, 1000*math.tan(edge), 1.0])
            self.assertAlmostEqual(p[1]/p[3], 1.0, places=6)

    def test_a_field_of_view_gives_the_lens_its_focal_length(self):
        camera = parse_view('eye=0,0,0 target=0,1000,0 fov=50 aperture=2'.split()).resolve(Terrain(), 16/9)
        self.assertAlmostEqual(camera['photo']['focal'], focal_from_fov(50.0))

    def test_unknown_keys_are_refused(self):
        with self.assertRaises(ValueError):
            parse_view('target=0,0 bokeh=5'.split())


if __name__ == '__main__':
    unittest.main()
