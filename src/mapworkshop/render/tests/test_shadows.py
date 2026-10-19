"""MapRenderer's shadow-map projection, without a GL context."""
import types
import unittest

import numpy as np

from mapworkshop.render.camera import look_at, perspective
from mapworkshop.render.engine import MapRenderer


def renderer():
    r = MapRenderer.__new__(MapRenderer)
    r.terrain = types.SimpleNamespace(heights=np.full((10, 10), 100.0), mean_height=100.0, max_height=100.0)
    sun = np.array([0.4, -0.3, 0.8])
    r.sun_dir = tuple(sun/np.linalg.norm(sun))
    r.shadow_settings = dict(texel=2*1500/1024)
    r.options = dict(shadows='map')
    return r


def camera(eye, target, ground=None):
    vp = perspective(40.0, 1.6, 2.0, 80000.0) @ look_at(eye, target)
    cam = dict(view_projection=vp, eye=np.asarray(eye, float), target=np.asarray(target, float))
    if ground is not None:
        cam['ground'] = np.asarray(ground, float)
    return cam


def texel_of(light_vp, size, point):
    """The shadow-map texel (column, row) and its fraction a world point falls in."""
    p = light_vp @ np.array([*point, 1.0])
    uv = (p[:2]/p[3]*0.5+0.5)*size
    return np.floor(uv), uv-np.floor(uv)


class ShadowProjectionTests(unittest.TestCase):
    def test_a_point_keeps_its_place_within_a_texel_as_the_camera_moves(self):
        # Shadow edges are point-sampled: if the map shifted by part of a texel,
        # every edge would jump as the camera moved.
        r, point = renderer(), (1500.0, 2400.0, 100.0)
        fractions = []
        for dx in (0.0, 0.37, 1.9, 13.3):
            eye = (1710.0+dx, 2469.0, 121.0)
            vp, size, _ = r._light_projection(camera(eye, (1560.0+dx, 2444.0, 103.0)), max_radius=4000.0,
                                              max_size=4096)
            fractions.append(texel_of(vp, size, point)[1])
        for f in fractions[1:]:
            np.testing.assert_allclose(f, fractions[0], atol=1e-4)

    def test_the_window_covers_the_footprint_on_the_game_texel(self):
        r = renderer()
        vp, size, _ = r._light_projection(camera((0.0, -800.0, 1500.0), (0.0, 0.0, 100.0)))
        texel = r.shadow_settings['texel']
        self.assertAlmostEqual(2/np.linalg.norm(vp[0, :3]), size*texel, places=3)     # the window's width
        for corner in ((-500.0, 0.0, 100.0), (500.0, 600.0, 100.0)):
            p = vp @ np.array([*corner, 1.0])
            self.assertTrue(np.all(np.abs(p[:3]/p[3]) < 1.0), corner)

    def test_a_ground_point_holds_the_shadows_where_the_target_moves(self):
        # Photo mode's target is the point in focus; refocusing must not move the shadows.
        r = renderer()
        eye = np.array([1710.0, 2469.0, 121.0])
        ahead = np.array([-0.98, -0.16, -0.12])
        ground = (eye[0]-1960.0, eye[1]-320.0, 100.0)
        first = r._light_projection(camera(eye, eye+ahead*150.0, ground), max_radius=4000.0, max_size=4096)
        for focus in (151.0, 173.0, 5000.0):
            vp, size, depth = r._light_projection(camera(eye, eye+ahead*focus, ground), max_radius=4000.0,
                                                  max_size=4096)
            np.testing.assert_allclose(vp, first[0])
            self.assertEqual(size, first[1])
            self.assertAlmostEqual(depth, first[2], places=6)


if __name__ == '__main__':
    unittest.main()
