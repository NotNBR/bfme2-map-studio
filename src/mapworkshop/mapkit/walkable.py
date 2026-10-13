"""Walkability categories and reachability for local estimates or native grids.

mapkit.pathing computes the default grid without launching the game. load()
only reads saved native captures for explicit verification.

The game divides the playable area into 10 x 10 cells (Pathfinder::newMap)
and gives each a type (Pathfinder::classifyMapCell; Open-BFME-2):

    0 clear, 1 water (shallow), 2 cliff (the terrain's impassable flag),
    4 obstacle (structures), 5 impassable, 7 deep water,
    6 the ground at a spanned bridge's ends, where units step onto its layer,
    8 the top of a walk-on object such as an object bridge.

Spanned bridges have their own layers: their deck cells are clear. The grid
is read from a running game (`mw walkable --native`, mapworkshop.native) and
kept next to the build as pathfind.npz with the map's hash, so it always
belongs to the map it describes.

Categories here: WALK (clear), SHALLOW (shallow water), BRIDGE (bridge decks,
their ends and walk-on tops) and BLOCKED (the rest). Reachability is an
8-connected fill over the first three from the player starts (from the
walkable cells within START_REACH of each: a start lies inside its start
building, an obstacle): a walkable cell it does not reach is cut off from
every start.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

CELL = 10
TYPES = {0: 'clear', 1: 'shallow water', 2: 'cliff', 4: 'obstacle', 5: 'impassable', 6: 'bridge end',
         7: 'deep water', 8: 'walk-on top'}
OUTSIDE, WALK, SHALLOW, BRIDGE, BLOCKED = 0, 1, 2, 3, 4
PASSABLE = (WALK, SHALLOW, BRIDGE)
START_REACH = 300          # map units around a start that seed the fill
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

# Overlay colours, RGBA; an alpha of 192 or more is drawn striped (blocked).
COLOURS = {WALK: (80, 200, 90, 30), SHALLOW: (70, 160, 255, 120), BRIDGE: (40, 230, 170, 150),
           BLOCKED: (225, 45, 35, 200)}
CUT_OFF = (255, 140, 0, 175)


def grid_files(map_file):
    folder = Path(map_file).parent
    return folder/'pathfind.npz', folder/'pathfind.json'


def load(map_file):
    """The game's grid for this exact map file, or None (none read yet, or
    read for an earlier build): dict(ground, layers, info)."""
    grid, meta = grid_files(map_file)
    if not grid.is_file() or not meta.is_file():
        return None
    info = json.loads(meta.read_text(encoding='utf-8'))
    if info.get('map_sha256') != hashlib.sha256(Path(map_file).read_bytes()).hexdigest():
        return None
    arrays = np.load(grid)
    layers = [dict(layer, cells=arrays[f"layer{layer['index']}"]) for layer in info.get('layers', [])]
    return dict(ground=arrays['ground'], layers=layers, info=info)


def categories(grid):
    """Per cell ([y][x]): WALK, SHALLOW, BRIDGE or BLOCKED; bridge decks from their layers."""
    kind = grid['ground'] & 0xF
    result = np.full(kind.shape, BLOCKED, np.uint8)
    result[kind == 0] = WALK
    result[kind == 1] = SHALLOW
    result[(kind == 6) | (kind == 8)] = BRIDGE
    h, w = kind.shape
    for layer in grid['layers']:
        if not layer.get('bridge'):
            continue
        deck = (layer['cells'] & 0xF) == 0
        y0, x0 = layer['y0'], layer['x0']
        ys, xs = np.nonzero(deck)
        ys, xs = ys + y0, xs + x0
        keep = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
        result[ys[keep], xs[keep]] = BRIDGE
    return result


def start_cells(m, shape):
    """Grid cells ([y, x]) of the map's player starts."""
    h, w = shape
    cells = []
    for o in m.objects():
        if any(k == 'waypointName' and str(v).startswith('Player_') and str(v).endswith('_Start')
               for k, _, v in o['properties']):
            cells.append((min(max(int(o['y'] // CELL), 0), h - 1), min(max(int(o['x'] // CELL), 0), w - 1)))
    return cells


def flood(passable, seeds):
    """Cells reachable from the seeds ([y, x]) over passable cells, 8-connected."""
    h, w = passable.shape
    reached = np.zeros((h, w), bool)
    frontier = np.array([s for s in seeds if passable[s]], dtype=np.int64).reshape(-1, 2)
    if len(frontier):
        reached[frontier[:, 0], frontier[:, 1]] = True
    while len(frontier):
        nxt = (frontier[:, None, :] + np.array(NEIGHBOURS)[None]).reshape(-1, 2)
        nxt = nxt[(nxt[:, 0] >= 0) & (nxt[:, 0] < h) & (nxt[:, 1] >= 0) & (nxt[:, 1] < w)]
        nxt = nxt[passable[nxt[:, 0], nxt[:, 1]] & ~reached[nxt[:, 0], nxt[:, 1]]]
        nxt = np.unique(nxt[:, 0] * w + nxt[:, 1])
        frontier = np.stack([nxt // w, nxt % w], axis=1)
        reached[frontier[:, 0], frontier[:, 1]] = True
    return reached


def analyse(grid, m):
    """categories, reached (from the starts) and the cut-off areas (largest first):
    each dict(cells, area in map units, box [x0, y0, x1, y1], centre)."""
    kinds = categories(grid)
    passable = np.isin(kinds, PASSABLE)
    starts = start_cells(m, kinds.shape)
    yy, xx = np.indices(kinds.shape)
    near = np.zeros(kinds.shape, bool)
    for y, x in starts:
        near |= np.hypot(yy - y, xx - x) * CELL <= START_REACH
    reached = flood(passable, [tuple(c) for c in np.argwhere(near & passable)])
    left = passable & ~reached
    areas = []
    while left.any():
        seed = tuple(np.argwhere(left)[0])
        region = flood(left, [seed])
        left &= ~region
        ys, xs = np.nonzero(region)
        areas.append(dict(cells=int(region.sum()), area=int(region.sum()) * CELL * CELL,
                          box=[int(xs.min()) * CELL, int(ys.min()) * CELL, int(xs.max() + 1) * CELL, int(ys.max() + 1) * CELL],
                          centre=[round(float(xs.mean() + .5) * CELL), round(float(ys.mean() + .5) * CELL)]))
    areas.sort(key=lambda a: -a['cells'])
    return dict(categories=kinds, reached=reached, starts=starts, cut_off=areas)


def overlay(result):
    """RGBA per cell ([y][x], north is the last row): the categories' colours, cut-off cells orange."""
    kinds, reached = result['categories'], result['reached']
    rgba = np.zeros(kinds.shape + (4,), np.uint8)
    for kind, colour in COLOURS.items():
        rgba[kinds == kind] = colour
    rgba[np.isin(kinds, PASSABLE) & ~reached] = CUT_OFF
    return rgba


def summary(result, info=None, limit=12):
    """Text lines: the share of each category and the cut-off areas."""
    kinds = result['categories']
    total = kinds.size
    names = {WALK: 'walkable', SHALLOW: 'shallow water', BRIDGE: 'bridges', BLOCKED: 'blocked'}
    lines = [', '.join(f'{names[k]} {100 * np.count_nonzero(kinds == k) / total:.1f}%' for k in names) + '.']
    lines.append(f"{len(result['starts'])} player starts; walkable cells reached from them: "
                 f"{100 * result['reached'].sum() / max(np.isin(kinds, PASSABLE).sum(), 1):.1f}%.")
    cut = result['cut_off']
    if not cut:
        lines.append('No cut-off areas: every walkable cell is reachable from a start.')
    else:
        lines.append(f'{len(cut)} cut-off areas ({sum(a["area"] for a in cut):,} square units), largest first:')
        for a in cut[:limit]:
            x0, y0, x1, y1 = a['box']
            lines.append(f"  {a['area']:>9,}  around ({a['centre'][0]}, {a['centre'][1]}), x {x0}..{x1}, y {y0}..{y1}")
        if len(cut) > limit:
            lines.append(f'  ... {len(cut) - limit} more')
    if info and info.get('source') == 'computed':
        lines.append('Computed locally from terrain, water, object footprints and walking meshes. '
                     'Estimate: spawned buildings, dynamic gates and scripts are not simulated.')
        lines.extend('  '+warning for warning in info.get('warnings', []))
    elif info:
        lines.append(f"Read from the game at frame {info.get('frame', '?')} ({info.get('read', '?')}).")
    return lines


def compare(estimate, native):
    """Category and passability differences against a saved native capture."""
    a, b = categories(estimate), categories(native)
    if a.shape != b.shape:
        raise ValueError('Computed and native grid sizes differ')
    return dict(cells=int(a.size), category_match_percent=float(100*np.mean(a == b)),
                category_differences=int(np.count_nonzero(a != b)),
                passability_differences=int(np.count_nonzero(np.isin(a, PASSABLE) != np.isin(b, PASSABLE))))
