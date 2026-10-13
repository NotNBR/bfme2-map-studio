"""Spanned bridge geometry (render.bridges), without a GPU."""
import unittest

import numpy as np

from mapworkshop.render.bridges import endpoint_pairs, layout, pieces, place


def part(name, x0, x1):
    positions = np.array([[x0, -5, 0], [x1, -5, 0], [x1, 5, 2]], np.float32)
    return dict(name=name, positions=positions, normals=np.tile([0, 0, 1], (3, 1)).astype(np.float32))


MODEL = dict(parts=[part('BRIDGE_LEFT', -10, 0), part('BRIDGE_SPAN', 0, 10), part('BRIDGE_RIGHT', 10, 20),
                    part('OTHER', 0, 1)])


class BridgeGeometryTests(unittest.TestCase):
    def test_spans_repeat_and_the_ends_meet_the_points(self):
        found = pieces(MODEL)
        self.assertEqual(sorted(found), ['BRIDGE_LEFT', 'BRIDGE_RIGHT', 'BRIDGE_SPAN'])
        start, end = (100., 50., 10.), (100., 150., 10.)          # 100 long, northwards
        plan = layout(found, start, end, scale=.5)
        self.assertEqual(plan['spans'], 8)                          # (100 - 20 + 5) // 10
        drawn = [place(found[piece][0], offset, plan, start)[0] for piece, offset in plan['draw']]
        self.assertEqual(len(drawn), 10)
        # Vertices at model y -5 lie 2.5 east of the axis (across x BridgeScale, the axis runs north).
        np.testing.assert_allclose(drawn[0][0], [102.5, 50, 10], atol=1e-4)     # left piece starts at the point
        np.testing.assert_allclose(drawn[-1][1], [102.5, 150, 10], atol=1e-4)   # right piece ends at the other
        np.testing.assert_allclose(drawn[0][2], [97.5, 60, 11], atol=1e-4)      # height x BridgeScale

    def test_without_pieces_nothing_or_one_stretched_piece(self):
        self.assertIsNone(layout({}, (0, 0, 0), (100, 0, 0), 1.))
        plan = layout({'BRIDGE_LEFT': [part('BRIDGE_LEFT', -10, 10)]}, (0, 0, 0), (100, 0, 0), 1.)
        self.assertEqual(plan['draw'], [('BRIDGE_LEFT', 10.)])
        positions, _ = place(part('BRIDGE_LEFT', -10, 10), 10., plan, (0, 0, 0))
        self.assertAlmostEqual(float(positions[1][0]), 100., places=4)

    def test_pairs_are_adjacent_0x10_then_0x20(self):
        objects = [dict(flags=0x10), dict(flags=0x20), dict(flags=0), dict(flags=0x10), dict(flags=0), dict(flags=0x20)]
        self.assertEqual(endpoint_pairs(objects), [(objects[0], objects[1])])


if __name__ == '__main__':
    unittest.main()
