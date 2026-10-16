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
  way; every new cell takes the texture whose field is highest. The game
  blends a change of texture inside one cell, which looks hard on patches
  three times the original's size, so where two ground textures of
  different colour meet, the darker side turns into bands of in-between
  textures the game has, chosen for each pair by colour and pattern
  (blends.py, after the Blend Lab: maps/blend_lab/map.py). The source has
  no cliff mapping.
- The impassable and flammability planes are resampled the same way.
- Its look is copied (LOOK): the lighting (overbright, warm sun, green
  fill), the environment's macro and cloud textures, the colour grade (a
  lookup table post effect, which the renderer does not draw) and its
  map.ini, which leaves the game's default weather. map.toml names no
  weather preset for that reason. Two things grow with the map: the macro
  tint and the cloud shadows repeat every 660 units by default, about eight
  times across the original but 21 across this map, where they show as a
  square grid. The macro tint is stretched over the whole map instead, and
  the clouds repeat CLOUD_SIZE apart, drifting as fast over the ground as
  the original's (CLOUD_DRIFT).
Not copied: the source's camera settings. Its objects are placed again at
their density and by their placement logic, on this map's scale: scenery.py.

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
- Neutral sites stay in the middle, as in the original (scenery.py). The
  original's four outposts become eight: LANE_OUTPOSTS adds a second to each
  basin lane.
- RAMPS: the forward terraces' ramps down into the north and south basins
  were 460 wide after the stretch, against 700-850 for the map's other
  ramps, and with eight armies a side they would be the narrowest way into
  the basins. They are rebuilt RAMP_WIDTH wide: a plane from the terrace
  down to the basin, cut into the cliffs on either side with steep, ragged,
  blocked walls (height alone never blocks: docs/game/navigation.md).
- Every ramp is cleaned (clean_ramps()): the original's ramps are flat
  slabs meeting the levels in dead-straight creases, painted in two or three
  dirts, which the stretch turns into long hard edges and blocks. The creases
  are rounded over about 200 units; each ramp of ordinary size becomes a
  worn track: one of its own ground textures, the one most common round it,
  over a ragged outline that hides the slab's straight sides, with the
  grass round it along the cliff walls (MARGIN); the soft bands
  (blends.py) blend it into the rest. The
  cliffs along the ramps end in straight walls, which read as ruled lines at
  this scale: ragged notches are cut into them (NOTCH), floored at the
  ramp's height and walled again.

The build refuses a layout in which a site has less than MIN_OPEN units of
flat, open ground around it, cannot be walked to from the centre, or walks
there or to its nearest outpost more than 5% farther than its twin.
report.json lists these per site, and layout.png shows the levels, the sites
and the ramps.
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
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.relief import distance_to

from .blends import ladders, soften
from .scenery import Ground, populate

ARCHIVE = '__patch202.big'      # in the ROTWK folder
SOURCE = 'maps/map mp nanduhirion/map mp nanduhirion.map'
SOURCE_INI = 'maps/map mp nanduhirion/map.ini'
LOOK = ('GlobalLighting', 'EnvironmentData', 'PostEffectsChunk')   # copied from the source
CLOUD_SIZE = (5200.0, 4700.0)   # one cloud repeat, map units (the game's default: 660 x 660)
# weather.ini's default drift, -0.012 and -0.018 of a 660-unit repeat a second.
CLOUD_DRIFT = (-0.012*660/CLOUD_SIZE[0], -0.018*660/CLOUD_SIZE[1])
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

# Each basin lane's second outpost, north lanes (the south ones are their
# twins): at the lane's inner end, where it opens into the arena, under the
# forward terrace's cliff; the nearest ground to it level enough for a
# neutral site, here and at its twin. The lane's first is the original's, in
# its far corner.
LANE_OUTPOSTS = [(5810, 10380), (8390, 10340)]

