"""The Godot viewer's companion: what `mw view MAP --godot` does while the
viewer is open. It talks to the viewer (viewer/godot/) over a local socket,
one JSON object per line, and keeps doing in Python what the studio viewer
does there:

- the marks: viewer.marks' Marks writes local/marks/<map>.json, and
  viewer.marking's MarkEditor turns the viewer's mouse and keys into marks
  (the viewer sends each event with the cursor's ray in map coordinates and
  what is under it on its screen; MarkEditor asks the ray for the ground);
- what the marks cover, for the marks panel and Copy for agent
  (marks.describe, worked out in the background as jobs.MarksSummary does);
- live reload: a new build of the map (mw build, mw dev) goes into OpenBFME's
  user maps folder, and the viewer builds the map again in place;
- the toolbar's jobs, with the studio viewer's own (viewer.jobs): another map
  from the Map menu, Build, Test In-Game, the project folder;
- Preview: the map again as a copy with a weather preset or a sun
  (godot_viewer.preview_map), which the viewer opens in its place;
- the View menu's overlays that need the map's analysis: the walkability
  estimate (render.overlays, worked out once per build in the background) and
  the river strips for the flow arrows (render.rivers).

From the viewer:

    ready {ms}                      the map is open (and how long it took)
    press / move / release / click / hover {ray, picks, shift, focus, seq}
                                    the left button and the cursor; ray: [origin, direction] in map units, picks:
                                    {handle, grab, mark, direction} as the overlay found them under the cursor,
                                    focus: {z, distance, angle} of the Edit camera
    tool {tool}                     a palette tool armed ('pin', 'circle', 'rect', 'freehand' or null)
    command {name}                  undo, delete, clear, escape, toggle (the marks shown or not), copy, build, test,
                                    open_folder, open_map {map}, test_game {choice}, overlay {overlay} ('walkable' or
                                    'flow' switched on), preview {weather, sun} (either)
    reloaded {ms} / reload_failed {error}

To the viewer:

    marks {...}                     marks_state(): the marks draped on the surface, the mark being drawn, the selected
                                    one's handles, what the mouse does now and its cursor; sent when it changed
    press_result {handled, seq}     whether the press numbered seq acts on the marks (else it orbits)
    panel {lines}                   the marks panel: [text, style] (marking.summary_lines)
    status {text, seconds}          a line for the status bar
    clipboard {text}                Copy for agent's text (at once when the panel's summary is current, else once read)
    reload {scene, new_map, what}   the build changed, another map or a preview (`what`, for the toast): read the scene
                                    and build the map
    menu {...}                      the toolbar's lists: map projects, the game's maps, Test In-Game's choice, Preview's
                                    choices, the current one and its label
    build {running, line, outcome}  the build chip
    walkable {image, size, cut_off} the walkability estimate: an RGBA image, one pixel per cell from the playable
                                    area's corner, its extent in map units and the cut-off areas; {error} if it failed
    flow {strips}                   the river strips: [{vertices: [x, y, z, u, v] * n, triangles, length}]
    toast {kind, title, detail, seconds}, window {minimized}
"""

import json
import os
import socket
import threading
import time
from pathlib import Path

import numpy as np

from mapworkshop.config import save_setting, setting
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.weather import preview_choices, preview_labels
from mapworkshop.viewer import jobs
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.camera import march
from mapworkshop.viewer.jobs import MarksSummary
from mapworkshop.viewer.loading import map_title
from mapworkshop.viewer.marking import MarkEditor, summary_lines
from mapworkshop.viewer.overlay import MarkOverlay

POLL = 0.25            # seconds between looks at the socket and the build


