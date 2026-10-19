"""Where an object's model stands: its outline cut at a height, its footprint
seen from above, its named points, in its own frame or on a map.

    from mapworkshop.render import footprint
    piers = footprint.section('GondorIthilienBridge2', -11)   # cut 11 below its origin
    roof = footprint.footprint('CBHobbitBldg01')               # all of it, from above
    hull = footprint.footprint('GondorIthilienBridge2', high=-5)   # only what lies below -5
    points = footprint.bones('GondorIthilienBridge2')          # {bone: (x, y, z)}
    on_map = footprint.to_world(piers[0], x, y, angle)         # for an object placed there

    mw item TEMPLATE --section H | --footprint [--low L] [--high H] | --bones
    mw where MAP PATTERN... [--layer L] [--near X,Y,R] [--section Z | --footprint | --bones]

The object's frame is the model's, in map units, scaled by the template's
Scale: at angle 0 its x points east and its y north, z up from the object's
origin (its position on the map: the ground there plus the object's z).
A placed object's angle turns the frame counter-clockwise, as
mapkit.blank.add_object takes it. Per-object scale variation
(InstanceScaleFuzziness, trees and shrubs) is not applied.

Outlines are closed polygons, a list of (x, y) points without the first
repeated, counter-clockwise round solid ground and clockwise round a hole in
it. They are traced from a grid of `step` map units (1 by default), so each
edge is accurate to about one step; straight edges come out straight.

- `section` cuts the visible meshes with a level plane: what is solid at that
  height (the piers at the waterline). A part of the model that is not a
  closed surface (a single wall plane) has no inside and drops out.
- `footprint` projects every visible triangle, clipped to the band of heights
  between `low` and `high`, onto the ground: the area the model covers seen
  from straight above, overhangs included.

Neither is the game's collision footprint: that is the template's Geometry
(a box or cylinder; `mw item TEMPLATE --info`), which
mapkit.pathing.footprint_cells lays onto terrain cells as the game does.
"""
import fnmatch
import math

import numpy as np


# The model --------------------------------------------------------------------
def _assets(assets):
    if assets is None:
        from mapworkshop.assets.library import GameAssets
        assets = GameAssets.shared()
    return assets


def model(template, assets=None):
    """The template's model, its scale and its visible triangles in the
    object's frame: dict(model, scale, parts=[(N, 3, 3) arrays, one per mesh
    part], bones={name: 4x4 matrix}). Raises LookupError for a template
    without a model."""
    assets = _assets(assets)
    info = assets.template_model(template)
    if info is None:
        raise LookupError(f'{template}: no such template, or it has no model')
    cache = assets.__dict__.setdefault('_footprint_models', {})
    key = info['model'].lower()
    if key not in cache:
        from mapworkshop.assets.models import ModelCache
        cache[key] = ModelCache(assets).load(info['model'])
    loaded = cache[key]
    if not loaded:
        raise LookupError(f'{template}: its model {info["model"]} could not be loaded')
    scale = info['scale']
    # Camera-facing parts (sprites that turn to the viewer) have no fixed shape.
    parts = [p['positions'][p['indices'].reshape(-1, 3)].astype(np.float64)*scale
             for p in loaded['parts'] if not p['camera'] and len(p['indices'])]
    bones = {name: np.asarray(m, np.float64) for name, m in loaded['bones'].items()}
    return dict(model=info['model'], scale=scale, parts=parts, bones=bones)


def bones(template, assets=None):
    """The model's named points (bones): {name: (x, y, z)} in the object's frame."""
    found = model(template, assets)
    return {name: tuple(round(float(v)*found['scale'], 2) for v in m[:3, 3])
            for name, m in sorted(found['bones'].items())}


def bounds(template, assets=None):
    """(low, high): the model's box in the object's frame, each (x, y, z)."""
    points = np.concatenate([p.reshape(-1, 3) for p in model(template, assets)['parts']])
    return tuple(round(float(v), 2) + 0. for v in points.min(0)), tuple(round(float(v), 2) + 0. for v in points.max(0))


