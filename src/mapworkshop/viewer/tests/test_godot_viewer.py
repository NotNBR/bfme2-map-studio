"""The Godot viewer's Python side (viewer/godot_viewer.py): the surface it sends and views resolved as mw render
resolves them; and, when OpenBFME is built, the viewer itself, headless: it opens a map through OpenBFME's library (a
lab's build from the user maps folder, else a stock map) and its camera projects map points onto the pixels mw
render's does."""
import re
import unittest
from unittest import mock

import numpy as np

from mapworkshop import project
from mapworkshop.native import openbfme
from mapworkshop.viewer import godot_viewer


class FakeMap:
    """A 6 x 5 sample height map with a border of 1 (a 30 x 40 playable area: 3 x 4 cells)."""

    def heightmap(self):
        elevations = (np.arange(30, dtype=np.uint16).reshape(6, 5)*256)
        return dict(width=5, height=6, border=1, borders=[(3, 4)], elevations=elevations)


LAKE = dict(water_height=300, points=[(-5, -5), (15, -5), (15, 15), (-5, 15)])


class SurfaceTests(unittest.TestCase):
    def test_standing_water_raises_the_samples_it_covers(self):
        with mock.patch.object(godot_viewer, 'records', return_value=[LAKE]):
            s = godot_viewer.Surface(FakeMap())
        heights = FakeMap().heightmap()['elevations']*0.0390625
        self.assertEqual(s.playable, (30.0, 40.0))
        # samples (0, 0) and (10, 10) in map units are inside the lake; their terrain is lower, so they are its level
        self.assertEqual(s.heights[1, 1], 300.0)
        self.assertEqual(s.heights[2, 2], 300.0)
        self.assertAlmostEqual(float(s.heights[4, 3]), float(heights[4, 3]))   # outside: the terrain's own
        self.assertAlmostEqual(float(s.height_at(0, 0)), 300.0)
        self.assertAlmostEqual(float(s.terrain.height_at(0, 0)), float(heights[1, 1]))

    def test_views_resolve_on_the_terrain_under_the_water(self):
        with mock.patch.object(godot_viewer, 'records', return_value=[LAKE]):
            s = godot_viewer.Surface(FakeMap())
        camera = godot_viewer.resolve('target=0,0 distance=500', s.terrain, (1600, 1000))
        # as mw render: the target stands on the terrain (sample (1, 1): 6 * 256 * 0.0390625), not on the lake
        self.assertAlmostEqual(camera['target'][2], 60.0)

    def test_without_water_it_is_the_terrain(self):
        with mock.patch.object(godot_viewer, 'records', return_value=[]):
            s = godot_viewer.Surface(FakeMap())
        self.assertAlmostEqual(float(s.height_at(5, 5)),
                               float(np.mean(FakeMap().heightmap()['elevations'][1:3, 1:3]*0.0390625)), places=4)


class FlatTerrain:
    def height_at(self, x, y):
        return np.zeros_like(np.asarray(x, float)) + 20.0


class ViewTests(unittest.TestCase):
    def test_a_view_resolves_to_its_eye_target_field_of_view_and_orbit(self):
        camera = godot_viewer.resolve('target=500,600 distance=1000 elevation=30 heading=90 fov=40', FlatTerrain(),
                                      (1600, 1000))
        self.assertAlmostEqual(camera['fov'], 40.0, places=6)
        self.assertEqual(camera['target'], [500.0, 600.0, 20.0])
        # heading 90: the camera stands west of the target and looks east
        self.assertAlmostEqual(camera['eye'][0], 500 - 1000*np.cos(np.radians(30)), places=6)
        self.assertAlmostEqual(camera['eye'][2], 20 + 500, places=6)
        # the Edit camera orbits the target from the eye: viewer.camera.Camera.aim's goal
        self.assertEqual(camera['orbit']['x'], 500.0)
        self.assertAlmostEqual(camera['orbit']['heading'], 90.0, places=6)
        self.assertAlmostEqual(camera['orbit']['elevation'], 30.0, places=6)
        self.assertAlmostEqual(camera['orbit']['distance'], 1000.0, places=6)
        x, y = godot_viewer.pixel(camera['view_projection'], camera['target'], (1600, 1000))
        self.assertAlmostEqual(x, 800.0, places=6)
        self.assertAlmostEqual(y, 500.0, places=6)

    def test_a_focal_length_frames_the_view(self):
        camera = godot_viewer.resolve('target=0,0 distance=800 focal=50 aperture=2', FlatTerrain(), (1500, 1000))
        self.assertAlmostEqual(camera['fov'], 2*np.degrees(np.arctan(18/50)), places=6)   # 36 mm wide at 3:2

    def test_a_top_view_is_refused(self):
        with self.assertRaises(RuntimeError):
            godot_viewer.resolve('kind=top', FlatTerrain(), (1600, 1000))


def lab():
    """A lab map with a build (opened from the user maps folder), else a stock map (from the archives)."""
    for name in ('blend-lab', 'water-lab'):
        try:
            if project.find(name).map_file.exists():
                return name
        except LookupError:
            pass
    return 'map mp evendim'


@unittest.skipUnless(openbfme.is_built() and openbfme.status()[0],
                     'the Godot viewer needs OpenBFME built for its pin and the game files (mw play --godot sets '
                     'both up)')
class LibraryTests(unittest.TestCase):
    def test_the_viewer_opens_a_map_and_projects_as_mw_render(self):
        code, lines = godot_viewer.run(lab(), 'target=200,300 distance=900 elevation=35 heading=20',
                                       probes=[(200, 300), (420, 120)], check=True, progress=lambda line: None,
                                       timeout=300)
        text = '\n'.join(line for line in lines if line.startswith('VIEWER'))
        self.assertEqual(code, 0, text)
        self.assertIn('VIEWER check ok', text)
        self.assertIn('MapObjects', text)          # the object layer, which key 1 switches
        apart = [float(v) for v in re.findall(r'([\d.]+) px apart', text)]
        self.assertEqual(len(apart), 2, text)
        self.assertLess(max(apart), 0.01, text)


if __name__ == '__main__':
    unittest.main()
