"""Films a map's scripts play (mapkit.cinematics)."""
import math
import unittest

from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit import cinematics
from mapworkshop.mapkit.blank import create
from mapworkshop.mapkit.script_writer import Writer


class Cinematics(unittest.TestCase):
    def test_orbit_and_move_keys(self):
        keys = cinematics.orbit((100, 200, 10), 50, 30, 0, 90, seconds=6)
        self.assertEqual(len(keys), 8)                     # steps of at most 15 degrees
        self.assertEqual((keys[0][0], keys[-1][0]), (0, 6))
        self.assertAlmostEqual(keys[0][1][0], 150)
        self.assertAlmostEqual(keys[-1][1][1], 250)
        self.assertEqual(keys[0][1][2], 40)
        self.assertEqual(keys[0][2], (100, 200, 10))
        move = cinematics.move((0, 0, 100), (100, 0, 100), (0, 50, 0), (100, 50, 0), seconds=4, steps=2)
        self.assertEqual(move[1], (2.0, (50.0, 0.0, 100.0), (50.0, 50.0, 0.0)))

    def test_animation_frames(self):
        a = cinematics.animation('Shot', [(0, (0, 0, 9), (1, 1, 0)), (2, (5, 0, 9), (1, 1, 0))])
        self.assertEqual((a['type'], a['num_frames']), ('look', 2*cinematics.FPS + 1))
        self.assertEqual([k['frame'] for k in a['camera_frames']], [0, 2*cinematics.FPS])
        self.assertAlmostEqual(a['camera_frames'][0]['fov_or_focal_parameter'], math.radians(50))
        with self.assertRaises(ValueError):
            cinematics.animation('Bad', [(1, (0, 0, 0), (0, 0, 0)), (1, (0, 0, 0), (0, 0, 0))])

    def test_animation_keys_carry_their_lens(self):
        a = cinematics.animation('Zoom', [(0, (0, 0, 9), (1, 1, 0)), (2, (5, 0, 9), (1, 1, 0), .3, .1)], fov=.8)
        self.assertEqual([(k['fov_or_focal_parameter'], k['roll']) for k in a['camera_frames']], [(.8, 0.0), (.3, .1)])

    def test_install_writes_animations_and_scripts(self):
        m = create(200, 200, 30)
        w = Writer(m)
        film = cinematics.Film(prefix='T', letterbox=True)
        film.shot('A', cinematics.move((0, 0, 500), (100, 0, 500), (500, 500, 0), seconds=5))
        film.shot('B', cinematics.orbit((500, 500, 0), 300, 200, 0, 45, seconds=3), start=20)
        self.assertEqual(film.timeline(1.0), [('A', 1.0, 6.0), ('B', 20, 23)])
        scripts = film.install(m, w, start=1.0)
        w.install(scripts, side_index=2)
        back = Map(m.encode())
        self.assertEqual([a['name'] for a in sections.read(back, 'CameraAnimationList')], ['T_A', 'T_B'])
        self.assertEqual(len(scripts), 3)                    # the setup and one per shot
        with self.assertRaises(ValueError):
            film.install(m, w)                               # the animations are there already


if __name__ == '__main__':
    unittest.main()
