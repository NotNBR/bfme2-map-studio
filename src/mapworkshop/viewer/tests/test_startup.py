"""Empty Studio startup and opening maps from its in-window picker."""
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mapworkshop import game
from mapworkshop.viewer import godot_link, godot_viewer


class StartupTests(unittest.TestCase):
    def test_no_argument_starts_empty_without_resolving_a_map(self):
        with mock.patch.object(godot_viewer.project, 'map_path') as resolve, \
                mock.patch.object(godot_viewer, 'run', return_value=0) as run:
            self.assertEqual(godot_viewer.main([]), 0)
            resolve.assert_not_called()
            self.assertIsNone(run.call_args.args[0])

    def test_explicit_map_opens_directly(self):
        with mock.patch.object(godot_viewer.project, 'map_path', return_value=Path('x.map')), \
                mock.patch.object(godot_viewer.project, 'for_map_file', return_value=None), \
                mock.patch.object(godot_viewer, 'run', return_value=0) as run:
            self.assertEqual(godot_viewer.main(['bramble-hollow']), 0)
            self.assertEqual(run.call_args.args[0], 'bramble-hollow')

    def test_screenshot_keeps_existing_default_map_resolution(self):
        with mock.patch.object(godot_viewer, 'run', return_value=(0, [])) as run:
            self.assertEqual(godot_viewer.main(['--screenshot', 'x.png']), 0)
            self.assertIsNone(run.call_args.args[0])

    def test_empty_session_can_poll_and_recover_from_failed_selection(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(godot_viewer.openbfme, 'HOME', Path(tmp)), \
                mock.patch.object(godot_viewer, 'scene') as scene:
            prepared = godot_viewer.prepare(None, port=1234)
            scene.assert_not_called()
            self.assertTrue(json.loads(prepared[0].read_text())['empty'])
            self.assertIsNone(prepared[3])
            companion = godot_link.Companion(prepared, mock.Mock(side_effect=ValueError('Broken map')))
            self.assertIsNone(companion.watch())
            self.assertIsNone(companion.panel_message())
            self.assertEqual(companion.pack_for_test(), [])
            self.assertFalse(companion.state()['visible'])
            self.assertEqual(companion.views_message()['items'], [])
            self.assertEqual(companion.handle(dict(type='command', name='build'))[0]['text'], 'Open a map first')
            with mock.patch.object(godot_link.project, 'for_map_file', return_value=None):
                reply = companion.open_map('missing.map')
            self.assertEqual(reply, [dict(type='map_open_failed', error='Broken map')])
            self.assertIsNone(companion.map_path)

    def test_catalog_includes_unbuilt_projects_and_builds_before_preparing(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(godot_viewer.openbfme, 'HOME', Path(tmp)):
            owner = SimpleNamespace(map_file=Path(tmp)/'draft.map', title='Draft')
            companion = godot_link.Companion(godot_viewer.prepare(None), mock.Mock())
            with mock.patch.object(godot_link.project, 'projects', return_value=[owner]), \
                    mock.patch.object(game, 'stock_maps', return_value=[Path(tmp)/'original.map']):
                menu = companion.menu()
            self.assertFalse(menu['loaded'])
            self.assertFalse(menu['projects'][0]['ready'])
            self.assertEqual(len(menu['stock']), 1)
            order = []
            def build(*args, **kwargs):
                order.append('build')
                return 0
            def prepare(*args):
                order.append('prepare')
                return ('scene.json', dict(title='Draft'), owner, None)
            companion.prepare = prepare
            with mock.patch.object(godot_link.project, 'for_map_file', return_value=owner), \
                    mock.patch.object(godot_link.project, 'run', side_effect=build), \
                    mock.patch.object(companion, '_show') as show, \
                    mock.patch.object(companion, 'menu', return_value=menu):
                self.assertEqual(companion.open_map(str(owner.map_file))[0]['type'], 'reload')
                show.assert_called_once()
            self.assertEqual(order, ['build', 'prepare'])
            with mock.patch.object(godot_link.project, 'for_map_file', return_value=owner), \
                    mock.patch.object(godot_link.project, 'run', return_value=1):
                self.assertEqual(companion.open_map(str(owner.map_file))[0]['type'], 'map_open_failed')


@unittest.skipUnless(godot_viewer.openbfme.is_built() and godot_viewer.openbfme.status()[0],
                     'needs the pinned Godot runtime and retail assets')
class PickerIntegrationTests(unittest.TestCase):
    def test_blank_studio_modal_and_first_map_load(self):
        from mapworkshop import project
        if not project.find('blend-lab').map_file.is_file():
            self.skipTest('needs Blend Lab built')
        engine = godot_viewer.openbfme
        _, console = engine.assemble(progress=lambda line: None)
        link = godot_link.Link()
        self.addCleanup(link.close)
        prepared = godot_viewer.prepare(None, port=link.port)
        companion = godot_link.Companion(prepared,
            lambda name, preview: godot_viewer.prepare(name, preview=preview, port=link.port), progress=lambda line: None)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp)/'picker.log'
            with log.open('w', encoding='utf-8') as output:
                process = subprocess.Popen([str(console), '--headless', '--path', str(engine.VIEWER),
                    '--script', 'res://tests/map_picker_test.gd', '--', f'--scene={prepared[0]}'],
                    env=engine.environment([]), stdout=output, stderr=subprocess.STDOUT)
                worker = threading.Thread(target=companion.serve, args=(link, process), daemon=True)
                worker.start()
                try:
                    code = process.wait(timeout=90)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                    worker.join(timeout=5)
            text = log.read_text(encoding='utf-8')
            self.assertEqual(code, 0, text)
            self.assertIn('PICKER RESULT: PASS (0 failed)', text)
            self.assertNotIn('SCRIPT ERROR', text)
