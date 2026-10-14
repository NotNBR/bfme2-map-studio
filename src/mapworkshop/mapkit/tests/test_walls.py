"""Chain walls and castle sites (mapkit.walls)."""
import math
import os
import unittest

from mapworkshop.config import GAME_DATA
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create
from mapworkshop.mapkit.walls import KITS, castle_site, ground_rise, owner_property, place_wall, slots, wall_line


def gaps(pieces):
    """The largest centre-to-centre distance between neighbouring pieces on each run, less their half lengths."""
    worst = 0.0
    runs = {}
    for p in pieces:
        if p.kind != 'hub':
            runs.setdefault(p.run, []).append(p)
    for run in runs.values():
        run.sort(key=lambda p: p.x*math.cos(p.heading)+p.y*math.sin(p.heading))
        for a, b in zip(run, run[1:]):
            worst = max(worst, math.dist((a.x, a.y), (b.x, b.y))-(a.length+b.length)/2)
    return worst


class WallLine(unittest.TestCase):
    def test_segments_reach_hub_to_hub_without_gaps(self):
        for kit in ('men', 'dwarves', 'dol_guldur', 'gondor_castle'):
            pieces = wall_line([(0, 0), (517, 0), (517, 333)], kit=kit)
            self.assertLessEqual(gaps(pieces), 1e-6, kit)
            hubs = [(p.x, p.y) for p in pieces if p.kind == 'hub']
            self.assertEqual(sorted(hubs), sorted([(0, 0), (517, 0), (517, 333)]))

    def test_angles_follow_the_run(self):
        men = [p for p in wall_line([(0, 0), (0, 400)]) if p.kind == 'segment']
        self.assertTrue(all(abs(math.remainder(p.angle-math.pi, math.tau)) < 1e-9 for p in men))   # run 90 + 90
        dol = [p for p in wall_line([(0, 0), (0, 400)], kit='dol_guldur') if p.kind == 'segment']
        self.assertTrue(all(abs(math.remainder(p.angle-math.pi/2, math.tau)) < 1e-9 for p in dol))  # along local x
        flipped = [p for p in wall_line([(0, 0), (0, 400)], flip=True) if p.kind == 'segment']
        self.assertTrue(all(abs(math.remainder(p.angle, math.tau)) < 1e-9 for p in flipped))

    def test_pieces_take_segment_places(self):
        plain = wall_line([(0, 0), (600, 0)])
        mixed = wall_line([(0, 0), (600, 0)], at={'gate': [(300, 0)], 'tower': [(80, 0)]})
        count = lambda ps, kind: sum(p.kind == kind for p in ps)
        self.assertEqual(slots(128, 38), 3)
        self.assertEqual(count(mixed, 'segment'), count(plain, 'segment')-3-1)
        gate = next(p for p in mixed if p.kind == 'gate')
        self.assertLess(abs(gate.x-300), 38)
        self.assertLessEqual(gaps(mixed), 1e-6)

    def test_closed_and_open_ends(self):
        square = [(0, 0), (400, 0), (400, 400), (0, 400)]
        self.assertEqual(sum(p.kind == 'hub' for p in wall_line(square, closed=True)), 4)
        self.assertEqual(sum(p.kind == 'hub' for p in wall_line(square, ends=False)), 2)
        self.assertEqual({p.run for p in wall_line(square, closed=True) if p.kind == 'segment'}, {0, 1, 2, 3})

    def test_refusals(self):
        with self.assertRaises(ValueError):
            wall_line([(0, 0)])
        with self.assertRaises(ValueError):
            wall_line([(0, 0), (30, 0)])                               # too short between its hubs
        with self.assertRaises(ValueError):
            wall_line([(0, 0), (400, 0)], kit='dol_guldur', at={'gate': [(200, 0)]})   # no gate in the kit
        with self.assertRaises(ValueError):
            wall_line([(0, 0), (130, 0)], at={'gate': [(65, 0)]})       # no room
        with self.assertRaises(ValueError):
            wall_line([(0, 0), (600, 0)], at={'gate': [(300, 0)], 'tower': [(300, 0)]})   # overlap

    def test_ground_rise(self):
        pieces = wall_line([(0, 0), (400, 0)])
        flat = ground_rise(pieces, lambda x, y: 100.0)
        slope = ground_rise(pieces, lambda x, y: x*.1)
        self.assertTrue(all(r == 0 for r in flat))
        self.assertAlmostEqual(max(r for r, p in zip(slope, pieces) if p.kind == 'segment'), 3.8, places=6)


