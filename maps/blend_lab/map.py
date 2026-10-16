"""Blend Lab: how can a change of terrain texture be made wider and softer
than the game's one-cell blend?

BFME2 blends two textures inside one 10-unit cell, through a fixed set of
64x64 alpha ramps, with at most three textures a cell and no ramp covering a
whole cell (docs/game/terrain-textures.md#blends): any transition wider than
a cell has to be built from whole cells. On a map scaled up from a small one
(Nanduhirion v1) the painted patches grow but the blend does not, so their
edges read as outlines. This lab sets sixteen ways of building a wider
transition side by side on flat ground, on the same pair: v1's dark grass
(GrassErebor08) round a disc of its pale path dirt (DirtAmon_Hen01), 900
across.

The in-between textures are the game's grass textures closest in colour to
points along the way from the grass to the dirt (mean colour, measured from
the texture files), a ladder of four, darkest first: GrassAmon_Hen06 (0.23
of the way), GrassAmon_Hen03 (0.41), GrassAmon_Hen04 (0.63) and
GrassAnfalas01 (0.81). The palette runs from the grass up the ladder to the
dirt: the writer blends the later texture over the earlier.

Panels (PANELS), rows north to south, each west to east. Rows 1 and 2, eight
ways:
  1 baseline        a clean circle, the toolkit's one-cell corner blends
  2 ragged          the circle's edge displaced by noise, up to about 60
  3 v1              v1's mixing: each side's coverage blurred over 3 cells,
                    plus its own noise (MIX 0.45), the higher wins
  4 wide dither     the dirt's share falls from 1 to 0 over 200 units, by cell
  5 clumped dither  the same, in clumps about 50 units across
  6 one between     a 120-unit band of Hen03, slightly ragged
  7 two between     Hen04 then Hen03, 90 units each
  8 graded dither   grass, Hen03, Hen04 and dirt dithered over 240 units, in
                    clumps
Rows 3 and 4, plain bands (BANDS) of the ladder, slightly ragged, varying how
many and how wide (the width of each band, then the whole transition):
   9 one band 60 (60)            10 one band 200 (200): Hen03
  11 two bands 50 (100)          12 two bands 150 (300): Hen03, Hen04
  13 three bands 40 (120)        14 three bands 120 (360): Hen06, Hen03, Hen04
  15 four bands 30 (120)         16 four bands 90 (360): the whole ladder

Renders: `mw render --map blend-lab --out local/renders/blend-lab --views
maps/blend_lab/views.json` (a top view and a game-height view of each).
In the game: `mw capture blend-lab --shot N X Y 300` at a panel's centre.
The light is v1's, Nanduhirion's own (SUN, FILL, OVERBRIGHT): a warm sun
from the south-west on terrain lit twice as bright, so the panels look as
they would on v1.

Answer for panels 1-8 (the renderer at Medium, 16 October 2026, under the
clear preset's light and again under v1's; not yet checked in the game):
mixing the two textures alone (3, 4, 5) leaves an
outline or turns speckled, since every mixed cell still carries the full
contrast, and 5's clumps read as camouflage; a ragged edge (2) only changes
the outline's shape. In-between textures make the change gradual: one band
(6) halves each step, two (7) leave no visible edge at playing distance,
though their rings show from above, and dithering through them (8) is as soft
without the rings. A high-contrast boundary is softened by textures of
intermediate tone, best dithered; mixing alone cannot.

Answer for panels 9-16 (the same): one band (9, 10) shows as a ring of its
own, at any width. Two or three narrow bands (11, 13: 100 and 120 across)
give the smoothest compact change, three the smoother; wide bands (12, 14:
300 and 360) fade softly over a broad, hazy halo, for wide natural
transitions. Four bands (15, 16) break down on GrassAnfalas01: its mean
colour fits the ladder, but its dark tufts make a spotted ring. An
in-between texture has to match the pair in pattern as well as in colour;
the Amon Hen grasses, one family, do.
"""
import numpy as np

from mapworkshop.formats.lighting import decode, encode
from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

WIDTH, HEIGHT, BORDER = 630, 630, 30     # cells: 6,300 x 6,300 units
GROUND = 100.0
PALETTE = ['GrassErebor08', 'GrassAmon_Hen06', 'GrassAmon_Hen03', 'GrassAmon_Hen04', 'GrassAnfalas01',
           'DirtAmon_Hen01']
GRASS, HEN06, HEN03, HEN04, ANFALAS, DIRT = range(6)
RADIUS = 450                             # the dirt disc
HALF = 700                               # each panel reaches this far from its centre
PANELS = [(900 + 1500*c, 5400 - 1500*r) for r in range(4) for c in range(4)]
NAMES = ['baseline', 'ragged', 'v1', 'wide dither', 'clumped dither', 'one between', 'two between',
         'graded dither', 'one band 60', 'one band 200', 'two bands 50', 'two bands 150',
         'three bands 40', 'three bands 120', 'four bands 30', 'four bands 90']
