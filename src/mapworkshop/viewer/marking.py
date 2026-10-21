"""Editing marks in the viewer: the marks tools, selecting a mark and
moving, resizing or rotating it, deleting and undoing, and Esc stepping
back. The companion (viewer.godot_link) drives it with the viewer's mouse
events.

The overlay (godot_link.Picks: what the viewer found under the cursor)
answers what is there, and `world` turns window positions into map points:

    world.ground_hit(pos, z=None)   terrain point under pos, else the plane at z
    world.plane_hit(pos, z)         the point on the plane at height z
    world.focus_z(), world.focus_distance(), world.screen_angle(), world.shift_held()

so the editor runs in tests with stand-ins for both.
"""

import math

from mapworkshop.viewer import marks as marklib

HINTS = {'pin': 'click the terrain to drop pins - Esc when done',
         'circle': 'drag from the centre outwards - Esc when done',
         'rect': 'drag from corner to corner, lined up with the screen - Esc when done',
         'freehand': 'hold the left button and draw - Esc when done'}
CLICK_PIXELS = 4          # a press and release closer than this is a click, not an orbit


class MarkEditor:
    """The marking state. `marks` is the shown map's Marks; set it when the
    map changes. A tool stays armed until Esc or a second click on it; with
    none, the mouse navigates and selects marks. While the marks are hidden
    (View > Marks) the mouse only navigates."""

    def __init__(self, overlay, world, status):
        self.overlay, self.world, self.status = overlay, world, status
        self.marks = None
        self.visible = True       # the marks are drawn and can be edited
        self.tool = None          # the armed tool: 'pin', 'circle', 'rect' or 'freehand', or None
        self.selected = None      # mark ids
        self.hovered = None
        self.drawing = None       # the mark being drawn: dict(kind, points, radius, start, angle)
        self.drag = None          # (kind, anchor): 'draw', 'move', 'resize' or 'rotate'
        self.edited = False       # the drag has changed the mark (and set an undo checkpoint)

    # Modes ------------------------------------------------------------------
    def toggle_visible(self):
        """Show or hide the marks; hiding them also puts the tool away."""
        self.visible = not self.visible
        self.tool = self.drawing = self.selected = self.hovered = self.drag = None

    def set_tool(self, key):
        """Arm a tool (None: navigate); the armed one again puts it away.
        Arming one shows hidden marks."""
        self.tool = None if self.tool == key else key
        self.drawing = self.selected = None
        if self.tool is not None:
            self.visible = True

    def reset(self):
        """Forget the selection and any drawing: another map is shown."""
        self.selected = self.drawing = self.drag = None

    def escape(self):
        """Step back one level: cancel a drawing, drop the selection, put the
        tool away. False when there was nothing to step back from."""
        if self.drawing is not None:
            self.drawing = self.drag = None
        elif self.selected is not None:
            self.selected = None
        elif self.tool is not None:
            self.tool = None
        else:
            return False
        return True

    # Mouse ------------------------------------------------------------------
    def press(self, pos, at, k):
        """A left press at window position `pos` (`at` and `k`: where and at
        what scale the overlay looks; the companion's picks need neither).
        True when it acts on marks, False to leave it to navigation.

        A handle of the selected mark resizes or rotates it; with no tool a
        mark's tag, pin or outline (or the inside of the selected area) moves
        it; an armed tool draws."""
        if not self.visible:
            return False
        handle = self.overlay.handle_at(at, k)
        mark = self.marks.get(self.selected)
        if handle == 'rotate' and mark:
            hit = self.world.ground_hit(pos)
            if hit is not None:
                c = marklib.center(mark)
                start = (mark.get('angle', 0.0), math.atan2(hit[1]-c[1], hit[0]-c[0]))
                self.drag, self.edited = ('rotate', (c, start, float(hit[2]))), False
            return True
        if handle is not None and mark:
            hit = self.world.ground_hit(pos)
            z = float(hit[2]) if hit is not None else self.world.focus_z()
            self.drag, self.edited = ('resize', (marklib.handles(mark)[(handle+2) % 4], z)), False
            return True
        grab = self.overlay.grab_at(at, self.selected, k) if self.tool is None else None
        if grab is not None:
            self.selected = grab
            self.drag, self.edited = ('move', self.world.ground_hit(pos)), False
            return True
        if self.tool is None:
            return False
        hit = self.world.ground_hit(pos)
        if hit is None:
            return True
        x, y = float(hit[0]), float(hit[1])
        if self.tool == 'pin':
            mark = self.marks.add('pin', [(x, y)])
            self.selected = mark['id']
            self.status.set(f'pin {mark["id"]} at ({x:.0f}, {y:.0f})', 3)
            return True
        self.drawing = dict(kind=self.tool, points=[[x, y], [x, y]], radius=0.0, start=(x, y),
                            angle=self.world.screen_angle() if self.tool == 'rect' else 0.0)
        self.drag = ('draw', hit)
        return True

    def move(self, pos):
        """The cursor moved to `pos` during a drag that press() started."""
        if self.drag is None:
            return
        kind, anchor = self.drag
        if kind == 'draw':
            d = self.drawing
            hit = self.world.ground_hit(pos, float(anchor[2]))
            if d is None or hit is None:
                return
            px, py = float(hit[0]), float(hit[1])
            if d['kind'] == 'circle':
                cx, cy = d['points'][0]
                d['radius'] = math.hypot(px-cx, py-cy)
            elif d['kind'] == 'rect':
                d['points'] = marklib.rect_points(d['start'], (px, py), d['angle'])
            else:
                lx, ly = d['points'][-1]
                if math.hypot(px-lx, py-ly) >= max(6.0, self.world.focus_distance()*0.006):
                    d['points'].append([px, py])
            return
        if self.selected is None:
            return
        if kind == 'move':
            if anchor is None:
                return
            hit = self.world.plane_hit(pos, float(anchor[2]))
            if hit is not None:
                self._checkpoint()
                self.marks.move(self.selected, float(hit[0]-anchor[0]), float(hit[1]-anchor[1]), save=False)
                self.drag = ('move', hit)
        elif kind == 'resize':
            fixed, z = anchor
            hit = self.world.ground_hit(pos, z)
            if hit is not None:
                self._checkpoint()
                self.marks.resize(self.selected, fixed, float(hit[0]), float(hit[1]), save=False)
        elif kind == 'rotate':
            c, (start, grip), z = anchor
            hit = self.world.ground_hit(pos, z)
            if hit is not None:
                self._checkpoint()
                angle = start + math.atan2(hit[1]-c[1], hit[0]-c[0]) - grip
                if self.world.shift_held():
                    angle = round(angle/math.radians(15))*math.radians(15)
                self.marks.rotate(self.selected, angle, save=False)
                self.status.set(f'turned {math.degrees(math.remainder(angle, 2*math.pi)):.0f} degrees'
                                ' (Shift snaps to 15)', 2)

    def _checkpoint(self):
        """The drag's first change: remember the marks before it for undo."""
        if not self.edited:
            self.marks.checkpoint()
            self.edited = True

    def release(self):
        """The button went up: finish a drawing, or save a moved, resized or
        rotated mark."""
        drag, self.drag = self.drag, None
        if drag is None:
            return
        if drag[0] == 'draw' and self.drawing:
            self._finish_drawing()
        elif drag[0] in ('move', 'resize', 'rotate') and self.edited:
            self.marks.save()

    def click(self, at, k):
        """A click that did not orbit: select the mark under it."""
        if self.visible and self.tool is None:
            self.selected = self.overlay.mark_at(at, k)

    def pointer(self, at, k, active):
        """Highlight the mark under the cursor and return the cursor that
        shows what a press there does: 'draw', 'move', a resize direction,
        'rotate', or None. `active`: the cursor is over the map."""
        hovered = cursor = None
        if active and self.visible:
            handle = self.overlay.handle_at(at, k)
            if handle is not None:
                hovered, cursor = self.selected, self.overlay.handle_direction(handle)
            elif self.tool is not None:
                cursor = 'draw'
            else:
                hovered = self.overlay.mark_at(at, k)
                if self.overlay.grab_at(at, self.selected, k) is not None:
                    cursor = 'move'
        self.hovered = hovered
        return cursor

    def _finish_drawing(self):
        d, self.drawing = self.drawing, None
        (x0, y0), (x1, y1) = d['points'][0], d['points'][-1]
        if d['kind'] == 'circle' and d['radius'] >= 5:
            mark = self.marks.add('circle', [d['points'][0]], radius=d['radius'])
        elif d['kind'] == 'rect' and abs(x1-x0) >= 5 and abs(y1-y0) >= 5:
            mark = self.marks.add('rect', d['points'], angle=d['angle'])
        elif d['kind'] == 'freehand' and len(d['points']) >= 3:
            mark = self.marks.add('freehand', d['points'][1:])
        else:
            return
        self.selected = mark['id']
        self.status.set(f'{mark["kind"]} {mark["id"]} added', 3)

    # Commands -----------------------------------------------------------------
    def delete_selected(self):
        if self.selected is None:
            self.status.set('nothing selected: click a mark first', 3)
            return
        self.marks.remove(self.selected)
        self.status.set(f'mark {self.selected} deleted - Ctrl+Z brings it back', 4)
        self.selected = self.hovered = None

    def clear(self):
        self.marks.clear()
        self.selected = self.hovered = None
        self.status.set('all marks cleared - Ctrl+Z brings them back', 5)

    def undo(self):
        self.drawing = self.drag = None
        if not self.marks.undo():
            self.status.set('nothing to undo', 2)
            return
        if not self.marks.get(self.selected):
            self.selected = None
        self.hovered = None
        self.status.set('mark change undone', 2)

    def hint(self):
        """What the mouse does now, for the status text: with a tool armed or
        a mark selected; else None."""
        if self.selected is not None:
            mark = self.marks.get(self.selected)
            resize = dict(circle=', handles resize', rect=', square handles resize, the round one rotates')
            return (f'mark {self.selected} selected: drag to move{resize.get(mark and mark["kind"], "")}, '
                    'Del deletes, Ctrl+Z undoes')
        return HINTS.get(self.tool) if self.tool else None


def summary_lines(items, result):
    """The marks panel's lines, (text, style) with style 'head', 'body' or
    'muted': each mark in `items` with what it covers from `result`
    (marks.describe), or 'reading...' while that is worked out."""
    lines = []
    for mark in items:
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
    if len(lines) > 17:
        # Keep the newest marks, which are the ones being worked on.
        hidden = len(lines)-16
        lines = [(f'{hidden} earlier lines not shown', 'muted')] + lines[-16:]
    return lines + [("Copy for agent (the palette's last button) puts all of it on the clipboard.", 'muted')]