# The forward terraces' ramps into the north and south basins, (top, bottom).
WEST_RAMPS = [((4696, 10857), (5197, 11275)), ((4647, 3018), (5085, 2658))]
RAMPS = WEST_RAMPS + [(twin(top), twin(bottom)) for top, bottom in WEST_RAMPS]
RAMP_WIDTH = 750
RAMP_CLIFF = 'CliffRhun01'      # the texture of a widened ramp's side walls
WALL = 40.0                     # how far a widened ramp's side walls reach into the cliff
STEEP = 10.0                    # a cell whose corners differ more than this is a wall: blocked
UNPAINTED = -1                  # a widened ramp's new ground, until clean_ramps() paints it
RAMP_SLOPE = .12                # walkable ground steeper than this (rise over run) can be ramp
RAMP_RISE = 80.0                # a ramp joins two levels: its slope rises at least this
RAMP_CELLS = 9000               # larger slopes (the broad ones up to the centre strip) keep their painting
CLEAN = 10                      # cells either side over which a ramp's heights are smoothed, twice
OUTLINE = 6                     # cells over which a ramp's painted outline is rounded
RAGGED = .2                     # how far noise moves that outline (share of its rounding)
RAMP_SHARE = .2                 # a texture covering this share of a ramp can paint it
NOTCH = (25.0, 20.0)            # notches cut into the cliffs along a ramp: mean depth, spread (map units)
MARGIN = (110.0, 45.0)          # a ramp's margin along its cliff walls: mean width, spread (map units)


def source():
    """Nanduhirion's heights (map units), texture names and labels per cell,
    impassable and flammability planes, border, objects, its LOOK sections
    and its map.ini."""
    folder = setting('rotwk')
    if not folder:
        raise RuntimeError('The source map is in the ROTWK folder: mw config rotwk DIR')
    archive = BigArchive(Path(folder)/ARCHIVE)
    m = Map(archive.read_bytes(SOURCE))
    t, b = m.heightmap(), m.blend()
    tile_starts = [tex['tile_start'] for tex in b['textures']]
    return dict(heights=t['elevations']*.0390625, border=t['border'],
                names=[tex['name'] for tex in b['textures']],
                labels=np.searchsorted(tile_starts, b['arrays']['tiles'], side='right') - 1,
                impassable=b['arrays']['impassable'], flammability=b['arrays']['flammability'],
                objects=m.objects(), look={name: sections.read(m, name) for name in LOOK},
                ini=archive.read(SOURCE_INI).replace('\r\n', '\n'))


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


def widen_ramp(z, labels, impassable, top, bottom, cliff, is_cliff):
    """Rebuild the ramp from map point `top` down to `bottom` RAMP_WIDTH wide:
    a plane between the terrain just beyond its two ends, its sides cut into
    the cliffs as walls WALL deep. Ramp cells become walkable, and those that
    had a cliff texture are left UNPAINTED; steep wall cells are blocked and
    take `cliff`."""
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
    labels[ramp & is_cliff[labels]] = UNPAINTED


def smooth(a, r):
    """`a` averaged over the (2r+1) x (2r+1) cells around each (edges repeated)."""
    n = 2*r + 1
    c = np.pad(np.cumsum(np.cumsum(np.pad(a, r, mode='edge'), 0), 1), ((1, 0), (1, 0)))
    return (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n])/(n*n)


def regions(mask):
    """The connected regions of `mask` (four-neighbour), as arrays of flat
    cell indices."""
    h, w = mask.shape
    flat = mask.ravel()
    seen = np.zeros(flat.size, bool)
    out = []
    for start in np.flatnonzero(flat):
        if seen[start]:
            continue
        seen[start] = True
        stack, cells = [start], []
        while stack:
            i = stack.pop()
            cells.append(i)
            y, x = divmod(i, w)
            for j, ok in ((i - w, y > 0), (i + w, y < h - 1), (i - 1, x > 0), (i + 1, x < w - 1)):
                if ok and flat[j] and not seen[j]:
                    seen[j] = True
                    stack.append(j)
        out.append(np.array(cells))
    return out