# On a map -----------------------------------------------------------------------
def placed(m, patterns=(), layer=None, near=None):
    """The objects placed on map `m` (formats.map.Map) that match: any of
    `patterns` against the template, the object's name or a waypoint's name
    (a wildcard such as *bridge*, else any part of it; case-insensitive), in
    `layer`, and within `near` = (x, y, radius). Each: dict(index, template,
    name, layer, x, y, ground (the terrain there), z (its origin's height on
    the map: the ground plus the object's own z), angle (radians,
    counter-clockwise from east))."""
    from mapworkshop.render.terrain import TerrainData
    terrain = None
    found = []
    for o in m.objects():
        props = {k: v for k, _, v in o['properties']}
        name = props.get('objectName') or props.get('waypointName') or ''
        if layer is not None and props.get('objectLayer', '') != layer:
            continue
        if near is not None and math.dist((o['x'], o['y']), near[:2]) > near[2]:
            continue
        if patterns and not any(_matches(pattern, text) for pattern in patterns
                                for text in (o['template'], name) if text):
            continue
        if terrain is None:
            terrain = TerrainData(m)
        ground = float(terrain.height_at(np.array([o['x']]), np.array([o['y']]))[0])
        found.append(dict(index=o['index'], template=o['template'], name=name, layer=props.get('objectLayer', ''),
                          x=round(o['x'], 1), y=round(o['y'], 1), ground=round(ground, 1),
                          z=round(ground + o['z'], 1), angle=o['angle']))
    return found


def _matches(pattern, text):
    pattern, text = pattern.lower(), text.lower()
    if any(ch in pattern for ch in '*?['):
        return fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(text.rsplit('/', 1)[-1], pattern)
    return pattern in text


# Outlines -----------------------------------------------------------------------
def section(template, height, step=1., assets=None):
    """Outlines of the model cut by the level plane `height` (object frame)."""
    return section_of(model(template, assets)['parts'], height, step)


def footprint(template, low=None, high=None, step=1., assets=None):
    """Outlines of the ground the model covers seen from above, counting only
    what lies between the heights `low` and `high` (object frame; None: no limit)."""
    return footprint_of(model(template, assets)['parts'], low, high, step)


def section_of(parts, height, step=1.):
    """section() for triangles: a list of (N, 3, 3) arrays, one per mesh part."""
    cuts = [c for c in (_cut(tris, height) for tris in parts) if len(c)]
    if not cuts:
        return []
    cuts = np.concatenate(cuts)
    grid = _Grid(cuts.reshape(-1, 2).min(0), cuts.reshape(-1, 2).max(0), step)
    return grid.outlines(grid.winding(cuts))


def footprint_of(parts, low=None, high=None, step=1.):
    """footprint() for triangles: a list of (N, 3, 3) arrays, one per mesh part."""
    polygons = []
    for tris in parts:
        for tri in tris:
            clipped = _clip(tri, low, high)
            if len(clipped) >= 3:
                polygons.append(clipped[:, :2])
    if not polygons:
        return []
    every = np.concatenate(polygons)
    grid = _Grid(every.min(0), every.max(0), step)
    return grid.outlines(grid.fill(polygons))


def to_world(points, x, y, angle, z=None):
    """Points of the object's frame, (x, y) or (x, y, z), on the map for an
    object at (x, y) turned `angle` radians; with `z` (the origin's height on
    the map) the points' heights too."""
    c, s = math.cos(angle), math.sin(angle)
    out = []
    for p in points:
        wx, wy = x + p[0]*c - p[1]*s, y + p[0]*s + p[1]*c
        if len(p) > 2 and z is not None:
            out.append((round(wx, 1), round(wy, 1), round(z + p[2], 1)))
        else:
            out.append((round(wx, 1), round(wy, 1)))
    return out


def area(points):
    """Signed area: positive for counter-clockwise (solid), negative for a hole."""
    p = np.asarray(points, float)
    return float(np.dot(p[:, 0], np.roll(p[:, 1], -1)) - np.dot(p[:, 1], np.roll(p[:, 0], -1)))/2


def describe(outlines):
    """One line per outline: its extent, area and corners."""
    lines = []
    for i, points in enumerate(outlines, 1):
        p = np.asarray(points)
        a = area(points)
        lines.append(f'#{i} {"hole" if a < 0 else "solid"}: x {p[:, 0].min():g}..{p[:, 0].max():g}, '
                     f'y {p[:, 1].min():g}..{p[:, 1].max():g}, area {abs(a):,.0f}, {len(points)} corners: '
                     + ' '.join(f'({px:g}, {py:g})' for px, py in points))
    return lines