# Panels 9-16: the band textures from the grass side to the dirt side, and
# the width of each band.
LADDERS = {1: [HEN03], 2: [HEN03, HEN04], 3: [HEN06, HEN03, HEN04], 4: [HEN06, HEN03, HEN04, ANFALAS]}
BANDS = [(1, 60), (1, 200), (2, 50), (2, 150), (3, 40), (3, 120), (4, 30), (4, 90)]
SEED = 707
# Nanduhirion's light, as v1 copies it: its sun and object fill, and overbright terrain.
SUN = dict(ambient=(.051, .051, .051), diffuse=(.686, .588, .510), direction=(.365, .686, -.629))
FILL = dict(ambient=(0., 0., 0.), diffuse=(.118, .196, .118), direction=(-.871, -.352, -.342))
OVERBRIGHT = 2.0


def blur(a, r):
    """`a` averaged over the (2r+1) x (2r+1) cells around each (edges repeated)."""
    n = 2*r + 1
    c = np.pad(np.cumsum(np.cumsum(np.pad(a, r, mode='edge'), 0), 1), ((1, 0), (1, 0)))
    return (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n])/(n*n)


def unit(a):
    """`a` shifted and scaled to mean 0 and spread 1."""
    return (a - a.mean())/a.std()


def uniform(a):
    """`a`'s ranks, as values evenly spread over 0..1."""
    out = np.empty(a.size)
    out[np.argsort(a, axis=None)] = (np.arange(a.size) + .5)/a.size
    return out.reshape(a.shape)


def bands(e, ladder, width):
    """Dirt inside, grass outside and the ladder's textures between, each
    `width` wide, the transition centred on the edge (e = 0)."""
    total = len(ladder)*width
    step = np.clip(np.floor((e + total/2)/width), -1, len(ladder)).astype(int)
    order = np.array([DIRT] + ladder[::-1] + [GRASS])      # dirt side first
    return order[step + 1]


def approaches(d, noise):
    """The labels of each panel's approach, from `d`, the signed distance to
    the disc's edge (negative on the dirt)."""
    wobble, white, clumps, own = noise
    e = d + 15*wobble                    # a slightly ragged edge for the bands
    cover = blur((d < 0).astype(float), 3)
    reach = lambda c, n: np.where(c >= .02, c + .45*n, -np.inf)
    t = np.clip(.5 - e/240, 0, 1)
    level = np.clip(np.floor(t*3 + clumps), 0, 3).astype(int)
    return [
        np.where(d < 0, DIRT, GRASS),
        np.where(d + 30*wobble < 0, DIRT, GRASS),
        np.where(reach(cover, own[1]) > reach(1 - cover, own[0]), DIRT, GRASS),
        np.where(white < np.clip(.5 - d/200, 0, 1), DIRT, GRASS),
        np.where(clumps < np.clip(.5 - d/200, 0, 1), DIRT, GRASS),
        bands(e, [HEN03], 120),
        bands(e, [HEN03, HEN04], 90),
        np.array([GRASS, HEN03, HEN04, DIRT])[level],
    ] + [bands(e, LADDERS[n], width) for n, width in BANDS]


def plan(labels):
    """The labels, north up, with each panel's number and name."""
    from PIL import Image, ImageDraw, ImageFont
    colours = np.array([(70, 80, 35), (90, 92, 45), (110, 105, 60), (150, 135, 95), (175, 160, 120),
                        (200, 185, 150)], np.uint8)
    image = Image.fromarray(colours[labels[BORDER:-BORDER, BORDER:-BORDER][::-1]]).resize((WIDTH*2, HEIGHT*2))
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(16)
    for k, ((cx, cy), name) in enumerate(zip(PANELS, NAMES), 1):
        draw.text((cx/5, (HEIGHT*10 - cy - HALF + 40)/5), f'{k} {name}', fill=(255, 255, 255), font=font, anchor='mm')
    return image


def build(b):
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    rows, cols = HEIGHT + 2*BORDER, WIDTH + 2*BORDER
    y, x = (np.mgrid[0:rows, 0:cols] - BORDER + .5)*10.0     # cell centres
    set_heights(m, np.full((rows, cols), GROUND))

    rng = np.random.default_rng(SEED)
    noise = (unit(fbm(x, y, scale=120, seed=SEED, octaves=3)), rng.random(x.shape),
             uniform(blur(rng.standard_normal(x.shape), 2)),
             [unit(blur(rng.standard_normal(x.shape), 1)) for _ in range(2)])
    labels = np.full(x.shape, GRASS)
    for (cx, cy), made in zip(PANELS, range(len(PANELS))):
        panel = (np.abs(x - cx) < HALF) & (np.abs(y - cy) < HALF)
        d = np.hypot(x - cx, y - cy) - RADIUS
        labels[panel] = approaches(d, noise)[made][panel]
    set_materials(m, PALETTE, labels, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    b.image('layout.png', plan(labels))

    starts(m, [(150, HEIGHT*5), (WIDTH*10 - 150, HEIGHT*5)])
    add_sky(m, b.project.weather, WIDTH*10, HEIGHT*10, BORDER*10)
    apply_weather(m, b.project.weather, sun=SUN, fill=FILL)
    chunk = m.chunk('GlobalLighting')
    chunk.data = encode(dict(decode(chunk.data, chunk.version), overbright_value=OVERBRIGHT), chunk.version)
    b.save(m, ini=ini_block(b.project.weather))
