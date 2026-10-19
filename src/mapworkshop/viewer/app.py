"""The map viewer: your maps rendered like the game, live as you build them.

    mw view [MAP]          a project (id or prefix), a stock map or a .map file;
                           by default the map you worked on last

Two cameras: Edit (the orbit camera, for working on the map) and Photo (a
free camera with a lens, for looking and pictures). V switches between them.

Edit mouse
  Left drag            orbit around the focus point
  Right / middle drag  grab and pan the ground
  Wheel                zoom towards the cursor
  Double-click         fly to the clicked point

Edit keyboard
  W A S D / arrows     move (Shift faster, Ctrl slower)
  Q / E                rotate left / right
  R / F                tilt up / down
  Z / X                zoom in / out
  Space / Home         reset to the whole-map view
  T                    toggle top-down view

Photo (the mouse is captured: Esc frees it, a click in the view takes it back)
  Mouse                look around
  Right drag           slide sideways and up
  Wheel                move forward / back;  Alt+wheel focal length;  Shift+wheel focus
  Middle click         focus on the centre of the view
  W A S D / arrows     fly (Shift faster, Ctrl slower);  Space / C  up / down
  Q / E, R             roll left / right, level again
  Nothing holds the camera above the ground. Marks are hidden; these controls
  are listed above the camera bar.

Both
  V          Edit / Photo
  Ctrl+1..9  go to saved view 1-9;  Ctrl+Shift+1..9  save the view there
  Ctrl+C     copy the view as a `mw render` command
  1 objects  2 water  3 shadows  4 normal maps  5 clouds  6 weather  7 walkable
  8 river flow arrows  9 editor markers  U units  M marks
  G grid  B border  P screenshot  F5 reload  Ctrl+B build  F1 controls
  Del        delete the selected mark;  Ctrl+Z  undo a mark change
  Esc        steps back: closes a menu or list, cancels a drawing, drops the
             selection, puts the mark tool away; in Photo frees the mouse, then
             goes back to Edit. It never closes the viewer

Toolbar
  Map        your map projects, then the game's maps; Open project folder; Browse...
  Properties the map's map-wide settings in a window: camera, WorldInfo flags,
             environment, water and weather (mapkit.properties). For a project,
             Save and build writes them into map.toml and rebuilds; a game map
             is shown read-only
  Build      rebuild the current project; the scene reloads when it is done and
             a failed build shows its error in the status bar. The chip at the
             right shows a running build, then when the last one ended
  Test In-Game  start BFME2 straight in a skirmish on the current project (mw play);
             the dropdown beside it picks OpenBFME instead (mw play --godot), and
             is remembered (test_game in local/config.toml)
  Preview    how the map is shown, without changing it: detail level (Low,
             Medium, High), the map's own weather or a preset (clear, haze, rain,
             snow, dusk), the weather's own sun or a light rig over it
  View       layers: objects, units, water, shadows; cloud shadows, normal maps,
             fog and rain/snow; grid, map border, walkable, river flow, marks;
             animate; the game's object limits; editor markers (9: the
             WorldBuilder-only models the game never draws, such as the AI's
             farm sites). Units (U): hordes as their members, each unit in the
             first frame of its idle animation; off leaves every unit out
  Buttons    top view, reset view, screenshot
  FPS        the frame rate at the right; click it to cap it (30-144), follow the
             monitor (VSync) or run unlimited. Default 60 (--fps).

Marks palette (top left of the view)
  Navigate, Pin, Circle, Rectangle, Freehand; Undo, Delete, Clear all; Copy for
  agent. The mouse navigates until you pick a tool; the tool then draws until
  Esc (or a second click on it). Click a mark to select it: drag it to move it,
  drag its square handles to resize it (a rectangle's round handle rotates it,
  Shift snaps to 15 degrees), Del deletes it, Ctrl+Z undoes. Rectangles are
  drawn lined up with the screen. Marks are red, numbered and saved per map, and
  a panel lists what each one covers. Copy for agent puts the marks, their map
  coordinates, the objects inside and the map's source project on the
  clipboard, to paste into an agent ("add a forest in mark 2"); `mw marks`
  prints the same.

Camera bar (bottom left of the view)
  Edit / Photo; Views (saved views with thumbnails: go to one, save, rename,
  delete; kept per map in local/views/); Copy view; in Photo the lens: focal
  length, aperture (depth of field), focus distance, exposure (EV) - wheel or
  drag sideways over one, click for presets - and the framing aids: Thirds and
  the frame's aspect (screenshots crop to it); then the camera readout.
  Depth of field and exposure are photo effects the game does not have.

Live reload: the viewer watches the map file and its map.ini. When either
changes (a build, `mw dev`, an editor save) the scene reloads in place and the
camera stays where it is. A failed reload keeps the previous scene.

The camera is a preview camera, not the game's. Rendering follows the game
detail level chosen with --lod (default medium).
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import glfw
import moderngl
import numpy as np

from mapworkshop import game, project
from mapworkshop.config import RENDERS, GAME_LABEL, save_setting, setting
from mapworkshop.mapkit.weather import PRESETS, SUNS
from mapworkshop.render.camera import view_from_dict
from mapworkshop.render.photo import Post, active, focal_from_fov, fov_from_focal, sensor
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer import camerabar as bar
from mapworkshop.viewer.camera import Camera, FlyCamera
from mapworkshop.viewer.camerabar import CameraBar, Sampler
from mapworkshop.viewer.commands import Command, Commands
from mapworkshop.viewer.jobs import TEST_GAMES, Build, MarksSummary, Status, Walkability, play
from mapworkshop.viewer.marking import CLICK_PIXELS, MarkEditor, summary_lines
from mapworkshop.viewer.overlay import MarkOverlay
from mapworkshop.viewer.palette import Palette
from mapworkshop.viewer.session import TOAST_DELAY, Session
from mapworkshop.viewer.toolbar import Toolbar
from mapworkshop.viewer.views import SLOTS, THUMBNAIL, Views, edit_spec, photo_spec, render_command

FPS_LIMITS = ('30', '60', '90', '120', '144', 'vsync', 'unlimited')
DOUBLE_CLICK = 0.3        # s between the clicks of a double-click
# The View menu: command ids in groups; None separates them.
VIEW_MENU = ('objects', 'units', 'water', 'shadows', None, 'clouds', 'normal_maps', 'fx', None,
             'grid', 'border', 'walkable', 'flow', 'marks', None, 'animate', 'limits', 'markers')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('map', nargs='?', help='Map project, stock map or .map file (default: the last one)')
    parser.add_argument('--map', dest='map_option', help=argparse.SUPPRESS)
    parser.add_argument('--lod', choices=['low', 'medium', 'high'], default='medium')
    parser.add_argument('--size', default='1600x1000', help='Initial window size')
    parser.add_argument('--samples', type=int, default=4, help='MSAA samples')
    parser.add_argument('--weather', default='map',
                        help="Weather: 'map' (the map's own) or a preset: clear, haze, rain, snow, dusk")
    parser.add_argument('--fps', default='60', choices=FPS_LIMITS,
                        help="Frame rate cap: 30, 60, 90, 120, 144, 'vsync' or 'unlimited' (default 60)")
    parser.add_argument('--sun', default='own',
                        help="Sun: 'own' (the weather's) or a mapkit.weather sun: ember, copper, blood, "
                             "sulphur, ash, violet")
    parser.add_argument('--exit-after', type=float, help=argparse.SUPPRESS)  # smoke tests
    parser.add_argument('--snapshot', type=Path, help=argparse.SUPPRESS)   # smoke tests: save the window
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        source = project.map_path(args.map or args.map_option)
    except LookupError as error:
        raise SystemExit(str(error))
    if project.for_map_file(source):
        project.remember(project.for_map_file(source))
    width, height = (int(v) for v in args.size.lower().split('x'))
    if not glfw.init():
        raise SystemExit('Could not initialise GLFW')
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.SAMPLES, args.samples)
    window = glfw.create_window(width, height, f'{source.stem} - loading...', None, None)
    if not window:
        glfw.terminate()
        raise SystemExit('Could not open an OpenGL 4.3 window')
    glfw.make_context_current(window)
    # Frames are paced by the limiter in run(); VSync only when chosen.
    glfw.swap_interval(1 if args.fps == 'vsync' else 0)
    ctx = moderngl.create_context(require=430)
    # Release the previous scene's GPU objects once a reload replaces it.
    ctx.gc_mode = 'auto'
    print(__doc__)
    viewer = Viewer(args, source, window, ctx)
    # CPU preparation and Pillow's UI text both use Python. A shorter
    # timeslice prevents repeated 5 ms GIL waits while drawing toolbar text.
    previous_switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.001)
    try:
        viewer.run()
    finally:
        viewer.close()
        glfw.terminate()
        sys.setswitchinterval(previous_switch_interval)
    return 0


class Viewer:
    """The viewer window: the scene (session), the camera, marks editing,
    the toolbar rows and the background jobs, tied to GLFW's input."""

    def __init__(self, args, source, window, ctx):
        self.args, self.window, self.ctx = args, window, ctx
        self.status = Status()
        self.session = Session(source, self.status, lod=args.lod, weather=args.weather, sun=args.sun)
        self.camera = Camera(lambda x, y: np.zeros_like(np.asarray(x, float)), (1000, 1000))
        self.fly = FlyCamera(self.camera.surface)
        self.mode = 'edit'                 # 'edit': the orbit camera; 'photo': the free camera (FlyCamera)
        self.captured = False              # Photo mode has the mouse
        self.look = None                   # the cursor position the last mouse look started from
        self.framing = dict(thirds=False, frame='free')
        self.camerabar = CameraBar(ctx)
        self.readout = Sampler()
        self.views = None                  # the map's saved views (viewer.views)
        self.pending_save = None           # (slot, mode, spec): saved with a thumbnail of the next frame
        self.scrub = None                  # a drag over a lens field: [field, last x, moved]
        self.post = None                   # Photo mode's exposure and depth of field (render.photo)
        self.autofocus = False             # focus on what the next frame shows at the centre
        self.build = Build(self.status, lambda toast: setattr(self.session, 'toast', toast))
        self.walkability = Walkability(self.status)
        self.summary = MarksSummary()
        self.overlay = MarkOverlay(ctx)
        self.editor = MarkEditor(self.overlay, self, self.status)
        self.editor.marks = self.session.marks
        self.view = dict(grid=False, border=False, animate=True)
        self.time = 0.0                    # the game clocks' time: animation, water, clouds
        self.fps, self.fps_limit, self.next_frame = 0.0, args.fps, 0.0
        self.nav = None                    # a navigation drag: ('orbit', last position) or ('pan', anchor)
        self.press = None                  # where the last button press was
        self.last_click = 0.0
        self.cursor = None
        self.properties = None             # the Properties window (viewer.properties)
        self.properties_saved = None       # the project its Save wrote, for the frame loop to build
        self.test_game = setting('test_game', 'original')   # what Test In-Game starts: TEST_GAMES
        if self.test_game not in TEST_GAMES:
            self.test_game = 'original'
        # Map actions, then how the map is previewed and what is shown, then
        # the camera; at the right the status text, the last build and the
        # frame rate.
        self.toolbar = Toolbar(ctx, [
            dict(kind='dropdown', id='map', label='Map'), dict(kind='button', id='properties', label='Properties'),
            dict(kind='button', id='build', label='Build'), dict(kind='button', id='play', label='Test In-Game'),
            dict(kind='dropdown', id='test_game'),
            dict(kind='gap'),
            dict(kind='dropdown', id='preview', label='Preview'),
            dict(kind='dropdown', id='view', title='View'),
            dict(kind='gap'),
            dict(kind='button', id='top', label='Top view'), dict(kind='button', id='reset', label='Reset view'),
            dict(kind='button', id='shot', label='Screenshot'),
            dict(kind='status', id='status'), dict(kind='chip', id='build_chip', align='right'),
            dict(kind='dropdown', id='fps', align='right')])
        # The marking tools, at the top left of the 3D view.
        self.palette = Palette(ctx, top=lambda: self.toolbar.height)
        self.commands = self._commands()
        self.cursors = {name: glfw.create_standard_cursor(shape) for name, shape in (
            ('draw', glfw.CROSSHAIR_CURSOR), ('move', glfw.RESIZE_ALL_CURSOR), ('rotate', glfw.POINTING_HAND_CURSOR),
            ('ew', glfw.RESIZE_EW_CURSOR), ('ns', glfw.RESIZE_NS_CURSOR),
            ('nesw', glfw.RESIZE_NESW_CURSOR), ('nwse', glfw.RESIZE_NWSE_CURSOR))}
        glfw.set_mouse_button_callback(window, self.guarded('the click', self.on_mouse_button))
        glfw.set_cursor_pos_callback(window, self.guarded('the mouse move', self.on_cursor))
        glfw.set_scroll_callback(window, self.guarded('the wheel', self.on_scroll))
        glfw.set_key_callback(window, self.guarded('the key', self.on_key))

    def guarded(self, what, handler):
        """`handler` for a GLFW callback: an error shows in the status bar (and
        the terminal) instead of closing the viewer, as pyGLFW re-raises it
        from poll_events."""
        def call(*args):
            try:
                return handler(*args)
            except Exception as error:
                self.report(what, error)
        return call

    def report(self, what, error):
        """An error in the status bar and the terminal, the viewer kept open."""
        import traceback
        traceback.print_exc()
        self.status.set(f'{what} failed: {error}'[:160], 10)

    @property
    def renderer(self):
        return self.session.renderer

    # Commands ------------------------------------------------------------------
    def _commands(self):
        c = Commands(lambda name: getattr(glfw, 'KEY_' + name))
        visible = lambda name: lambda: self.renderer.visible[name]
        option = lambda name: lambda: self.renderer.options[name]
        view = lambda name: lambda: self.view[name]
        c.add(
            # The View menu's layers and options.
            Command('objects', lambda: self.flip_visible('objects'), 'Objects', ('1',), visible('objects')),
            Command('units', self.flip_units, 'Units (in their idle pose)', ('U',), option('units')),
            Command('water', lambda: self.flip_visible('water'), 'Water', ('2',), visible('water')),
            Command('shadows', lambda: self.flip_visible('shadows'), 'Shadows', ('3',), visible('shadows')),
            Command('normal_maps', lambda: self.flip_option('normal_maps'), 'Normal maps', ('4',),
                    option('normal_maps')),
            Command('clouds', lambda: self.flip_option('clouds'), 'Cloud shadows', ('5',), option('clouds')),
            Command('fx', lambda: self.flip_visible('weather'), 'Fog and rain/snow', ('6',), visible('weather')),
            Command('walkable', self.flip_walkable, 'Walkable (local estimate)', ('7',), visible('walkable')),
            Command('flow', lambda: self.flip_visible('flow'), 'River flow arrows', ('8',), visible('flow')),
            Command('marks', self.editor.toggle_visible, 'Marks', ('M',), lambda: self.editor.visible),
            Command('grid', lambda: self.flip_view('grid'), 'Grid', ('G',), view('grid')),
            Command('border', lambda: self.flip_view('border'), 'Map border', ('B',), view('border')),
            Command('animate', lambda: self.flip_view('animate'), 'Animate', checked=view('animate')),
            Command('limits', self.flip_limits, 'Game object limits (1,200 trees, 2,000 shrubs)',
                    checked=option('vegetation_limits')),
            Command('markers', self.flip_markers, 'Editor markers (AI farm sites, cinematic proxies)', ('9',),
                    option('editor_markers')),
            # Toolbar buttons and keys. Build, Test In-Game and Properties need
            # no scene: they work while the first load is still running or after it failed.
            Command('build', lambda: self.build.start(self.session.owner), keys=('Ctrl+B',), needs_scene=False),
            Command('play', lambda: play(self.session.owner, self.status, self.test_game), needs_scene=False),
            Command('properties', self.open_properties, needs_scene=False),
            Command('reload', self.request_reload, keys=('F5',), needs_scene=False),
            Command('back', self.back, keys=('Esc',), needs_scene=False),
            Command('top', self.top_view, keys=('T',)),
            Command('reset', self.reset_view, keys=('Space', 'Home')),
            Command('shot', self.screenshot, keys=('P',)),
            Command('help', lambda: print(__doc__), keys=('F1',)),
            # The camera bar.
            Command('mode', lambda: self.set_mode('edit' if self.mode == 'photo' else 'photo'), 'Photo mode', ('V',)),
            Command('copy_view', self.copy_view, keys=('Ctrl+C',)),
            # Marks.
            Command('delete', self.editor.delete_selected, keys=('Del', 'Backspace'),
                    when=lambda: self.editor.visible and self.mode == 'edit'),
            Command('undo', self.editor.undo, keys=('Ctrl+Z',), when=lambda: self.mode == 'edit'),
            Command('clear', self.editor.clear),
            Command('copy', self.copy_for_agent))
        for slot in SLOTS:
            c.add(Command(f'view{slot}', lambda slot=slot: self.recall_view(slot), keys=(f'Ctrl+{slot}',)),
                  Command(f'save{slot}', lambda slot=slot: self.save_view(slot), keys=(f'Ctrl+Shift+{slot}',)))
        return c

    def flip_visible(self, name):
        self.renderer.visible[name] = not self.renderer.visible[name]

    def flip_walkable(self):
        self.flip_visible('walkable')
        self.walkability.request(self.renderer)

    def flip_option(self, name):
        """Normal maps or cloud shadows: switched on the scene, and kept for the next load."""
        self.session.options[name] = not self.renderer.options[name]
        self.renderer.set_option(name, self.session.options[name])

    def flip_limits(self):
        self.session.options['limits'] = not self.session.options['limits']
        self.session.reload = True

    def flip_markers(self):
        """Show or hide the WorldBuilder-only models, which the game never draws."""
        self.session.options['markers'] = not self.session.options['markers']
        self.session.reload = True

    def flip_units(self):
        """Show the units, hordes as their members in their idle pose, or hide them."""
        self.session.options['units'] = not self.session.options['units']
        self.session.reload = True

    def flip_view(self, name):
        self.view[name] = not self.view[name]

    def request_reload(self):
        self.session.reload = True

    def back(self):
        """Esc steps back: close a menu or the camera bar's list, then the
        marking levels (MarkEditor.escape); in Photo mode free the mouse, then
        go back to Edit. It never closes the viewer."""
        if self.toolbar.open_menu:
            self.toolbar.open_menu = None
        elif self.camerabar.open:
            self.camerabar.open = None
        elif self.mode == 'photo':
            if self.captured:
                self.set_capture(False)
            else:
                self.set_mode('edit')
        elif self.renderer is not None:
            self.editor.escape()
        if self.renderer is not None and self.editor.drag is None and self.nav is None:
            self.update_pointer(self.toolbar_target(self.cursor_pos()), self.cursor_pos())

    # Toolbar and menus ------------------------------------------------------------
    def menu_entries(self, menu):
        o = self.session.options
        if menu == 'map':
            self.session.refresh_owners()
            current = self.session.requested
            own = [(str(p.map_file), p.title, p.map_file.resolve() == current)
                   for p in self.session.owners.values() if p.map_file.exists()]
            stock = sorted(((str(m), self.session.title(m), m == current) for m in game.stock_maps()),
                           key=lambda e: e[1].lower())
            folder = [('folder', 'Open project folder', None)] if self.session.owner else []
            return own + [(None, '', None)] + stock + [(None, '', None)] + folder + [('browse', 'Browse...', None)]
        if menu == 'preview':
            # Values are 'option:value'; headings are (None, text, None).
            entry = lambda key, value, text: (f'{key}:{value}', text, o[key] == value)
            return ([(None, 'Preview only: these do not change the map', None), (None, '', None),
                     (None, 'Detail', None)] +
                    [entry('lod', v, v.title()) for v in ('low', 'medium', 'high')] +
                    [(None, 'Weather', None), entry('weather', 'map', "Map's own")] +
                    [entry('weather', v, v.title()) for v in PRESETS] +
                    [(None, 'Sun', None), entry('sun', 'own', "Weather's own")] +
                    [entry('sun', k, v['label']) for k, v in SUNS.items()] +
                    [(None, '', None), (None, "The map's own weather: Properties", None)])
        if menu == 'test_game':
            return [(None, 'Test In-Game starts', None),
                    ('original', f'{GAME_LABEL}, straight in a skirmish', self.test_game == 'original'),
                    ('openbfme', 'OpenBFME (Godot), at its menu', self.test_game == 'openbfme')]
        if menu == 'fps':
            label = lambda v: dict(vsync='VSync (monitor rate)', unlimited='Unlimited').get(v, f'{v} fps')
            return [(v, label(v), self.fps_limit == v) for v in FPS_LIMITS[:-2]] + [(None, '', None)] + \
                   [(v, label(v), self.fps_limit == v) for v in FPS_LIMITS[-2:]]
        return self.commands.menu(VIEW_MENU, self.renderer is not None)

    def toolbar_state(self):
        r, o = self.renderer, self.session.options
        message = self.status.current()
        hint = self.editor.hint() if r is not None else None
        if self.session.loading and r is None:
            status = ''
        elif self.build.running:
            status = f'building: {self.build.line}'
        elif message is not None:
            status = message
        elif r is None:
            status = 'Choose a map to load'
        elif self.mode == 'photo':
            status = ('Photo: the mouse looks around - Esc frees it, V goes back to Edit' if self.captured
                      else 'Photo: click the view to look around - Esc or V goes back to Edit')
        elif hint:
            status = hint
        else:
            status = ''
        preview = [o['lod'].title(), "Map's own" if o['weather'] == 'map' else o['weather'].title()]
        if o['sun'] != 'own':
            preview.append(SUNS[o['sun']]['label'])
        return dict(map=self.session.title(), preview=' · '.join(preview), status=status,
                    test_game='OpenBFME' if self.test_game == 'openbfme' else GAME_LABEL,
                    build_chip=self.build_chip(),
                    fps=f'{self.fps:.0f} fps' + ('' if self.fps_limit in ('vsync', 'unlimited')
                                                 else f' / {self.fps_limit}'))

    def build_chip(self):
        """The toolbar's build chip: a build running, or how the viewer's
        last build ended and when; '' before the first."""
        build = self.build
        if build.running:
            return f'Building {time.perf_counter()-build.started:.0f} s', 'busy'
        if build.outcome is None:
            return ''
        ok, seconds, finished = build.outcome
        at = time.strftime('%H:%M', time.localtime(finished))
        return (f'Built {at} · {seconds:.0f} s', 'good') if ok else (f'Build failed {at}', 'bad')

    def toolbar_target(self, pos):
        k = self.scale()
        target = self.toolbar.target_at(pos[0]*k, pos[1]*k)
        if target is None and self.renderer is not None:
            target = self.camerabar.target_at(pos[0]*k, pos[1]*k)
            if target is None and self.mode == 'edit':
                target = self.palette.target_at(pos[0]*k, pos[1]*k)
        return target

    def toolbar_click(self, target):
        """Act on a toolbar click; an error shows in the status bar (and the
        terminal) instead of closing the viewer."""
        try:
            self.handle_click(target)
        except Exception as error:
            self.report(target[1] if isinstance(target, tuple) else target, error)

    def handle_click(self, target):
        toolbar = self.toolbar
        if target == 'menu':
            return
        if target in ('bar', 'panel', 'palette', 'camerabar', 'popover'):
            toolbar.open_menu = None
            return
        kind = target[0]
        if kind in ('mode', 'field', 'toggle', 'pick', 'rename', 'delete') or target in (
                ('menu', 'views'), ('menu', 'frame'), ('button', 'copy_view')):
            toolbar.open_menu = None
            self.camera_click(target)
        elif kind == 'menu_scroll':
            toolbar.scroll_menu(target[2]*5)
        elif kind == 'dropdown':
            menu = target[1]
            if toolbar.open_menu and toolbar.open_menu[0] == menu:
                toolbar.open_menu = None
            else:
                toolbar.open_menu = (menu, self.menu_entries(menu))
        elif kind == 'menu':
            self.choose(target[1], target[2])
        else:
            toolbar.open_menu = None
            if kind == 'tool':
                self.editor.set_tool(target[1])
            elif kind == 'button':
                self.commands.run(target[1], self.renderer is not None)

    def choose(self, menu, value):
        """A menu entry was clicked."""
        if menu in ('view', 'preview'):
            # These menus stay open so several settings can be switched.
            if menu == 'view':
                self.commands.run(value, self.renderer is not None)
            else:
                self.set_preview(*value.split(':', 1))
            self.toolbar.open_menu = (menu, self.menu_entries(menu))
            return
        self.toolbar.open_menu = None
        if menu == 'test_game':
            self.test_game = value
            save_setting('test_game', value)
            self.status.set('Test In-Game starts ' + ('OpenBFME' if value == 'openbfme' else GAME_LABEL), 4)
        elif menu == 'fps':
            self.fps_limit = value
            glfw.swap_interval(1 if value == 'vsync' else 0)
            self.next_frame = 0.0
            self.status.set(f'frame rate: {value}', 2)
        elif menu == 'map':
            if value == 'folder':
                # The menu may have been opened for the map shown before.
                owner = self.session.owner
                if owner is None:
                    self.status.set('this map is not a project: it has no project folder', 4)
                else:
                    import os
                    os.startfile(owner.folder)
                return
            path = self.browse_map() if value == 'browse' else Path(value)
            if path:
                self.session.open_map(path)

    def set_preview(self, option, value):
        """Detail ('lod'), 'weather' or 'sun': reloads the scene with it."""
        if self.session.options[option] != value:
            self.session.options[option] = value
            if option == 'lod':
                self.session.options['normal_maps'] = None
            self.session.reload = True

    def browse_map(self):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(title='Open a BFME2 map', initialdir=str(self.session.source.parent.parent),
                                          filetypes=[('BFME2 maps', '*.map'), ('All files', '*.*')])
        root.destroy()
        return Path(path) if path else None

    def open_properties(self):
        """The Properties window (viewer.properties) for the map shown: editable
        for a project, read-only for a game map. Saving rebuilds the project."""
        from mapworkshop.render.assets import GameAssets
        from mapworkshop.viewer.properties import PropertiesDialog
        if self.properties is not None and self.properties.is_open:
            self.properties.lift()
            return
        r = self.renderer
        assets = r.assets if r is not None else GameAssets()
        ini_texts = dict(Weather=assets.ini_text('weather.ini'), WaterTransparency=assets.ini_text('water.ini'))

        def saved(updated):
            self.properties_saved = updated
        self.properties = PropertiesDialog(self.session.source, self.session.owner, ini_texts, saved)
        self.properties.open()

    def copy_for_agent(self):
        marks = self.session.marks
        if not marks.items:
            self.status.set('no marks to copy: draw some first', 4)
            return
        try:
            r = self.renderer
            data = json.loads(marks.path.read_text(encoding='utf-8'))
            text = marklib.agent_text(marklib.describe(data, assets=r.assets, m=r.map, terrain=r.terrain))
        except Exception as error:
            self.status.set(f'could not read the marks: {error}'[:140], 8)
            return
        glfw.set_clipboard_string(self.window, text)
        self.status.set(f'copied {len(marks.items)} marks for an agent - paste them into your request', 6)

    # Cameras -------------------------------------------------------------------------
    def current_camera(self, aspect):
        return self.fly.matrices(aspect) if self.mode == 'photo' else self.camera.matrices(aspect)

    def set_capture(self, on):
        """Photo mode takes the mouse (hidden, turning the view) or frees it."""
        self.captured = on
        glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_DISABLED if on else glfw.CURSOR_NORMAL)
        if glfw.raw_mouse_motion_supported():
            glfw.set_input_mode(self.window, glfw.RAW_MOUSE_MOTION, glfw.TRUE if on else glfw.FALSE)
        self.look = self.cursor_pos() if on else None
        self.nav = None
        if on:
            self.camerabar.open = None
            self.toolbar.open_menu = None

    def set_mode(self, mode):
        """Switch between Edit and Photo without moving the view: Photo starts
        where the orbit camera is, with its lens as it was left; Edit orbits
        the ground Photo looks at."""
        if mode == self.mode or self.renderer is None:
            return
        if mode == 'photo':
            w, h = self.window_size()
            cam = self.camera.matrices(w/max(h, 1))
            ahead = cam['target']-cam['eye']
            self.fly.place(cam['eye'], ahead, focus=float(np.linalg.norm(ahead)))
        else:
            self.camera.aim(self.fly.eye, self.fly.forward(), self.fly.pick_ahead(self.window_size()))
        self._enter(mode)

    def _enter(self, mode):
        self.mode = mode
        self.camerabar.open = None
        self.autofocus = False
        if mode == 'edit' and self.post is not None:
            self.post.release()            # the lens's targets: a full-size MSAA frame and more
            self.post = None
        if mode == 'photo':
            self.editor.set_tool(None)
        self.set_capture(mode == 'photo')

    def top_view(self):
        if self.mode == 'photo':
            self.set_mode('edit')
        self.camera.toggle_top()

    def reset_view(self):
        if self.mode == 'photo':
            self.set_mode('edit')
        self.camera.reset()

    def view_spec(self):
        """(mode, render.camera spec) of the current view."""
        if self.mode == 'photo':
            return 'photo', photo_spec(self.fly)
        return 'edit', edit_spec(self.camera)

    def copy_view(self):
        _, spec = self.view_spec()
        owner = self.session.owner
        glfw.set_clipboard_string(self.window, render_command(owner.id if owner else f'"{self.session.source}"',
                                                              'view', spec))
        self.status.set('copied the view as a mw render command', 5)

    def save_view(self, slot=None):
        """Save the view in `slot` (1-9; None: the first free one) with a
        thumbnail of the next frame."""
        if self.views is not None:
            self.pending_save = (slot,) + self.view_spec()

    def finish_save(self, size):
        """The pending save, with the frame just drawn (before the bars) as its thumbnail."""
        from PIL import Image, ImageOps
        slot, mode, spec = self.pending_save
        self.pending_save = None
        w, h = size
        pixels = np.frombuffer(self.ctx.screen.read(viewport=(0, 0, w, h), components=3), np.uint8).reshape(h, w, 3)
        image = Image.fromarray(np.flipud(pixels))
        if mode == 'photo':
            image = image.crop(bar.frame_rect(size, bar.frame_ratio(self.framing['frame'])))
        entry = self.views.save(mode, spec, slot, ImageOps.fit(image, THUMBNAIL, Image.LANCZOS))
        where = f' - Ctrl+{entry["slot"]} goes back to it' if entry['slot'] else ''
        self.status.set(f'saved {entry["name"]}{where}', 5)
        if self.camerabar.open and self.camerabar.open[0] == 'views':
            self.camerabar.refresh_list(self.view_entries())

    def recall_view(self, slot):
        entry = self.views.by_slot(slot) if self.views is not None else None
        if entry is None:
            self.status.set(f'no view saved as {slot} - Ctrl+Shift+{slot} saves the current one there', 4)
            return
        self.apply_view(entry)

    def apply_view(self, entry):
        """Go to a saved view, in its mode."""
        try:
            view = view_from_dict(entry['spec'])
        except ValueError as error:
            self.status.set(f'{entry["name"]}: {error}', 6)
            return
        if entry['mode'] == 'photo':
            eye = np.array(view.eye, float)
            target = np.array(view.target[:3], float) if len(view.target) > 2 else \
                np.array([*view.target[:2], self.camera.ground(*view.target[:2])])
            self.fly.place(eye, target-eye, focus=view.focus or float(np.linalg.norm(target-eye)))
            self.fly.roll = view.roll or 0.0
            self.fly.focal = view.focal or focal_from_fov(view.fov)
            self.fly.aperture, self.fly.ev = view.aperture, view.ev or 0.0
            if self.mode != 'photo':
                self._enter('photo')
        else:
            g = self.camera.goal
            g.update(x=float(view.target[0]), y=float(view.target[1]), distance=float(view.distance),
                     elevation=float(view.elevation), heading=float(view.heading))
            self.camera.top = None
            if self.mode != 'edit':
                self._enter('edit')
        self.status.set(entry['name'], 2)

    def view_entries(self):
        """The Views list: save, then each saved view."""
        views = self.views
        free = views.free_slot()
        out = [dict(target=('pick', 'views', 'save'), text='Save the current view',
                    hint=f'Ctrl+Shift+{free}' if free else '')]
        out.append(dict(target=None, text='Saved views' if views.items else 'No saved views yet'))
        for v in views.items:
            out.append(dict(target=('pick', 'views', v['name']), text=v['name'], name=v['name'],
                            hint=v['mode'].title() + (f'   Ctrl+{v["slot"]}' if v['slot'] else ''),
                            thumbnail=views.thumbnail_path(v['name']), actions=(('rename', '…'), ('delete', '×'))))
        return out

    def lens_entries(self, field):
        """A lens field's presets."""
        f = self.fly
        if field == 'focal':
            w, h = self.window_size()
            width = sensor(f.frame_aspect(w/max(h, 1)))[0]
            return [dict(target=None, text='Focal length (full frame)')] + [
                dict(target=('pick', 'focal', v), text=f'{v} mm', hint=f'{fov_from_focal(v, width):.0f}° wide',
                     checked=abs(f.focal-v) < 0.5) for v in bar.FOCALS]
        if field == 'aperture':
            return [dict(target=None, text='Aperture: depth of field')] + [
                dict(target=('pick', 'aperture', v), text='Off: all sharp' if v is None else f'f/{v:g}',
                     checked=f.aperture == v) for v in bar.APERTURES]
        if field == 'focus':
            return [dict(target=None, text='Focus distance'),
                    dict(target=('pick', 'focus', 'centre'), text='On the centre of the view', hint='middle click')] + [
                dict(target=('pick', 'focus', v), text=f'{v:,} units', hint=f'{v/10:g} m',
                     checked=abs(f.focus-v) < 0.5) for v in bar.FOCUS_DISTANCES]
        return [dict(target=None, text='Exposure')] + [
            dict(target=('pick', 'ev', v), text=bar.ev_text(v), checked=abs(f.ev-v) < 1e-6) for v in bar.EXPOSURES]

    def frame_entries(self):
        return [dict(target=None, text='Frame (screenshots crop to it)')] + [
            dict(target=('pick', 'frame', v), text=label, checked=self.framing['frame'] == v) for v, label, _ in bar.FRAMES]

    def camera_click(self, target):
        """A click on the camera bar or its list."""
        kind, value = target[0], target[1]
        cb = self.camerabar
        if kind == 'mode':
            self.set_mode(value)
        elif target == ('menu', 'views'):
            cb.toggle_list('views', self.view_entries())
        elif target == ('menu', 'frame'):
            cb.toggle_list('frame', self.frame_entries())
        elif target == ('button', 'copy_view'):
            self.copy_view()
        elif kind == 'toggle':
            self.framing[value] = not self.framing[value]
        elif kind == 'field':
            cb.toggle_list(value, self.lens_entries(value))
        elif kind == 'pick':
            self.pick(target[1], target[2])
        elif kind == 'rename':
            self.rename_view(value)
        elif kind == 'delete' and self.views.delete(value):
            self.status.set(f'deleted {value}', 4)
            cb.refresh_list(self.view_entries())

    def pick(self, menu, value):
        """An entry of the camera bar's list was clicked."""
        self.camerabar.open = None
        f = self.fly
        if menu == 'views':
            if value == 'save':
                self.save_view()
            else:
                self.apply_view(self.views.by_name(value))
        elif menu == 'frame':
            self.framing['frame'] = value
            f.frame = bar.frame_ratio(value)
        elif menu == 'focal':
            f.focal = float(value)
        elif menu == 'aperture':
            f.aperture = value
        elif menu == 'focus':
            if value == 'centre':
                self.focus_centre()
            else:
                f.focus = float(value)
        elif menu == 'ev':
            f.ev = float(value)

    def rename_view(self, name):
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        new = simpledialog.askstring('Rename view', 'Name of the view:', initialvalue=name, parent=root)
        root.destroy()
        if new:
            try:
                self.views.rename(name, new)
            except ValueError as error:
                self.status.set(str(error), 5)
        self.camerabar.refresh_list(self.view_entries())

    def focus_centre(self):
        """Focus on what is at the centre of the view, ground or object: read
        from the next frame's depth (draw)."""
        self.autofocus = True

    def focused(self, distance):
        """Autofocus found `distance` along the view at the centre (None: nothing drawn there)."""
        self.autofocus = False
        if distance is None:
            self.status.set('nothing at the centre of the view to focus on', 3)
            return
        self.fly.focus = distance
        self.status.set(f'focus {distance:,.0f}', 2)

    def adjust_field(self, field, notches):
        """The wheel (or a sideways drag) over a lens field."""
        f = self.fly
        if field == 'focal':
            f.zoom(notches)
        elif field == 'aperture':
            steps = list(bar.APERTURES)
            i = steps.index(f.aperture) if f.aperture in steps else min(
                range(1, len(steps)), key=lambda k: abs(steps[k]-f.aperture))
            f.aperture = steps[min(len(steps)-1, max(0, i+int(math.copysign(1, notches))))]
        elif field == 'focus':
            f.refocus(notches)
        elif field == 'ev':
            f.ev = min(3.0, max(-3.0, round(f.ev+0.1*notches, 2)))
        if self.camerabar.open and self.camerabar.open[0] == field:
            self.camerabar.refresh_list(self.lens_entries(field))

    def bar_state(self):
        w, h = self.window_size()
        state = dict(mode=self.mode, readout=self.readout.get(
            lambda: bar.readout(self.mode, self.camera, self.fly, w/max(h, 1))))
        if self.mode == 'photo':
            f = self.fly
            state.update(focal=round(f.focal, 1), aperture=f.aperture, focus=round(f.focus), ev=round(f.ev, 2),
                         thirds=self.framing['thirds'], frame=self.framing['frame'])
        return state

    def screenshot(self):
        """The view as a PNG in local/renders/; in Photo mode with the lens and
        exposure, cropped to the frame."""
        RENDERS.mkdir(parents=True, exist_ok=True)
        ctx, samples = self.ctx, self.args.samples
        w, h = glfw.get_framebuffer_size(self.window)
        cam = self.current_camera(w/h)
        pixels_rb = ctx.renderbuffer((w, h), 4)
        resolve = ctx.framebuffer([pixels_rb])
        options = dict(grid=self.view['grid'], border=self.view['border'], shadow_radius=6000, time=self.time)
        photo = self.mode == 'photo'
        if photo and active(self.fly.settings()):
            if self.post is None:
                self.post = Post(ctx, samples)
            self.renderer.draw(cam, (w, h), self.post.target((w, h)), **options)
            self.post.finish(cam, self.fly.settings(), resolve, taps=256)
            items = (resolve, pixels_rb)
        else:
            color = ctx.renderbuffer((w, h), 4, samples=samples)
            depth = ctx.depth_renderbuffer((w, h), samples=samples)
            fbo = ctx.framebuffer([color], depth)
            self.renderer.draw(cam, (w, h), fbo, **options)
            ctx.copy_framebuffer(resolve, fbo)
            items = (fbo, resolve, color, depth, pixels_rb)
        pixels = np.flipud(np.frombuffer(resolve.read(components=4), np.uint8).reshape(h, w, 4))[..., :3]
        for item in items:
            item.release()
        if photo:
            x0, y0, x1, y1 = bar.frame_rect((w, h), bar.frame_ratio(self.framing['frame']))
            pixels = pixels[y0:y1, x0:x1]
        kind = '-photo' if photo else ''
        path = RENDERS/f'{self.session.source.stem}{kind}-{time.strftime("%Y%m%d-%H%M%S")}.png'
        self.renderer.save(np.ascontiguousarray(pixels), path)
        self.session.toast = dict(kind='done', title='Screenshot saved', detail=f'{path.name}  ·  {RENDERS}',
                                  until=time.perf_counter()+4.0)
        print('Saved', path)

    # The world, for MarkEditor ------------------------------------------------------
    def ground_hit(self, pos, z=None):
        """Map point under the cursor: the terrain, or the plane at height z."""
        hit = self.camera.pick(pos, self.window_size())
        if hit is None and z is not None:
            hit = self.camera.plane_hit(pos, self.window_size(), z)
        return hit

    def plane_hit(self, pos, z):
        return self.camera.plane_hit(pos, self.window_size(), z)

    def focus_z(self):
        return self.camera.cur['z']

    def focus_distance(self):
        return self.camera.cur['distance']

    def screen_angle(self):
        return self.camera.screen_angle()

    def shift_held(self):
        return self.key_down(glfw.KEY_LEFT_SHIFT, glfw.KEY_RIGHT_SHIFT)

    # Input ---------------------------------------------------------------------------
    def scale(self):
        """Framebuffer pixels per window pixel."""
        ww = glfw.get_window_size(self.window)[0] or 1
        return glfw.get_framebuffer_size(self.window)[0]/ww

    def window_size(self):
        return glfw.get_window_size(self.window)

    def cursor_pos(self):
        return glfw.get_cursor_pos(self.window)

    def key_down(self, *keys):
        return any(glfw.get_key(self.window, k) == glfw.PRESS for k in keys)

    def on_mouse_button(self, win, button, action, mods):
        if self.mode == 'photo' and self.captured:
            self.photo_button(button, action)
            return
        pos = self.cursor_pos()
        target = self.toolbar_target(pos)
        if self.renderer is None:
            # The Map menu remains usable even before the first scene is ready.
            if action == glfw.PRESS and button == glfw.MOUSE_BUTTON_LEFT and target is not None:
                self.toolbar_click(target)
            return
        if action == glfw.RELEASE and self.scrub is not None:
            field, _, moved = self.scrub
            self.scrub = None
            if not moved:
                self.toolbar_click(('field', field))
            return
        if action == glfw.PRESS:
            if target is not None:
                if button == glfw.MOUSE_BUTTON_LEFT:
                    if isinstance(target, tuple) and target[0] == 'field':
                        self.scrub = [target[1], pos[0], False]     # a click opens its presets, a drag scrubs
                    else:
                        self.toolbar_click(target)
                return
            if self.toolbar.open_menu or self.camerabar.open:
                self.toolbar.open_menu = self.camerabar.open = None
                return
            if self.mode == 'photo':
                if button == glfw.MOUSE_BUTTON_LEFT:
                    self.set_capture(True)
                return
            self.press = pos
            if button == glfw.MOUSE_BUTTON_LEFT:
                k = self.scale()
                if self.editor.press(pos, (pos[0]*k, pos[1]*k), k):
                    return
                now = time.perf_counter()
                if now-self.last_click < DOUBLE_CLICK:
                    hit = self.camera.pick(pos, self.window_size())
                    if hit is not None:
                        self.camera.fly_to(hit)
                    self.last_click = 0.0
                    return
                self.last_click = now
                self.nav = ('orbit', pos)
            elif button in (glfw.MOUSE_BUTTON_RIGHT, glfw.MOUSE_BUTTON_MIDDLE):
                hit = self.camera.pick(pos, self.window_size())
                anchor = hit if hit is not None else self.camera.plane_hit(pos, self.window_size(), self.camera.cur['z'])
                self.nav = ('pan', anchor)
        elif action == glfw.RELEASE:
            nav, self.nav = self.nav, None
            self.editor.release()
            press = self.press
            if nav and nav[0] == 'orbit' and press and math.hypot(pos[0]-press[0], pos[1]-press[1]) < CLICK_PIXELS:
                # A click that did not orbit selects the mark under it.
                k = self.scale()
                self.editor.click((pos[0]*k, pos[1]*k), k)
            self.update_pointer(target, pos)

    def photo_button(self, button, action):
        """A button while Photo mode has the mouse: right drag slides, a
        middle click focuses on the centre."""
        if button == glfw.MOUSE_BUTTON_RIGHT:
            self.nav = ('slide', None) if action == glfw.PRESS else None
        elif button == glfw.MOUSE_BUTTON_MIDDLE and action == glfw.PRESS:
            self.focus_centre()

    def update_pointer(self, target, pos):
        """Show with the cursor what a press here does (MarkEditor.pointer)."""
        k = self.scale()
        active = (target is None and self.renderer is not None and not self.toolbar.open_menu
                  and self.mode == 'edit')
        cursor = self.editor.pointer((pos[0]*k, pos[1]*k), k, active)
        if cursor != self.cursor:
            self.cursor = cursor
            glfw.set_cursor(self.window, self.cursors.get(cursor))

    def on_cursor(self, win, x, y):
        if self.mode == 'photo' and self.captured:
            last = self.look or (x, y)
            self.look = (x, y)
            dx, dy = x-last[0], y-last[1]
            if self.nav and self.nav[0] == 'slide':
                self.fly.slide(dx, dy)
            else:
                self.fly.look(dx, dy)
            return
        if self.scrub is not None:
            field, last, _ = self.scrub
            notches = int((x-last)/6)
            if notches:
                self.adjust_field(field, notches)
                self.scrub = [field, last+notches*6, True]
            return
        if self.editor.drag is not None:
            self.editor.move((x, y))
            return
        if self.nav is None:
            target = self.toolbar_target((x, y))
            hover = target if isinstance(target, tuple) else None
            self.toolbar.hover = self.palette.hover = self.camerabar.hover = hover
            self.update_pointer(target, (x, y))
            return
        kind, anchor = self.nav
        if kind == 'orbit':
            self.camera.orbit(x-anchor[0], y-anchor[1])
            self.nav = ('orbit', (x, y))
        elif kind == 'pan' and anchor is not None:
            hit = self.camera.plane_hit((x, y), self.window_size(), float(anchor[2]))
            if hit is not None:
                self.camera.pan(anchor, hit)

    def on_scroll(self, win, dx, dy):
        if self.mode == 'photo' and self.captured:
            alt = self.key_down(glfw.KEY_LEFT_ALT, glfw.KEY_RIGHT_ALT)
            if alt:
                self.fly.zoom(dy)
            elif self.shift_held():
                self.fly.refocus(dy)
            else:
                self.fly.dolly(dy)
            return
        target = self.toolbar_target(self.cursor_pos())
        if target is not None:
            if isinstance(target, tuple) and target[0] == 'field':
                self.adjust_field(target[1], dy)
            elif target == 'menu' or (isinstance(target, tuple) and target[0] in ('menu', 'menu_scroll')):
                self.toolbar.scroll_menu(-dy*3)
            return
        if self.mode == 'edit':
            self.camera.zoom(dy, self.camera.pick(self.cursor_pos(), self.window_size()))

    def on_key(self, win, key, scancode, action, mods):
        if action != glfw.PRESS:
            return
        ctrl, shift = bool(mods & glfw.MOD_CONTROL), bool(mods & glfw.MOD_SHIFT)
        if self.mode == 'photo':
            # Flying keys, with Ctrl (slower) or Shift (faster) too: Space must
            # never reach Reset view by the Ctrl fallback of Commands.for_key.
            if key == glfw.KEY_SPACE:
                return                     # flies up (drive)
            if key == glfw.KEY_R:
                self.fly.roll = 0.0
                return
        command = self.commands.for_key(key, ctrl, shift)
        if command is not None:
            try:
                self.commands.run(command, self.renderer is not None)
            except Exception as error:
                self.report(command.label or command.id, error)

    # The frame loop ------------------------------------------------------------------
    def installed(self, event):
        """A new scene is shown: fit the camera to it and start what depends on it."""
        r = self.renderer
        if event['changed_map']:
            self.editor.reset()
            self.editor.marks = self.session.marks
        self.summary.invalidate()
        self.camera.surface, self.camera.playable = r.surface_at, r.playable
        self.fly.surface = r.surface_at
        if event['changed_map'] or event['first']:
            self.camera.reset()
            self.camera.snap()
            self.views = Views(self.session.source)
            if self.mode == 'photo':
                self._enter('edit')
        self.walkability.request(r)

    def drive(self, dt):
        """Continuous keyboard movement, scaled by zoom level (Edit) or the
        height above the ground (Photo)."""
        down = self.key_down
        ctrl = down(glfw.KEY_LEFT_CONTROL, glfw.KEY_RIGHT_CONTROL)
        speed = (3 if down(glfw.KEY_LEFT_SHIFT, glfw.KEY_RIGHT_SHIFT) else 1)*(0.3 if ctrl else 1)
        if self.mode == 'photo':
            # Ctrl+C copies the view instead of sinking.
            self.fly.drive(dt, forward=down(glfw.KEY_W, glfw.KEY_UP)-down(glfw.KEY_S, glfw.KEY_DOWN),
                           right=down(glfw.KEY_D, glfw.KEY_RIGHT)-down(glfw.KEY_A, glfw.KEY_LEFT),
                           up=down(glfw.KEY_SPACE)-(0 if ctrl else down(glfw.KEY_C)),
                           roll=down(glfw.KEY_E)-down(glfw.KEY_Q), speed=speed)
            return
        self.camera.drive(dt, forward=down(glfw.KEY_W, glfw.KEY_UP)-down(glfw.KEY_S, glfw.KEY_DOWN),
                          right=down(glfw.KEY_D, glfw.KEY_RIGHT)-down(glfw.KEY_A, glfw.KEY_LEFT),
                          turn=down(glfw.KEY_E)-down(glfw.KEY_Q), tilt=down(glfw.KEY_R)-down(glfw.KEY_F),
                          # Ctrl+Z undoes instead.
                          zoom=0 if ctrl else down(glfw.KEY_X)-down(glfw.KEY_Z), speed=speed)

    def draw(self, size):
        fw, fh = size
        r, k = self.renderer, self.scale()
        photo = self.mode == 'photo'
        cam = self.current_camera(fw/fh)
        if r is not None:
            options = dict(grid=self.view['grid'], border=self.view['border'], shadow_radius=4000.0, shadow_size=4096,
                           time=self.time)
            if photo and (active(self.fly.settings()) or self.autofocus):
                # Exposure and depth of field over the scene (render.photo); its depth also serves autofocus.
                if self.post is None:
                    self.post = Post(self.ctx, self.args.samples)
                r.draw(cam, size, self.post.target(size), **options)
                self.post.finish(cam, self.fly.settings(), self.ctx.screen, taps=128)
                if self.autofocus:
                    self.focused(self.post.distance_at(cam, fw//2, fh//2))
            else:
                r.draw(cam, size, self.ctx.screen, **options)
            if self.pending_save is not None:
                try:
                    self.finish_save(size)
                except Exception as error:
                    self.pending_save = None
                    self.report('saving the view', error)
            # Every frame, so picking never sees marks that are gone or hidden. Photo mode shows none.
            shown = self.session.marks.items if self.editor.visible and not photo else []
            self.overlay.draw(shown, self.editor.drawing if not photo else None, self.editor.selected, cam,
                              r.surface_at, size, k, self.editor.hovered)
            if photo:
                self.camerabar.draw_frame(size, bar.frame_ratio(self.framing['frame']), self.framing['thirds'],
                                          bool(self.fly.aperture) and self.captured)
        else:
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, fw, fh)
            self.ctx.clear(0.08, 0.09, 0.10)
        toolbar = self.toolbar
        if toolbar.open_menu and toolbar.open_menu[0] != 'map':
            # Keep check marks current (keyboard toggles, a finished reload).
            toolbar.open_menu = (toolbar.open_menu[0], self.menu_entries(toolbar.open_menu[0]))
        toolbar.draw(size, k, self.toolbar_state())
        toolbar.panel_rect = self.palette.rect = None
        marks = self.session.marks
        self.camerabar.rect = self.camerabar.pop_rect = None
        if r is not None:
            if not photo:
                self.palette.draw(size, k, self.editor.tool)
                if marks.items and self.editor.visible:
                    self.summary.update(r, marks, self.session.source)
                    toolbar.draw_panel(size, k, 'Marks', summary_lines(marks.items, self.summary.get(r, marks)),
                                       toolbar.height)
            self.camerabar.draw(size, k, self.bar_state())
            if photo:
                self.camerabar.draw_help(size, k, title='Photo mode' if self.captured
                                         else 'Photo mode - click the view to look around')
        self.draw_toast(size)
        # Last, so the palette, the panel and the loading toast never cover it.
        toolbar.draw_menu(size, k)

    def draw_toast(self, size):
        """The toast at the top left, below the toolbar and beside the
        palette: a load's progress or a build's latest output line while they
        run, then briefly how they ended."""
        session, build = self.session, self.build
        top, left = self.toolbar.height, self.palette.rect[2] if self.palette.rect else 0
        now = time.perf_counter()
        if session.toast_shown(now):
            fraction, step = session.request.progress if session.request else (0.0, 'Starting')
            alpha = min(1.0, (now-session.load_started-TOAST_DELAY)/0.15)
            self.toolbar.draw_toast(size, self.scale(), top, session.load_title, step, fraction, 'loading', alpha,
                                    left=left)
        elif build.running:
            elapsed = now-build.started
            self.toolbar.draw_toast(size, self.scale(), top, f'{build.title}  ·  {elapsed:.0f} s', build.line,
                                    None, 'loading', min(1.0, elapsed/0.15), left=left)
        elif session.toast and now < session.toast['until']:
            toast = session.toast
            self.toolbar.draw_toast(size, self.scale(), top, toast['title'], toast['detail'], None, toast['kind'],
                                    min(1.0, (toast['until']-now)/0.4), left=left)

    def pace(self):
        """Wait for the next frame under the frame rate cap."""
        if self.fps_limit in ('vsync', 'unlimited'):
            return
        # Sleep most of the way to the next frame, then spin the last
        # millisecond or two (sleep alone overshoots by up to a few ms).
        period = 1.0/int(self.fps_limit)
        target = self.next_frame + period
        current = time.perf_counter()
        if target < current - period:
            target = current
        if target - current > 0.002:
            time.sleep(target - current - 0.0015)
        while time.perf_counter() < target:
            time.sleep(0)    # yield to background work (builds, the marks panel)
        self.next_frame = target

    def run(self):
        session, window = self.session, self.window
        session.start_load()
        previous = time.perf_counter()
        frames, fps_time = 0, previous
        started = previous
        while not glfw.window_should_close(window):
            glfw.poll_events()
            now = time.perf_counter()
            session.poll(now)
            if session.reload:
                session.start_load()
            if self.properties_saved:
                # The Properties window wrote map.toml: rebuild with it.
                updated, self.properties_saved = self.properties_saved, None
                session.owners[updated.map_file.resolve()] = updated
                self.status.set('map properties saved to map.toml - building', 4)
                self.build.start(session.owner)
            event = session.advance(self.ctx)
            if event:
                self.installed(event)
            self.walkability.advance(self.renderer)
            now = time.perf_counter()
            dt = min(now-previous, 0.1)
            previous = now
            self.drive(dt)
            if self.mode == 'photo':
                self.fly.update(dt)
            else:
                self.camera.update(dt)
            if self.view['animate']:
                self.time += dt
            fw, fh = glfw.get_framebuffer_size(window)
            if fw and fh:
                self.draw((fw, fh))
                glfw.swap_buffers(window)
            self.pace()
            frames += 1
            if self.args.exit_after and now-started > self.args.exit_after:
                print(f'Smoke test: {self.fps:.0f} fps')
                if self.args.snapshot and fw and fh:
                    from PIL import Image
                    pixels = np.frombuffer(self.ctx.screen.read(components=3), np.uint8).reshape(fh, fw, 3)
                    Image.fromarray(np.flipud(pixels)).save(self.args.snapshot)
                glfw.set_window_should_close(window, True)
            if now-fps_time > 0.5:
                self.fps = frames/(now-fps_time)
                frames, fps_time = 0, now
                message = self.status.current(now)
                status = f'{message}  |  ' if message is not None else 'live  |  '
                o = session.options
                glfw.set_window_title(window, f'{session.source.stem}  |  {GAME_LABEL}  |  {status}{self.fps:.0f} fps  |  '
                                      f'{self.mode.title()}  |  lod {o["lod"]}  weather {o["weather"]}  |  F1 controls')

    def close(self):
        self.session.close()
        self.walkability.close()


if __name__ == '__main__':
    raise SystemExit(main())