def marks_state(marks, surface, editor=None):
    """What the viewer draws of the marks: each mark's outline draped on the surface (MarkOverlay.drape), the mark
    being drawn, the selected mark's handles (marks.handles, its centre, a rectangle's rotate anchor), and the editor's
    tool, hover and hint."""
    drape = lambda points: MarkOverlay.drape(points, surface.height_at).round(1).tolist()

    def shown(mark):
        points, closed = marklib.outline(mark)
        return dict(id=mark.get('id'), kind=mark['kind'], world=drape(points), closed=bool(closed))

    state = dict(type='marks', marks=[shown(m) for m in marks.items], preview=None, selected=None, hovered=None,
                 handles=None, tool=None, visible=True, hint=None)
    if editor is None:
        return state
    state.update(selected=editor.selected, hovered=editor.hovered, tool=editor.tool, visible=editor.visible,
                 hint=editor.hint(), preview=shown(editor.drawing) if editor.drawing else None)
    mark = marks.get(editor.selected)
    if mark is not None and mark['kind'] in ('circle', 'rect'):
        spots = [list(p) for p in marklib.handles(mark)]
        extra = [list(marklib.center(mark))] + ([list(marklib.rotate_anchor(mark)[1])] if mark['kind'] == 'rect' else [])
        world = drape(np.array(spots + extra, float))
        state['handles'] = dict(spots=world[:len(spots)], center=world[len(spots)],
                                rotate=world[len(spots) + 1] if mark['kind'] == 'rect' else None)
    return state


def _ids(picks):
    """The picks with mark ids and handle indices as integers (JSON from GDScript has floats)."""
    return {k: int(v) if isinstance(v, float) else v for k, v in picks.items()}


OWN = dict(weather='map', sun='own')     # Preview's choice when it shows the map as it is (the studio viewer's values)


class Picks:
    """MarkEditor's overlay: what the viewer found under the cursor for the event being handled."""

    def __init__(self):
        self.found = {}

    def handle_at(self, at, k=1.0):
        return self.found.get('handle')

    def grab_at(self, at, selected=None, k=1.0):
        return self.found.get('grab')

    def mark_at(self, at, k=1.0):
        return self.found.get('mark')

    def handle_direction(self, key):
        return self.found.get('direction') or 'ew'


class World:
    """MarkEditor's world: the ground under the event's ray (the surface Python sent the viewer, as viewer.camera's
    pick), and the Edit camera's focus as the viewer reports it."""

    def __init__(self, surface):
        self.surface, self.event = surface, {}

    def _ray(self):
        origin, direction = self.event['ray']
        return np.asarray(origin, float), np.asarray(direction, float)

    def ground_hit(self, pos, z=None):
        origin, direction = self._ray()
        reach = self.focus_distance()*6 + 20000
        hit = march(origin, direction, self.surface.height_at, reach)
        if hit is None and z is not None:
            hit = self.plane_hit(pos, z)
        return hit

    def plane_hit(self, pos, z):
        origin, direction = self._ray()
        if abs(direction[2]) < 1e-6:
            return None
        t = (z - origin[2])/direction[2]
        return origin + direction*t if t > 0 else None

    def focus_z(self):
        return float(self.event['focus']['z'])

    def focus_distance(self):
        return float(self.event['focus']['distance'])

    def screen_angle(self):
        return float(self.event['focus']['angle'])

    def shift_held(self):
        return bool(self.event.get('shift'))


class Status:
    """MarkEditor's status bar: the lines go to the viewer."""

    def __init__(self):
        self.lines = []

    def set(self, text, seconds=3):
        self.lines.append(dict(type='status', text=text, seconds=seconds))


class Loaded:
    """What marks.describe needs of the open map, as MarksSummary takes it from a renderer: the map, its terrain
    (heights and playable extent) and the game's assets, which load in the background unless given (a reload keeps
    them)."""

    def __init__(self, map_path, surface, assets=None):
        self.map = Map(map_path.read_bytes())
        self.terrain = surface.terrain
        self.assets = assets
        self.walkable = None              # the walkable message, once worked out (Companion.overlay)
        self.walking = False              # being worked out
        self._loaded = threading.Event()
        self._error = None
        if assets is None:
            threading.Thread(target=self._load_assets, daemon=True).start()
        else:
            self._loaded.set()

    def _load_assets(self):
        from mapworkshop.assets.library import GameAssets
        try:
            self.assets = GameAssets()
        except Exception as error:
            self._error = error
        finally:
            self._loaded.set()

    def game_assets(self):
        """The game's assets, once loaded; raises what stopped them loading."""
        self._loaded.wait()
        if self.assets is None:
            raise RuntimeError(f'the game files did not load: {self._error}')
        return self.assets


