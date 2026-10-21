"""The Godot viewer's companion (viewer/godot_link.py): mouse events with a ray become marks through MarkEditor, the
commands, the state the viewer draws, Copy for agent, the socket, live reload; and, when OpenBFME is built, the viewer
itself driven headless: marks drawn and dragged by scripted input (the overlay picking the mark to drag) read in
`mw marks` as the same marks drawn in the studio viewer's way."""
import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from mapworkshop.native import openbfme
from mapworkshop.viewer import godot_link, godot_viewer
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.marking import MarkEditor


class FlatSurface:
    """Ground at height 50 everywhere, as godot_viewer.Surface answers it."""

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
                   mock.patch.object(godot_link, 'Loaded', mock.MagicMock())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.companion = godot_link.Companion(self.map_path, FlatSurface(), progress=lambda line: None)

    def send(self, *messages):
        out = []
        for message in messages:
            out += self.companion.handle(message)
        return out

    def saved(self):
        return json.loads(marklib.marks_path(self.map_path).read_text(encoding='utf-8'))['marks']

    def test_a_circle_drawn_by_the_mouse_is_saved(self):
        self.send(dict(type='tool', tool='circle'))
        replies = self.send(event('press', 400, 400))
        self.assertEqual(replies[0], dict(type='press_result', handled=True, seq=7))     # the press's number back
        self.send(event('move', 450, 400), event('move', 500, 400), event('release', 500, 400))
        self.assertEqual(self.saved(), [dict(id=1, kind='circle', points=[[400.0, 400.0]], radius=100.0)])

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
        self.companion.rescene = mock.MagicMock(side_effect=OSError('half written'))
        time.sleep(0.01)
        self.map_path.write_bytes(b'broken')
        reply = self.companion.watch()
        self.assertEqual(reply['type'], 'status')
        self.assertIsNone(self.companion.watch())                      # not again for the same build
        self.assertIsNone(self.companion.reload_started)

    def test_a_new_build_is_reloaded_once_it_has_settled(self):
        rescene = mock.MagicMock(return_value=FlatSurface())
        self.companion.rescene = rescene
        self.assertIsNone(self.companion.watch())
        time.sleep(0.01)
        self.map_path.write_bytes(b'rebuilt')
        self.assertEqual(self.companion.watch(), dict(type='reload'))
        rescene.assert_called_once()
        self.assertIsNone(self.companion.watch())


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
    """The studio viewer's world for MarkEditor, hitting the map points it is told (as its camera picks them)."""

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
            map_path = godot_viewer.source('blend-lab')[0]
            godot = json.loads(marklib.marks_path(map_path).read_text(encoding='utf-8'))
            # the same marks through MarkEditor as the studio viewer drives it, its camera picking those points
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
            self.assertEqual(godot['marks'], studio_marks.plain())
            describe = lambda marks: marklib.text(marklib.describe(dict(map_path=str(map_path), map=map_path.stem,
                                                                        updated='now', marks=marks)))
            self.assertEqual(describe(godot['marks']), describe(studio_marks.plain()))


if __name__ == '__main__':
    unittest.main()