class Placing(unittest.TestCase):
    def test_place_wall_and_castle_site(self):
        m = create(200, 200, 30)
        pieces = wall_line([(300, 300), (700, 300)])
        self.assertEqual(place_wall(m, pieces, owner='Player_1'), len(pieces))
        castle_site(m, 1200, 1200, 'NE')
        back = list(Map(m.encode()).objects())
        walls = [o for o in back if o['template'].startswith('MenWall')]
        self.assertEqual(len(walls), len(pieces))
        owners = {next(v for k, _, v in o['properties'] if k == 'originalOwner') for o in walls}
        self.assertEqual(owners, {'Player_1/teamPlayer_1'})
        self.assertTrue(any(o['template'] == 'CastleFlagNE' for o in back))
        self.assertEqual(owner_property('PlyrCivilian/teamPlyrCivilian'), 'PlyrCivilian/teamPlyrCivilian')
        with self.assertRaises(ValueError):
            castle_site(m, 0, 0, 'N')

    def test_kits_name_their_pieces(self):
        for name, kit in KITS.items():
            self.assertTrue(kit.segment and kit.hub and kit.length > 0, name)
            self.assertIn(kit.along, ('x', 'y'))


@unittest.skipUnless(os.environ.get('MW_CORPUS') and (GAME_DATA/'maps').is_dir(),
                     'stock maps: run `mw test --corpus` after `mw setup`')
class Stock(unittest.TestCase):
    def test_tutorial_runs_rebuilt(self):
        """The advanced tutorial's straight Men wall runs, laid again between
        their own hubs with their own gates, towers and trebuchets: the same
        number of pieces, each within 20 of the stock one."""
        from mapworkshop.formats.map_archive import unpack
        data = next((GAME_DATA/'maps'/'map advanced tutorial').glob('*.map')).read_bytes()
        data = data if data[:4] == b'CkMp' else unpack(data)
        objs = [o for o in Map(data).objects() if o['template'].startswith('MenWall')]
        hubs = [o for o in objs if o['template'] == 'MenWallHubSmall']
        inline = [o for o in objs if o['template'] != 'MenWallHubSmall']
        kinds = {'MenWallGateSmall': 'gate', 'MenWallTowerSmall': 'tower', 'MenWallTrebuchetSmall': 'trebuchet'}
        matched = 0
        for i, a in enumerate(hubs):
            for b in hubs[i+1:]:
                ax, ay, bx, by = a['x'], a['y'], b['x'], b['y']
                length = math.hypot(bx-ax, by-ay)
                if length > 600:
                    continue
                def off(o):
                    t = max(0, min(1, ((o['x']-ax)*(bx-ax)+(o['y']-ay)*(by-ay))/length**2))
                    return math.hypot(o['x']-ax-t*(bx-ax), o['y']-ay-t*(by-ay)), t
                on = [o for o in inline if off(o)[0] < 6 and 0 < off(o)[1] < 1]
                if len(on) < 3:
                    continue
                at = {}
                for o in on:
                    if o['template'] in kinds:
                        at.setdefault(kinds[o['template']], []).append((o['x'], o['y']))
                ours = [p for p in wall_line([(ax, ay), (bx, by)], at=at) if p.kind != 'hub']
                if len(ours) != len(on):
                    continue
                worst = max(min(math.dist((p.x, p.y), (o['x'], o['y'])) for o in on) for p in ours)
                self.assertLess(worst, 20)
                matched += 1
        self.assertGreaterEqual(matched, 5)


if __name__ == '__main__':
    unittest.main()
