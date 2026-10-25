"""Grass Lab entry points and its self-contained viewer payload."""
import unittest
import tempfile
from unittest import mock
from mapworkshop.native import openbfme
from mapworkshop.viewer import godot_viewer
from mapworkshop.native.tests.test_engine_bundle import fixture as runtime_fixture


class GrassLabTests(unittest.TestCase):
    def test_cli_starts_lab_without_map_picker_or_retail_assets(self):
        with mock.patch.object(godot_viewer, 'run_grass_lab', return_value=0) as run, \
             mock.patch.object(openbfme, 'assets') as assets:
            self.assertEqual(godot_viewer.main(['--grass-lab']), 0)
            run.assert_called_once_with()
            assets.assert_not_called()

    def test_lab_rejects_a_map_instead_of_ignoring_it(self):
        with self.assertRaisesRegex(SystemExit, 'own scene'):
            godot_viewer.main(['some-map', '--grass-lab'])

    def test_launch_uses_assembled_studio_scene(self):
        with mock.patch.object(openbfme, 'assemble', return_value=('godot.exe', 'console.exe')), \
             mock.patch.object(openbfme, 'environment', return_value={}), \
             mock.patch.object(godot_viewer.subprocess, 'call', return_value=0) as call:
            self.assertEqual(godot_viewer.run_grass_lab(lambda _: None), 0)
            self.assertEqual(call.call_args.args[0], ['godot.exe', '--path', str(openbfme.VIEWER),
                                                    'res://labs/grass/scenes/grass_lab.tscn'])

    def test_assembly_contains_lab_and_keeps_regular_terrain_shader(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = runtime_fixture(tmp)
            files = openbfme.viewer_files(bundle)
            for name in ['scenes/grass_lab.tscn', 'scripts/grass_lab.gd', 'shaders/ground_cover.gdshader',
                         'shaders/terrain.gdshader', 'shaders/natural_ground.gdshaderinc', 'assets/turf_detail.png']:
                self.assertTrue(files['labs/grass/' + name].is_file(), name)
            self.assertEqual(files['shaders/terrain.gdshader'], bundle.file('viewer', 'shaders/terrain.gdshader'))
