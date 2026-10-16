"""Nanduhirion v1: Nanduhirion's terrain stretched to 14,250 x 14,250 map
units and laid out for sixteen players, eight a side. The game seats eight
for now, so eight of the sixteen base sites carry starts.

The terrain is made as for Nanduhirion Enlarged (maps/nanduhirion_enlarged/):
`map mp nanduhirion` from the community 2.02 patch (`__patch202.big` in the
ROTWK folder, `mw config rotwk`), read at build time; maps/nanduhirion/
builds the original unchanged. Its playable area is 5,500 x 4,500, so the
copy is stretched 2.59 times east to west and 3.17 times south to north, and
its heights 2.86 times, the geometric mean of the two, so cliffs stay cliffs.
- Heights are resampled along Catmull-Rom curves, held within the four source
  samples around each point.
- Textures: each source texture's cells as a 0/1 field, resampled the same
  way; every new cell takes the texture whose field is highest, and
  set_materials blends the boundaries again. The source has no cliff mapping.
- The impassable and flammability planes are resampled the same way.
Not copied: the source's lighting and camera settings. Its objects are
placed again at their density and by their placement logic, on this map's
scale: scenery.py.

The layout. Nanduhirion is a stepped bowl, west against east: the battle
basin in the middle (height 0), a forward terrace on each side (143), an
outer ring with a pocket in each corner (286) and a plateau at the back
(429). Cliffs part the levels, and ramps cross them, nine a side. The east
half is the west half turned half a turn about CENTRE, to within a few units,
so every site and ramp in the west has a twin in the east.
- SITES: sixteen base sites, two in each of the four base areas a side
  (plateau, north and south pockets, forward terrace), where the original
  has one. Site k+8 is site k's twin.
- STARTS: the sites with player starts while the game seats eight, one per
  base area a side; players 1-4 west, 5-8 east.
- RAMPS: the forward terraces' ramps down into the north and south basins
  were 460 wide after the stretch, against 700-850 for the map's other
  ramps, and with eight armies a side they would be the narrowest way into
  the basins. They are rebuilt RAMP_WIDTH wide: a plane from the terrace
  down to the basin, cut into the cliffs on either side with steep, ragged,
  blocked walls (height alone never blocks: docs/game/navigation.md).

The build refuses a layout in which a site has less than MIN_OPEN units of
flat, open ground around it, cannot be walked to from the centre, or walks
there more than 5% farther than its twin. report.json lists both per site,
and layout.png shows the levels, the sites and the ramps.
"""
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mapworkshop.config import setting
from mapworkshop.formats import sections
from mapworkshop.formats.big import BigArchive
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.checks.strategy import at, distance_field, walk_grid
from mapworkshop.mapkit.relief import distance_to
from mapworkshop.mapkit.weather import apply_weather, ini_block

from .scenery import Ground, populate

ARCHIVE = '__patch202.big'      # in the ROTWK folder
SOURCE = 'maps/map mp nanduhirion/map mp nanduhirion.map'
WIDTH = HEIGHT = 1425           # playable size in cells: 14,250 map units
BORDER = 30                     # cells of unplayable border around it

CENTRE = (7140, 6975)           # the half-turn about it carries the west half onto the east


def twin(p):
    """Where the half-turn about CENTRE puts map point p: its place on the other side."""
    return 2*CENTRE[0] - p[0], 2*CENTRE[1] - p[1]


WEST_SITES = [
    ('plateau north', (1150, 8300)),
    ('plateau south', (1200, 5650)),
    ('north pocket, outer', (1375, 12675)),
    ('north pocket, inner', (2325, 11075)),
    ('south pocket, outer', (1375, 1075)),
    ('south pocket, inner', (2275, 2675)),
    ('forward terrace north', (4625, 8800)),
    ('forward terrace south', (4625, 5150)),
]
SITES = [p for _, p in WEST_SITES] + [twin(p) for _, p in WEST_SITES]
SITE_NAMES = [f'west {name}' for name, _ in WEST_SITES] + [f'east, twin of {k}' for k in range(1, 9)]
STARTS = [1, 4, 6, 8, 9, 12, 14, 16]   # site numbers; all sixteen once the game seats sixteen
MIN_OPEN = 650                  # flat open ground every site needs around it, map units

# The forward terraces' ramps into the north and south basins, (top, bottom).
WEST_RAMPS = [((4696, 10857), (5197, 11275)), ((4647, 3018), (5085, 2658))]
RAMPS = WEST_RAMPS + [(twin(top), twin(bottom)) for top, bottom in WEST_RAMPS]
RAMP_WIDTH = 750
RAMP_GROUND, RAMP_CLIFF = 'DirtMordor14', 'CliffRhun01'   # the narrow ramps' own textures
WALL = 40.0                     # how far a widened ramp's side walls reach into the cliff
STEEP = 10.0                    # a cell whose corners differ more than this is a wall: blocked