# Geometry -----------------------------------------------------------------------
def _cut(tris, height):
    """Segments (N, 2, 2) where triangles cross the level plane `height`."""
    z = tris[:, :, 2] - height
    z = np.where(z == 0, 1e-6, z)           # a vertex on the plane counts as just above it
    above = z > 0
    crossing = above.any(1) & ~above.all(1)
    tris, z, above = tris[crossing], z[crossing], above[crossing]
    if not len(tris):
        return np.zeros((0, 2, 2))
    ends = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        with np.errstate(divide='ignore', invalid='ignore'):     # edges that don't cross: unused
            t = z[:, a]/(z[:, a] - z[:, b])
            point = tris[:, a, :2] + (tris[:, b, :2] - tris[:, a, :2])*t[:, None]
        ends.append((above[:, a] != above[:, b], point))
    # Exactly two of the three edges cross the plane.
    first = np.where(ends[0][0][:, None], ends[0][1], ends[1][1])
    second = np.where(ends[2][0][:, None], ends[2][1], ends[1][1])
    # Direct each segment along the surface, the triangle's facing on its
    # right, so closed surfaces give loops of one sense (holes the other).
    normal = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])[:, :2]
    along = second - first
    flip = along[:, 0]*normal[:, 1] - along[:, 1]*normal[:, 0] > 0
    first, second = np.where(flip[:, None], second, first), np.where(flip[:, None], first, second)
    return np.stack([first, second], 1)


def _clip(tri, low, high):
    """The triangle clipped to low <= z <= high (Sutherland-Hodgman)."""
    poly = list(tri)
    for limit, keep in ((low, lambda v, l: v >= l), (high, lambda v, l: v <= l)):
        if limit is None or not poly:
            continue
        out = []
        for i, cur in enumerate(poly):
            prev = poly[i - 1]
            if keep(cur[2], limit):
                if not keep(prev[2], limit):
                    out.append(prev + (cur - prev)*(limit - prev[2])/(cur[2] - prev[2]))
                out.append(cur)
            elif keep(prev[2], limit):
                out.append(prev + (cur - prev)*(limit - prev[2])/(cur[2] - prev[2]))
        poly = out
    return np.asarray(poly).reshape(-1, 3)


class _Grid:
    """A grid of `step`-sized cells over a box, with a cell's margin round it."""

    def __init__(self, low, high, step):
        self.step = float(step)
        self.origin = np.floor(np.asarray(low)/self.step)*self.step - self.step
        cells = np.ceil((np.asarray(high) - self.origin)/self.step).astype(int) + 2
        self.shape = (int(cells[1]), int(cells[0]))         # rows (y), columns (x)

    def fill(self, polygons):
        """Cells whose centres lie inside any of the convex polygons; a polygon
        that covers no centre (a wall seen edge-on) marks the cells along its
        edges, where no filled cell lies within half a cell (so the walls of a
        solid add nothing round it)."""
        mask = np.zeros(self.shape, bool)
        thin = []
        for poly in polygons:
            p = (np.asarray(poly, float) - self.origin)/self.step      # cell (i, j) has its centre at (j + .5, i + .5)
            j0, i0 = np.ceil(p.min(0) - .5).astype(int)
            j1, i1 = np.floor(p.max(0) - .5).astype(int)
            hit = False
            if j1 >= j0 and i1 >= i0:
                cx, cy = np.meshgrid(np.arange(j0, j1 + 1) + .5, np.arange(i0, i1 + 1) + .5)
                side = [(b[0] - a[0])*(cy - a[1]) - (b[1] - a[1])*(cx - a[0]) for a, b in zip(p, np.roll(p, -1, 0))]
                inside = np.all([s >= 0 for s in side], 0) | np.all([s <= 0 for s in side], 0)
                if inside.any():
                    mask[i0:i1 + 1, j0:j1 + 1] |= inside
                    hit = True
            if not hit:
                for a, b in zip(p, np.roll(p, -1, 0)):
                    t = np.linspace(0, 1, int(np.hypot(*(b - a))*2) + 2)[:, None]
                    thin.append(a + (b - a)*t)
        if thin:
            points = np.concatenate(thin)
            near = np.zeros(len(points), bool)
            for dj in (-.5, .5):
                for di in (-.5, .5):
                    j, i = np.floor(points[:, 0] + dj).astype(int), np.floor(points[:, 1] + di).astype(int)
                    near |= mask[i, j]
            cells = np.floor(points[~near]).astype(int)
            mask[cells[:, 1], cells[:, 0]] = True
        return mask

    def winding(self, segments):
        """Cells whose centres the directed segments wind round (non-zero rule,
        either sense), so overlapping solids add instead of cancelling."""
        mask = np.zeros(self.shape, bool)
        ys = self.origin[1] + (np.arange(self.shape[0]) + .5)*self.step
        xs = self.origin[0] + (np.arange(self.shape[1]) + .5)*self.step
        (x0, y0), (x1, y1) = segments[:, 0].T, segments[:, 1].T
        for row, y in enumerate(ys):
            hit = (y0 <= y) != (y1 <= y)
            if not hit.any():
                continue
            cross = x0[hit] + (y - y0[hit])*(x1[hit] - x0[hit])/(y1[hit] - y0[hit])
            sense = np.where(y1[hit] > y0[hit], 1, -1)
            order = np.argsort(cross)
            cross, sense = cross[order], sense[order]
            # Winding at x: the senses of the crossings to its right.
            right = np.concatenate([np.cumsum(sense[::-1])[::-1], [0]])
            mask[row] = right[np.searchsorted(cross, xs)] != 0
        return mask

    def outlines(self, mask):
        """Closed outlines round the cells of `mask`, in map units."""
        loops = _trace(mask)
        out = []
        for loop in loops:
            points = [(self.origin[0] + x*self.step, self.origin[1] + y*self.step) for x, y in loop]
            points = _simplify(points, self.step)
            if len(points) >= 3:
                out.append([(round(float(x), 1), round(float(y), 1)) for x, y in points])
        out.sort(key=lambda p: (-abs(area(p)), p[0]))
        return out


