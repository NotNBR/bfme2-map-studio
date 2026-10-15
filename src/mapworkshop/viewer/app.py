"""The map viewer: your maps rendered like the game, live as you build them.

    mw view [MAP]          a project (id or prefix), a stock map or a .map file;
                           by default the map you worked on last

Mouse
  Left drag            orbit around the focus point
  Right / middle drag  grab and pan the ground
  Wheel                zoom towards the cursor
  Double-click         fly to the clicked point

Keyboard
  W A S D / arrows     move (Shift faster, Ctrl slower)
  Q / E                rotate left / right
  R / F                tilt up / down
  Z / X                zoom in / out
  Space / Home         reset to the whole-map view
  T                    toggle top-down view
  1 objects  2 water  3 shadows  4 normal maps  5 clouds  6 weather  7 walkable
  8 river flow arrows  M marks
  G grid  B border  P screenshot  F5 reload  Ctrl+B build  F1 controls
  Del        delete the selected mark;  Ctrl+Z  undo a mark change
  Esc        steps back: closes a menu, cancels a drawing, drops the selection,
             puts the mark tool away, then quits

Toolbar
  Map        your map projects, then the game's maps; Open project folder; Browse...
  Properties the map's map-wide settings in a window: camera, WorldInfo flags,
             environment, water and weather (mapkit.properties). For a project,
             Save and build writes them into map.toml and rebuilds; a game map
             is shown read-only
  Build      rebuild the current project; the scene reloads when it is done and
             a failed build shows its error in the status bar. The chip at the
             right shows a running build, then when the last one ended
  Test In-Game  start BFME2 straight in a skirmish on the current project (mw play)
  Preview    how the map is shown, without changing it: detail level (Low,
             Medium, High), the map's own weather or a preset (clear, haze, rain,
             snow, dusk), the weather's own sun or a light rig over it
  View       layers: objects, water, shadows; cloud shadows, normal maps, fog and
             rain/snow; grid, map border, walkable, river flow, marks; animate;
             the game's object limits
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
from mapworkshop.config import RENDERS
from mapworkshop.mapkit.weather import PRESETS, SUNS
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.camera import Camera
from mapworkshop.viewer.commands import Command, Commands
from mapworkshop.viewer.jobs import Build, MarksSummary, Status, Walkability, play
from mapworkshop.viewer.marking import CLICK_PIXELS, MarkEditor, summary_lines
from mapworkshop.viewer.overlay import MarkOverlay
from mapworkshop.viewer.palette import Palette
from mapworkshop.viewer.session import TOAST_DELAY, Session
from mapworkshop.viewer.toolbar import Toolbar

FPS_LIMITS = ('30', '60', '90', '120', '144', 'vsync', 'unlimited')
DOUBLE_CLICK = 0.3        # s between the clicks of a double-click
# The View menu: command ids in groups; None separates them.
VIEW_MENU = ('objects', 'water', 'shadows', None, 'clouds', 'normal_maps', 'fx', None,
             'grid', 'border', 'walkable', 'flow', 'marks', None, 'animate', 'limits')


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
        self.focus_text, self.focus_sample = '', 0.0
        self.properties = None             # the Properties window (viewer.properties)
        self.properties_saved = None       # the project its Save wrote, for the frame loop to build
        # Map actions, then how the map is previewed and what is shown, then
        # the camera; at the right the status text, the last build and the
        # frame rate.
        self.toolbar = Toolbar(ctx, [
            dict(kind='dropdown', id='map', label='Map'), dict(kind='button', id='properties', label='Properties'),
            dict(kind='button', id='build', label='Build'), dict(kind='button', id='play', label='Test In-Game'),
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
        glfw.set_mouse_button_callback(window, self.on_mouse_button)
        glfw.set_cursor_pos_callback(window, self.on_cursor)
        glfw.set_scroll_callback(window, self.on_scroll)
        glfw.set_key_callback(window, self.on_key)

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
            # Toolbar buttons and keys. Build, Test In-Game and Properties need
            # no scene: they work while the first load is still running or after it failed.
            Command('build', lambda: self.build.start(self.session.owner), keys=('Ctrl+B',), needs_scene=False),
            Command('play', lambda: play(self.session.owner, self.status), needs_scene=False),
            Command('properties', self.open_properties, needs_scene=False),
            Command('reload', self.request_reload, keys=('F5',), needs_scene=False),
            Command('back', self.back, keys=('Esc',), needs_scene=False),
            Command('top', self.camera.toggle_top, keys=('T',)),
            Command('reset', self.camera.reset, keys=('Space', 'Home')),
            Command('shot', self.screenshot, keys=('P',)),
            Command('help', lambda: print(__doc__), keys=('F1',)),
            # Marks.
            Command('delete', self.editor.delete_selected, keys=('Del', 'Backspace'), when=lambda: self.editor.visible),
            Command('undo', self.editor.undo, keys=('Ctrl+Z',)),
            Command('clear', self.editor.clear),
            Command('copy', self.copy_for_agent))
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

    def flip_view(self, name):
        self.view[name] = not self.view[name]

    def request_reload(self):
        self.session.reload = True

    def back(self):
        """Esc steps back: close a menu, then the marking levels
        (MarkEditor.escape); with nothing left to step back from it quits."""
        if self.toolbar.open_menu:
            self.toolbar.open_menu = None
        elif self.renderer is None or not self.editor.escape():
            glfw.set_window_should_close(self.window, True)
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
        elif hint:
            status = hint
        else:
            if time.perf_counter() >= self.focus_sample:
                c = self.camera.cur
                self.focus_text = f'focus {c["x"]:.0f}, {c["y"]:.0f}   distance {c["distance"]:.0f}'
                self.focus_sample = time.perf_counter() + 0.15
            status = self.focus_text
        preview = [o['lod'].title(), "Map's own" if o['weather'] == 'map' else o['weather'].title()]
        if o['sun'] != 'own':
            preview.append(SUNS[o['sun']]['label'])
        return dict(map=self.session.title(), preview=' · '.join(preview), status=status,
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
            target = self.palette.target_at(pos[0]*k, pos[1]*k)
        return target

    def toolbar_click(self, target):
        """Act on a toolbar click; an error shows in the status bar (and the
        terminal) instead of closing the viewer."""
        try:
            self.handle_click(target)
        except Exception as error:
            import traceback
            traceback.print_exc()
            self.status.set(f'{target[1] if isinstance(target, tuple) else target} failed: {error}', 10)

    def handle_click(self, target):
        toolbar = self.toolbar
        if target == 'menu':
            return
        if target in ('bar', 'panel', 'palette'):
            toolbar.open_menu = None
            return
        kind = target[0]
        if kind == 'menu_scroll':
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
        if menu == 'fps':
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

    def screenshot(self):
        RENDERS.mkdir(parents=True, exist_ok=True)
        ctx, samples = self.ctx, self.args.samples
        w, h = glfw.get_framebuffer_size(self.window)
        cam = self.camera.matrices(w/h)
        color = ctx.renderbuffer((w, h), 4, samples=samples)
        depth = ctx.depth_renderbuffer((w, h), samples=samples)
        fbo = ctx.framebuffer([color], depth)
        resolve = ctx.framebuffer([ctx.renderbuffer((w, h), 4)])
        self.renderer.draw(cam, (w, h), fbo, grid=self.view['grid'], border=self.view['border'], shadow_radius=6000,
                           time=self.time)
        ctx.copy_framebuffer(resolve, fbo)
        pixels = np.flipud(np.frombuffer(resolve.read(components=4), np.uint8).reshape(h, w, 4))[..., :3]
        for item in (fbo, resolve, color, depth):
            item.release()
        path = RENDERS/f'{self.session.source.stem}-{time.strftime("%Y%m%d-%H%M%S")}.png'
        self.renderer.save(np.ascontiguousarray(pixels), path)
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
        pos = self.cursor_pos()
        target = self.toolbar_target(pos)
        if self.renderer is None:
            # The Map menu remains usable even before the first scene is ready.
            if action == glfw.PRESS and button == glfw.MOUSE_BUTTON_LEFT and target is not None:
                self.toolbar_click(target)
            return
        if action == glfw.PRESS:
            if target is not None:
                if button == glfw.MOUSE_BUTTON_LEFT:
                    self.toolbar_click(target)
                return
            if self.toolbar.open_menu:
                self.toolbar.open_menu = None
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

    def update_pointer(self, target, pos):
        """Show with the cursor what a press here does (MarkEditor.pointer)."""
        k = self.scale()
        active = target is None and self.renderer is not None and not self.toolbar.open_menu
        cursor = self.editor.pointer((pos[0]*k, pos[1]*k), k, active)
        if cursor != self.cursor:
            self.cursor = cursor
            glfw.set_cursor(self.window, self.cursors.get(cursor))

    def on_cursor(self, win, x, y):
        if self.editor.drag is not None:
            self.editor.move((x, y))
            return
        if self.nav is None:
            target = self.toolbar_target((x, y))
            self.toolbar.hover = self.palette.hover = target if isinstance(target, tuple) else None
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
        target = self.toolbar_target(self.cursor_pos())
        if target is not None:
            if target == 'menu' or (isinstance(target, tuple) and target[0] in ('menu', 'menu_scroll')):
                self.toolbar.scroll_menu(-dy*3)
            return
        self.camera.zoom(dy, self.camera.pick(self.cursor_pos(), self.window_size()))

    def on_key(self, win, key, scancode, action, mods):
        if action != glfw.PRESS:
            return
        command = self.commands.for_key(key, bool(mods & glfw.MOD_CONTROL))
        if command is not None:
            self.commands.run(command, self.renderer is not None)

    # The frame loop ------------------------------------------------------------------
    def installed(self, event):
        """A new scene is shown: fit the camera to it and start what depends on it."""
        r = self.renderer
        if event['changed_map']:
            self.editor.reset()
            self.editor.marks = self.session.marks
        self.summary.invalidate()
        self.camera.surface, self.camera.playable = r.surface_at, r.playable
        if event['changed_map'] or event['first']:
            self.camera.reset()
            self.camera.snap()
        self.walkability.request(r)

    def drive(self, dt):
        """Continuous keyboard movement, scaled by zoom level."""
        down = self.key_down
        ctrl = down(glfw.KEY_LEFT_CONTROL, glfw.KEY_RIGHT_CONTROL)
        speed = (3 if down(glfw.KEY_LEFT_SHIFT, glfw.KEY_RIGHT_SHIFT) else 1)*(0.3 if ctrl else 1)
        self.camera.drive(dt, forward=down(glfw.KEY_W, glfw.KEY_UP)-down(glfw.KEY_S, glfw.KEY_DOWN),
                          right=down(glfw.KEY_D, glfw.KEY_RIGHT)-down(glfw.KEY_A, glfw.KEY_LEFT),
                          turn=down(glfw.KEY_E)-down(glfw.KEY_Q), tilt=down(glfw.KEY_R)-down(glfw.KEY_F),
                          # Ctrl+Z undoes instead.
                          zoom=0 if ctrl else down(glfw.KEY_X)-down(glfw.KEY_Z), speed=speed)

    def draw(self, size):
        fw, fh = size
        r, k = self.renderer, self.scale()
        cam = self.camera.matrices(fw/fh)
        if r is not None:
            r.draw(cam, size, self.ctx.screen, grid=self.view['grid'], border=self.view['border'],
                   shadow_radius=4000.0, shadow_size=4096, time=self.time)
            # Every frame, so picking never sees marks that are gone or hidden.
            shown = self.session.marks.items if self.editor.visible else []
            self.overlay.draw(shown, self.editor.drawing, self.editor.selected, cam,
                              r.surface_at, size, k, self.editor.hovered)
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
        if r is not None:
            self.palette.draw(size, k, self.editor.tool)
            if marks.items and self.editor.visible:
                self.summary.update(r, marks, self.session.source)
                toolbar.draw_panel(size, k, 'Marks', summary_lines(marks.items, self.summary.get(r, marks)),
                                   toolbar.height)
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
                c = self.camera.cur
                message = self.status.current(now)
                status = f'{message}  |  ' if message is not None else 'live  |  '
                o = session.options
                glfw.set_window_title(window, f'{session.source.stem}  |  {status}{self.fps:.0f} fps  |  '
                                      f'heading {c["heading"] % 360:.0f}  elevation {c["elevation"]:.0f}  |  '
                                      f'lod {o["lod"]}  weather {o["weather"]}  |  F1 controls')

    def close(self):
        self.session.close()
        self.walkability.close()


if __name__ == '__main__':
    raise SystemExit(main())
