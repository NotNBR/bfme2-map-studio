"""The Godot viewer's Python side (viewer/godot_viewer.py): the surface it sends, views resolved as mw render
resolves them and Preview's copies of a map; and, when OpenBFME is built, the viewer itself, headless: it opens a map
through OpenBFME's library (a lab's build from the user maps folder, else a stock map) and its camera projects map
points onto the pixels mw render's does."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mapworkshop import project
from mapworkshop.formats.lighting import decode
from mapworkshop.formats.map import Map
from mapworkshop.formats.sections import read
from mapworkshop.mapkit import blank
from mapworkshop.native import openbfme
from mapworkshop.viewer import godot_viewer
from mapworkshop.viewer import marks as marklib


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


class PreviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        patch = mock.patch.object(openbfme, 'user_maps', return_value=self.tmp/'Maps')
        patch.start()
        self.addCleanup(patch.stop)
        m = blank.create(64, 64, 4)
        blank.add_object(m, 'WaterReflectionSkydome_GapOfRohan', 200, 200)
        self.source = self.tmp/'build'/'map mp test.map'
        self.source.parent.mkdir()
        self.source.write_bytes(m.encode())
        self.source.with_name('map.ini').write_bytes(b'Weather\n  IsSnowing = yes\nEnd\n; caf\xe9 \x81\n')
        self.source.with_name('map.str').write_text('MAP:TEST\n"Test"\nEND\n', encoding='cp1252')

    def copy(self, name):
        folder = self.tmp/'Maps'/name
        return Map((folder/f'{name}.map').read_bytes()), (folder/'map.ini').read_bytes()

    def test_a_weather_and_a_sun_go_into_a_copy_of_the_map(self):
        name = godot_viewer.preview_map(self.source, 'map mp test', 'dusk', 'ember')
        self.assertEqual(name, 'map mp test studio preview')
        m, ini = self.copy(name)
        own = Map(self.source.read_bytes())
        self.assertEqual(dict((k, v) for k, _, v in read(m, 'WorldInfo'))['weather'], 4)        # dusk: SUNNY
        lit = lambda mm: decode(mm.chunk('GlobalLighting').data, mm.chunk('GlobalLighting').version)
        self.assertNotEqual(lit(m), lit(own))
        self.assertEqual([o['template'] for o in m.objects()], ['WaterReflectionSkydome_MinasMorgul'])  # the sun's
        self.assertNotIn(b'IsSnowing', ini)                       # the preset's Weather in place of the map's ...
        self.assertIn(b'; caf\xe9 \x81', ini)                     # ... the rest kept, byte for byte
        self.assertIn(b'HardwareFogStart = 4200', ini)
        self.assertTrue(ini.endswith(b'HardwareFogStart = 5000\n  HardwareFogEnd = 17000\nEnd\n'))  # the sun's last
        self.assertTrue((self.tmp/'Maps'/name/'map.str').is_file())
        self.assertEqual(Map(self.source.read_bytes()).encode(), own.encode())          # the map itself unchanged

    def test_a_sun_alone_keeps_the_maps_weather_under_its_fog(self):
        m, ini = self.copy(godot_viewer.preview_map(self.source, 'map mp test', sun='ash'))
        self.assertTrue(ini.startswith(b'Weather\n  IsSnowing = yes'))
        self.assertTrue(ini.endswith(b'HardwareFogEnd = 17000\nEnd\n'))

    def test_the_map_as_it_is_opens_itself_and_copies_are_removed(self):
        with mock.patch.object(godot_viewer, 'source', return_value=(self.source, 'map mp test', True, None)), \
                mock.patch.object(godot_viewer, 'SCENES', self.tmp/'scenes'), \
                mock.patch.object(marklib, 'MARKS_DIR', self.tmp/'marks'):
            data = godot_viewer.scene('test', preview=godot_viewer.OWN)[1]
            self.assertEqual((data['map'], data['preview']), ('map mp test', godot_viewer.OWN))
            self.assertFalse((self.tmp/'Maps').exists())
            data = godot_viewer.scene('test', preview=dict(weather='haze'))[1]
        self.assertEqual(data['map'], 'map mp test studio preview')
        m, ini = self.copy(data['map'])
        self.assertEqual([o['template'] for o in m.objects()], ['WaterReflectionSkydome_Celduin'])
        (self.tmp/'Maps'/'map mp other').mkdir()
        godot_viewer.remove_previews()
        self.assertEqual([p.name for p in (self.tmp/'Maps').iterdir()], ['map mp other'])


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
        # the lens, for Photo mode: focused on the target unless told
        self.assertEqual(camera['photo'], dict(focal=50.0, aperture=2.0, ev=0.0, focus=800.0))

    def test_without_an_aperture_the_lens_keeps_everything_sharp(self):
        plain = godot_viewer.resolve('target=0,0 distance=800', FlatTerrain(), (1500, 1000))['photo']
        self.assertEqual((plain['aperture'], plain['ev']), (None, 0.0))         # the viewer stays in Edit
        self.assertEqual(godot_viewer.resolve('target=0,0 distance=800 ev=1', FlatTerrain(), (1500, 1000))['photo']['ev'],
                         1.0)                                                    # an exposure alone: Photo mode

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
        self.assertNotIn('VIEWER mode', text)        # no lens: the Edit camera

    def test_a_view_with_a_lens_opens_in_photo_mode_and_projects_as_mw_render(self):
        view = 'target=200,300 distance=700 elevation=15 heading=200 focal=85 aperture=2 focus=500 roll=4'
        code, lines = godot_viewer.run(lab(), view, probes=[(200, 300), (330, 380)], check=True,
                                       progress=lambda line: None, timeout=300)
        text = '\n'.join(line for line in lines if line.startswith('VIEWER'))
        self.assertEqual(code, 0, text)
        apart = [float(v) for v in re.findall(r'([\d.]+) px apart', text)]
        self.assertEqual(len(apart), 2, text)
        self.assertLess(max(apart), 0.01, text)    # the free camera, its focal length and roll, as mw render's
        self.assertIn('VIEWER mode photo', text)


if __name__ == '__main__':
    unittest.main()
