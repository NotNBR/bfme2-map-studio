"""What `mw marks` reports about the objects under a mark, and editing marks."""
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object, create
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.marks import Marks, contains, corners, describe, handles, rect_points, text


class NoVegetation:
    def template_model(self, template):
        return None


class MarkTests(unittest.TestCase):
    def test_objects_carry_the_layer_they_were_placed_with(self):
        m = create(71, 83, 3)
        add_object(m, 'Barrel', 300, 300, layer='Yard')
        add_object(m, 'Crate01', 330, 300, layer='Yard')
        add_object(m, 'Cart01', 900, 900, layer='Road')
        data = dict(map='test', map_path='no-such-project.map', updated='now',
                    marks=[dict(id=1, kind='circle', points=[[310, 300]], radius=100)])
        mark, = describe(data, assets=NoVegetation(), m=Map(m.encode()))['marks']
        self.assertEqual([(o['template'], o['layer']) for o in mark['objects']], [('Barrel', 'Yard'), ('Crate01', 'Yard')])
        self.assertEqual(mark['layers'], {'Yard': 2})
        report = text(dict(data, title='Test', playable=[700, 820], marks=[mark]))
        self.assertIn('Barrel at (300, 300) [Yard]', report)
        self.assertIn('layers: Yard 2', report)


class EditTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(marklib, 'MARKS_DIR', Path(folder.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.marks = Marks('test.map')

    def test_undo_steps_back_through_add_remove_and_clear(self):
        m = self.marks
        m.add('pin', [(10, 20)])
        m.add('circle', [(100, 100)], radius=50)
        m.remove(1)
        m.clear()
        self.assertTrue(m.undo())
        self.assertEqual([x['id'] for x in m.items], [2])
        self.assertTrue(m.undo())
        self.assertEqual([x['id'] for x in m.items], [1, 2])
        m.undo()
        m.undo()
        self.assertEqual(m.items, [])
        self.assertFalse(m.undo())
        self.assertEqual(Marks('test.map').items, [])

    def test_undo_restores_ids_after_clear(self):
        self.marks.add('pin', [(0, 0)])
        self.marks.clear()
        self.marks.undo()
        self.assertEqual(self.marks.add('pin', [(5, 5)])['id'], 2)

    def test_resize_drags_a_handle(self):
        m = self.marks
        circle = m.add('circle', [(100, 100)], radius=50)
        m.resize(circle['id'], None, 100, 180)
        self.assertEqual(circle['radius'], 80)
        rect = m.add('rect', [(0, 0), (100, 50)])
        corners = handles(rect)
        # Dragging corner 2 (x1, y1) past corner 0 flips the rectangle.
        m.resize(rect['id'], corners[0], -40, -20)
        self.assertEqual(rect['points'], [[-40, -20], [0, 0]])
        self.assertEqual(len(handles(m.add('pin', [(1, 1)]))), 0)

    def test_rotated_rectangle(self):
        m = self.marks
        # Drawn from corner (0, 0) to (100, 100) with its sides turned 0.3 radians.
        points = rect_points((0, 0), (100, 100), 0.3)
        rect = m.add('rect', points, angle=0.3)
        c = corners(rect)
        self.assertTrue(np.allclose(c[0], [0, 0], atol=0.2) and np.allclose(c[2], [100, 100], atol=0.2))
        self.assertTrue(contains(rect, np.array([50.0, 50.0, 100.0]), np.array([50.0, 50.0, 0.0])).tolist()
                        == [True, True, False])
        # Resizing keeps the angle and works along the turned sides.
        m.resize(rect['id'], c[0], 0, 200)
        self.assertEqual(rect['angle'], 0.3)
        self.assertTrue(np.allclose(corners(rect)[2], [0, 200], atol=0.2))
        m.rotate(rect['id'], 0)
        self.assertNotIn('angle', rect)
        self.assertNotIn('angle', m.add('rect', [(0, 0), (10, 10)]))

    def test_rotated_rectangle_reports_its_corners(self):
        m = create(71, 83, 3)
        add_object(m, 'Barrel', 300, 300, layer='Yard')
        add_object(m, 'Crate01', 380, 300, layer='Yard')
        rect = dict(id=1, kind='rect', points=[[200, 280], [400, 320]], angle=round(math.pi/2, 4))
        data = dict(map='test', map_path='no-such-project.map', updated='now', marks=[rect])
        result = describe(data, assets=NoVegetation(), m=Map(m.encode()))
        mark, = result['marks']
        self.assertEqual([o['template'] for o in mark['objects']], ['Barrel'])
        report = text(dict(result, title='Test'))
        self.assertIn('200 x 40 turned 90.0 degrees counter-clockwise, corners (320, 200)', report)


if __name__ == '__main__':
    unittest.main()
