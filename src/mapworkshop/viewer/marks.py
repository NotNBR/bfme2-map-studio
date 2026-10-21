"""Map marks: pins and shapes drawn in the viewer to point at places on a map.

The viewer's Mark tools (pin, circle, rectangle, freehand) draw red marks on
the terrain; clicking a mark selects it to move, resize or delete it. Marks
are kept per map in local/marks/<map file name>.json and rewritten on every
change, so another program can read them while the viewer runs:

    mw marks [MAP] [--json]

prints each mark with its shape in map coordinates (x east and y north in
map units, the coordinates of map objects and of build scripts; z is the
terrain height there) and the map objects inside it. Use it to act on what
the user points at, e.g. "add a forest in mark 2" or "remove the bridge in
mark 1". Shapes: pin = a point (objects within --near units count as
inside), circle = centre and radius, rect = two opposite corners of the
rectangle before rotation plus an optional angle (radians, counter-clockwise,
like object angles) it is turned by around its centre, freehand = a path; a
path whose ends meet is an area, otherwise objects within --near of the line
count.
"""

import argparse
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np

from mapworkshop.config import MARKS, ROOT

MARKS_DIR = MARKS
KINDS = ('pin', 'circle', 'rect', 'freehand')


def marks_path(map_path):
    return MARKS_DIR/(Path(map_path).stem + '.json')


class Marks:
    """The marks of one map; every change is written to marks_path().
    add, remove and clear can be undone; so can a move or resize that
    called checkpoint() first."""

    UNDO_STEPS = 50

    def __init__(self, map_path):
        self.map_path = Path(map_path)
        self.path = marks_path(map_path)
        self.items, self.next_id = [], 1
        self.history = []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.items = [m for m in data.get('marks', []) if m.get('kind') in KINDS]
            self.next_id = max([m['id'] for m in self.items], default=0) + 1
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def checkpoint(self):
        """Remember the current marks for undo()."""
        self.history.append((json.loads(json.dumps(self.plain())), self.next_id))
        del self.history[:-self.UNDO_STEPS]

    def undo(self):
        """Go back to the last checkpoint; False when there is none."""
        if not self.history:
            return False
        self.items, self.next_id = self.history.pop()
        self.save()
        return True

    def add(self, kind, points, radius=None, angle=0.0):
        self.checkpoint()
        mark = dict(id=self.next_id, kind=kind, points=[[round(float(x), 1), round(float(y), 1)] for x, y in points])
        if radius is not None:
            mark['radius'] = round(float(radius), 1)
        _set_angle(mark, angle)
        self.next_id += 1
        self.items.append(mark)
        self.save()
        return mark

    def get(self, mark_id):
        return next((m for m in self.items if m['id'] == mark_id), None)

    def move(self, mark_id, dx, dy, save=True):
        mark = self.get(mark_id)
        if mark:
            mark.pop('_world', None)
            mark['points'] = [[round(x + dx, 1), round(y + dy, 1)] for x, y in mark['points']]
            if save:
                self.save()

    def resize(self, mark_id, fixed, x, y, save=True):
        """Drag a handle (see handles()) to map point x, y: a circle's rim,
        or a rectangle's corner opposite the corner `fixed`, along the
        rectangle's own (rotated) sides."""
        mark = self.get(mark_id)
        if not mark:
            return
        mark.pop('_world', None)
        if mark['kind'] == 'circle':
            cx, cy = mark['points'][0]
            mark['radius'] = round(max(5.0, math.hypot(x - cx, y - cy)), 1)
        elif mark['kind'] == 'rect':
            mark['points'] = rect_points(fixed, (x, y), mark.get('angle', 0.0))
        if save:
            self.save()

    def rotate(self, mark_id, angle, save=True):
        """Turn a rectangle to `angle` (radians, counter-clockwise) around its centre."""
        mark = self.get(mark_id)
        if mark and mark['kind'] == 'rect':
            mark.pop('_world', None)
            _set_angle(mark, angle)
            if save:
                self.save()

    def remove(self, mark_id):
        self.checkpoint()
        self.items = [m for m in self.items if m['id'] != mark_id]
        self.save()

    def clear(self):
        self.checkpoint()
        self.items = []
        self.next_id = 1
        self.save()

    def plain(self):
        """The marks without the viewer's cached fields."""
        return [{k: v for k, v in m.items() if not k.startswith('_')} for m in self.items]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(map=self.map_path.stem, map_path=str(self.map_path.resolve()),
                    updated=time.strftime('%Y-%m-%d %H:%M:%S'),
                    coordinates='map units: x east, y north (map object coordinates); z terrain height',
                    marks=self.plain())
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(temp, self.path)


