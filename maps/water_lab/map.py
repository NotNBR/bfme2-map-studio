"""Water Lab: what water can do in BFME2, every test on one map.

Water in BFME2 is flat: a standing water area has one height, and a river
strip too. The lab's three bands, south to north, show the ways water can
still run downhill, and what does not work (docs/research/water.md):

  falls.py     y 0..2700     waterfalls off cliffs into a pool, and a river
                             stepping down terraces and a cascade of weirs
  pools.py     y 2700..4500  a river descending as pools and rapids
  channels.py  y 4500..6100  channels down a slope: a river strip and roads
                             (neither works), and particle streams in
                             several looks and at several gradients

Each band is built on its own rows; where two meet, both rise to a ridge.
Each module's docstring holds its layout and its result in the game.
"""
import numpy as np

from mapworkshop.formats.water import standing_water
from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.cliffs import steep_cells
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

from maps.water_lab import channels, falls, pools
from maps.water_lab.common import (BORDER, CHANNELS_Y, CLIFF, FALLS_Y, HEIGHT, PALETTE, POOLS_Y, RIDGE, SPAN_Y, WIDTH,
                                   smooth)

BANDS = [(falls, FALLS_Y), (pools, POOLS_Y), (channels, CHANNELS_Y)]
EASE = 150                     # how far before a shared edge a band rises to the ridge


def terrain():
    """Each band's terrain on its own rows, eased up to RIDGE at the edges it
    shares with another, so they meet without a seam."""
    rows, cols = HEIGHT+2*BORDER, WIDTH+2*BORDER
    y, x = (np.mgrid[0:rows, 0:cols]-BORDER)*10.0
    z = np.zeros(x.shape)
    parts = []
    for module, (y0, y1) in BANDS:
        lo = -np.inf if y0 == 0 else y0
        hi = np.inf if y1 == SPAN_Y else y1
        rows_in = (y[:, 0] >= lo) & (y[:, 0] < hi)
        t = module.terrain(x[rows_in], y[rows_in])
        ease = np.zeros(t['z'].shape)
        if y0 > 0:
            ease = np.maximum(ease, smooth(y0+EASE, y0, t['y']))
        if y1 < SPAN_Y:
            ease = np.maximum(ease, smooth(y1-EASE, y1, t['y']))
        t['z'] = t['z']*(1-ease)+RIDGE*ease
        z[rows_in] = t['z']
        parts.append((module, rows_in, t))
    return x, y, z, parts


def build(b):
    x, y, z, parts = terrain()
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    set_heights(m, z)
    gy, gx = np.gradient(z, 10); slope = np.hypot(gx, gy)
    labels = np.zeros(z.shape, 'u2')
    for module, rows_in, t in parts:
        labels[rows_in] = module.materials(t, slope[rows_in])
    cliffs = steep_cells(z, 1.0)
    labels[cliffs] = CLIFF
    set_materials(m, PALETTE, labels, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True, cliffs=cliffs)

    t_pools = next(t for module, _, t in parts if module is pools)
    areas = falls.water()+pools.water(t_pools)
    m.chunk('StandingWaterAreas').data = standing_water([dict(id=i+1, **a) for i, a in enumerate(areas)])

    def ground(px, py):
        return float(z[min(max(round(py/10)+BORDER, 0), z.shape[0]-1), min(max(round(px/10)+BORDER, 0), z.shape[1]-1)])
    falls.decorate(m, ground)
    pools.decorate(m, t_pools, ground)
    channels.decorate(m, ground)
    starts(m, [(250, 150), (falls.SPAN_X-250, 150)])
    add_sky(m, b.project.weather, WIDTH*10, HEIGHT*10, BORDER*10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather)
           + f'WaterTransparency\n  ReflectionPlaneZ = {falls.POOL}\n  ReflectionOn = Yes\nEnd\n\n' + channels.ini())
    print(f'{len(areas)} water areas, {len(channels.streams())} particle streams')