def walkability(loaded, map_ini, path):
    """The walkability estimate of the map as the studio viewer works it out (render.overlays), its image saved at
    `path`: the viewer's walkable message."""
    from types import SimpleNamespace
    from PIL import Image
    from mapworkshop.assets.models import ModelCache
    from mapworkshop.mapkit import walkable
    from mapworkshop.render.overlays import OverlaysMixin
    assets = loaded.game_assets()
    text = map_ini.read_text(encoding='cp1252', errors='replace') if map_ini.is_file() else ''
    result, rgba = OverlaysMixin.compute_walkability(SimpleNamespace(
        map=loaded.map, pathing_assets=assets, map_ini=text, model_cache=ModelCache(assets)))
    Image.fromarray(rgba, 'RGBA').save(path)
    h, w = rgba.shape[:2]
    return dict(type='walkable', image=str(path), size=[w*walkable.CELL, h*walkable.CELL],
                cut_off=len(result['cut_off']))


class Link:
    """The socket the viewer connects to: one connection, JSON lines both ways."""

    def __init__(self):
        self.server = socket.create_server(('127.0.0.1', 0))
        self.port = self.server.getsockname()[1]
        self.connection, self.buffer = None, b''

    def accept(self, timeout):
        self.server.settimeout(timeout)
        try:
            self.connection, _ = self.server.accept()
        except TimeoutError:
            return False
        self.connection.settimeout(POLL)
        return True

    def send(self, message):
        if self.connection is not None:
            self.connection.sendall((json.dumps(message) + '\n').encode('utf-8'))

    def receive(self):
        """The messages that arrived within POLL seconds; None once the viewer has closed the connection."""
        try:
            data = self.connection.recv(1 << 16)
        except TimeoutError:
            return []
        except OSError:
            return None
        if not data:
            return None
        self.buffer += data
        *lines, self.buffer = self.buffer.split(b'\n')
        return [json.loads(line) for line in lines if line.strip()]

    def close(self):
        for s in (self.connection, self.server):
            if s is not None:
                s.close()


