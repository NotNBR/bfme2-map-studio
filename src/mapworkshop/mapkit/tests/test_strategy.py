"""Walking distances from the bases to the neutral sites (mapkit.checks.strategy, `mw sites`)."""
import math
import unittest

from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create, starts
from mapworkshop.mapkit.checks.strategy import analyse, lines, parse_teams
from mapworkshop.mapkit.sites import creep_lair, neutral_site

DIAGONAL = 20*math.sqrt(2)               # one diagonal step of the 20-unit grid


class Strategy(unittest.TestCase):
    def setUp(self):
        m = create(200, 200, 30)
        starts(m, [(300, 300), (1700, 1700)])
        neutral_site(m, 'Outpost', 500, 500)
        creep_lair(m, 'CaveTrollLair', 1000, 1000)
        self.m = Map(m.encode())

    def test_sites_with_their_team_and_margin(self):
        report = analyse(self.m, [[1], [2]])[0]
        sites = {s['kind']: s for s in report['sites']}
        self.assertEqual(set(sites), {'Outpost', 'CaveTrollLair'})     # the flag is no site
        outpost, lair = sites['Outpost'], sites['CaveTrollLair']
        self.assertEqual((outpost['owner'], outpost['team']), (1, 1))
        self.assertAlmostEqual(outpost['distances'][0], 10*DIAGONAL, delta=1)
        self.assertAlmostEqual(outpost['team_margin'], 50*DIAGONAL, delta=2)
        self.assertEqual(lair['team_margin'], 0)                     # halfway between the starts
        self.assertEqual(report['players'][0]['Outpost']['nearest'], round(10*DIAGONAL))

    def test_given_bases_and_text(self):
        report = analyse(self.m, [[1, 2], [3]], bases=[(300, 300), (300, 1700), (1700, 1700)])[0]
        self.assertEqual((report['starts'], report['bases']), (3, 'given'))
        text = '\n'.join(lines(report, 'test'))
        self.assertIn('test: 3 bases (the given points); teams 1,2 / 3.', text)
        self.assertIn('Outpost', text.splitlines()[3])                 # capturable sites before lairs
        self.assertIn('team 1: #1 283', text)

    def test_parse_teams(self):
        self.assertEqual(parse_teams('1-4/5,6,8'), [[1, 2, 3, 4], [5, 6, 8]])


if __name__ == '__main__':
    unittest.main()
