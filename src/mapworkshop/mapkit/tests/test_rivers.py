"""Flowing rivers and shore waves (mapkit.rivers, render.rivers)."""
import math
import os
import unittest

import numpy as np

from mapworkshop.config import GAME_DATA
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create, water_plane
from mapworkshop.mapkit.rivers import (WAVE, add_river, add_shore_wave, add_shore_waves, cross_sections,
                                       point_along)
from mapworkshop.mapkit.sites import shipwright
from mapworkshop.render.rivers import mesh


class Rivers(unittest.TestCase):
    def test_cross_sections_run_across_the_line(self):
        cs = cross_sections([(0, 0), (1000, 0)], 140, step=100)
        self.assertEqual(len(cs), 11)
        for lx, ly, rx, ry in cs:
            self.assertAlmostEqual(math.hypot(rx-lx, ry-ly), 140)
            self.assertAlmostEqual(lx, rx)                      # across the line
            self.assertGreater(ly, ry)                          # left of the flow first
        tapered = cross_sections([(0, 0), (1000, 0)], lambda s: 40+s/10, step=500)
        self.assertEqual([round(math.hypot(c[2]-c[0], c[3]-c[1])) for c in tapered], [40, 90, 140])

    def test_add_river_round_trips_after_the_standing_water(self):
        m = create(200, 200, 30)
        water_plane(m, 'Lake', 150)
        river = add_river(m, 'Brook', [(100, 1000), (1000, 1100), (1900, 900)], width=140, height=151)
        back = sections.read(Map(m.encode()), 'RiverAreas')
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0]['id'], 2)                      # after the lake's 1
        self.assertEqual((back[0]['water_height'], back[0]['additive'], back[0]['texture']), (151, 1, 'TWWaterEmpty.tga'))
        self.assertEqual(len(back[0]['cross_sections']), len(river['cross_sections']))
        with self.assertRaises(ValueError):
            add_river(m, 'Dot', [(0, 0), (0, 0)], 50, 151)

    def test_mesh(self):
        vertices, triangles = mesh([(0, 50, 0, -50), (100, 50, 100, -50), (200, 50, 200, -50)], 151)
        self.assertEqual(vertices.shape, (6, 5))
        self.assertEqual(triangles.shape, (4, 3))
        self.assertTrue(np.all(vertices[:, 2] == 151))
        self.assertEqual(list(vertices[:, 3]), [0, 1, 0, 1, 0, 1])
        self.assertEqual(list(vertices[::2, 4]), [0, 1, 2])          # strip widths along
        self.assertIsNone(mesh([(0, 0, 0, 10)], 151))


class Waves(unittest.TestCase):
    def test_waves_along_a_shore(self):
        m = create(200, 200, 30)
        self.assertEqual(add_shore_waves(m, 'Beach', [(0, 300), (1000, 300), (1000, 1300)], length=400, gap=50), 4)
        back = sections.read(Map(m.encode()), 'StandingWaveAreas')
        self.assertEqual([w['name'] for w in back], ['Beach 1', 'Beach 2', 'Beach 3', 'Beach 4'])
        self.assertTrue(all(w['wave_parameters_raw'] == WAVE and w['texture'] == 'wave256.tga' for w in back))
        self.assertAlmostEqual(math.dist(*back[0]['points']), 400, places=4)
        self.assertEqual(point_along([(0, 0), (10, 0)], 50), (10.0, 0.0))
        with self.assertRaises(ValueError):
            add_shore_wave(m, 'Bad', (0, 0), (100, 0), parameters=(1, 2, 3))

    def test_shipwright_flag_on_the_land(self):
        m = create(200, 200, 30)
        shipwright(m, 1000, 1000, water=0.0)                    # water to the east
        ship, flag = Map(m.encode()).objects()
        self.assertEqual((ship['template'], flag['template']), ('ShipWright', 'CaptureFlag'))
        self.assertAlmostEqual(flag['x'], 1000-145, places=3)


@unittest.skipUnless(os.environ.get('MW_CORPUS') and (GAME_DATA/'maps').is_dir(),
                     'stock maps: run `mw test --corpus` after `mw setup`')
class Stock(unittest.TestCase):
    def test_stock_rivers_lie_over_standing_water(self):
        """Every stock multiplayer river's height is within 1 to 2 above a standing water area's."""
        from mapworkshop.formats.map_archive import unpack
        checked = 0
        for path in sorted((GAME_DATA/'maps').glob('map mp */*.map')):
            data = path.read_bytes()
            m = Map(data if data[:4] == b'CkMp' else unpack(data))
            rivers = sections.read(m, 'RiverAreas')
            levels = [a['water_height'] for a in sections.read(m, 'StandingWaterAreas')]
            for r in rivers:
                if r['additive']:
                    self.assertTrue(any(0 <= r['water_height']-h <= 2 for h in levels), (path.parent.name, r['name']))
                    checked += 1
        self.assertGreater(checked, 5)


if __name__ == '__main__':
    unittest.main()
