"""viewer.marking: drawing, selecting, moving and Esc, without a window.

The stand-in world maps a window position (x, y) to the map point (x, y) at
height 0, and framebuffer pixels equal window pixels.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.jobs import Status
from mapworkshop.viewer.marking import MarkEditor
from mapworkshop.viewer.marks import Marks


class World:
    def ground_hit(self, pos, z=None):
        return np.array([float(pos[0]), float(pos[1]), 0.0])

    def plane_hit(self, pos, z):
        return np.array([float(pos[0]), float(pos[1]), z])

    def focus_z(self):
        return 0.0

    def focus_distance(self):
        return 1000.0

    def screen_angle(self):
        return 0.0

    def shift_held(self):
        return False


class Overlay:
    """Answers what is under the cursor from `under`: a mark id, or None."""
    def __init__(self):
        self.under = None

    def handle_at(self, pos, scale=1.0):
        return None

    def grab_at(self, pos, selected=None, scale=1.0):
        return self.under

    def mark_at(self, pos, scale=1.0):
        return self.under


class EditorTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(marklib, 'MARKS_DIR', Path(folder.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.overlay = Overlay()
        self.editor = MarkEditor(self.overlay, World(), Status())
        self.editor.marks = Marks('test.map')

    def drag(self, start, end):
        e = self.editor
        consumed = e.press(start, start, 1.0)
        e.move(end)
        e.release()
        return consumed

    def test_hidden_marks_leave_presses_to_navigation_until_a_tool_is_picked(self):
        e = self.editor
        e.toggle_visible()
        self.assertFalse(e.press((10, 10), (10, 10), 1.0))
        e.set_tool('pin')
        self.assertTrue(e.visible)
        self.assertTrue(e.press((10, 10), (10, 10), 1.0))

    def test_navigate_puts_the_tool_away(self):
        e = self.editor
        e.set_tool('circle')
        e.set_tool(None)
        self.assertIsNone(e.tool)
        self.assertEqual(e.hint(), None)

    def test_with_no_tool_a_press_beside_the_marks_navigates(self):
        self.assertFalse(self.editor.press((10, 10), (10, 10), 1.0))

    def test_a_pin_is_added_and_selected(self):
        e = self.editor
        e.set_tool('pin')
        self.assertTrue(e.press((120, 80), (120, 80), 1.0))
        e.release()
        mark, = e.marks.items
        self.assertEqual((mark['kind'], mark['points'], e.selected), ('pin', [[120.0, 80.0]], mark['id']))

    def test_a_circle_is_drawn_from_its_centre(self):
        e = self.editor
        e.set_tool('circle')
        self.drag((100, 100), (130, 140))
        mark, = e.marks.items
        self.assertEqual((mark['points'], mark['radius'], e.selected), ([[100.0, 100.0]], 50.0, mark['id']))
        self.assertIsNone(e.drawing)

    def test_a_tiny_circle_is_dropped(self):
        e = self.editor
        e.set_tool('circle')
        self.drag((100, 100), (102, 101))
        self.assertEqual(e.marks.items, [])

    def test_dragging_a_mark_moves_it_and_undo_moves_it_back(self):
        e = self.editor
        mark = e.marks.add('pin', [(10, 10)])
        self.overlay.under = mark['id']
        self.assertTrue(self.drag((10, 10), (40, 30)))
        self.assertEqual((e.selected, e.marks.get(mark['id'])['points']), (mark['id'], [[40.0, 30.0]]))
        e.undo()
        self.assertEqual(e.marks.get(mark['id'])['points'], [[10.0, 10.0]])

    def test_a_click_selects_the_mark_under_it(self):
        e = self.editor
        mark = e.marks.add('pin', [(10, 10)])
        self.overlay.under = mark['id']
        e.click((10, 10), 1.0)
        self.assertEqual(e.selected, mark['id'])
        e.set_tool('pin')
        self.overlay.under = None
        e.click((10, 10), 1.0)        # with a tool armed, clicks draw instead
        self.assertIsNone(e.selected)

    def test_escape_steps_back_one_level_at_a_time(self):
        e = self.editor
        e.set_tool('circle')
        e.press((100, 100), (100, 100), 1.0)
        e.selected = 7
        steps = []
        while e.escape():
            steps.append((e.drawing is not None, e.selected, e.tool))
        self.assertEqual(steps, [(False, 7, 'circle'), (False, None, 'circle'), (False, None, None)])

    def test_delete_needs_a_selection_and_undo_brings_the_mark_back(self):
        e = self.editor
        e.delete_selected()
        self.assertEqual(e.status.text, 'nothing selected: click a mark first')
        mark = e.marks.add('pin', [(10, 10)])
        e.selected = mark['id']
        e.delete_selected()
        self.assertEqual((e.marks.items, e.selected), ([], None))
        e.undo()
        self.assertEqual([m['id'] for m in e.marks.items], [mark['id']])


if __name__ == '__main__':
    unittest.main()