def clean_ramps(z, labels, impassable, names):
    """Round the ramps and paint each in one texture, in place; returns how
    many ramps were found. A ramp is a connected region of walkable ground
    steeper than RAMP_SLOPE rising at least RAMP_RISE. Its heights, with
    2*CLEAN cells round it, are smoothed twice over CLEAN cells, averaging
    walkable ground only, so the creases at its top and foot round off and
    the cliffs beside it neither move nor pull bumps into it. A ramp of up to
    RAMP_CELLS cells then takes, of the ground textures covering RAMP_SHARE of
    it, the one most common within 2*CLEAN cells round it, over its outline
    rounded by OUTLINE cells and made ragged by RAGGED of noise; within
    MARGIN (a mean width and a spread of noise) of blocked ground it takes
    instead the grass most common round it, if any, so the ramp is a track
    worn through the grass it joins. UNPAINTED cells left
    over take the texture round them.

    First the blocked ground along each ramp is notched: within 2*CLEAN
    cells of it, blocked cells less than NOTCH (a mean depth and a spread of
    noise) from walkable ground become ramp, at the height of the ramp beside
    them (the ramp's own cells within 8) and UNPAINTED; those left steeper
    than STEEP are blocked again, as
    the notches' walls. The noise is the same at a point and its twin."""
    walk = ~impassable
    gy, gx = np.gradient(z, 10.)
    found = [cells for cells in regions(walk & (np.hypot(gx, gy) > RAMP_SLOPE))
             if np.ptp(z.ravel()[cells]) >= RAMP_RISE]
    ramp = np.zeros(z.shape, bool)
    for cells in found:
        ramp.ravel()[cells] = True
    y, x = (np.mgrid[0:z.shape[0], 0:z.shape[1]] - BORDER)*10.0
    wobble = fbm(x, y, scale=70, seed=440, octaves=3) + fbm(2*CENTRE[0] - x, 2*CENTRE[1] - y, scale=70, seed=440, octaves=3)
    depth = np.maximum(NOTCH[0] + NOTCH[1]*wobble/wobble.std(), 0)
    notch = impassable & (smooth(ramp.astype(float), 2*CLEAN) > 0) & (distance_to(walk)*10 < depth)
    weight = (ramp & walk).astype(float)          # the ramp's own ground, not a level beyond the cliff
    beside = smooth(z*weight, 8)/np.maximum(smooth(weight, 8), 1e-9)
    notch &= smooth(weight, 8) > 0
    z[notch] = beside[notch]
    impassable[notch], labels[notch] = False, UNPAINTED
    wall = notch & (steepness(z) > STEEP)
    impassable[wall], labels[wall] = True, names.index(RAMP_CLIFF)
    walk = ~impassable
    zone = walk & (smooth(ramp.astype(float), 2*CLEAN) > 0)
    weight = walk.astype(float)
    smoothed = z.copy()
    for _ in range(2):
        smoothed = np.where(walk, smooth(smoothed*weight, CLEAN)/np.maximum(smooth(weight, CLEAN), 1e-9), z)
    z += (smoothed - z)*smooth(zone.astype(float), CLEAN)*walk
    np.maximum(z, 0, out=z)              # the running sums leave -1e-9 on the basin floor
    ground = np.array([not name.startswith(('Cliff', 'Rock')) for name in names])
    wall = zone & (steepness(z) > STEEP)
    impassable[wall], labels[wall] = True, names.index(RAMP_CLIFF)
    walk = ~impassable
    paintable = walk & (steepness(z) <= STEEP)
    noise = fbm(x, y, scale=90, seed=430, octaves=3)
    noise = RAGGED*noise/noise.std()
    edge = fbm(x, y, scale=80, seed=450, octaves=3) + fbm(2*CENTRE[0] - x, 2*CENTRE[1] - y, scale=80, seed=450, octaves=3)
    margin = distance_to(impassable)*10 < MARGIN[0] + MARGIN[1]*edge/edge.std()
    for cells in found:
        if len(cells) > RAMP_CELLS:
            continue
        here = labels.ravel()[cells]
        here = here[(here != UNPAINTED) & ground[np.maximum(here, 0)]]
        if not len(here):
            continue
        share = np.bincount(here, minlength=len(names))/len(here)
        mask = np.zeros(z.shape, bool)
        mask.ravel()[cells] = True
        ring = (smooth(mask.astype(float), 2*CLEAN) > 0) & ~mask & (labels != UNPAINTED)
        around = np.bincount(labels[ring], minlength=len(names))
        candidates = np.flatnonzero(share >= RAMP_SHARE)
        texture = candidates[np.argmax(around[candidates])] if len(candidates) else share.argmax()
        outline = (smooth(mask.astype(float), OUTLINE) + noise >= .5) & paintable
        labels[outline] = texture
        around[[not name.startswith('Grass') for name in names]] = 0
        around[texture] = 0
        if around.any():
            labels[outline & margin] = around.argmax()
    reach = OUTLINE
    while (labels == UNPAINTED).any():
        best, pick = np.zeros(z.shape), labels.copy()
        for k in np.unique(labels[labels != UNPAINTED]):
            if ground[k]:
                cover = smooth((labels == k).astype(float), reach)
                better = (labels == UNPAINTED) & (cover > best)
                pick[better], best[better] = k, cover[better]
        labels[(labels == UNPAINTED) & (best > 0)] = pick[(labels == UNPAINTED) & (best > 0)]
        reach *= 2
    return len(found)


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
        widen_ramp(z, labels, impassable, top, bottom, names.index(RAMP_CLIFF), is_cliff)
    cleaned = clean_ramps(z, labels, impassable, names)
    painted = labels                     # the original's painting, which the scenery follows
    names, chosen = ladders(painted, names)
    labels = soften(painted, chosen)

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
                      Ground(z, impassable, painted, names, BORDER), (sx, sy, sz), SITES, CENTRE, twin, LANE_OUTPOSTS)
    look = dict(src['look'])
    look['EnvironmentData'] = dict(look['EnvironmentData'], macro_texture_stretched=1)
    for name, value in look.items():
        sections.write(m, name, value)

    # Every site needs open ground, a way to the centre, and the same walk as its twin.
    space = open_ground(z, impassable)
    opens = [float(space[round(y/10) + BORDER, round(x/10) + BORDER]) for x, y in SITES]
    walk, _ = walk_grid(m)
    field = distance_field(walk, CENTRE)
    walks = [at(field, walk, p) for p in SITES]
    outposts = [distance_field(walk, p) for p in placed['outposts']]
    to_outpost = [min(at(f, walk, p) for f in outposts) for p in SITES]
    b.report.update(scale=dict(x=sx, y=sy, z=sz), palette=palette, placed=placed, ramps_cleaned=cleaned,
                    blends={f'{names[a]} > {names[b]}': [names[k] for k in steps] for (a, b), steps in chosen.items()},
                    sites=[
        dict(site=k, name=name, x=p[0], y=p[1], open=round(r), walk_to_centre=round(d),
             walk_to_outpost=round(o), player=STARTS.index(k) + 1 if k in STARTS else None)
        for k, (name, p, r, d, o) in enumerate(zip(SITE_NAMES, SITES, opens, walks, to_outpost), 1)])
    b.image('layout.png', plan(z, impassable, opens))
    problems = [f'site {k}: {r:.0f} units of open ground' for k, r in enumerate(opens, 1) if r < MIN_OPEN]
    problems += [f'site {k}: no way to the centre' for k, d in enumerate(walks, 1) if not math.isfinite(d)]
    problems += [f'sites {k} and {k + 8}: {walks[k - 1]:.0f} and {walks[k + 7]:.0f} to the centre'
                 for k in range(1, 9) if abs(walks[k - 1] - walks[k + 7]) > .05*min(walks[k - 1], walks[k + 7])]
    problems += [f'sites {k} and {k + 8}: {to_outpost[k - 1]:.0f} and {to_outpost[k + 7]:.0f} to an outpost'
                 for k in range(1, 9)
                 if abs(to_outpost[k - 1] - to_outpost[k + 7]) > .05*min(to_outpost[k - 1], to_outpost[k + 7])]
    if problems:
        raise ValueError('Layout: ' + '; '.join(problems))
    clouds = (f'Weather\n  CloudTextureSize = X:{CLOUD_SIZE[0]:.1f} Y:{CLOUD_SIZE[1]:.1f}\n'
              f'  CloudOffsetPerSecond = X:{CLOUD_DRIFT[0]:.5f} Y:{CLOUD_DRIFT[1]:.5f}\nEnd\n')
    b.save(m, ini=src['ini'].rstrip() + '\n\n' + clouds)
