"""Unnamed viewer launches pick a map; cancellation never starts the engine."""
import unittest
from pathlib import Path
from unittest import mock

from mapworkshop.viewer import godot_viewer, startup


class StartupTests(unittest.TestCase):
    def test_no_argument_opens_picker_and_loads_its_selection(self):
        with mock.patch.object(startup, 'choose_map', return_value='bramble-hollow') as choose, \
                mock.patch.object(godot_viewer.project, 'map_path', return_value=Path('x.map')), \
                mock.patch.object(godot_viewer.project, 'for_map_file', return_value=mock.sentinel.owner), \
                mock.patch.object(godot_viewer.project, 'remember'), \
                mock.patch.object(godot_viewer, 'run', return_value=0) as run:
            self.assertEqual(godot_viewer.main([]), 0)
            choose.assert_called_once_with()
            self.assertEqual(run.call_args.args[0], 'bramble-hollow')

    def test_closing_picker_exits_cleanly_without_resolving_or_loading_a_map(self):
        with mock.patch.object(startup, 'choose_map', return_value=None), \
                mock.patch.object(godot_viewer.project, 'map_path') as resolve, \
                mock.patch.object(godot_viewer, 'run') as run:
            self.assertEqual(godot_viewer.main([]), 0)
            resolve.assert_not_called()
            run.assert_not_called()

    def test_explicit_map_bypasses_picker(self):
        with mock.patch.object(startup, 'choose_map') as choose, \
                mock.patch.object(godot_viewer.project, 'map_path', return_value=Path('x.map')), \
                mock.patch.object(godot_viewer.project, 'for_map_file', return_value=mock.sentinel.owner), \
                mock.patch.object(godot_viewer.project, 'remember'), \
                mock.patch.object(godot_viewer, 'run', return_value=0):
            self.assertEqual(godot_viewer.main(['bramble-hollow']), 0)
            choose.assert_not_called()

    def test_automated_screenshot_keeps_last_map_resolution_without_picker(self):
        with mock.patch.object(startup, 'choose_map') as choose, \
                mock.patch.object(godot_viewer, 'run', return_value=(0, [])) as run:
            self.assertEqual(godot_viewer.main(['--screenshot', 'x.png']), 0)
            choose.assert_not_called()
            self.assertIsNone(run.call_args.args[0])