class Companion:
    """The marks, the panel, the toolbar's jobs and live reload for the map shown. handle() answers one message from
    the viewer with the messages to send back; serve() runs the link until the viewer closes.

    `prepare(name)` readies a map for the viewer (godot_viewer.prepare: its build in the user maps folder, its scene
    written) and returns (scene.json, the scene, the project or None, the Surface); `prepared` is what it returned for
    the map the viewer opens with."""

    def __init__(self, prepared, prepare=None, progress=print):
        self.prepare, self.progress = prepare, progress
        self.picks, self.status = Picks(), Status()
        self.jobs = jobs.Status()             # the build's and the test game's lines, for the status line
        self.build = jobs.Build(self.jobs, self._toast)
        self.toasts = []
        self.sent_job = None                  # the job line and build outcome last sent
        self.loaded = None
        self.copied = None                    # Copy for agent's message once worked out in the background
        self._show(*prepared)

    def _show(self, scene_path, data, owner, surface):
        """Hold `data`'s map: its marks, surface, summary and build watch (a new map drops the old selection)."""
        self.scene_path, self.data, self.owner, self.surface = scene_path, data, owner, surface
        self.map_path = Path(data['map_path'])
        self.preview = data['preview']
        self.marks = marklib.Marks(self.map_path)
        self.world = World(surface)
        self.editor = MarkEditor(self.picks, self.world, self.status)
        self.editor.marks = self.marks
        self.summary = MarksSummary()
        self.loaded = Loaded(self.map_path, surface, self.loaded.assets if self.loaded else None)
        # another map's panel is cleared (None differs from any lines); the first map's starts empty
        self.panel, self.shown = (None if hasattr(self, 'panel') else []), None
        self.stamp = self._build_stamp()
        self.reload_started = None            # when the new build was found (perf_counter), and its file's time

    def _toast(self, toast):
        self.toasts.append(dict(type='toast', kind=toast['kind'], title=toast['title'], detail=toast.get('detail', ''),
                                seconds=max(0.5, toast['until'] - time.perf_counter())))

    # Messages --------------------------------------------------------------------------------------------------------
    def handle(self, message):
        """The messages that answer `message`; an error in it becomes a status line, and the session goes on."""
        try:
            return self._handle(message)
        except Exception as error:
            self.progress(f'The Godot viewer\'s companion could not handle {message.get("type")}: {error!r}')
            return [dict(type='status', text=f'that did not work: {error}', seconds=5)]

    def _handle(self, message):
        kind = message.get('type')
        out, cursor = [], None
        if kind in ('press', 'move', 'release', 'click', 'hover'):
            self.world.event, self.picks.found = message, _ids(message.get('picks') or {})
            if kind == 'press':
                handled = bool(self.editor.press(None, None, 1.0))
                out.append(dict(type='press_result', handled=handled, seq=message.get('seq')))
            elif kind == 'move':
                self.editor.move(None)
            elif kind == 'release':
                self.editor.release()
            elif kind == 'click':
                self.editor.click(None, 1.0)
            # the cursor for what a press here would do, as the studio viewer sets it after every mouse event
            cursor = self.editor.pointer(None, 1.0, True)
        elif kind == 'tool':
            self.editor.set_tool(message.get('tool'))
        elif kind == 'command':
            out += self._command(message.get('name'), message)
        elif kind == 'ready':
            self.progress(f'The Godot viewer opened {self.data["title"]} in {message.get("ms", 0)/1000:.1f} s.')
            out.append(self.menu())
        elif kind == 'reloaded':
            if self.reload_started is not None:
                found, built = self.reload_started
                self.progress(f'Reloaded in the Godot viewer {time.time() - built:.1f} s after the build wrote the map '
                              f'(the viewer took {message.get("ms", 0)/1000:.1f} s, found {time.perf_counter() - found:.1f} '
                              f's ago).')
                out.append(dict(type='status', text=f'reloaded {time.time() - built:.1f} s after the build', seconds=3))
                self.reload_started = None
        elif kind == 'reload_failed':
            self.progress(f'The Godot viewer could not reload the map: {message.get("error")}')
        else:
            return []
        state = self.changed_state(cursor)
        return out + self._status() + ([state] if state else [])

    def _command(self, name, message):
        out = []
        if name == 'undo':
            self.editor.undo()
        elif name == 'escape':
            self.editor.escape()
        elif name == 'toggle':
            self.editor.toggle_visible()
        elif name == 'copy':
            out.append(self._copy())
        elif name in ('delete', 'clear') and self.editor.visible:         # as the studio viewer: not on hidden marks
            (self.editor.delete_selected if name == 'delete' else self.editor.clear)()
        elif name == 'open_map':
            out += self.open_map(message['map'])
        elif name == 'overlay':
            out += self.overlay(message['overlay'])
        elif name == 'preview':
            out += self.set_preview({k: message[k] for k in ('weather', 'sun') if message.get(k)})
        elif name == 'open_folder':
            if self.owner is None:
                out.append(dict(type='status', text='a game map has no project folder', seconds=4))
            else:
                os.startfile(self.owner.folder)
        elif name == 'build':
            self.build.start(self.owner)
        elif name == 'test':
            choice = setting('test_game', jobs.TEST_GAMES[0])
            jobs.play(self.owner, self.jobs, choice if choice in jobs.TEST_GAMES else jobs.TEST_GAMES[0], self._played)
        elif name == 'test_game':
            if message.get('choice') in jobs.TEST_GAMES:
                save_setting('test_game', message['choice'])
            out.append(self.menu())
        return out

    def overlay(self, key):
        """An overlay of the View menu switched on that Python works out: 'flow', each river strip's mesh at once;
        'walkable', the walkability estimate, worked out once per build in the background and sent when it is
        ready (the viewer drops it if the overlay was switched off meanwhile)."""
        if key == 'flow':
            return [dict(type='flow', strips=self.flow_strips())]
        if key != 'walkable':
            return []
        loaded = self.loaded
        if loaded.walkable is not None:
            return [loaded.walkable]
        if not loaded.walking:
            loaded.walking = True
            path = Path(self.scene_path).parent/f'walkable-{int(time.time()*1000)}.png'     # one per build
            map_ini = self.map_path.with_name('map.ini')

            def work():
                try:
                    message = walkability(loaded, map_ini, path)
                except Exception as error:
                    message = dict(type='walkable', error=str(error))
                    loaded.walking = False                 # switching it on again tries again
                else:
                    loaded.walkable = message
                if loaded is self.loaded:                  # still the map shown
                    self.toasts.append(message)
            threading.Thread(target=work, daemon=True).start()
        return [dict(type='status', text='Computing walkability...', seconds=60)]

    def flow_strips(self):
        """The map's river strips for the flow arrows, every one as OpenBFME draws them: vertices [x, y, z, u, v] flat
        (u across the strip from 0 to 1, v along it), triangles flat, length in v (render.rivers.strips)."""
        from mapworkshop.render import rivers
        return [dict(vertices=vertices[:, [0, 1, 2, 4, 5]].round(2).ravel().tolist(),
                     triangles=triangles.ravel().tolist(), length=float(vertices[-1, 5]))
                for _, (vertices, triangles) in rivers.strips(self.loaded.map)]

    def _played(self, event):
        """Test In-Game's events: the viewer minimises while the game is up and comes back when it closes."""
        self.toasts.append(dict(type='window', minimized=event == 'started'))

    def open_map(self, name):
        """Another map: readied (prepare), then the viewer reads its scene."""
        if self.prepare is None:
            return [dict(type='status', text='this viewer shows one map only', seconds=4)]
        self._show(*self.prepare(name, self.preview))
        self.progress(f'Opening {self.data["title"]} in the Godot viewer...')
        return [dict(type='reload', scene=str(self.scene_path), new_map=True), self.menu()]

    def set_preview(self, choice):
        """Preview's weather or sun: the map prepared again as that preview (the same map: the marks, the analysis
        and the camera stay), and the viewer told to build it."""
        if self.prepare is None:
            return [dict(type='status', text='this viewer shows the map as it is only', seconds=4)]
        try:
            self.scene_path, self.data = self.prepare(str(self.map_path), dict(self.preview, **choice))[:2]
        except Exception as error:            # the menu back to what is shown
            return [dict(type='status', text=f'the preview did not work: {error}', seconds=8), self.menu()]
        self.preview = self.data['preview']
        what = ' · '.join(preview_labels(self.preview['weather'], self.preview['sun']))
        return [dict(type='reload', scene=str(self.scene_path), new_map=False, what=f'the preview: {what}'), self.menu()]

    def menu(self):
        """The toolbar's lists: the map projects with a build, then the game's maps (Map), and the Test In-Game
        choice, as the studio viewer's toolbar has them."""
        from mapworkshop import game, project
        current = self.map_path.resolve()
        own = sorted(((str(p.map_file), p.title) for p in project.projects() if p.map_file.exists()),
                     key=lambda e: e[1].lower())
        stock = sorted(((str(m), map_title(m, {})) for m in game.stock_maps()), key=lambda e: e[1].lower())
        entry = lambda path, title: dict(map=path, title=title, current=Path(path).resolve() == current)
        preview = dict(preview_choices(), current=self.preview,
                       label=' · '.join(preview_labels(self.preview['weather'], self.preview['sun'])))
        return dict(type='menu', title=self.data['title'], project=self.owner is not None,
                    projects=[entry(*e) for e in own], stock=[entry(*e) for e in stock],
                    test_games=list(jobs.TEST_GAMES), test_game=setting('test_game', jobs.TEST_GAMES[0]),
                    preview=preview)

    def state(self):
        return marks_state(self.marks, self.surface, self.editor)

    def changed_state(self, cursor=None):
        """The marks state (with the cursor) when it differs from the one last sent, else None."""
        state = self.state()
        state['cursor'] = cursor
        if state == self.shown:
            return None
        self.shown = state
        return state

    def _status(self):
        lines, self.status.lines = self.status.lines, []
        return lines

    def job_messages(self):
        """The toasts, and the jobs' status line and build chip when they changed (Build, Test In-Game)."""
        out, self.toasts = self.toasts, []
        line = self.jobs.current()
        outcome = self.build.outcome
        job = (line, self.build.running, self.build.line if self.build.running else None, outcome)
        if job != self.sent_job:
            self.sent_job = job
            if line:
                out.append(dict(type='status', text=line, seconds=max(0.5, self.jobs.until - time.perf_counter())))
            out.append(dict(type='build', running=self.build.running, line=job[2],
                            outcome=None if outcome is None else dict(ok=outcome[0], seconds=outcome[1], ended=outcome[2])))
        return out

    def _copy(self):
        """Copy for agent: the marks text now when the panel's summary is current, else a status line, and the
        text when it has been worked out in the background (serve sends it)."""
        if not self.marks.items:
            return dict(type='status', text='no marks to copy: draw one first', seconds=3)
        result = self._described()
        if result is not None:
            return dict(type='clipboard', text=marklib.agent_text(result))
        data = json.loads(json.dumps(dict(map_path=str(self.map_path), map=self.map_path.stem,
                                          marks=self.marks.plain())))
        loaded = self.loaded

        def work():
            try:
                result = marklib.describe(data, assets=loaded.game_assets(), m=loaded.map, terrain=loaded.terrain)
                self.copied = dict(type='clipboard', text=marklib.agent_text(result))
            except Exception as error:
                self.copied = dict(type='status', text=f'the marks could not be read: {error}', seconds=5)
        threading.Thread(target=work, daemon=True).start()
        return dict(type='status', text='reading the marks for the agent...', seconds=10)

    def _described(self):
        """marks.describe's result for the marks as they are now, or None while it is worked out."""
        if self.loaded.assets is None:
            return None
        self.summary.update(self.loaded, self.marks, self.map_path)
        return self.summary.get(self.loaded, self.marks)

    def panel_message(self):
        """The marks panel's lines when they changed since last sent, else None."""
        lines = summary_lines(self.marks.items, self._described()) if self.marks.items else []
        if lines == self.panel:
            return None
        self.panel = lines
        return dict(type='panel', lines=[list(line) for line in lines])

    # Live reload -----------------------------------------------------------------------------------------------------
    def _build_stamp(self):
        files = [self.map_path, self.map_path.with_name('map.ini')]
        return tuple((f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else None for f in files)

    def watch(self):
        """A reload message when a new build of a project has settled (the map file and its map.ini unchanged for a
        moment, as the studio viewer waits), else None. A build that cannot be read is reported and the last good one
        stays."""
        stamp = self._build_stamp()
        if stamp == self.stamp or self.owner is None or self.prepare is None:
            return None
        time.sleep(0.3)
        if self._build_stamp() != stamp:
            return None                       # still being written: look again next time
        self.stamp = stamp                    # this build, good or not: the next one is looked at again
        try:
            scene_path, data, owner, surface = self.prepare(str(self.map_path), self.preview)
            loaded = Loaded(self.map_path, surface, self.loaded.assets)
        except Exception as error:
            self.progress(f'{self.map_path.name} changed, but it cannot be read: {error!r}; the viewer keeps the last good one')
            return dict(type='status', text=f'the new build cannot be read: {error}', seconds=6)
        self.reload_started = (time.perf_counter(), self.map_path.stat().st_mtime)
        self.data, self.surface = data, surface
        self.world.surface = surface
        self.loaded, self.shown = loaded, None
        self.progress(f'{self.map_path.name} changed: reloading it in the Godot viewer...')
        return dict(type='reload', scene=str(scene_path), new_map=False)

    def serve(self, link, process, connect_timeout=120):
        """Answer the viewer until it closes (or `process` ends)."""
        while not link.accept(1.0):
            if process.poll() is not None or connect_timeout <= 0:
                return
            connect_timeout -= 1
        link.send(self.changed_state())
        while True:
            messages = link.receive()
            if messages is None or process.poll() is not None:
                return
            for message in messages:
                for reply in self.handle(message):
                    link.send(reply)
            copied, self.copied = self.copied, None
            for extra in [self.watch(), self.panel_message(), copied, *self.job_messages()]:
                if extra is not None:
                    link.send(extra)
                    if extra['type'] == 'reload':
                        link.send(self.changed_state())