# Geometry --------------------------------------------------------------------
def closed(mark):
    """Whether a mark encloses an area (a freehand path whose ends meet)."""
    if mark['kind'] in ('circle', 'rect'):
        return True
    if mark['kind'] != 'freehand' or len(mark['points']) < 3:
        return False
    p = np.asarray(mark['points'], float)
    length = float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
    return float(np.linalg.norm(p[0] - p[-1])) <= max(0.2*length, 1.0)


def outline(mark, step=40.0):
    """The mark's outline in map x/y: (points [n, 2], closed)."""
    p = np.asarray(mark['points'], float)
    if mark['kind'] == 'pin':
        return p[:1], False
    if mark['kind'] == 'circle':
        r = float(mark['radius'])
        n = max(24, min(160, int(2*math.pi*r/step)))
        a = np.linspace(0, 2*math.pi, n, endpoint=False)
        return p[0] + np.column_stack([np.cos(a), np.sin(a)])*r, True
    if mark['kind'] == 'rect':
        edges = []
        for a, b in zip(corners(mark), np.roll(corners(mark), -1, axis=0)):
            n = max(1, int(np.linalg.norm(b - a)/step))
            edges.append(a + np.outer(np.arange(n)/n, b - a))
        return np.concatenate(edges), True
    return p, closed(mark)


def _set_angle(mark, angle):
    """Store a rectangle's angle in (-pi, pi]; an unrotated one has none."""
    angle = round(math.remainder(float(angle), 2*math.pi), 4)
    if mark['kind'] == 'rect' and angle:
        mark['angle'] = angle
    else:
        mark.pop('angle', None)


def _turn(v, angle):
    """Vectors [n, 2] turned counter-clockwise by angle (radians)."""
    c, s = math.cos(angle), math.sin(angle)
    return np.asarray(v, float) @ np.array([[c, s], [-s, c]])


def rect_points(a, b, angle=0.0):
    """A rectangle's points from two opposite corners a and b (map x/y) and
    the angle its sides are turned by: the corners before rotation."""
    a, b = _turn([a, b], -angle)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    centre = _turn([(lo + hi)/2], angle)[0]
    half = (hi - lo)/2
    return [[round(float(v), 1) for v in centre - half], [round(float(v), 1) for v in centre + half]]


def corners(mark):
    """A rectangle's corners [4, 2] in map x/y, counter-clockwise from the
    one that is south-west before rotation."""
    p = np.asarray(mark['points'], float)
    lo, hi = p[:2].min(axis=0), p[:2].max(axis=0)
    half = (hi - lo)/2
    local = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*half
    return (lo + hi)/2 + _turn(local, mark.get('angle', 0.0))


def rotate_anchor(mark):
    """(centre, middle of the side that faces north before rotation) of a
    rectangle, in map x/y: the rotation handle sits beyond that side."""
    c = corners(mark)
    return c.mean(axis=0), (c[2] + c[3])/2


def handles(mark):
    """Resize handles in map x/y [n, 2]: a circle's rim at east, north, west
    and south, a rectangle's corners (see corners()); none for pins and
    freehand paths. Handle i of a rectangle is dragged against corner (i+2)%4."""
    p = np.asarray(mark['points'], float)
    if mark['kind'] == 'circle':
        r = float(mark['radius'])
        return p[0] + np.array([[r, 0], [0, r], [-r, 0], [0, -r]])
    if mark['kind'] == 'rect':
        return corners(mark)
    return np.zeros((0, 2))


def center(mark):
    p = np.asarray(mark['points'], float)
    if mark['kind'] in ('pin', 'circle'):
        return p[0]
    if mark['kind'] == 'rect':
        return p[:2].mean(axis=0)
    return p.mean(axis=0)


def _point_in_polygon(x, y, poly):
    inside = np.zeros(np.shape(x), bool)
    px, py = poly[:, 0], poly[:, 1]
    j = len(poly) - 1
    for i in range(len(poly)):
        crosses = (py[i] > y) != (py[j] > y)
        with np.errstate(divide='ignore', invalid='ignore'):
            xs = (px[j] - px[i])*(y - py[i])/(py[j] - py[i]) + px[i]
        inside ^= crosses & (x < xs)
        j = i
    return inside


