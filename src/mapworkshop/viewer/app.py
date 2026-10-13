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
  G grid  B border  P screenshot  F5 reload  Ctrl+B build  F1 controls  Esc quit

Toolbar
  Map        your map projects, then the game's maps; Open project folder; Browse...
  Build      rebuild the current project; the scene reloads when it is done and
             a failed build shows its error in the status bar
  Play       copy the current project into the game's user maps and start BFME2
  Detail     game detail level (Low, Medium, High)
  Weather    the map's own weather, or a preset (clear, haze, rain, snow, dusk)
  Sun        the weather's own sun, or a light rig over it
  View       layers: objects, water, shadows; cloud shadows, normal maps, fog and
             rain/snow; grid, map border; animate; the game's object limits
  Mark       the marking row: Pin, Circle, Rectangle, Freehand, Select, Delete,
             Clear all and Copy for agent. Marks are red, numbered and saved per
             map, and a panel lists what each one covers. Copy for agent puts the
             marks, their map coordinates, the objects inside and the map's source
             project on the clipboard, to paste into an agent ("add a forest in
             mark 2"); `mw marks` prints the same.
  Buttons    top view, reset view, screenshot
  FPS        the frame rate at the right; click it to cap it (30-144), follow the
             monitor (VSync) or run unlimited. Default 60 (--fps).

Live reload: the viewer watches the map file and its map.ini. When either
changes (a build, `mw dev`, an editor save) the scene reloads in place and the
camera stays where it is. A failed reload keeps the previous scene.

The camera is a preview camera, not the game's. Rendering follows the game
detail level chosen with --lod (default medium).
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from mapworkshop.config import RENDERS
from mapworkshop.render.camera import look_at, perspective

ORBIT_DEGREES_PER_PIXEL = 0.25
SMOOTHING = 16.0          # 1/s; higher follows input faster
MIN_DISTANCE, MAX_DISTANCE = 60.0, 40000.0


def smooth(current, goal, dt, rate=SMOOTHING):
    return current + (goal-current)*(1-math.exp(-rate*dt))


class Camera:
    """Orbit camera with separate goal and current state for smooth motion."""

    def __init__(self, surface, playable):
        self.surface = surface          # (x, y) -> visible height (terrain or water)
        self.playable = playable
        self.fov = 50.0
        self.reset()
        self.snap()

    def reset(self):
        w, h = self.playable
        self.goal = dict(x=w/2, y=h/2, distance=max(w, h)*0.75, heading=0.0, elevation=55.0)

    def snap(self):
        self.cur = dict(self.goal)
        self.cur['z'] = self.ground(self.cur['x'], self.cur['y'])

    def ground(self, x, y):
        return float(self.surface(x, y))

    def update(self, dt):
        for key in ('x', 'y', 'heading', 'elevation'):
            self.cur[key] = smooth(self.cur[key], self.goal[key], dt)
        # Zoom is smoothed in log space so it feels uniform at every scale.
        self.cur['distance'] = math.exp(smooth(math.log(self.cur['distance']), math.log(self.goal['distance']), dt))
        self.cur['z'] = smooth(self.cur['z'], self.ground(self.cur['x'], self.cur['y']), dt, 8.0)

    def matrices(self, aspect, state=None):
        s = state or self.cur
        e, h = math.radians(s['elevation']), math.radians(s['heading'])
        target = np.array([s['x'], s['y'], s['z']])
        eye = target + np.array([-math.sin(h)*math.cos(e), -math.cos(h)*math.cos(e), math.sin(e)])*s['distance']
        # Never look from inside the terrain.
        floor = self.ground(eye[0], eye[1])+15.0
        if eye[2] < floor:
            eye[2] = floor
        fov_y = 2*math.degrees(math.atan(math.tan(math.radians(self.fov)/2)/aspect))
        near = max(2.0, s['distance']*0.01)
        proj = perspective(fov_y, aspect, near, s['distance']*20+30000)
        return dict(view_projection=proj @ look_at(eye, target), eye=eye, target=target)

    def ray(self, cursor, size):
        """World-space ray through a window position (pixels, origin top-left)."""
        cam = self.matrices(size[0]/size[1])
        inv = np.linalg.inv(cam['view_projection'])
        nx = 2*cursor[0]/size[0]-1
        ny = 1-2*cursor[1]/size[1]
        near = inv @ np.array([nx, ny, -1, 1.0]); near = near[:3]/near[3]
        far = inv @ np.array([nx, ny, 1, 1.0]); far = far[:3]/far[3]
        return near, (far-near)/np.linalg.norm(far-near)

    def pick(self, cursor, size):
        """Terrain point under the cursor (ray march + bisection), or None."""
        origin, direction = self.ray(cursor, size)
        reach = self.cur['distance']*6+20000
        t = np.linspace(0, reach, 1500)
        points = origin+np.outer(t, direction)
        below = points[:, 2] <= self.surface(points[:, 0], points[:, 1])
        hits = np.nonzero(below)[0]
        if not len(hits):
            return None
        i = hits[0]
        lo, hi = t[max(i-1, 0)], t[i]
        for _ in range(20):
            mid = (lo+hi)/2
            p = origin+direction*mid
            if p[2] <= self.surface(p[0], p[1]):
                hi = mid
            else:
                lo = mid
        return origin+direction*hi

    def plane_hit(self, cursor, size, z):
        origin, direction = self.ray(cursor, size)
        if abs(direction[2]) < 1e-6:
            return None
        t = (z-origin[2])/direction[2]
        return origin+direction*t if t > 0 else None


FPS_LIMITS = ('30', '60', '90', '120', '144', 'vsync', 'unlimited')


def main(argv=None):
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
    parser.add_argument('--marking', action='store_true', help=argparse.SUPPRESS)  # start with Mark on
    args = parser.parse_args(argv)

    import threading
    import glfw
    import moderngl
    from mapworkshop import game, project
    from mapworkshop.render.engine import MapRenderer
    from mapworkshop.viewer import marks as marklib

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
    # Frames are paced by the limiter below; VSync only when chosen.
    glfw.swap_interval(1 if args.fps == 'vsync' else 0)
    ctx = moderngl.create_context(require=430)
    # Release the previous scene's GPU objects once a reload replaces it.
    ctx.gc_mode = 'auto'
    print(__doc__)
    from mapworkshop.mapkit.weather import PRESETS, SUNS
    from mapworkshop.viewer.toolbar import Toolbar
    from mapworkshop.viewer.marks import Marks
    from mapworkshop.viewer.overlay import MarkOverlay
    shared = {}
    state = dict(grid=False, border=False, top=None, drag=None, last=None, shots=0,
                 last_click=0.0, fps=0.0, help=True, status='', status_until=0.0,
                 reload=False, changed_at=None, lod=args.lod, weather=args.weather, source=source,
                 loading=False, animate=True, time=0.0, sun=args.sun,
                 marking=args.marking, tool='pin', selected=None, drawing=None,
                 fps_limit=args.fps, next_frame=0.0, building=False, build_line='',
                 summary=None, summary_key=None, summary_busy=False)
    scene = dict(renderer=None)
    out_dir = RENDERS
    watched = [source, source.parent/'map.ini']
    toolbar = Toolbar(ctx, [
        dict(kind='dropdown', id='map', label='Map'),
        dict(kind='button', id='build', label='Build'), dict(kind='button', id='play', label='Play'),
        dict(kind='gap'),
        dict(kind='dropdown', id='lod', label='Detail'),
        dict(kind='dropdown', id='weather', label='Weather'),
        dict(kind='dropdown', id='sun', label='Sun'), dict(kind='gap'),
        dict(kind='dropdown', id='view', title='View'), dict(kind='toggle', id='marking', label='Mark'),
        dict(kind='gap'),
        dict(kind='button', id='top', label='Top view'), dict(kind='button', id='reset', label='Reset view'),
        dict(kind='button', id='shot', label='Screenshot'),
        dict(kind='status', id='status'), dict(kind='dropdown', id='fps', align='right')])
    # The marking row, shown below the main one while Mark is on.
    tools = [('pin', 'Pin'), ('circle', 'Circle'), ('rect', 'Rectangle'), ('freehand', 'Freehand'),
             ('select', 'Select')]
    hints = dict(pin='click the terrain to drop a pin', circle='drag from the centre outwards',
                 rect='drag from corner to corner', freehand='hold the left button and draw',
                 select='click a mark to select it, drag to move, Del to delete')
    mark_bar = Toolbar(ctx, [dict(kind='toggle', id='tool_'+key, label=label) for key, label in tools] +
                       [dict(kind='gap'), dict(kind='button', id='delete', label='Delete'),
                        dict(kind='button', id='clear', label='Clear all'), dict(kind='gap'),
                        dict(kind='button', id='copy', label='Copy for agent'), dict(kind='status', id='hint')],
                       top=lambda: toolbar.height)
    overlay = MarkOverlay(ctx)
    scene['marks'] = Marks(source)
    # The View menu: (id, label) in groups; None separates them.
    view_items = [('objects', 'Objects'), ('water', 'Water'), ('shadows', 'Shadows'), None,
                  ('clouds', 'Cloud shadows'), ('normal_maps', 'Normal maps'), ('fx', 'Fog and rain/snow'), None,
                  ('grid', 'Grid'), ('border', 'Map border'), ('walkable', 'Walkable (local estimate)'), None,
                  ('animate', 'Animate'), ('limits', 'Game object limits (1,200 trees, 2,000 shrubs)')]

    def loading_progress(title):
        """Progress callback for MapRenderer: redraws the window with a loading
        card (over the dimmed previous scene) and keeps it responsive."""
        last = [0.0]

        def progress(fraction, step):
            now = time.perf_counter()
            if now-last[0] < 0.05 and fraction < 1.0:
                return
            last[0] = now
            glfw.poll_events()
            fw, fh = glfw.get_framebuffer_size(window)
            if not fw or not fh:
                return
            old = scene['renderer']
            if old is not None:
                old.draw(camera.matrices(fw/fh), (fw, fh), ctx.screen, grid=state['grid'], border=state['border'],
                         shadow_radius=4000.0, shadow_size=4096, time=state['time'])
            else:
                ctx.screen.use()
                ctx.viewport = (0, 0, fw, fh)
                ctx.clear(0.08, 0.09, 0.10)
            toolbar.draw((fw, fh), scale(), toolbar_state())
            toolbar.draw_loading((fw, fh), scale(), title, step, fraction)
            glfw.swap_buffers(window)
        return progress

    def map_title(path):
        """A project's title, or for a stock map 'map mp fords of isen' -> 'Fords Of Isen'."""
        owner = project.for_map_file(path)
        if owner:
            return owner.title
        words = Path(path).stem.split()
        for prefix in (['map', 'mp'], ['bfmexbar']):
            if [w.lower() for w in words[:len(prefix)]] == prefix and len(words) > len(prefix):
                words = words[len(prefix):]
        return ' '.join(w[:1].upper()+w[1:] for w in words)

    def view_state(name):
        r = scene['renderer']
        if name in ('objects', 'water', 'shadows', 'walkable'):
            return r.visible[name]
        if name == 'fx':
            return r.visible['weather']
        if name in ('normal_maps', 'clouds'):
            return r.options[name]
        if name == 'limits':
            return r.options['vegetation_limits']
        return state[name]

    def menu_entries(menu):
        if menu == 'map':
            current = state['source'].resolve()
            own = [(str(p.map_file), p.title, p.map_file.resolve() == current)
                   for p in project.projects() if p.map_file.exists()]
            stock = sorted(((str(m), map_title(m), m.resolve() == current) for m in game.stock_maps()),
                           key=lambda e: e[1].lower())
            folder = [('folder', 'Open project folder', None)] if project.for_map_file(state['source']) else []
            return own + [(None, '', None)] + stock + [(None, '', None)] + folder + [('browse', 'Browse...', None)]
        if menu == 'lod':
            return [(v, v.title(), state['lod'] == v) for v in ('low', 'medium', 'high')]
        if menu == 'weather':
            return [('map', "Map's own", state['weather'] == 'map'), (None, '', None)] + \
                   [(v, v.title(), state['weather'] == v) for v in PRESETS]
        if menu == 'fps':
            label = lambda v: dict(vsync='VSync (monitor rate)', unlimited='Unlimited').get(v, f'{v} fps')
            return [(v, label(v), state['fps_limit'] == v) for v in FPS_LIMITS[:-2]] + [(None, '', None)] + \
                   [(v, label(v), state['fps_limit'] == v) for v in FPS_LIMITS[-2:]]
        if menu == 'sun':
            return [('own', "Weather's own", state['sun'] == 'own'), (None, '', None)] + \
                   [(k, v['label'], state['sun'] == k) for k, v in SUNS.items()]
        return [(None, '', None) if item is None else (item[0], item[1], bool(view_state(item[0])))
                for item in view_items]

    def browse_map():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(title='Open a BFME2 map', initialdir=str(state['source'].parent.parent),
                                          filetypes=[('BFME2 maps', '*.map'), ('All files', '*.*')])
        root.destroy()
        return Path(path) if path else None

    def open_map(path):
        state['source'] = Path(path)
        if project.for_map_file(path):
            project.remember(project.for_map_file(path))
        watched[:] = [state['source'], state['source'].parent/'map.ini']
        state['signature'] = signature()
        state['reload'] = 'map'

    def toolbar_state():
        r = scene['renderer']
        if state['loading'] or r is None:
            status = 'loading...'
        elif state['building']:
            status = f'building: {state["build_line"]}'
        elif time.perf_counter() < state['status_until']:
            status = state['status']
        else:
            c = camera.cur
            status = f'focus {c["x"]:.0f}, {c["y"]:.0f}   distance {c["distance"]:.0f}'
        weather = "Map's own" if state['weather'] == 'map' else state['weather'].title()
        sun = "Weather's own" if state['sun'] == 'own' else SUNS[state['sun']]['label']
        return dict(map=map_title(state['source']), lod=state['lod'].title(), weather=weather, sun=sun,
                    marking=state['marking'], status=status,
                    fps=f'{state["fps"]:.0f} fps' + ('' if state['fps_limit'] in ('vsync', 'unlimited')
                                                     else f' / {state["fps_limit"]}'))

    def marks_bar_state():
        count = len(scene['marks'].items)
        hint = hints[state['tool']]
        if state['selected'] is not None:
            hint = f'mark {state["selected"]} selected: drag to move, Del to delete'
        return dict({f'tool_{key}': state['tool'] == key for key, _ in tools},
                    hint=f'{hint}   |   {count} mark{"s" if count != 1 else ""}')

    def scale():
        ww = glfw.get_window_size(window)[0] or 1
        return glfw.get_framebuffer_size(window)[0]/ww

    def toolbar_target(pos):
        k = scale()
        target = toolbar.target_at(pos[0]*k, pos[1]*k)
        if target is None and state['marking']:
            target = mark_bar.target_at(pos[0]*k, pos[1]*k)
        return target

    def toggle_top():
        if state['top'] is None:
            state['top'] = (camera.goal['elevation'], camera.goal['heading'])
            camera.goal['elevation'], camera.goal['heading'] = 89.5, round(camera.goal['heading']/360)*360
        else:
            camera.goal['elevation'] = state['top'][0]
            state['top'] = None

    def toolbar_click(target):
        if target == 'menu' or state['loading']:
            return
        if target == 'bar':
            toolbar.open_menu = None
            return
        kind = target[0]
        if kind == 'dropdown':
            menu = target[1]
            if toolbar.open_menu and toolbar.open_menu[0] == menu:
                toolbar.open_menu = None
            else:
                toolbar.open_menu = (menu, menu_entries(menu))
            return
        if kind == 'menu':
            _, menu, value = target
            if menu == 'view':
                # The View menu stays open so several layers can be switched.
                toggle(value)
                toolbar.open_menu = (menu, menu_entries(menu))
                return
            toolbar.open_menu = None
            if menu == 'fps':
                state['fps_limit'] = value
                glfw.swap_interval(1 if value == 'vsync' else 0)
                state['next_frame'] = 0.0
                set_status(f'frame rate: {value}', 2)
                return
            if menu == 'map':
                if value == 'folder':
                    import os
                    os.startfile(project.for_map_file(state['source']).folder)
                    return
                path = browse_map() if value == 'browse' else Path(value)
                if path:
                    open_map(path)
            elif state[menu] != value:
                state[menu] = value
                if menu in ('weather', 'sun'):
                    # Lighting, fog, particles and the sky switch in place.
                    started = time.perf_counter()
                    scene['renderer'].set_weather(state['weather'], state['sun'])
                    set_status(f'{menu} {value} ({time.perf_counter()-started:.2f} s)', 3)
                else:
                    state['reload'] = 'options'
            return
        toolbar.open_menu = None
        if kind == 'toggle':
            name = target[1]
            if name == 'marking':
                state['marking'] = not state['marking']
                state['drawing'] = None
                if not state['marking']:
                    state['selected'] = None
            elif name.startswith('tool_'):
                state['tool'] = name[5:]
                state['drawing'] = None
                if state['tool'] != 'select':
                    state['selected'] = None
            return
        if kind == 'button':
            action = target[1]
            if action == 'delete':
                delete_selected()
            elif action == 'clear':
                scene['marks'].clear()
                state['selected'] = None
                set_status('all marks cleared', 3)
            elif action == 'top':
                toggle_top()
            elif action == 'reset':
                camera.reset()
            elif action == 'build':
                start_build()
            elif action == 'play':
                play()
            elif action == 'copy':
                copy_for_agent()
            elif action == 'shot':
                screenshot()

    def start_build():
        owner = project.for_map_file(state['source'])
        if owner is None:
            set_status("a game map: nothing to build (start your own with `mw new`)", 5)
            return
        if state['building']:
            return
        state['building'], state['build_line'] = True, 'starting'
        lines = []

        def on_line(line):
            lines.append(line)
            if line.strip():
                state['build_line'] = line.strip()[:100]

        def work():
            code = project.run(owner, on_line=on_line)
            state['building'] = False
            if code:
                print('\n'.join(lines[-40:]))
                error = next((l.strip() for l in reversed(lines) if l.strip()), 'see the terminal')
                set_status(f'build failed: {error[:120]}', 15)
            else:
                # The build ends with what it changed since the previous build (mapkit.mapdiff).
                start = next((i for i, l in enumerate(lines) if l.startswith('Changes since')), len(lines))
                changes = [l.strip() for l in lines[start + 1:] if l.strip()]
                if changes:
                    print('\n'.join(lines[start:]))
                set_status('built - reloading' + (f': {changes[0][:110]}' if changes else '...'), 6 if changes else 3)
        threading.Thread(target=work, daemon=True).start()

    def play():
        owner = project.for_map_file(state['source'])
        try:
            if owner:
                game.install(owner.build_dir, owner.native_name)
            game.launch()
            set_status((f'{owner.title} installed in the game\'s maps; ' if owner else '') + 'starting BFME2...', 8)
        except Exception as error:
            set_status(str(error)[:140], 10)

    def marks_result():
        data = json.loads(scene['marks'].path.read_text(encoding='utf-8'))
        r = scene['renderer']
        return marklib.describe(data, assets=r.assets, m=r.map, terrain=r.terrain)

    def copy_for_agent():
        if not scene['marks'].items:
            set_status('no marks to copy: draw some first', 4)
            return
        try:
            text = marklib.agent_text(marks_result())
        except Exception as error:
            set_status(f'could not read the marks: {error}'[:140], 8)
            return
        glfw.set_clipboard_string(window, text)
        set_status(f'copied {len(scene["marks"].items)} marks for an agent - paste them into your request', 6)

    def marks_key():
        return (str(scene['marks'].path), json.dumps([{k: v for k, v in m.items() if not k.startswith('_')}
                                                     for m in scene['marks'].items]))

    def update_summary():
        """Describe the marks in the background whenever they change."""
        key = marks_key()
        if key == state['summary_key'] or state['summary_busy'] or not scene['marks'].items:
            return
        state['summary_busy'] = True

        def work():
            try:
                state['summary'] = (key, marks_result())
            except Exception as error:
                print('Marks summary failed:', error)
            finally:
                state['summary_key'], state['summary_busy'] = key, False
        threading.Thread(target=work, daemon=True).start()

    def summary_lines():
        lines = []
        result = state['summary'][1] if state['summary'] and state['summary'][0] == marks_key() else None
        for mark in scene['marks'].items:
            entry = next((m for m in result['marks'] if m['id'] == mark['id']), None) if result else None
            if entry is None:
                lines.append((f'#{mark["id"]} {mark["kind"]}', 'head'))
                lines.append(('reading...', 'muted'))
                continue
            x, y, _ = entry['center']
            lines.append((f'#{mark["id"]} {mark["kind"]} at {x:.0f}, {y:.0f}', 'head'))
            names = [o['template'] for o in entry['objects']]
            if names:
                lines.append(('objects: ' + ', '.join(names), 'body'))
            if entry['vegetation']:
                total = sum(entry['vegetation'].values())
                lines.append((f'vegetation: {total} (' + ', '.join(
                    f'{n} {t}' for t, n in sorted(entry['vegetation'].items(), key=lambda kv: -kv[1])) + ')', 'muted'))
            if not names and not entry['vegetation']:
                lines.append(('no objects', 'muted'))
        lines.append(('Copy for agent puts this on the clipboard.', 'muted'))
        return lines[-18:]

    def delete_selected():
        if state['selected'] is not None:
            scene['marks'].remove(state['selected'])
            set_status(f'mark {state["selected"]} deleted', 3)
            state['selected'] = None

    def ground_hit(pos, z=None):
        """Map point under the cursor: the terrain, or the plane at height z."""
        hit = camera.pick(pos, window_size())
        if hit is None and z is not None:
            hit = camera.plane_hit(pos, window_size(), z)
        return hit

    def toggle(name):
        """Flip a View menu layer or option (the renderer's or the viewer's)."""
        r = scene['renderer']
        if name in ('objects', 'water', 'shadows'):
            r.visible[name] = not r.visible[name]
        elif name == 'walkable':
            if not r.visible['walkable']:
                try:
                    r.walkable_overlay()
                except (ValueError, LookupError, OSError) as error:
                    set_status('Could not compute walkability: '+str(error), 8)
                    return
            r.visible['walkable'] = not r.visible['walkable']
            cut = r.walkable['cut_off'] if r.visible['walkable'] else []
            if r.visible['walkable']:
                set_status('walkable estimate: green open, blue shallow water, cyan bridges, red striped blocked, '
                           + (f'orange cut off ({len(cut)} areas)' if cut else 'nothing cut off'), 8)
        elif name == 'fx':
            r.visible['weather'] = not r.visible['weather']
        elif name in ('normal_maps', 'clouds'):
            r.set_option(name, not r.options[name])
        elif name == 'limits':
            # The game's tree (1,200) and shrub (2,000) buffer limits;
            # only the objects rebuild.
            started = time.perf_counter()
            r.set_vegetation_limits(not r.options['vegetation_limits'])
            v = r.report['vegetation']
            dropped = v['trees_dropped'] + v['shrubs_dropped']
            set_status(f'game limits {"on" if v["limits"] else "off"}: {v["trees"]} trees, {v["shrubs"]} shrubs'
                       + (f', {dropped} dropped' if dropped else '')
                       + f' ({time.perf_counter()-started:.1f} s)', 5)
        else:
            state[name] = not state[name]

    state['loading'] = True
    scene['renderer'] = MapRenderer(source, ctx=ctx, lod=args.lod, shared=shared, weather=args.weather, sun=args.sun,
                                    progress=loading_progress(map_title(source)))
    state['loading'] = False
    camera = Camera(scene['renderer'].surface_at, scene['renderer'].playable)

    def signature():
        result = []
        for path in watched:
            try:
                info = path.stat()
                result.append((info.st_mtime_ns, info.st_size))
            except OSError:
                result.append(None)
        return tuple(result)

    state['signature'] = signature()

    def reload(new_map=False):
        old = scene['renderer']
        source = state['source']
        started = time.perf_counter()
        state['loading'] = True
        try:
            new = MapRenderer(source, assets=None if new_map else old.assets, ctx=ctx, lod=state['lod'],
                              shared=shared, weather=state['weather'], progress=loading_progress(map_title(source)),
                              vegetation_limits=old.options['vegetation_limits'], sun=state['sun'])
        except Exception as error:  # keep the last good scene on any load failure
            state['loading'] = False
            message = str(error).splitlines()[0][:120] if str(error) else type(error).__name__
            set_status(f'reload failed: {message}', 8)
            print('Reload failed:', error)
            return False
        new.visible.update(old.visible)
        for name in ('normal_maps', 'clouds'):
            if new.options[name] != old.options[name]:
                new.set_option(name, old.options[name])
        state['loading'] = False
        scene['renderer'] = new
        for mark in scene['marks'].items:
            mark.pop('_world', None)  # re-drape on the reloaded terrain
        camera.surface, camera.playable = new.surface_at, new.playable
        if new_map:
            camera.reset()
            camera.snap()
        seconds = time.perf_counter()-started
        set_status(f'reloaded {time.strftime("%H:%M:%S")} ({seconds:.1f} s)', 5)
        print(f'Reloaded {source.name} in {seconds:.1f} s')
        return True

    def set_status(text, seconds):
        state['status'] = text
        state['status_until'] = time.perf_counter()+seconds

    def window_size():
        return glfw.get_window_size(window)

    def cursor_pos():
        return glfw.get_cursor_pos(window)

    def on_mouse_button(win, button, action, mods):
        pos = cursor_pos()
        if state['loading']:
            return
        if action == glfw.PRESS:
            target = toolbar_target(pos)
            if target is not None:
                if button == glfw.MOUSE_BUTTON_LEFT:
                    toolbar_click(target)
                return
            if toolbar.open_menu:
                toolbar.open_menu = None
                return
            if button == glfw.MOUSE_BUTTON_LEFT and state['marking']:
                tool = state['tool']
                if tool == 'select':
                    k = scale()
                    picked = overlay.mark_at((pos[0]*k, pos[1]*k), k)
                    state['selected'] = picked
                    if picked is not None:
                        hit = ground_hit(pos)
                        state['drag'] = ('move', hit)
                        return
                else:
                    hit = ground_hit(pos)
                    if hit is None:
                        return
                    x, y = float(hit[0]), float(hit[1])
                    if tool == 'pin':
                        mark = scene['marks'].add('pin', [(x, y)])
                        set_status(f'pin {mark["id"]} at ({x:.0f}, {y:.0f})', 3)
                        return
                    state['drawing'] = dict(kind=tool, points=[[x, y], [x, y]], radius=0.0)
                    state['drag'] = ('draw', hit)
                    return
            if button == glfw.MOUSE_BUTTON_LEFT:
                now = time.perf_counter()
                if now-state['last_click'] < 0.3:
                    hit = camera.pick(pos, window_size())
                    if hit is not None:
                        camera.goal['x'], camera.goal['y'] = float(hit[0]), float(hit[1])
                        camera.goal['distance'] = max(MIN_DISTANCE, min(camera.goal['distance'], 1500.0))
                    state['last_click'] = 0.0
                    return
                state['last_click'] = now
                state['drag'] = ('orbit', pos)
            elif button in (glfw.MOUSE_BUTTON_RIGHT, glfw.MOUSE_BUTTON_MIDDLE):
                hit = camera.pick(pos, window_size())
                anchor = hit if hit is not None else camera.plane_hit(pos, window_size(), camera.cur['z'])
                state['drag'] = ('pan', anchor)
        elif action == glfw.RELEASE:
            drag, state['drag'] = state['drag'], None
            if drag and drag[0] == 'draw' and state['drawing']:
                finish_drawing()
            elif drag and drag[0] == 'move':
                scene['marks'].save()

    def finish_drawing():
        d, state['drawing'] = state['drawing'], None
        marks = scene['marks']
        (x0, y0), (x1, y1) = d['points'][0], d['points'][-1]
        if d['kind'] == 'circle' and d['radius'] >= 5:
            mark = marks.add('circle', [d['points'][0]], radius=d['radius'])
        elif d['kind'] == 'rect' and abs(x1-x0) >= 5 and abs(y1-y0) >= 5:
            mark = marks.add('rect', [(min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))])
        elif d['kind'] == 'freehand' and len(d['points']) >= 3:
            mark = marks.add('freehand', d['points'][1:])
        else:
            return
        set_status(f'{mark["kind"]} {mark["id"]} added', 3)

    def on_cursor(win, x, y):
        drag = state['drag']
        if drag is None:
            target = toolbar_target((x, y))
            toolbar.hover = mark_bar.hover = target if isinstance(target, tuple) else None
            return
        kind, anchor = drag
        if kind == 'draw':
            d = state['drawing']
            hit = ground_hit((x, y), float(anchor[2]))
            if d is None or hit is None:
                return
            px, py = float(hit[0]), float(hit[1])
            if d['kind'] == 'circle':
                cx, cy = d['points'][0]
                d['radius'] = math.hypot(px-cx, py-cy)
            elif d['kind'] == 'rect':
                d['points'][-1] = [px, py]
            else:
                lx, ly = d['points'][-1]
                if math.hypot(px-lx, py-ly) >= max(6.0, camera.cur['distance']*0.006):
                    d['points'].append([px, py])
            return
        if kind == 'move':
            if anchor is None or state['selected'] is None:
                return
            hit = camera.plane_hit((x, y), window_size(), float(anchor[2]))
            if hit is not None:
                scene['marks'].move(state['selected'], float(hit[0]-anchor[0]), float(hit[1]-anchor[1]), save=False)
                state['drag'] = ('move', hit)
            return
        if kind == 'orbit':
            dx, dy = x-anchor[0], y-anchor[1]
            camera.goal['heading'] = (camera.goal['heading']+dx*ORBIT_DEGREES_PER_PIXEL)
            camera.goal['elevation'] = min(89.5, max(5.0, camera.goal['elevation']+dy*ORBIT_DEGREES_PER_PIXEL))
            state['drag'] = ('orbit', (x, y))
        elif kind == 'pan' and anchor is not None:
            # Keep the grabbed ground point under the cursor (1:1, unsmoothed).
            hit = camera.plane_hit((x, y), window_size(), float(anchor[2]))
            if hit is not None:
                shift = anchor[:2]-hit[:2]
                for key, value in zip(('x', 'y'), shift):
                    camera.goal[key] += float(value)
                    camera.cur[key] += float(value)

    def on_scroll(win, dx, dy):
        if toolbar_target(cursor_pos()) is not None:
            return
        factor = 0.82**dy
        old = camera.goal['distance']
        new = min(MAX_DISTANCE, max(MIN_DISTANCE, old*factor))
        hit = camera.pick(cursor_pos(), window_size())
        if hit is not None:
            # Zoom towards the point under the cursor.
            k = 1-new/old
            camera.goal['x'] += float((hit[0]-camera.goal['x'])*k)
            camera.goal['y'] += float((hit[1]-camera.goal['y'])*k)
        camera.goal['distance'] = new

    def screenshot():
        out_dir.mkdir(parents=True, exist_ok=True)
        w, h = glfw.get_framebuffer_size(window)
        cam = camera.matrices(w/h)
        color = ctx.renderbuffer((w, h), 4, samples=args.samples)
        depth = ctx.depth_renderbuffer((w, h), samples=args.samples)
        fbo = ctx.framebuffer([color], depth)
        resolve = ctx.framebuffer([ctx.renderbuffer((w, h), 4)])
        scene['renderer'].draw(cam, (w, h), fbo, grid=state['grid'], border=state['border'], shadow_radius=6000,
                               time=state['time'])
        ctx.copy_framebuffer(resolve, fbo)
        pixels = np.flipud(np.frombuffer(resolve.read(components=4), np.uint8).reshape(h, w, 4))[..., :3]
        for item in (fbo, resolve, color, depth):
            item.release()
        path = out_dir/f'{state["source"].stem}-{time.strftime("%Y%m%d-%H%M%S")}.png'
        scene['renderer'].save(np.ascontiguousarray(pixels), path)
        print('Saved', path)

    toggles = {glfw.KEY_1: 'objects', glfw.KEY_2: 'water', glfw.KEY_3: 'shadows', glfw.KEY_6: 'weather'}
    options = {glfw.KEY_4: 'normal_maps', glfw.KEY_5: 'clouds'}

    def on_key(win, key, scancode, action, mods):
        if action != glfw.PRESS:
            return
        if key == glfw.KEY_ESCAPE:
            # Esc steps back: cancel a drawing, drop the selection, leave the
            # marking row; with nothing left to undo it quits.
            if state['drawing'] is not None:
                state['drawing'] = None
                state['drag'] = None
            elif state['selected'] is not None:
                state['selected'] = None
            elif state['marking']:
                state['marking'] = False
            else:
                glfw.set_window_should_close(window, True)
        elif key in (glfw.KEY_DELETE, glfw.KEY_BACKSPACE) and state['marking']:
            delete_selected()
        elif key == glfw.KEY_7:
            toggle('walkable')
        elif key in toggles:
            name = toggles[key]
            scene['renderer'].visible[name] = not scene['renderer'].visible[name]
        elif key in options:
            name = options[key]
            scene['renderer'].set_option(name, not scene['renderer'].options[name])
        elif key == glfw.KEY_F5:
            state['reload'] = True
        elif key == glfw.KEY_B and mods & glfw.MOD_CONTROL:
            start_build()
        elif key == glfw.KEY_G:
            state['grid'] = not state['grid']
        elif key == glfw.KEY_B:
            state['border'] = not state['border']
        elif key in (glfw.KEY_SPACE, glfw.KEY_HOME):
            camera.reset()
        elif key == glfw.KEY_T:
            toggle_top()
        elif key == glfw.KEY_P:
            screenshot()
        elif key == glfw.KEY_F1:
            print(__doc__)

    glfw.set_mouse_button_callback(window, on_mouse_button)
    glfw.set_cursor_pos_callback(window, on_cursor)
    glfw.set_scroll_callback(window, on_scroll)
    glfw.set_key_callback(window, on_key)

    previous = time.perf_counter()
    frames, fps_time = 0, previous
    started = previous
    watch_time = previous
    while not glfw.window_should_close(window):
        glfw.poll_events()
        now = time.perf_counter()
        # Watch for map changes; reload once the files stop changing (a
        # writer may still be busy) or immediately on F5.
        if now-watch_time > 0.25:
            watch_time = now
            current = signature()
            if current != state['signature']:
                state['signature'] = current
                state['changed_at'] = now
                set_status('map changed - reloading...', 2)
            elif state['changed_at'] is not None and now-state['changed_at'] > 0.5:
                state['changed_at'] = None
                state['reload'] = True
        if state['reload']:
            kind, state['reload'] = state['reload'], False
            glfw.set_window_title(window, f'{state["source"].stem}  |  loading...')
            reload(new_map=kind == 'map')
            now = time.perf_counter()
            previous = now
        dt = min(now-previous, 0.1)
        previous = now
        # Continuous keyboard movement, scaled by zoom level.
        pressed = lambda *keys: any(glfw.get_key(window, k) == glfw.PRESS for k in keys)
        speed = camera.goal['distance']*1.1
        if pressed(glfw.KEY_LEFT_SHIFT, glfw.KEY_RIGHT_SHIFT):
            speed *= 3
        if pressed(glfw.KEY_LEFT_CONTROL, glfw.KEY_RIGHT_CONTROL):
            speed *= 0.3
        forward = (pressed(glfw.KEY_W, glfw.KEY_UP)-pressed(glfw.KEY_S, glfw.KEY_DOWN))
        right = (pressed(glfw.KEY_D, glfw.KEY_RIGHT)-pressed(glfw.KEY_A, glfw.KEY_LEFT))
        if forward or right:
            h = math.radians(camera.goal['heading'])
            camera.goal['x'] += (math.sin(h)*forward+math.cos(h)*right)*speed*dt
            camera.goal['y'] += (math.cos(h)*forward-math.sin(h)*right)*speed*dt
        camera.goal['heading'] += (pressed(glfw.KEY_E)-pressed(glfw.KEY_Q))*90*dt
        camera.goal['elevation'] = min(89.5, max(5.0, camera.goal['elevation']+(pressed(glfw.KEY_R)-pressed(glfw.KEY_F))*60*dt))
        if pressed(glfw.KEY_Z) or pressed(glfw.KEY_X):
            camera.goal['distance'] = min(MAX_DISTANCE, max(MIN_DISTANCE,
                camera.goal['distance']*math.exp((pressed(glfw.KEY_X)-pressed(glfw.KEY_Z))*1.5*dt)))
        w, h = camera.playable
        camera.goal['x'] = min(w, max(0.0, camera.goal['x']))
        camera.goal['y'] = min(h, max(0.0, camera.goal['y']))
        camera.update(dt)
        if state['animate']:
            state['time'] += dt

        if scene['marks'].map_path != state['source']:
            scene['marks'] = Marks(state['source'])
            state['selected'] = state['drawing'] = None
        fw, fh = glfw.get_framebuffer_size(window)
        if fw and fh:
            cam = camera.matrices(fw/fh)
            scene['renderer'].draw(cam, (fw, fh), ctx.screen, grid=state['grid'], border=state['border'],
                                   shadow_radius=4000.0, shadow_size=4096, time=state['time'])
            if scene['marks'].items or state['drawing']:
                overlay.draw(scene['marks'].items, state['drawing'], state['selected'], cam,
                             scene['renderer'].surface_at, (fw, fh), scale())
            if toolbar.open_menu and toolbar.open_menu[0] != 'map':
                # Keep check marks current (keyboard toggles, a finished reload).
                toolbar.open_menu = (toolbar.open_menu[0], menu_entries(toolbar.open_menu[0]))
            toolbar.draw((fw, fh), scale(), toolbar_state())
            if state['marking']:
                mark_bar.draw((fw, fh), scale(), marks_bar_state())
                if scene['marks'].items:
                    update_summary()
                    toolbar.draw_panel((fw, fh), scale(), 'Marks', summary_lines(),
                                       toolbar.height + mark_bar.height)
            glfw.swap_buffers(window)
        limit = state['fps_limit']
        if limit not in ('vsync', 'unlimited'):
            # Sleep most of the way to the next frame, then spin the last
            # millisecond or two (sleep alone overshoots by up to a few ms).
            period = 1.0/int(limit)
            target = state['next_frame'] + period
            current = time.perf_counter()
            if target < current - period:
                target = current
            if target - current > 0.002:
                time.sleep(target - current - 0.0015)
            while time.perf_counter() < target:
                time.sleep(0)    # yield to background work (builds, the marks panel)
            state['next_frame'] = target
        frames += 1
        if args.exit_after and now-started > args.exit_after:
            print(f'Smoke test: {state["fps"]:.0f} fps')
            if args.snapshot and fw and fh:
                from PIL import Image
                pixels = np.frombuffer(ctx.screen.read(components=3), np.uint8).reshape(fh, fw, 3)
                Image.fromarray(np.flipud(pixels)).save(args.snapshot)
            glfw.set_window_should_close(window, True)
        if now-fps_time > 0.5:
            state['fps'] = frames/(now-fps_time)
            frames, fps_time = 0, now
            c = camera.cur
            status = f'{state["status"]}  |  ' if now < state['status_until'] else 'live  |  '
            glfw.set_window_title(window, f'{state["source"].stem}  |  {status}{state["fps"]:.0f} fps  |  '
                                  f'heading {c["heading"] % 360:.0f}  elevation {c["elevation"]:.0f}  |  '
                                  f'lod {state["lod"]}  weather {state["weather"]}  |  F1 controls')
    glfw.terminate()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
