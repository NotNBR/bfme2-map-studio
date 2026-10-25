"""Unnamed viewer launches pick a map; cancellation never starts the engine."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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


class PickerBuildTests(unittest.TestCase):
    def test_unbuilt_project_confirms_then_builds_before_opening(self):
        class Widget:
            def __init__(self, *args, **kwargs):
                self.command = kwargs.get('command')
                if kwargs.get('text') in ('Open', 'Cancel'):
                    buttons[kwargs['text']] = self
            def pack(self, **kwargs): pass
            def configure(self, **kwargs): pass
            def heading(self, *args, **kwargs): pass
            def column(self, *args, **kwargs): pass
            def insert(self, *args, **kwargs): pass
            def bind(self, *args, **kwargs): pass
            def selection(self): return ('draft',)
            def selection_set(self, *args): pass
            def see(self, *args): pass
            def focus_set(self): pass
            def yview(self, *args): pass
            def set(self, *args): pass

        class Window:
            def __init__(self): self.destroyed = False
            def title(self, *args): pass
            def geometry(self, *args): pass
            def minsize(self, *args): pass
            def bind(self, *args): pass
            def protocol(self, *args): pass
            def after(self, delay, callback): callback()
            def destroy(self): self.destroyed = True
            def mainloop(self):
                buttons['Open'].command()
                if not self.destroyed:
                    buttons['Cancel'].command()

        class ImmediateThread:
            def __init__(self, target, daemon): self.target = target
            def start(self): self.target()

        class Variable:
            def __init__(self, value): self.value = value
            def set(self, value): self.value = value

        for built, confirmed, build_code, expected in (
                (False, False, 0, None),
                (False, True, 0, 'draft'),
                (False, True, 1, None),
                (True, False, 0, 'draft')):
            with self.subTest(built=built, confirmed=confirmed, build_code=build_code), tempfile.TemporaryDirectory() as tmp:
                buttons = {}
                map_file = Path(tmp)/'draft.map'
                if built:
                    map_file.write_bytes(b'map')
                owner = SimpleNamespace(id='draft', title='Draft', map_file=map_file)
                ask = mock.Mock(return_value=confirmed)
                error = mock.Mock()
                def build(project, on_line):
                    self.assertIs(project, owner)
                    on_line('Building Draft')
                    if build_code == 0:
                        map_file.write_bytes(b'map')
                    return build_code
                run = mock.Mock(side_effect=build)
                ttk = SimpleNamespace(Frame=Widget, Label=Widget, Treeview=Widget, Scrollbar=Widget, Button=Widget)
                tkinter = SimpleNamespace(Tk=Window, StringVar=Variable, ttk=ttk,
                                          filedialog=SimpleNamespace(askopenfilename=mock.Mock()),
                                          messagebox=SimpleNamespace(askokcancel=ask, showerror=error))
                with mock.patch.dict(sys.modules, {'tkinter': tkinter, 'tkinter.ttk': ttk}), \
                        mock.patch.object(startup.project, 'projects', return_value=[owner]), \
                        mock.patch.object(startup.project, 'run', run), \
                        mock.patch.object(startup, 'setting', return_value=None), \
                        mock.patch('threading.Thread', ImmediateThread):
                    self.assertEqual(startup.choose_map(), expected)
                self.assertEqual(ask.call_count, 0 if built else 1)
                self.assertEqual(run.call_count, 1 if confirmed and not built else 0)
                self.assertEqual(error.call_count, 1 if confirmed and not built and build_code else 0)
