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
  user maps folder, and the viewer builds the map again in place.

From the viewer:

    ready {ms}                      the map is open (and how long it took)
    press / move / release / click / hover {ray, picks, shift, focus, seq}
                                    the left button and the cursor; ray: [origin, direction] in map units, picks:
                                    {handle, grab, mark, direction} as the overlay found them under the cursor,
                                    focus: {z, distance, angle} of the Edit camera
    tool {tool}                     a palette tool armed ('pin', 'circle', 'rect', 'freehand' or null)
    command {name}                  undo, delete, clear, escape, toggle (the marks shown or not), copy
    reloaded {ms} / reload_failed {error}

To the viewer:

    marks {...}                     marks_state(): the marks draped on the surface, the mark being drawn, the selected
                                    one's handles, what the mouse does now and its cursor; sent when it changed
    press_result {handled, seq}     whether the press numbered seq acts on the marks (else it orbits)
    panel {lines}                   the marks panel: [text, style] (marking.summary_lines)
    status {text, seconds}          a line for the status bar
    clipboard {text}                Copy for agent's text (at once when the panel's summary is current, else once read)
    reload {}                       the build changed: read the scene again and build the map
"""

import json
import socket
import threading
import time

import numpy as np

from mapworkshop.formats.map import Map
from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.camera import march
from mapworkshop.viewer.jobs import MarksSummary
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
        if assets is None:
            threading.Thread(target=self._load_assets, daemon=True).start()

    def _load_assets(self):
        from mapworkshop.assets.library import GameAssets
        self.assets = GameAssets()


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
    """The marks, the panel and live reload for one open map. handle() answers one message from the viewer with the
    messages to send back; serve() runs the link until the viewer closes."""

    def __init__(self, map_path, surface, rescene=None, progress=print):
        self.map_path, self.surface, self.progress = map_path, surface, progress
        self.rescene = rescene            # () -> Surface: the build changed; install it and write the scene again
        self.marks = marklib.Marks(map_path)
        self.picks, self.world, self.status = Picks(), World(surface), Status()
        self.editor = MarkEditor(self.picks, self.world, self.status)
        self.editor.marks = self.marks
        self.summary, self.loaded = MarksSummary(), Loaded(map_path, surface)
        self.panel = []                   # the panel lines last sent (none: no marks)
        self.shown = None                 # the marks state last sent
        self.copied = None                # Copy for agent's message once worked out in the background
        self.stamp = self._build_stamp()
        self.reload_started = None        # when the new build was found (perf_counter), and its file's time

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
            name = message.get('name')
            if name == 'undo':
                self.editor.undo()
            elif name == 'escape':
                self.editor.escape()
            elif name == 'toggle':
                self.editor.toggle_visible()
            elif name == 'copy':
                out.append(self._copy())
            elif name in ('delete', 'clear') and self.editor.visible:    # as the studio viewer: not on hidden marks
                (self.editor.delete_selected if name == 'delete' else self.editor.clear)()
        elif kind == 'ready':
            self.progress(f'The Godot viewer opened the map in {message.get("ms", 0)/1000:.1f} s.')
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
            while loaded.assets is None:
                time.sleep(0.05)
            try:
                result = marklib.describe(data, assets=loaded.assets, m=loaded.map, terrain=loaded.terrain)
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
        """A reload message when a new build has settled (the map file and its map.ini unchanged for a moment, as the
        studio viewer waits), else None. A build that cannot be read is reported and the last good one stays."""
        stamp = self._build_stamp()
        if stamp == self.stamp or self.rescene is None:
            return None
        time.sleep(0.3)
        if self._build_stamp() != stamp:
            return None                       # still being written: look again next time
        self.stamp = stamp                    # this build, good or not: the next one is looked at again
        try:
            surface = self.rescene()
            loaded = Loaded(self.map_path, surface, self.loaded.assets)
        except Exception as error:
            self.progress(f'{self.map_path.name} changed, but it cannot be read: {error!r}; the viewer keeps the last good one')
            return dict(type='status', text=f'the new build cannot be read: {error}', seconds=6)
        self.reload_started = (time.perf_counter(), self.map_path.stat().st_mtime)
        self.surface = self.world.surface = surface
        self.loaded, self.shown = loaded, None
        self.progress(f'{self.map_path.name} changed: reloading it in the Godot viewer...')
        return dict(type='reload')

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
            for extra in (self.watch(), self.panel_message(), copied):
                if extra is not None:
                    link.send(extra)
                    if extra['type'] == 'reload':
                        link.send(self.changed_state())
