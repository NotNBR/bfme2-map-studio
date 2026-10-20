import unittest

from mapworkshop.native import battle

LOG = """frame 5 | Player_1 troops 10 raised 0 battalions 1 heroes 0 | siege idle 0 | gates whole | walls whole
  GondorArcherHorde HS_A1 (400 600 100) hp 1000 state 0 victim - phase -1
  GondorArcherHorde HS_A2 (400 800 100) hp 1000 state 0 victim - phase -1
  IsengardSiegeLadder  (100 50 100) hp 600 state 0 victim - phase 0
frame 10 | Player_1 troops 10 raised 0 battalions 1 heroes 0 | siege idle 0 | gates whole | walls whole
  GondorArcherHorde HS_A1 (450 600 100) hp 1000 state 1 victim - phase -1
  GondorArcherHorde HS_A2 (400 800 100) hp 1000 state 0 victim - phase -1
  IsengardSiegeLadder  (100 50 100) hp 0 dead state 0 victim - phase 0
frame 15 | Player_1 troops 10 raised 0 battalions 1 heroes 0 | siege idle 0 | gates whole | walls whole
  GondorArcherHorde HS_A1 (500 540 100) hp 1000 state 1 victim - phase -1
  GondorArcherHorde HS_A2 (400 800 100) hp 1000 state 0 victim - phase -1
"""


class BattleLogTest(unittest.TestCase):
    def test_parse_reads_lines_and_objects(self):
        log = battle.parse(LOG)
        self.assertEqual([f for f, _ in log['frames']], [5, 10, 15])
        self.assertEqual(set(log['objects']), {'HS_A1', 'HS_A2', 'IsengardSiegeLadder#1'})
        a1 = log['objects']['HS_A1']
        self.assertEqual(a1['template'], 'GondorArcherHorde')
        self.assertEqual([(f, x, y) for f, x, y, *_ in a1['track']], [(5, 400., 600.), (10, 450., 600.), (15, 500., 540.)])
        self.assertTrue(log['objects']['IsengardSiegeLadder#1']['track'][-1][5])     # dead at its last line

    def test_summary_counts_movers_and_backwards(self):
        rows = {r['template']: r for r in battle.summary(battle.parse(LOG))}
        archers = rows['GondorArcherHorde']
        self.assertEqual((archers['count'], archers['never_moved']), (2, 1))
        self.assertEqual((archers['start'], archers['stop']), (10, 15))
        self.assertEqual((archers['dx'], archers['dy'], archers['backwards']), (100., -60., 1))
        self.assertEqual(rows['IsengardSiegeLadder']['never_moved'], 1)

    def test_formations_relates_member_goals_to_their_battalion(self):
        trace = dict(goals=[
            dict(frame=1, id=1, horde=True, at=(400, 600), goal=(905, 705), angle=0),
            dict(frame=1, id=2, horde=False, at=(417.5, 600), goal=(922.5, 705), angle=0),
            dict(frame=1, id=3, horde=False, at=(377.5, 600), goal=(882.5, 705), angle=0),
            dict(frame=1, id=4, horde=True, at=(400, 800), goal=(965, 705), angle=0),
            dict(frame=1, id=5, horde=False, at=(417.5, 800), goal=(982.5, 705), angle=0),
            dict(frame=1, id=6, horde=False, at=(1350, 7450), goal=(1350, 7450), angle=0),  # another player's unit, far away: not a member
            dict(frame=2, id=2, horde=False, at=(420, 600), goal=(0, 0), angle=0),      # a later reservation: not the first
        ])
        f = battle.formations(trace)
        self.assertEqual([x['id'] for x in f], [1, 4])
        self.assertEqual(f[0]['members'], [(17.5, 0.0), (-22.5, 0.0)])
        self.assertEqual(f[1]['members'], [(17.5, 0.0)])


if __name__ == '__main__':
    unittest.main()