def _trace(mask):
    """Loops of grid corners (x, y) round the cells of `mask`: each cell edge
    between a set and an unset cell, directed with the set cell on its left,
    joined end to start, turning left first where two loops touch at a corner."""
    m = np.pad(mask, 1)
    edges = {}
    rows, cols = np.nonzero(m)
    for r, c in zip(rows, cols):
        x, y = c - 1, r - 1                  # the cell's lower-left corner, in cells of the unpadded grid
        if not m[r - 1, c]:
            edges.setdefault((x, y), []).append((x + 1, y))           # below: east
        if not m[r, c + 1]:
            edges.setdefault((x + 1, y), []).append((x + 1, y + 1))   # right: north
        if not m[r + 1, c]:
            edges.setdefault((x + 1, y + 1), []).append((x, y + 1))   # above: west
        if not m[r, c - 1]:
            edges.setdefault((x, y + 1), []).append((x, y))           # left: south
    loops = []
    while edges:
        start = min(edges)
        loop, at, heading = [start], start, None
        while True:
            options = edges[at]
            if heading is None or len(options) == 1:
                nxt = options[0]
            else:
                def turn(p):
                    d = (p[0] - at[0], p[1] - at[1])
                    cross = heading[0]*d[1] - heading[1]*d[0]
                    return -cross                    # left turns first
                nxt = min(options, key=turn)
            options.remove(nxt)
            if not options:
                del edges[at]
            heading = (nxt[0] - at[0], nxt[1] - at[1])
            at = nxt
            if at == start:
                break
            loop.append(at)
        loops.append(loop)
    return loops


def _simplify(points, tolerance):
    """Douglas-Peucker on a closed loop, keeping its corners."""
    p = np.asarray(points, float)
    if len(p) < 4:
        return [tuple(v) for v in p]
    # Split the loop at the point farthest from the first, simplify both halves.
    far = int(np.argmax(((p - p[0])**2).sum(1)))
    keep = np.zeros(len(p), bool)
    keep[[0, far]] = True

    def run(i, j):
        stack = [(i, j)]
        while stack:
            i, j = stack.pop()
            if j - i < 2:
                continue
            a, b = p[i], p[j % len(p)]
            seg = b - a
            idx = np.arange(i + 1, j) % len(p)
            v = p[idx] - a
            n = math.hypot(*seg)
            d = np.abs(seg[0]*v[:, 1] - seg[1]*v[:, 0])/n if n else np.hypot(v[:, 0], v[:, 1])
            k = int(np.argmax(d))
            if d[k] > tolerance:
                keep[idx[k]] = True
                stack += [(i, i + 1 + k), (i + 1 + k, j)]
    run(0, far)
    run(far, len(p))
    return [tuple(v) for v in p[keep]]
