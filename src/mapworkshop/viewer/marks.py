"""Map marks: pins and shapes drawn in the viewer to point at places on a map.

The viewer's Mark tools (pin, circle, rectangle, freehand) draw red marks on
the terrain; Select moves or deletes them. Marks are kept per map in
local/marks/<map file name>.json and rewritten on every change, so another
program can read them while the viewer runs:

    mw marks [MAP] [--json]

prints each mark with its shape in map coordinates (x east and y north in
map units, the coordinates of map objects and of build scripts; z is the
terrain height there) and the map objects inside it. Use it to act on what
the user points at, e.g. "add a forest in mark 2" or "remove the bridge in
mark 1". Shapes: pin = a point (objects within --near units count as
inside), circle = centre and radius, rect = two opposite corners (axis
aligned in map coordinates), freehand = a path; a path whose ends meet is an
area, otherwise objects within --near of the line count.
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
    """The marks of one map; every change is written to marks_path()."""

    def __init__(self, map_path):
        self.map_path = Path(map_path)
        self.path = marks_path(map_path)
        self.items, self.next_id = [], 1
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.items = [m for m in data.get('marks', []) if m.get('kind') in KINDS]
            self.next_id = max([m['id'] for m in self.items], default=0) + 1
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def add(self, kind, points, radius=None):
        mark = dict(id=self.next_id, kind=kind, points=[[round(float(x), 1), round(float(y), 1)] for x, y in points])
        if radius is not None:
            mark['radius'] = round(float(radius), 1)
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

    def remove(self, mark_id):
        self.items = [m for m in self.items if m['id'] != mark_id]
        self.save()

    def clear(self):
        self.items = []
        self.next_id = 1
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(map=self.map_path.stem, map_path=str(self.map_path.resolve()),
                    updated=time.strftime('%Y-%m-%d %H:%M:%S'),
                    coordinates='map units: x east, y north (map object coordinates); z terrain height',
                    marks=[{k: v for k, v in m.items() if not k.startswith('_')} for m in self.items])
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
        (x0, y0), (x1, y1) = p[0], p[1]
        corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        edges = []
        for a, b in zip(corners, np.roll(corners, -1, axis=0)):
            n = max(1, int(np.linalg.norm(b - a)/step))
            edges.append(a + np.outer(np.arange(n)/n, b - a))
        return np.concatenate(edges), True
    return p, closed(mark)


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
        return (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
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
    map objects it covers. `m` and `terrain` (the map and its TerrainData)
    skip reading the map file again when the caller has them loaded."""
    from mapworkshop.formats.map import Map
    from mapworkshop.render.terrain import TerrainData
    m = m or Map(Path(data['map_path']).read_bytes())
    terrain = terrain or TerrainData(m)
    objects = list(m.objects())
    ox = np.array([o['x'] for o in objects], float)
    oy = np.array([o['y'] for o in objects], float)
    if assets is None:
        from mapworkshop.render.assets import GameAssets
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
    width, height = (terrain.width - 1 - 2*terrain.border)*10, (terrain.height - 1 - 2*terrain.border)*10
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
