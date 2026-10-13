"""Offline navigation rules: independent maps and geometry, no installed game needed."""
import math
import unittest
from unittest.mock import Mock

import numpy as np

from mapworkshop.formats.map import Map
from mapworkshop.mapkit import pathing, walkable
from mapworkshop.mapkit.blank import create, set_heights, set_materials, water_plane, add_object
from mapworkshop.mapkit.bridges import add_bridge
from mapworkshop.render.assets import GameAssets


def assets(body='', name='House'):
    # Exercise the real override parser without opening game archives.
    a = GameAssets.__new__(GameAssets)
    a._templates = {name.lower(): dict(name=name, parent=None, body=body)} if body else {}
    return a


HOUSE = '''
Draw = W3DScriptedModelDraw Tag
  DefaultModelConditionState
    Model = None
  End
End
// ArmorSet
//   Geometry = SPHERE
// End
KindOf = STRUCTURE IMMOBILE
Geometry = BOX
GeometryMajorRadius = 20
GeometryMinorRadius = 10
GeometryOffset = X:10 Y:0 Z:0
GeometryIsSmall = No
End
'''


class PathingTests(unittest.TestCase):
    def test_border_and_cliff_expansion_do_not_wrap(self):
        m = create(64, 64, 3)
        blocked = np.zeros((70, 70), np.uint8)
        blocked[3, 3] = 1
        blocked[0, :] = 1  # non-playable border must not affect the opposite edge
        set_materials(m, ['A'], np.zeros_like(blocked), blocked, cell_sizes=[4])
        g = pathing.terrain_grid(Map(m.encode()))
        self.assertEqual(g.shape, (64, 64))
        self.assertEqual(np.count_nonzero(g == 2), 4)
        self.assertTrue(np.all(g[-1] == 0))

    def test_strict_water_depths_and_native_corner_order(self):
        m = create(64, 64, 3)
        water_plane(m, 'Water', 106)
        # 6 units is shallow, strictly greater than 6 is deep.
        g = pathing.terrain_grid(Map(m.encode()))
        self.assertTrue(np.all(g == 1))
        heights = np.full((70, 70), 100.)
        heights[13, 13] = 99.
        heights[13, 14] = 100.5  # last corner of cell (10,10): shallow overrides deep
        set_heights(m, heights)
        g = pathing.terrain_grid(Map(m.encode()))
        self.assertEqual(g[10, 10], 1)
        self.assertEqual(g[9, 12], 1)
        self.assertEqual(g[10, 9], 7)  # the lowered vertex is this cell's final corner
        water_plane(m, 'Water', 105)
        set_heights(m, np.full((70, 70), 100.))
        self.assertTrue(np.all(pathing.terrain_grid(Map(m.encode())) == 0))

    def test_inheritance_comments_and_additional_shapes(self):
        a = assets(HOUSE)
        a._templates['child'] = dict(parent='house', body='''
KindOf = +DO_NOT_CLASSIFY -IMMOBILE
AdditionalGeometry = CYLINDER
GeometryMajorRadius = 15
GeometryOffset = X:0 Y:30 Z:0
End
''')
        value = pathing.template_data(a.templates, 'Child')
        self.assertEqual(value['kinds'], {'STRUCTURE', 'DO_NOT_CLASSIFY'})
        self.assertEqual([s['type'] for s in value['shapes']], ['BOX', 'CYLINDER'])
        self.assertEqual(pathing.template_data(a.templates, 'House')['shapes'][0]['major'], 20)

    def test_rotation_offset_and_small_or_raised_structures(self):
        m = create(64, 64, 3)
        add_object(m, 'House', 200, 200, angle=math.pi/2)
        add_object(m, 'House', 400, 400, z=11)
        add_object(m, 'Small', 500, 500)
        a = assets(HOUSE)
        a._templates['small'] = dict(parent='house', body='GeometryIsSmall = Yes\nEnd')
        grid = pathing.compute(Map(m.encode()), assets=a)['ground']
        ys, xs = np.nonzero(grid == 4)
        # Samples stop before the far edge: x=190,195,200,205 after rotation.
        self.assertEqual((xs.min(), xs.max(), ys.min(), ys.max()), (19, 20, 19, 22))
        self.assertEqual(grid[40, 40], 0)
        self.assertEqual(grid[50, 50], 0)

    def test_map_override_keeps_base_geometry_and_does_not_leak(self):
        m = create(64, 64, 3)
        add_object(m, 'House', 200, 200)
        m = Map(m.encode())
        a = assets(HOUSE)
        hidden = pathing.compute(m, assets=a, map_ini='Object House\nKindOf = +DO_NOT_CLASSIFY\nEnd\n')
        shown = pathing.compute(m, assets=a, map_ini='Object House\nDisplayName = Test\nEnd\n')
        self.assertFalse(np.any(hidden['ground'] == 4))
        self.assertTrue(np.any(shown['ground'] == 4))
        self.assertEqual(a.templates['house']['body'], HOUSE)
        self.assertEqual(len(a.templates), 1)

    def test_circle_and_unknown_template_reporting(self):
        shape = dict(type='CYLINDER', major=10., minor=0., offset=(0, 0, 0))
        ys, xs = pathing.footprint_cells(shape, dict(x=200., y=200., angle=0.), (64, 64))
        self.assertEqual(set(zip(ys, xs)), {(19, 19), (19, 20), (20, 19), (20, 20)})
        m = create(64, 64, 3)
        add_object(m, 'Missing', 200, 200)
        result = pathing.compute(Map(m.encode()), assets=assets())
        self.assertIn('Unknown object template: Missing', result['info']['warnings'])

    def test_comparison_distinguishes_colour_from_passability(self):
        a = dict(ground=np.array([[0, 1, 4]], np.uint32), layers=[])
        b = dict(ground=np.array([[1, 1, 0]], np.uint32), layers=[])
        report = walkable.compare(a, b)
        self.assertEqual(report['category_differences'], 2)
        self.assertEqual(report['passability_differences'], 1)

    def test_bridge_crosses_water_without_a_native_capture(self):
        m = create(64, 64, 3)
        water_plane(m, 'River', 120, points=[(280, 0), (360, 0), (360, 640), (280, 640)])
        add_bridge(m, 'Bridge', (250, 300), (390, 300), name='test', assets=False)
        a = assets()
        a.ini_text = lambda _: 'Bridge Bridge\nBridgeModelName = Model\nBridgeScale = 1\nEnd\n'
        model = dict(parts=[dict(name='BRIDGE_LEFT', positions=np.array([[0, -20, 0], [10, 20, 0]]))])
        grid = pathing.compute(Map(m.encode()), assets=a, models=Mock(load=Mock(return_value=model)))
        kinds = walkable.categories(grid)
        self.assertEqual(kinds[30, 32], walkable.BRIDGE)
        self.assertEqual(kinds[20, 32], walkable.BLOCKED)

    def test_walking_mesh_scale_and_off_map_polygons(self):
        m = create(64, 64, 3)
        add_object(m, 'House', 200, 200, extra=[('objectPrototypeScale', 2, .5)])
        a = assets(HOUSE.replace('Model = None', 'Model = Bridge\nWallBoundsMesh = Deck')
                   .replace('STRUCTURE IMMOBILE', 'STRUCTURE IMMOBILE WALK_ON_TOP_OF_WALL'))
        model = dict(collision=[dict(name='Deck', positions=np.array([[-40, -40, 0], [40, -40, 0],
                                                                     [40, 40, 0], [-40, 40, 0]]),
                                     indices=np.array([[0, 1, 2], [0, 2, 3]]))])
        grid = pathing.compute(Map(m.encode()), assets=a, models=Mock(load=Mock(return_value=model)))
        self.assertEqual(grid['ground'][20, 20], 8)
        self.assertEqual(grid['ground'][20, 23], 0)
        self.assertEqual(len(pathing.polygon_cells([(-100, -100), (-90, -100), (-90, -90)], (64, 64))[0]), 0)


if __name__ == '__main__':
    unittest.main()