def source():
    """Nanduhirion's heights (map units), texture names and labels per cell,
    impassable and flammability planes, border and objects."""
    folder = setting('rotwk')
    if not folder:
        raise RuntimeError('The source map is in the ROTWK folder: mw config rotwk DIR')
    m = Map(BigArchive(Path(folder)/ARCHIVE).read_bytes(SOURCE))
    t, b = m.heightmap(), m.blend()
    tile_starts = [tex['tile_start'] for tex in b['textures']]
    return dict(heights=t['elevations']*.0390625, border=t['border'],
                names=[tex['name'] for tex in b['textures']],
                labels=np.searchsorted(tile_starts, b['arrays']['tiles'], side='right') - 1,
                impassable=b['arrays']['impassable'], flammability=b['arrays']['flammability'],
                objects=m.objects())


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


def level(z, p):
    """The terrain's height around map point p: the median within 50 units."""
    j, i = round(p[0]/10) + BORDER, round(p[1]/10) + BORDER
    return float(np.median(z[i-5:i+6, j-5:j+6]))


def steepness(z):
    """Per cell, the height range of its four corners (0 in the last row and
    column, which have no cell)."""
    corners = [z[:-1, :-1], z[:-1, 1:], z[1:, :-1], z[1:, 1:]]
    out = np.zeros_like(z)
    out[:-1, :-1] = np.maximum.reduce(corners) - np.minimum.reduce(corners)
    return out


def widen_ramp(z, labels, impassable, top, bottom, ground, cliff, is_cliff):
    """Rebuild the ramp from map point `top` down to `bottom` RAMP_WIDTH wide:
    a plane between the terrain just beyond its two ends, its sides cut into
    the cliffs as walls WALL deep. Ramp cells become walkable, and those that
    had a cliff texture take `ground`; steep wall cells are blocked and take
    `cliff`."""
    top, bottom = np.asarray(top, float), np.asarray(bottom, float)
    length = math.dist(top, bottom)
    u = (bottom - top)/length
    n = np.array([-u[1], u[0]])
    z_top, z_bottom = level(z, top - 100*u), level(z, bottom + 100*u)

    def frame(offset):
        """Along and across the ramp, at the samples (offset 0) or cell centres (5)."""
        y, x = (np.mgrid[0:z.shape[0], 0:z.shape[1]] - BORDER)*10.0 + offset
        s = (x - top[0])*u[0] + (y - top[1])*u[1]
        a = (x - top[0])*n[0] + (y - top[1])*n[1]
        # Each side ragged in its own way, so the cut does not look ruled.
        side = RAMP_WIDTH/2 + np.where(a > 0, 18*np.sin(s/43 + 1.3) + 8*np.sin(s/16),
                                       18*np.sin(s/37 + 4.1) + 8*np.sin(s/14 + 2.))
        w = (np.clip((side + WALL - np.abs(a))/WALL, 0, 1)*np.clip((s + WALL)/WALL, 0, 1)
             * np.clip((length + WALL - s)/WALL, 0, 1))
        return s, np.abs(a) <= side, w*w*(3 - 2*w)

    s, _, w = frame(0.)
    z += (z_top + (z_bottom - z_top)*np.clip(s/length, 0, 1) - z)*w
    s, inside, w = frame(5.)
    steep = steepness(z) > STEEP
    ramp = inside & (s > -WALL/2) & (s < length + WALL/2) & ~steep
    wall = (w > 0) & steep
    impassable[ramp] = False
    impassable[wall] = True
    labels[wall] = cliff
    labels[ramp & is_cliff[labels]] = ground


def open_ground(z, impassable):
    """Per cell, the distance in map units to the nearest blocked or sloping
    cell or the playable area's edge."""
    rough = impassable | (steepness(z) > 1.5)
    rough[:BORDER] = rough[-BORDER-1:] = True
    rough[:, :BORDER] = rough[:, -BORDER-1:] = True
    return distance_to(rough)*10


