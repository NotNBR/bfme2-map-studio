"""Nanduhirion Enlarged: the terrain of Nanduhirion stretched to 14,250 x
14,250 map units, and nothing else.

The source is `map mp nanduhirion` from the community 2.02 patch
(`__patch202.big` in the ROTWK folder, `mw config rotwk`), read at build
time: the ROTWK profile's extracted data leaves that archive out
(maps/nanduhirion/ builds the original unchanged). Its playable
area is 5,500 x 4,500 (550 x 450 cells), so the copy is stretched 2.59 times
east to west and 3.17 times south to north. Heights are scaled by 2.86, the
geometric mean of the two, so slopes keep about their steepness and cliffs
stay cliffs instead of becoming ramps: 0-224 becomes 0-642.

What is copied:
- heights, resampled along Catmull-Rom curves and held within the four source
  samples around each point, so slopes stay smooth without overshooting at
  cliff edges;
- textures: each source texture's cells as a 0/1 field, resampled the same
  way; every new cell takes the texture whose field is highest. Painted
  boundaries come out as curves at the larger scale, not 3-cell stairs, and
  set_materials blends them again (corner blends). The source has no cliff
  mapping;
- the impassable and flammability planes, resampled the same way;
- the eight player starts, moved with the terrain: a skirmish map needs them.

Not copied: the source's other 1,875 objects (trees, buildings, Gollum's
spawn points), its lighting and its camera settings.
"""
import math
import re
from pathlib import Path

import numpy as np

from mapworkshop.config import setting
from mapworkshop.formats import sections
from mapworkshop.formats.big import BigArchive
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.weather import apply_weather, ini_block

ARCHIVE = '__patch202.big'      # in the ROTWK folder
SOURCE = 'maps/map mp nanduhirion/map mp nanduhirion.map'
WIDTH = HEIGHT = 1425           # playable size in cells: 14,250 map units
BORDER = 30                     # cells of unplayable border around it


def source():
    """Nanduhirion's heights (map units), texture names and labels per cell,
    impassable and flammability planes, border, and player starts in order."""
    folder = setting('rotwk')
    if not folder:
        raise RuntimeError('The source map is in the ROTWK folder: mw config rotwk DIR')
    m = Map(BigArchive(Path(folder)/ARCHIVE).read_bytes(SOURCE))
    t, b = m.heightmap(), m.blend()
    tile_starts = [tex['tile_start'] for tex in b['textures']]
    found = {}
    for o in m.objects():
        name = dict((k, v) for k, _, v in o['properties']).get('waypointName', '')
        if match := re.fullmatch(r'Player_(\d+)_Start', name):
            found[int(match.group(1))] = (o['x'], o['y'])
    return dict(heights=t['elevations']*.0390625, border=t['border'],
                names=[tex['name'] for tex in b['textures']],
                labels=np.searchsorted(tile_starts, b['arrays']['tiles'], side='right') - 1,
                impassable=b['arrays']['impassable'], flammability=b['arrays']['flammability'],
                starts=[found[i] for i in sorted(found)])


def grid(cells, scale, border, size, centre=False):
    """Fractional source indices of the new samples along an axis of `cells`
    playable cells, or of the new cells' centres; `border` and `size` are
    the source's."""
    half = .5 if centre else 0.
    j = np.arange(cells + 2*BORDER) + half
    return np.clip((j - BORDER)/scale + border - half, 0, size - 1)


def catmull_rom(size, f):
    """The four taps and weights along an axis of `size` samples at indices `f`."""
    i = np.floor(f).astype(int); t = f - i
    taps = [np.clip(i + k, 0, size - 1) for k in (-1, 0, 1, 2)]
    weights = [((-t + 2)*t - 1)*t/2, ((3*t - 5)*t*t + 2)/2, ((-3*t + 4)*t + 1)*t/2, (t - 1)*t*t/2]
    return taps, weights


def resample(a, fy, fx):
    """`a` at rows `fy` and columns `fx`, along Catmull-Rom curves each way."""
    (cy, wy), (cx, wx) = catmull_rom(a.shape[0], fy), catmull_rom(a.shape[1], fx)
    rows = sum(a[:, c]*w for c, w in zip(cx, wx))
    return sum(rows[c]*w[:, None] for c, w in zip(cy, wy))


def within(a, fy, fx, z):
    """`z` held between the lowest and highest of the four samples of `a` around each point."""
    y0, x0 = np.floor(fy).astype(int), np.floor(fx).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    corners = [a[np.ix_(y, x)] for y in (y0, y1) for x in (x0, x1)]
    return np.clip(z, np.minimum.reduce(corners), np.maximum.reduce(corners))


def textures(labels, fy, fx):
    """Per new cell, the source texture whose resampled 0/1 field is highest."""
    best = out = None
    for k in np.unique(labels):
        field = resample((labels == k).astype(float), fy, fx)
        if best is None:
            best, out = field, np.full(field.shape, k)
        else:
            out = np.where(field > best, k, out); best = np.maximum(field, best)
    return out


def build(b):
    src = source()
    rows, cols = src['heights'].shape
    sx = WIDTH/(cols - 2*src['border'])
    sy = HEIGHT/(rows - 2*src['border'])
    sz = math.sqrt(sx*sy)

    fy, fx = grid(HEIGHT, sy, src['border'], rows), grid(WIDTH, sx, src['border'], cols)
    z = within(src['heights'], fy, fx, resample(src['heights'], fy, fx))*sz

    cy, cx = grid(HEIGHT, sy, src['border'], rows, True), grid(WIDTH, sx, src['border'], cols, True)
    labels = textures(src['labels'], cy, cx)
    used = np.unique(labels)
    palette = [src['names'][k] for k in used]
    labels = np.searchsorted(used, labels)
    impassable = resample(src['impassable'].astype(float), cy, cx) >= .5
    flammability = resample(src['flammability'].astype(float), cy, cx) >= .5

    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    set_heights(m, z)
    set_materials(m, palette, labels, blocked=impassable,
                  cell_sizes=terrain_cell_sizes(palette), corner_blends=True)
    blend = sections.read(m, 'BlendTileData')
    blend['arrays']['flammability'] = flammability.astype('u1')
    sections.write(m, 'BlendTileData', blend)

    starts(m, [(x*sx, y*sy) for x, y in src['starts']])
    apply_weather(m, b.project.weather)
    b.report.update(scale=dict(x=sx, y=sy, z=sz), palette=palette,
                    height_range=[float(z.min()), float(z.max())])
    b.save(m, ini=ini_block(b.project.weather))
