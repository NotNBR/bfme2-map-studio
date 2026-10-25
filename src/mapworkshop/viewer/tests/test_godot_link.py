"""The Godot viewer's companion (viewer/godot_link.py): mouse events with a ray become marks through MarkEditor, the
commands, the state the viewer draws, Copy for agent, the socket, live reload; and, when OpenBFME is built, the viewer
itself driven headless: marks drawn and dragged by scripted input (the overlay picking the mark to drag) read in
`mw marks` as the marks MarkEditor makes from the same strokes driven directly."""
import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mapworkshop.native import openbfme
from mapworkshop.render import godot
from mapworkshop.viewer import godot_link, godot_viewer
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer import views as viewlib
from mapworkshop.viewer.marking import MarkEditor


class FlatSurface:
    """Ground at height 50 everywhere, as render.godot.Surface answers it."""

    def __init__(self):
        self.terrain = self
        self.playable = (2000.0, 2000.0)

    def height_at(self, x, y):
        return np.zeros_like(np.asarray(x, float)) + 50.0


def event(kind, x, y, **picks):
    """A viewer event whose ray comes straight down onto map point x, y."""
    return dict(type=kind, ray=[[x, y, 1050.0], [0.0, 0.0, -1.0]], picks=picks, shift=False,
                focus=dict(z=50.0, distance=1500.0, angle=0.0), seq=7)


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.map_path = tmp/'map mp test.map'
        self.map_path.write_bytes(b'')
        patches = [mock.patch.object(marklib, 'MARKS_DIR', tmp/'marks'),
                   mock.patch.object(viewlib, 'VIEWS', tmp/'views'),
                   mock.patch.object(godot_link, 'Loaded', mock.MagicMock())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.data = dict(map_path=str(self.map_path), title='Test', preview=godot_link.OWN)
        self.companion = godot_link.Companion((tmp/'scene.json', self.data, None, FlatSurface()),
                                              progress=lambda line: None)

    def send(self, *messages):
        out = []
        for message in messages:
            out += self.companion.handle(message)
        return out

    def saved(self):
        return json.loads(marklib.marks_path(self.map_path).read_text(encoding='utf-8'))['marks']

    def test_placement_export_keeps_the_requested_map_when_viewer_switches_maps(self):
        from mapworkshop.render import placements
        out=self.map_path.with_suffix('.png')
        with mock.patch.object(godot_link.threading,'Thread') as thread, \
                mock.patch.object(placements,'export',return_value=(out,out.with_suffix('.json'))) as export, \
                mock.patch.object(godot_link.os,'startfile',create=True) as open_image:
            self.send(dict(type='command',name='placement'))
            self.send(dict(type='command',name='placement'))
            thread.assert_called_once()
            self.companion.map_path=self.map_path.with_name('another.map')
            thread.call_args.kwargs['target']()
            export.assert_called_once_with([str(self.map_path)])
            open_image.assert_called_once_with(str(out))
        self.assertFalse(self.companion.exporting_placement)
        self.assertEqual(self.companion.toasts[-1]['kind'],'done')

    def test_a_circle_drawn_by_the_mouse_is_saved(self):
        self.send(dict(type='tool', tool='circle'))
        replies = self.send(event('press', 400, 400))
        self.assertEqual(replies[0], dict(type='press_result', handled=True, seq=7))     # the press's number back
        self.send(event('move', 450, 400), event('move', 500, 400), event('release', 500, 400))
        self.assertEqual(self.saved(), [dict(id=1, kind='circle', points=[[400.0, 400.0]], radius=100.0)])

    def test_test_mode_runs_the_map_packed_as_the_viewer_started(self):
        tmp = self.map_path.parent
        (tmp/'map mp test').mkdir()
        shown = tmp/'map mp test'/'map mp test.map'
        shown.write_bytes(b'the build')
        self.data.update(map='map mp test', user_map=True, user_map_folder=str(tmp))
        with mock.patch.object(godot_link.openbfme, 'pack_for_test', return_value=['a.big']) as pack:
            self.assertEqual(self.companion.pack_for_test(), ['a.big'])
        pack.assert_called_once_with(shown, 'map mp test', 'Test')
        replies = self.send(dict(type='command', name='test_mode', camera=EDIT))
        self.assertEqual(replies[0]['type'], 'test_mode')
        self.assertEqual(replies[0]['map'], 'map mp test')
        self.assertEqual([s['player'] for s in replies[0]['slots']], ['Player_1', 'Player_2'])
        self.assertIsNone(self.companion.restart)
        shown.write_bytes(b'a new build')                    # since the viewer started: it starts again
        self.companion.prepare = mock.MagicMock()             # a companion that can prepare the map again
        replies = self.send(dict(type='command', name='test_mode', camera=EDIT, views=dict(grid=True)))
        self.assertEqual([r['type'] for r in replies], ['toast', 'quit'])
        self.assertEqual(self.companion.restart['views'], dict(grid=True))
        self.assertIn('target=400,300', self.companion.restart['view'])

    def test_a_press_without_a_tool_or_a_mark_is_left_to_the_camera(self):
        self.assertEqual(self.send(event('press', 400, 400))[0], dict(type='press_result', handled=False, seq=7))

    def test_select_delete_undo_and_escape(self):
        self.send(dict(type='tool', tool='pin'), event('press', 300, 300), event('release', 300, 300),
                  dict(type='tool', tool=None))
        self.send(event('click', 300, 300, mark=1.0))            # ids come from GDScript as floats
        self.assertEqual(self.companion.editor.selected, 1)
        self.send(dict(type='command', name='delete'))
        self.assertEqual(self.saved(), [])
        self.send(dict(type='command', name='undo'))
        self.assertEqual([m['id'] for m in self.saved()], [1])
        self.send(event('click', 300, 300, mark=1.0), dict(type='command', name='escape'))
        self.assertIsNone(self.companion.editor.selected)

    def test_a_drag_on_a_mark_moves_it(self):
        self.send(dict(type='tool', tool='pin'), event('press', 300, 300), event('release', 300, 300),
                  dict(type='tool', tool=None))
        self.assertTrue(self.send(event('press', 300, 300, grab=1.0))[0]['handled'])
        self.send(event('move', 340, 330), event('release', 340, 330))
        self.assertEqual(self.saved()[0]['points'], [[340.0, 330.0]])

    def test_the_state_drapes_the_marks_and_gives_the_selected_rectangle_its_handles(self):
        self.send(dict(type='tool', tool='rect'), event('press', 100, 100), event('move', 300, 200),
                  event('release', 300, 200))
        state = self.companion.state()
        rect = state['marks'][0]
        self.assertEqual(rect['kind'], 'rect')
        self.assertTrue(rect['closed'])
        self.assertTrue(all(p[2] == 53.0 for p in rect['world']))        # 3 units over the surface, as overlay.drape
        self.assertEqual(state['selected'], 1)                           # a new mark is selected
        self.assertEqual(len(state['handles']['spots']), 4)
        self.assertEqual(state['handles']['center'], [200.0, 150.0, 53.0])
        self.assertIsNotNone(state['handles']['rotate'])

    def test_a_hover_answers_with_the_cursor(self):
        self.send(dict(type='tool', tool='pin'))
        replies = self.send(event('hover', 10, 10))
        self.assertEqual(replies[-1]['cursor'], 'draw')

    def test_copy_for_agent_gives_the_marks_text(self):
        self.send(dict(type='tool', tool='pin'), event('press', 300, 300), event('release', 300, 300))
        with mock.patch.object(marklib, 'describe', return_value='described'), \
                mock.patch.object(marklib, 'agent_text', return_value='the marks') as text:
            replies = self.send(dict(type='command', name='copy'))
        self.assertEqual(replies[0], dict(type='clipboard', text='the marks'))
        text.assert_called_once_with('described')

    def test_the_panel_is_sent_when_its_lines_change(self):
        self.assertEqual(self.companion.panel_message(), None)          # no marks, no panel: nothing new to send
        self.send(dict(type='tool', tool='pin'), event('press', 300, 300), event('release', 300, 300))
        self.companion.summary = mock.MagicMock(**{'get.return_value': None})      # still being worked out
        message = self.companion.panel_message()
        self.assertEqual(message['type'], 'panel')
        self.assertEqual(message['lines'][:2], [['#1 pin', 'head'], ['reading...', 'muted']])
        self.assertIsNone(self.companion.panel_message())

    def test_an_error_becomes_a_status_line_and_the_session_goes_on(self):
        with mock.patch.object(self.companion.editor, 'undo', side_effect=ValueError('broken')):
            replies = self.send(dict(type='command', name='undo'))
        self.assertEqual(replies, [dict(type='status', text='that did not work: broken', seconds=5)])
        self.assertEqual(self.send(dict(type='tool', tool='pin'))[-1]['tool'], 'pin')

    def test_the_state_is_sent_only_when_it_changed(self):
        self.send(dict(type='tool', tool='pin'))
        self.assertEqual(self.send(event('hover', 10, 10))[-1]['cursor'], 'draw')
        self.assertEqual(self.send(event('hover', 12, 10)), [])          # the same marks, the same cursor

    def test_a_build_that_cannot_be_read_keeps_the_last_good_one(self):
        self.companion.owner = mock.MagicMock(id='test')
        self.companion.prepare = mock.MagicMock(side_effect=OSError('half written'))
        time.sleep(0.01)
        self.map_path.write_bytes(b'broken')
        reply = self.companion.watch()
        self.assertEqual(reply['type'], 'status')
        self.assertIsNone(self.companion.watch())                      # not again for the same build
        self.assertIsNone(self.companion.reload_started)

    def test_a_new_build_is_reloaded_once_it_has_settled(self):
        self.companion.owner = mock.MagicMock(id='test')
        prepare = mock.MagicMock(return_value=(Path('scene.json'), self.data, self.companion.owner, FlatSurface()))
        self.companion.prepare = prepare
        self.assertIsNone(self.companion.watch())
        time.sleep(0.01)
        self.map_path.write_bytes(b'rebuilt')
        self.assertEqual(self.companion.watch(), dict(type='reload', scene='scene.json', new_map=False))
        prepare.assert_called_once_with(str(self.map_path), godot_link.OWN)
        self.assertIsNone(self.companion.watch())

    def test_another_map_is_prepared_and_the_viewer_told_to_read_it(self):
        other = Path(self.tmp.name)/'map mp other.map'
        other.write_bytes(b'')
        self.companion.prepare = mock.MagicMock(
            return_value=(Path('other.json'), dict(map_path=str(other), title='Other', preview=godot_link.OWN), None,
                          FlatSurface()))
        with mock.patch.object(self.companion, 'menu', return_value=dict(type='menu')):
            replies = self.send(dict(type='command', name='open_map', map=str(other)))
        self.assertEqual(replies[0], dict(type='reload', scene='other.json', new_map=True))
        self.assertEqual(self.companion.map_path, other)
        self.assertEqual(self.companion.marks.items, [])               # that map's marks, not this one's

    def test_another_project_becomes_the_last_map(self):
        owner = mock.MagicMock(id='other')
        self.companion.prepare = mock.MagicMock(
            return_value=(Path('other.json'), dict(self.data, title='Other'), owner, FlatSurface()))
        with mock.patch.object(self.companion, 'menu', return_value=dict(type='menu')),                 mock.patch.object(godot_link.project, 'remember') as remember:
            self.send(dict(type='command', name='open_map', map='other'))
        remember.assert_called_once_with(owner)                        # `mw` alone opens it next time

    def test_the_units_switch_prepares_a_copy_without_them(self):
        preview = dict(godot_link.OWN, units=False)
        self.companion.prepare = mock.MagicMock(
            return_value=(Path('preview.json'), dict(self.data, map='map mp test studio preview', preview=preview),
                          None, FlatSurface()))
        with mock.patch.object(self.companion, 'menu', return_value=dict(type='menu')):
            replies = self.send(dict(type='command', name='preview', units=False))
        self.companion.prepare.assert_called_once_with(str(self.map_path), preview)
        self.assertEqual(replies[0]['what'], "the preview: Map's own · no units")

    def test_a_preview_prepares_the_same_map_again_with_it(self):
        preview = dict(godot_link.OWN, weather='rain')
        self.companion.prepare = mock.MagicMock(
            return_value=(Path('preview.json'), dict(self.data, map='map mp test studio preview', preview=preview),
                          None, FlatSurface()))
        loaded = self.companion.loaded
        with mock.patch.object(self.companion, 'menu', return_value=dict(type='menu')):
            replies = self.send(dict(type='command', name='preview', weather='rain'))
        self.companion.prepare.assert_called_once_with(str(self.map_path), preview)
        self.assertEqual(replies[0], dict(type='reload', scene='preview.json', new_map=False, what='the preview: Rain'))
        self.assertEqual(self.companion.preview, preview)
        self.assertIs(self.companion.loaded, loaded)                   # the same map: its marks and analysis stay

    def test_f5_reads_the_map_again_with_its_preview(self):
        self.companion.prepare = mock.MagicMock(return_value=(Path('again.json'), self.data, None, FlatSurface()))
        with mock.patch.object(self.companion, 'menu', return_value=dict(type='menu')):
            replies = self.send(dict(type='command', name='reload'))
        self.companion.prepare.assert_called_once_with(str(self.map_path), godot_link.OWN)
        self.assertEqual(replies[0], dict(type='reload', scene='again.json', new_map=False, what='the map again'))

    def test_a_preview_that_fails_puts_the_menu_back(self):
        self.companion.prepare = mock.MagicMock(side_effect=OSError('disk full'))
        with mock.patch.object(self.companion, 'menu', return_value=dict(type='menu')):
            replies = self.send(dict(type='command', name='preview', sun='ember'))
        self.assertEqual([r['type'] for r in replies[:2]], ['status', 'menu'])
        self.assertEqual(self.companion.preview, godot_link.OWN)

    def test_properties_open_the_studio_viewers_window_whose_save_builds(self):
        at_once = mock.MagicMock(side_effect=lambda target, daemon: mock.MagicMock(start=target))
        dialog = mock.MagicMock()
        with mock.patch('mapworkshop.viewer.properties.PropertiesDialog', return_value=dialog) as window, \
                mock.patch.object(godot_link.threading, 'Thread', at_once):
            self.send(dict(type='command', name='properties'))
        path, owner, texts, saved = window.call_args[0]
        self.assertEqual((path, owner, sorted(texts)), (self.map_path, None, ['WaterTransparency', 'Weather']))
        dialog.open.assert_called_once_with()
        updated = mock.MagicMock(**{'map_file.resolve.return_value': self.map_path.resolve()})
        saved(updated)                                             # Save, on the window's thread: only noted
        with mock.patch.object(self.companion.build, 'start') as build:
            self.companion.job_messages()                          # the serving loop builds it
        build.assert_called_once_with(updated)
        dialog.is_open, dialog.map_path = True, self.map_path
        self.assertEqual(self.send(dict(type='command', name='properties')), [])   # open: brought to the front
        dialog.lift.assert_called_once_with()

    def test_a_map_chosen_by_browse_opens_from_the_serving_loop(self):
        self.companion.browsed = str(self.map_path)
        with mock.patch.object(self.companion, 'open_map', return_value=[dict(type='reload')]) as open_map:
            self.assertEqual(self.companion.job_messages()[0], dict(type='reload'))
        open_map.assert_called_once_with(str(self.map_path))
        self.companion.browsed = 'elsewhere.map'
        with mock.patch.object(self.companion, 'open_map', side_effect=RuntimeError('neither')):
            self.assertIn('cannot be opened', self.companion.job_messages()[0]['text'])

    def test_build_and_test_in_game_start_the_studio_viewers_jobs(self):
        with mock.patch.object(self.companion.build, 'start') as build:
            self.send(dict(type='command', name='build'))
        build.assert_called_once_with(None)
        with mock.patch.object(godot_link.jobs, 'play') as play, \
                mock.patch.object(godot_link, 'setting', return_value='openbfme'):
            self.send(dict(type='command', name='test'))
        self.assertEqual(play.call_args[0][2], 'openbfme')
        self.companion.jobs.set('building...', 5)
        self.assertEqual([m['type'] for m in self.companion.job_messages()], ['status', 'build'])
        self.assertEqual(self.companion.job_messages(), [])            # nothing new

    def test_the_flow_overlay_sends_each_river_strip(self):
        area = dict(cross_sections=[0, 0, 0, 100, 300, 0, 300, 100, 600, 0, 600, 100], water_height=20.0)
        with mock.patch('mapworkshop.render.rivers.records', return_value=[area]):
            replies = self.send(dict(type='command', name='overlay', overlay='flow'))
        strip = replies[0]['strips'][0]
        self.assertEqual(replies[0]['type'], 'flow')
        self.assertEqual(len(strip['vertices']), 6*5)                   # three cross-sections, two banks
        self.assertEqual(strip['vertices'][:5], [0.0, 100.0, 20.0, 1.0, 0.0])      # the second bank: u 1, v 0
        self.assertEqual(len(strip['triangles']), 4*3)
        self.assertEqual(strip['length'], 4.5)       # v per section: (half the outline less an end) / end / sections

    def test_the_walkable_overlay_is_worked_out_once_in_the_background(self):
        ready = dict(type='walkable', image='walkable.png', size=[2000, 2000], cut_off=0)
        self.companion.loaded.walkable, self.companion.loaded.walking = None, False
        at_once = mock.MagicMock(side_effect=lambda target, daemon: mock.MagicMock(start=target))
        with mock.patch.object(godot_link, 'walkability', return_value=ready) as work, \
                mock.patch.object(godot_link.threading, 'Thread', at_once):
            self.assertEqual(self.send(dict(type='command', name='overlay', overlay='walkable'))[0]['type'], 'status')
            self.assertEqual(self.companion.job_messages()[0], ready)
            self.assertEqual(self.send(dict(type='command', name='overlay', overlay='walkable')), [ready])
        work.assert_called_once()                                       # once per build

    def test_a_walkability_that_fails_says_so_and_can_be_tried_again(self):
        self.companion.loaded.walkable, self.companion.loaded.walking = None, False
        at_once = mock.MagicMock(side_effect=lambda target, daemon: mock.MagicMock(start=target))
        with mock.patch.object(godot_link, 'walkability', side_effect=RuntimeError('no game files')), \
                mock.patch.object(godot_link.threading, 'Thread', at_once):
            self.send(dict(type='command', name='overlay', overlay='walkable'))
        self.assertEqual(self.companion.job_messages()[0], dict(type='walkable', error='no game files'))
        self.assertFalse(self.companion.loaded.walking)


EDIT = dict(mode='edit', orbit=dict(x=400.0, y=300.0, distance=1200.0, elevation=35.0, heading=90.0, fov=50.0),
            fly=dict(goal=[0, 0, 0], forward=[0, 1, 0], focal=39.0, roll=0.0, aperture=0.0, focus=1500.0, ev=0.0))
PHOTO = dict(EDIT, mode='photo', fly=dict(goal=[100.0, 200.0, 400.0], forward=[0.0, 0.6, -0.8], focal=85.0, roll=4.0,
                                         aperture=2.0, focus=500.0, ev=0.5))


class ViewsTests(unittest.TestCase):
    """The saved views (local/views/<map>.json, thumbnails beside it) and Copy view (a mw render command)."""
    setUp, send = CompanionTests.setUp, CompanionTests.send

    def test_a_view_is_saved_with_its_thumbnail_and_gone_back_to(self):
        from PIL import Image
        shot = Path(self.tmp.name)/'view.png'
        Image.new('RGB', (1600, 1000), (200, 10, 10)).save(shot)
        replies = self.send(dict(type='command', name='save_view', camera=EDIT, slot=3, thumbnail=str(shot)))
        self.assertEqual(replies[0]['text'], 'saved View 1 - Ctrl+3 goes back to it')
        self.assertFalse(shot.exists())                             # the viewer's picture, taken
        items = replies[1]['items']
        self.assertEqual([(v['name'], v['slot'], v['mode']) for v in items], [('View 1', 3, 'edit')])
        with Image.open(items[0]['thumbnail']) as thumbnail:
            self.assertEqual(thumbnail.size, viewlib.THUMBNAIL)
        saved = viewlib.Views(self.map_path).by_name('View 1')['spec']         # as viewer.views reads it
        self.assertEqual(saved, dict(target=[400, 300, 50], distance=1200, elevation=35, heading=90, fov=50))
        view = self.send(dict(type='command', name='apply_view', slot=3, size=[1600, 1000]))[0]
        self.assertEqual((view['type'], view['mode'], view['name']), ('view', 'edit', 'View 1'))
        self.assertAlmostEqual(view['orbit']['distance'], 1200.0)
        self.assertAlmostEqual(view['orbit']['heading'], 90.0)
        self.assertIn('Ctrl+Shift+4', self.send(dict(type='command', name='apply_view', slot=4))[0]['text'])

    def test_an_edit_view_keeps_its_own_heading(self):
        self.send(dict(type='command', name='save_view', camera=dict(EDIT, orbit=dict(EDIT['orbit'], heading=200.0))))
        view = self.send(dict(type='command', name='apply_view', view='View 1'))[0]
        self.assertAlmostEqual(view['orbit']['heading'], 200.0)    # not -160: the viewer turns the short way from it

    def test_a_photo_view_keeps_its_lens(self):
        self.send(dict(type='command', name='save_view', camera=PHOTO))
        saved = viewlib.Views(self.map_path).items[0]
        self.assertEqual(saved['mode'], 'photo')
        self.assertEqual(saved['spec'], dict(eye=[100, 200, 400], target=[100, 500, 0], focal=85, roll=4, aperture=2,
                                             focus=500, ev=0.5))
        view = self.send(dict(type='command', name='apply_view', view=saved['name'], size=[1600, 1000]))[0]
        self.assertEqual(view['photo'], dict(focal=85.0, aperture=2.0, ev=0.5, focus=500.0))
        self.assertEqual(view['eye'], [100.0, 200.0, 400.0])

    def test_rename_and_delete(self):
        self.send(dict(type='command', name='save_view', camera=EDIT))
        renamed = self.send(dict(type='command', name='rename_view', view='View 1', new='Gate'))[0]
        self.assertEqual(renamed['items'][0]['name'], 'Gate')
        replies = self.send(dict(type='command', name='delete_view', view='Gate'))
        self.assertEqual(replies[1]['items'], [])

    def test_copy_view_gives_the_mw_render_command_of_the_picture(self):
        self.companion.preview = dict(godot_link.OWN, weather='rain', limits=True)
        replies = self.send(dict(type='command', name='copy_view', camera=EDIT,
                                 preview=dict(size=[1600, 1000], objects=True, water=False, fog=True, grid=True)))
        text = replies[0]['text']
        self.assertEqual(replies[0]['type'], 'clipboard')
        self.assertTrue(text.startswith('mw render --map "'), text)                 # not a project: the file
        for part in ('--size 1600x1000', '--weather rain', '--grid', '--vegetation-limits', 'target=400,300,50 distance=1200'):
            self.assertIn(part, text)
        self.assertNotIn('--sun', text)
        self.assertNotIn('--no-units', text)
        self.assertIn('mw render always draws it', replies[0]['what'])             # the water was hidden


class HelperTests(unittest.TestCase):
    def test_a_game_maps_title_comes_from_its_file_name_without_the_disk(self):
        with mock.patch.object(Path, 'resolve', side_effect=AssertionError('disk lookup')):
            self.assertEqual(godot_link.map_title(Path('map mp my valley.map')), 'My Valley')
            self.assertEqual(godot_link.map_title(Path('bfmexbar fords.map')), 'Fords')

    def test_a_ray_finds_the_ground(self):
        hit = godot_link.march(np.array([0.0, 0.0, 100.0]), np.array([0.6, 0.0, -0.8]), FlatSurface().height_at, 500)
        self.assertAlmostEqual(hit[2], 50.0, places=3)
        self.assertAlmostEqual(hit[0], 37.5, places=3)
        self.assertIsNone(godot_link.march(np.zeros(3) + 100, np.array([0.0, 0.0, 1.0]), FlatSurface().height_at, 500))


class LinkTests(unittest.TestCase):
    def test_json_lines_both_ways(self):
        link = godot_link.Link()
        client = socket.create_connection(('127.0.0.1', link.port))
        try:
            self.assertTrue(link.accept(2.0))
            client.sendall(b'{"type": "ready", "ms": 5}\n{"type": "tool", ')
            self.assertEqual(link.receive(), [dict(type='ready', ms=5)])
            client.sendall(b'"tool": "pin"}\n')
            self.assertEqual(link.receive(), [dict(type='tool', tool='pin')])
            link.send(dict(type='reload'))
            self.assertEqual(client.recv(100), b'{"type": "reload"}\n')
            client.close()
            self.assertIsNone(link.receive())
        finally:
            link.close()


class Ground:
    """A world for MarkEditor that hits the map points it is told: the strokes as a camera picking them would."""

    def __init__(self):
        self.at = None

    def ground_hit(self, pos, z=None):
        return np.array([*self.at, 0.0])

    def plane_hit(self, pos, z):
        return self.ground_hit(pos)

    def focus_z(self):
        return 0.0

    def focus_distance(self):
        return 1500.0

    def screen_angle(self):
        return 0.0

    def shift_held(self):
        return False


def lab():
    try:
        from mapworkshop import project
        return 'blend-lab' if project.find('blend-lab').map_file.exists() else None
    except LookupError:
        return None


@unittest.skipUnless(openbfme.is_built() and openbfme.status()[0] and lab(),
                     'needs OpenBFME built for its pin, the game files (mw play --godot sets both up) and Blend Lab\'s '
                     'build (mw build blend-lab)')
class DrivenViewerTests(unittest.TestCase):
    CIRCLE, RECT = ((400, 400), (500, 400)), ((600, 600), (750, 700))
    GRAB, DROP = (500, 400), (520, 400)        # the circle's rim, picked by the viewer's overlay, and where it goes

    def test_marks_drawn_in_the_godot_viewer_read_as_the_studio_viewers(self):
        (c0, c1), (r0, r1) = self.CIRCLE, self.RECT
        drive = [dict(do='tool', tool='circle'), dict(do='press', at=c0), dict(do='move', at=c1),
                 dict(do='release', at=c1), dict(do='tool', tool='rect'), dict(do='press', at=r0),
                 dict(do='move', at=r1), dict(do='release', at=r1), dict(do='tool', tool=None),
                 dict(do='press', at=self.GRAB), dict(do='move', at=self.DROP), dict(do='release', at=self.DROP)]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(marklib, 'MARKS_DIR', Path(tmp)):
            code = godot_viewer.run('blend-lab', 'target=500,500 distance=1400 elevation=60', drive=drive,
                                    progress=lambda line: None, timeout=300)
            self.assertEqual(code, 0)
            map_path = godot.source('blend-lab')[0]
            drawn = json.loads(marklib.marks_path(map_path).read_text(encoding='utf-8'))
            # the same marks through MarkEditor driven directly, a camera picking those points
            studio_marks = marklib.Marks(Path(tmp)/'studio.map')        # a marks file of its own
            ground, status = Ground(), mock.MagicMock()
            overlay = mock.MagicMock(**{'handle_at.return_value': None, 'grab_at.return_value': None})
            editor = MarkEditor(overlay, ground, status)
            editor.marks = studio_marks
            strokes = [('circle', self.CIRCLE), ('rect', self.RECT), (None, (self.GRAB, self.DROP))]
            for tool, (a, b) in strokes:
                editor.set_tool(tool)
                overlay.grab_at.return_value = 1 if tool is None else None    # the studio overlay finds the rim
                ground.at = a
                editor.press(None, None, 1.0)
                ground.at = b
                editor.move(None)
                editor.release()
            self.assertEqual(studio_marks.get(1)['points'], [[420.0, 400.0]])     # the circle moved by the drag
            self.assertEqual(drawn['marks'], studio_marks.plain())
            describe = lambda marks: marklib.text(marklib.describe(dict(map_path=str(map_path), map=map_path.stem,
                                                                        updated='now', marks=marks)))
            self.assertEqual(describe(drawn['marks']), describe(studio_marks.plain()))


if __name__ == '__main__':
    unittest.main()