def plan(z, impassable, opens):
    """The levels, blocked ground, sites (circled by their open ground,
    filled where they have a start) and widened ramps, north up."""
    colours = np.array([(64, 76, 58), (92, 108, 74), (126, 140, 96), (166, 172, 128)], np.uint8)
    tier = np.clip(np.round(z/143), 0, 3).astype(int)
    image = colours[tier]
    image[impassable] = (170, 60, 50)
    image = Image.fromarray(image[BORDER:-BORDER, BORDER:-BORDER][::-1]).resize((950, 950))
    d = ImageDraw.Draw(image, 'RGBA')
    font = ImageFont.load_default(16)
    scale = 950/(WIDTH*10)
    point = lambda p: (p[0]*scale, 950 - p[1]*scale)
    for top, bottom in RAMPS:
        d.line([point(top), point(bottom)], fill=(255, 255, 255, 255), width=4)
    for k, (p, r) in enumerate(zip(SITES, opens), 1):
        x, y = point(p)
        colour = (90, 160, 255) if k <= 8 else (255, 160, 70)
        d.ellipse([x - r*scale, y - r*scale, x + r*scale, y + r*scale], outline=colour + (255,), width=2)
        d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=colour + ((255,) if k in STARTS else (90,)),
                  outline=(0, 0, 0, 255))
        d.text((x, y), str(k), fill=(0, 0, 0), font=font, anchor='mm')
    return image


def build(b):
    if b.project.players != len(STARTS):
        raise ValueError(f'map.toml says {b.project.players} players; STARTS places {len(STARTS)}')
    src = source()
    rows, cols = src['heights'].shape
    sx = WIDTH/(cols - 2*src['border'])
    sy = HEIGHT/(rows - 2*src['border'])
    sz = math.sqrt(sx*sy)

    fy, fx = grid(HEIGHT, sy, src['border'], rows), grid(WIDTH, sx, src['border'], cols)
    z = within(src['heights'], fy, fx, resample(src['heights'], fy, fx))*sz

    cy, cx = grid(HEIGHT, sy, src['border'], rows, True), grid(WIDTH, sx, src['border'], cols, True)
    labels = textures(src['labels'], cy, cx)
    impassable = resample(src['impassable'].astype(float), cy, cx) >= .5
    flammability = resample(src['flammability'].astype(float), cy, cx) >= .5

    names = src['names']
    is_cliff = np.array([name.startswith('Cliff') for name in names])
    for top, bottom in RAMPS:
        widen_ramp(z, labels, impassable, top, bottom, names.index(RAMP_GROUND), names.index(RAMP_CLIFF), is_cliff)

    used = np.unique(labels)
    palette = [names[k] for k in used]
    labels = np.searchsorted(used, labels)

    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    set_heights(m, z)
    set_materials(m, palette, labels, blocked=impassable,
                  cell_sizes=terrain_cell_sizes(palette), corner_blends=True)
    blend = sections.read(m, 'BlendTileData')
    blend['arrays']['flammability'] = flammability.astype('u1')
    sections.write(m, 'BlendTileData', blend)
    starts(m, [SITES[k - 1] for k in STARTS])
    placed = populate(m, src['objects'], Ground(src['heights'], src['impassable'], src['labels'], names, src['border']),
                      Ground(z, impassable, labels, palette, BORDER), (sx, sy, sz), SITES, CENTRE, twin, RAMPS)
    apply_weather(m, b.project.weather)

    # Every site needs open ground, a way to the centre, and the same walk as its twin.
    space = open_ground(z, impassable)
    opens = [float(space[round(y/10) + BORDER, round(x/10) + BORDER]) for x, y in SITES]
    walk, _ = walk_grid(m)
    field = distance_field(walk, CENTRE)
    walks = [at(field, walk, p) for p in SITES]
    b.report.update(scale=dict(x=sx, y=sy, z=sz), palette=palette, placed=placed, sites=[
        dict(site=k, name=name, x=p[0], y=p[1], open=round(r), walk_to_centre=round(d),
             player=STARTS.index(k) + 1 if k in STARTS else None)
        for k, (name, p, r, d) in enumerate(zip(SITE_NAMES, SITES, opens, walks), 1)])
    b.image('layout.png', plan(z, impassable, opens))
    problems = [f'site {k}: {r:.0f} units of open ground' for k, r in enumerate(opens, 1) if r < MIN_OPEN]
    problems += [f'site {k}: no way to the centre' for k, d in enumerate(walks, 1) if not math.isfinite(d)]
    problems += [f'sites {k} and {k + 8}: {walks[k - 1]:.0f} and {walks[k + 7]:.0f} to the centre'
                 for k in range(1, 9) if abs(walks[k - 1] - walks[k + 7]) > .05*min(walks[k - 1], walks[k + 7])]
    if problems:
        raise ValueError('Layout: ' + '; '.join(problems))
    b.save(m, ini=ini_block(b.project.weather))