def _distance_to_path(x, y, path):
    best = np.full(np.shape(x), np.inf)
    for a, b in zip(path[:-1], path[1:]):
        d = b - a
        t = np.clip(((x - a[0])*d[0] + (y - a[1])*d[1])/max(float(d @ d), 1e-9), 0, 1)
        best = np.minimum(best, np.hypot(x - (a[0] + t*d[0]), y - (a[1] + t*d[1])))
    return best


def contains(mark, x, y, near=150.0):
    """Which of the points (x, y arrays) a mark covers."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    p = np.asarray(mark['points'], float)
    if mark['kind'] == 'pin':
        return np.hypot(x - p[0, 0], y - p[0, 1]) <= near
    if mark['kind'] == 'circle':
        return np.hypot(x - p[0, 0], y - p[0, 1]) <= mark['radius']
    if mark['kind'] == 'rect':
        lo, hi = p[:2].min(axis=0), p[:2].max(axis=0)
        c = (lo + hi)/2
        local = _turn(np.column_stack([x.ravel() - c[0], y.ravel() - c[1]]), -mark.get('angle', 0.0))
        half = (hi - lo)/2
        return ((np.abs(local[:, 0]) <= half[0]) & (np.abs(local[:, 1]) <= half[1])).reshape(x.shape)
    if closed(mark):
        return _point_in_polygon(x, y, p)
    return _distance_to_path(x, y, p) <= near


def area(mark):
    if mark['kind'] == 'circle':
        return math.pi*mark['radius']**2
    if not closed(mark):
        return 0.0
    poly, _ = outline(mark)
    x, y = poly[:, 0], poly[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))/2)


# Command line ----------------------------------------------------------------
def layer(o):
    """An object's layer: the name the build placed it with (add_object's layer)."""
    return next((v for k, _, v in o['properties'] if k == 'objectLayer'), '')


def describe(data, near=150.0, assets=None, m=None, terrain=None):
    """The marks file with each mark's centre, terrain height, extent and the
    map objects it covers. `m` and `terrain` (the map and its formats.terrain.Heights)
    skip reading the map file again when the caller has them loaded."""
    from mapworkshop.formats.map import Map
    from mapworkshop.formats.terrain import Heights
    m = m or Map(Path(data['map_path']).read_bytes())
    terrain = terrain or Heights.of(m)
    objects = list(m.objects())
    ox = np.array([o['x'] for o in objects], float)
    oy = np.array([o['y'] for o in objects], float)
    if assets is None:
        from mapworkshop.assets.library import GameAssets
        assets = GameAssets()
    vegetation = {}

    def is_vegetation(template):
        if template not in vegetation:
            r = assets.template_model(template)
            vegetation[template] = bool(r and r['tree'])
        return vegetation[template]

    marks = []
    for mark in data['marks']:
        c = center(mark)
        entry = dict(mark)
        entry['center'] = [round(float(c[0]), 1), round(float(c[1]), 1),
                           round(float(terrain.height_at(np.array([c[0]]), np.array([c[1]]))[0]), 1)]
        pts, _ = outline(mark)
        if mark['kind'] == 'rect':
            entry['corners'] = [[round(float(v), 1) for v in c] for c in corners(mark)]
        if mark['kind'] != 'pin':
            entry['bounds'] = [round(float(v), 1) for v in (*pts.min(axis=0), *pts.max(axis=0))]
            entry['area'] = round(area(mark))
            entry['closed'] = closed(mark)
        inside = np.nonzero(contains(mark, ox, oy, near))[0] if len(objects) else []
        found = [objects[i] for i in inside if 'skydome' not in objects[i]['template'].lower()]
        entry['objects'] = [dict(template=o['template'], x=round(o['x'], 1), y=round(o['y'], 1), index=o['index'],
                                 layer=layer(o)) for o in found if not is_vegetation(o['template'])]
        entry['vegetation'] = dict(Counter(o['template'] for o in found if is_vegetation(o['template'])))
        entry['layers'] = dict(Counter(layer(o) for o in found if layer(o)).most_common())
        marks.append(entry)
    width, height = terrain.playable
    from mapworkshop.project import for_map_file
    owner = for_map_file(data['map_path'])
    return dict(data, title=owner.title if owner else data['map'], playable=[width, height], near=near, marks=marks)


def text(result):
    lines = [f"Marks on {result.get('title', result['map'])} (updated {result['updated']})",
             f"Coordinates: map units, x east and y north; playable area 0..{result['playable'][0]:g} x "
             f"0..{result['playable'][1]:g}; z is the terrain height.", '']
    if not result['marks']:
        lines.append('No marks.')
    for m in result['marks']:
        x, y, z = m['center']
        if m['kind'] == 'pin':
            shape = f'at ({x:g}, {y:g}), ground z {z:g}'
        elif m['kind'] == 'circle':
            shape = f'centre ({x:g}, {y:g}), radius {m["radius"]:g}, ground z {z:g}'
        elif m['kind'] == 'rect' and m.get('angle'):
            (x0, y0), (x1, y1) = m['points']
            shape = (f'centre ({x:g}, {y:g}), {abs(x1 - x0):g} x {abs(y1 - y0):g} turned '
                     f'{math.degrees(m["angle"]):.1f} degrees counter-clockwise, corners '
                     + ', '.join(f'({cx:g}, {cy:g})' for cx, cy in corners(m)))
        elif m['kind'] == 'rect':
            (x0, y0), (x1, y1) = m['points']
            shape = f'from ({min(x0, x1):g}, {min(y0, y1):g}) to ({max(x0, x1):g}, {max(y0, y1):g}), centre ({x:g}, {y:g})'
        else:
            shape = (f'{"area" if m["closed"] else "path"} of {len(m["points"])} points, centre ({x:g}, {y:g}), '
                     f'bounds {m["bounds"]}')
        lines.append(f'#{m["id"]} {m["kind"]}: {shape}' + (f', area {m["area"]:,}' if m.get('area') else ''))
        if m['objects']:
            lines.append('   objects: ' + '; '.join(f'{o["template"]} at ({o["x"]:g}, {o["y"]:g})'
                                                    + (f' [{o["layer"]}]' if o.get('layer') else '')
                                                    for o in m['objects'][:25])
                         + (f'; ... {len(m["objects"]) - 25} more' if len(m['objects']) > 25 else ''))
        if m['vegetation']:
            lines.append('   vegetation: ' + ', '.join(f'{n} x {t}' for t, n in
                                                       sorted(m['vegetation'].items(), key=lambda kv: -kv[1])))
        if m.get('layers'):
            lines.append('   layers: ' + ', '.join(f'{name} {n}' for name, n in m['layers'].items()))
        if not m['objects'] and not m['vegetation']:
            lines.append('   no objects')
    return '\n'.join(lines)


def source_hint(map_path):
    """Where the marked map comes from and how to change it, for an agent."""
    from mapworkshop import project
    p = project.for_map_file(map_path)
    if p is None:
        return (f'Map: {Path(map_path).stem}, a stock map (read-only). To change it, start a project from it '
                f'in maps/ (see AGENTS.md).')
    entry = (p.folder/(p.module_name.rsplit('.', 1)[-1] + '.py')).relative_to(ROOT).as_posix()
    return (f'Map: {p.title}, project maps/{p.folder.name}/ ({entry} builds it). '
            f'Change the source there, then run `mw build {p.id}`; the viewer reloads the new build. '
            f"An object's [layer] is the layer name the source placed it with; search the source for that name.")


def agent_text(result):
    """The marks as text, with the map's source project: what Copy for agent copies."""
    return text(result) + '\n\n' + source_hint(result['map_path'])


def main(argv=None):
    parser = argparse.ArgumentParser(prog='mw marks', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('map', nargs='?', help='Map project, stock map or .map file (default: the map whose marks changed last)')
    parser.add_argument('--map', dest='map_option', help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true', help='Print JSON instead of text')
    parser.add_argument('--near', type=float, default=150.0,
                        help='Distance in map units around pins and open paths that counts as inside (150)')
    args = parser.parse_args(argv)
    name = args.map or args.map_option
    if name:
        from mapworkshop import project
        try:
            path = marks_path(project.map_path(name))
        except LookupError:
            path = marks_path(name)
    else:
        files = sorted(MARKS_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime) if MARKS_DIR.is_dir() else []
        if not files:
            print('No marks yet: draw some with the Mark tools in the viewer (mw view).')
            return 1
        path = files[-1]
    if not path.is_file():
        print(f'No marks on {Path(path).stem} yet: draw some with Mark in the viewer (mw view).')
        return 1
    result = describe(json.loads(path.read_text(encoding='utf-8')), near=args.near)
    print(json.dumps(result, indent=2) if args.json else agent_text(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
