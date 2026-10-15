"""Cliff mapping on synthetic terrain: UV density along the faces and the written records."""

import math
import unittest

import numpy as np

from mapworkshop.formats.terrain import terrain_records
from mapworkshop.mapkit.blank import create, set_heights, set_materials
from mapworkshop.mapkit.cliffs import UV_PER_CELL, cliff_uvs, steep_cells


def wall(size=40, rise=30.0, facing=0.0):
    """Heights rising `rise` per cell (world units) away from a line through
    the middle, the uphill direction at `facing` radians from +x."""
    y, x = np.indices((size, size), float)
    t = (x-size/2)*math.cos(facing)+(y-size/2)*math.sin(facing)
    return 100+np.clip(t, 0, None)*rise


class CliffUVTests(unittest.TestCase):
    def edge_ratios(self, z, uv, mask):
        """UV length per cell of true surface length, over every mapped edge."""
        out = []
        for y, x in zip(*np.nonzero(mask)):
            corners = [(x, y), (x+1, y), (x+1, y+1), (x, y+1)]
            for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
                (ax, ay), (bx, by) = corners[a], corners[b]
                surface = math.sqrt(1+((z[by, bx]-z[ay, ax])/10)**2)
                du = uv[y, x, 2*b]-uv[y, x, 2*a]; dv = uv[y, x, 2*b+1]-uv[y, x, 2*a+1]
                out.append(math.hypot(du, dv)/surface)
        return np.array(out)

    def test_steep_faces_keep_the_stock_density(self):
        for facing in (0.0, math.pi/2, math.pi/4, 2.0):
            z = wall(facing=facing)
            mask = steep_cells(z)
            mask[:4, :] = mask[-5:, :] = mask[:, :4] = mask[:, -5:] = False
            uv, _ = cliff_uvs(z, mask)
            ratios = self.edge_ratios(z, uv, mask)
            # Along the wall U is exact; up it V drops the short horizontal
            # run; cells at the wall's foot and crest bend between the two.
            self.assertGreater(np.percentile(ratios, 5), UV_PER_CELL*.85, facing)
            self.assertLess(ratios.max(), UV_PER_CELL*1.01, facing)

    def test_flat_ground_is_not_steep(self):
        self.assertFalse(steep_cells(np.full((8, 8), 50.0)).any())
        self.assertFalse(steep_cells(wall(rise=9.0)).any())

    def test_set_materials_writes_one_record_per_mapped_cell(self):
        m = create(64, 64, 4, player_count=2)
        z = wall(72, facing=1.0)
        set_heights(m, z)
        labels = np.zeros(z.shape, int)
        mask = steep_cells(z)
        labels[mask] = 1
        set_materials(m, ['GrassTest', 'CliffTest'], labels, cell_sizes=[4, 4], cliffs=mask)
        blend = m.blend()
        index = blend['arrays']['cliffs']
        records = terrain_records(m)['cliffs']
        self.assertEqual(int(np.count_nonzero(index)), len(records))
        self.assertEqual(int(np.count_nonzero(index[mask])), len(records))
        cliff_tile = blend['textures'][1]['tile_start']
        self.assertEqual({r['tile'] for r in records}, {cliff_tile})
        self.assertFalse(blend['arrays']['blends'][index > 0].any())

    def test_one_texture_only(self):
        m = create(64, 64, 4, player_count=2)
        z = wall(72)
        set_heights(m, z)
        labels = np.zeros(z.shape, int)
        mask = steep_cells(z)
        labels[mask] = 1
        labels[mask & (np.indices(z.shape)[0] < 10)] = 2
        with self.assertRaises(ValueError):
            set_materials(m, ['GrassTest', 'CliffTest', 'RockTest'], labels, cell_sizes=[4, 4, 4], cliffs=mask)


if __name__ == '__main__':
    unittest.main()
