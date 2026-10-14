"""Neutral sites, creep lairs, Gollum's spawn points and ambient sound (mapkit.sites, mapkit.ambient)."""
import math
import os
import unittest

from mapworkshop.config import GAME_DATA
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.ambient import PALETTES, along, ambient, plan
from mapworkshop.mapkit.blank import create, starts
from mapworkshop.mapkit.sites import (FLAG, GOLLUM, LINKED, creep_lair, flag_position, gollum_spawns, neutral_site,
                                      spread)


def props(o):
    return {k: v for k, _, v in o['properties']}


class Sites(unittest.TestCase):
    def test_neutral_site_with_flag(self):
        m = create(200, 200, 30)
        fx, fy = neutral_site(m, 'Outpost', 1000, 1000, angle=math.pi/2)
        self.assertAlmostEqual(fx, 1000, places=6)
        self.assertAlmostEqual(fy, 1105, places=6)          # 105 along the outpost's facing
        neutral_site(m, 'SignalFire', 500, 500, flag=(520, 500))
        objs = list(Map(m.encode()).objects())
        self.assertEqual([o['template'] for o in objs], ['Outpost', FLAG, 'SignalFire', FLAG])
        self.assertTrue(all(props(o)['originalOwner'] == 'PlyrNeutral/teamPlyrNeutral' for o in objs))
        self.assertEqual((objs[3]['x'], objs[3]['y']), (520, 500))
        with self.assertRaises(ValueError):
            neutral_site(m, 'WargLair', 0, 0)

    def test_flag_positions_follow_the_stock_directions(self):
        for template, (distance, turn) in LINKED.items():
            x, y = flag_position(template, 0, 0, 0.3)
            self.assertAlmostEqual(math.hypot(x, y), distance)
            self.assertAlmostEqual(math.remainder(math.atan2(y, x)-0.3-turn, math.tau), 0, places=9)

    def test_creep_lair(self):
        m = create(200, 200, 30)
        creep_lair(m, 'WargLair', 300, 300)
        o = Map(m.encode()).objects()[0]
        self.assertEqual(props(o)['originalOwner'], 'PlyrCreeps/teamPlyrCreeps')
        with self.assertRaises(ValueError):
            creep_lair(m, 'Outpost', 0, 0)

    def test_gollum_spawns_follow_the_starts(self):
        m = create(200, 200, 30)
        starts(m, [(300, 300), (1600, 1600)])
        gollum_spawns(m, [(900, 400), (1000, 1500), (400, 1200)])
        waypoints = [props(o) for o in Map(m.encode()).objects() if o['template'] == '*Waypoints/Waypoint']
        names = [w['waypointName'] for w in waypoints]
        self.assertEqual(names[2:], [f'{GOLLUM}{i}' for i in (1, 2, 3)])
        ids = [w['waypointID'] for w in waypoints]
        self.assertEqual(len(set(ids)), len(ids))

    def test_spread(self):
        grid = [(x, y) for x in range(0, 2001, 100) for y in range(0, 2001, 100)]
        chosen = spread(grid, 6, avoid=[(0, 0)], clear=800, apart=400)
        self.assertEqual(len(chosen), 6)
        self.assertTrue(all(math.dist(p, (0, 0)) >= 800 for p in chosen))
        self.assertTrue(all(math.dist(a, b) >= 400 for i, a in enumerate(chosen) for b in chosen[i+1:]))
        self.assertEqual(chosen, spread(grid, 6, avoid=[(0, 0)], clear=800, apart=400))


class Ambient(unittest.TestCase):
    def test_along(self):
        points = along([(0, 0), (1000, 0), (1000, 500)], 300)
        self.assertEqual(len(points), 5)
        self.assertEqual(points[0], (150, 0))

    def test_plan_spacing_and_cycling(self):
        line = along([(0, 1000), (4000, 1000)], 100)
        emitters = plan('rohan', (2000, 2000), dict(river=line, heights=[(500, 3000), (3500, 3000)]))
        self.assertEqual(emitters[0], ('AmbStream_PlainsOfRohan', 2000.0, 2000.0))
        river = [e for e in emitters[1:] if e[2] == 1000]
        self.assertTrue(all(abs(a[1]-b[1]) >= 700 for i, a in enumerate(river) for b in river[i+1:]))
        self.assertEqual({e[0] for e in river}, set(PALETTES['rohan']['zones']['river']))
        with self.assertRaises(ValueError):
            plan('desert', (0, 0), dict(woods=[(1, 1)]))

    def test_ambient_keeps_to_the_map(self):
        m = create(200, 200, 30)
        emitters = ambient(m, 'forest', (1000, 1000), dict(woods=[(500, 500), (5000, 5000)]))
        self.assertEqual(len(emitters), 2)
        self.assertEqual(len(list(Map(m.encode()).objects())), 2)


@unittest.skipUnless(os.environ.get('MW_CORPUS') and (GAME_DATA/'maps').is_dir(),
                     'stock maps: run `mw test --corpus` after `mw setup`')
class Stock(unittest.TestCase):
    def test_flags_stand_where_the_stock_maps_put_them(self):
        """Most stock flags lie within 60 of flag_position for their structure."""
        from mapworkshop.formats.map_archive import unpack
        near = total = 0
        for path in sorted((GAME_DATA/'maps').glob('map mp */*.map')):
            data = path.read_bytes()
            objs = list(Map(data if data[:4] == b'CkMp' else unpack(data)).objects())
            flags = [(o['x'], o['y']) for o in objs if o['template'] == FLAG]
            for o in objs:
                if o['template'] in LINKED and flags:
                    total += 1
                    p = flag_position(o['template'], o['x'], o['y'], o['angle'])
                    near += min(math.dist(p, f) for f in flags) < 60
        self.assertGreater(total, 30)
        self.assertGreater(near/total, .5)


if __name__ == '__main__':
    unittest.main()
