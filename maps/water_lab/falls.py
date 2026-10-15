"""The south band: waterfalls, and a river stepping down in flat stretches.

Water in BFME2 is flat: a standing water area has one height, and a river
strip (the flowing surface over it) too. A river runs downhill only in steps,
each with its own water area and strip, and a waterfall object hides each
step, as the Fords of Isen do (water 364, 294 and 245, WideWaterfall01 at
the steps). A waterfall model's origin is the foot of the fall; its lip
reaches back over the upper level, LIP high at scale 1 (the Rivendell falls
about 305).

South, a cliff along y 880 above a pool (water 140):
  great falls  RivendellWaterfall02 and 01, off a cliff about 305 high
  gallery      WaterfallC01, C02, C04 and WideWaterfall01, off a cliff 72 high
Each fall is fed by a stream on the plateau above it, at its lip's height.
North of a ridge, a river flowing east:
  terraces   water 300, 230 and 160: a 70 drop at x 1000 and at 1900, each
             hidden by a WideWaterfall01 across the river
  cascade    from x 2600 on, eight steps of 8 down to water 96, each a weir
             of miniature WideWaterfall01 pieces side by side

Results, BFME2 1.06 in game at Medium: every fall draws. The Rivendell falls
slant back from their foot, so they stand out in the pool in front of the
cliff (else most of the sheet is inside the rock); falls show only from
downstream. The cascade reads best as a river running downhill.
"""
import math

import numpy as np

from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.rivers import add_river

from maps.water_lab.common import GRASS, LUSH, ROCK, SAND, SPAN_X, smooth, water_area

LIP = 72                       # a small fall's drop at scale 1
RIVER_Y, RIVER_HALF = 2050, 95
TERRACES = [(-300, 300), (1000, 230), (1900, 160)]     # (from x, water)
CASCADE = (2600, 110, 8, 8)                            # from x, step length, steps, drop per step
POOL = 140
CLIFF_Y = 880                                          # the cliff's foot
# Template, x, its stream's half-width, scale, drop at scale 1, the model's
# side that faces upstream (where its lip reaches), and how far out in front
# of the cliff's foot it stands: the Rivendell falls' sheets slant back
# (02 rises 311 over 83, 01 300 over about 180), so they stand out in the pool,
# their foot in the water and their top at the cliff's edge.
FALLS = [('RivendellWaterfall02', 650, 70, 1.0, 305, '+x', 55), ('RivendellWaterfall01', 1300, 95, 1.0, 305, '+x', 120),
         ('WaterfallC01', 1950, 80, 1.0, LIP, '+y', 5), ('WaterfallC02', 2350, 30, 1.0, LIP, '+y', 5),
         ('WaterfallC04', 2700, 18, 1.0, LIP, '+y', 5), ('WideWaterfall01', 3150, 80, 1.0, LIP, '+y', 5)]
# The local direction of each side, as an angle from the model's local +x.
SIDE = {'+x': 0., '+y': math.pi/2, '-x': math.pi, '-y': -math.pi/2}


def facing(side, direction):
    """The map angle that turns a model's `side` towards `direction` (radians, 0 east)."""
    return direction-SIDE[side]


def river_levels():
    """(x from, x to, water) for each flat stretch of the river."""
    x0, step, n, drop = CASCADE
    stretches = [(a, b, w) for (a, w), (b, _) in zip(TERRACES, TERRACES[1:]+[(x0, None)])]
    w = TERRACES[-1][1]
    for k in range(n):
        stretches.append((x0+k*step, x0+(k+1)*step if k < n-1 else SPAN_X+400, w-(k+1)*drop))
    return stretches


def terrain(x, y):
    noise = fbm(x, y, scale=300, seed=91, octaves=3)
    # South: the pool's shore and bed, then the cliff up to the two plateaus.
    z = 155+3*noise
    edge = np.minimum.reduce([y-300, CLIFF_Y-20-y, x-150, SPAN_X-150-x])
    z = np.where(edge > 0, POOL-2-18*smooth(0, 120, edge), z)
    plateau = np.where(x < 1700, POOL+305+12, POOL+LIP+12)+4*noise
    up = smooth(CLIFF_Y, CLIFF_Y+35, y)
    z = z*(1-up)+plateau*up
    # The ridge between the falls and the river.
    ridge = smooth(1300, 1400, y)*(1-smooth(1450, 1550, y))
    z = np.maximum(z, (540+60*noise)*ridge)
    # North: the river's terraces, each stretch's banks 12 above its water.
    level = np.zeros(x.shape)
    for a, b, w in river_levels():
        level = np.where((x >= a) & (x < b), w, level)
    north = smooth(1450, 1550, y)
    z = np.where(y > 1450, np.maximum(z*(1-north), (level+12+3*noise)*north), z)
    # The river's channel: banks down to the water, the bed 14 below.
    d = np.abs(y-RIVER_Y)-RIVER_HALF-6*noise
    bed = level-14*smooth(0, 40, -d)
    channel = (y > 1500) & (d < 30)
    z = np.where(channel, np.minimum(z, np.where(d < 0, bed, level+.5+11.5*smooth(0, 30, d))), z)
    # The streams on the plateaus, each down to its fall's lip.
    for template, fx, half, scale, drop, *_ in FALLS:
        w = POOL+drop*scale
        s = np.abs(x-fx)-half-4*noise
        on = (y > CLIFF_Y+20) & (y < 1290) & (s < 25)
        z = np.where(on, np.minimum(z, np.where(s < 0, w-10, w+.5+11*smooth(0, 25, s))), z)
    return dict(x=x, y=y, z=z)


def materials(t, slope):
    x, y, z = t['x'], t['y'], t['z']
    labels = np.full(z.shape, GRASS, 'u2')
    labels[slope > .35] = ROCK
    labels[(np.abs(y-RIVER_Y) < RIVER_HALF+60) & (slope <= .35)] = LUSH
    labels[(z < POOL+6) & (y < CLIFF_Y)] = SAND
    labels[(np.abs(y-RIVER_Y) < RIVER_HALF+4) & (slope <= .35)] = SAND
    return labels


def water():
    areas = [water_area('Pool', [(150, 300), (SPAN_X-150, 300), (SPAN_X-150, CLIFF_Y-5), (150, CLIFF_Y-5)], POOL)]
    for i, (a, b, w) in enumerate(river_levels()):
        areas.append(water_area(f'River {i+1}', [(a, 1600), (b, 1600), (b, 2500), (a, 2500)], w))
    for template, fx, half, scale, drop, *_ in FALLS:
        areas.append(water_area('Stream '+template, [(fx-half-30, CLIFF_Y+45), (fx+half+30, CLIFF_Y+45),
                                                     (fx+half+30, 1295), (fx-half-30, 1295)], round(POOL+drop*scale)))
    return areas


def decorate(m, ground):
    # Each flat stretch's flowing strip, 1 above its water; a stream's over each stream.
    for i, (a, bx, w) in enumerate(river_levels()):
        add_river(m, f'River {i+1}', [(max(a, -250), RIVER_Y), (min(bx, SPAN_X+250), RIVER_Y)],
                  width=2*RIVER_HALF+20, height=w+1, step=60)
    for template, fx, half, scale, drop, *_ in FALLS:
        add_river(m, 'Stream '+template, [(fx, 1280), (fx, CLIFF_Y+40)], width=2*half+16,
                  height=round(POOL+drop*scale)+1, step=60)
    west = math.pi
    # The terrace falls: across the river at each 70 step, lip upstream (west).
    for k, (a, _, w) in enumerate(river_levels()[1:3]):
        upper = TERRACES[k][1]
        add_object(m, 'WideWaterfall01', a+14, RIVER_Y, angle=facing('+y', west), layer='Falls',
                   extra=[('objectPrototypeScale', 2, round((upper-w)/LIP, 3))], z=w-ground(a+14, RIVER_Y))
    # The cascade: at each 8 drop, a weir of miniature falls across the river.
    for a, _, w in river_levels()[3:]:
        for k in range(-4, 5):
            yy = RIVER_Y+k*22
            add_object(m, 'WideWaterfall01', a+4, yy, angle=facing('+y', west), layer='Cascade',
                       extra=[('objectPrototypeScale', 2, round(8/LIP, 3))], z=w-ground(a+4, yy))
        for k in range(-3, 4):
            add_object(m, 'WaterRipples', a+30, RIVER_Y+k*28, layer='Cascade', z=w+.3-ground(a+30, RIVER_Y+k*28))
    # The south falls: at the cliff's foot on the pool, lip over the plateau (north).
    for template, fx, half, scale, drop, side, out in FALLS:
        add_object(m, template, fx, CLIFF_Y-out, angle=facing(side, math.pi/2), layer='Falls',
                   extra=[('objectPrototypeScale', 2, scale)], z=POOL-ground(fx, CLIFF_Y-out))
    for x, y, sound in [(650, 700, 'Amb_WaterfallMoria'), (1300, 700, 'Amb_WaterfallMoria'), (2500, 700, 'Amb_WaterRiver1Loop'),
                        (1000, RIVER_Y, 'Amb_WaterRiver1Loop'), (1900, RIVER_Y, 'Amb_WaterRiver1Loop'),
                        (3000, RIVER_Y, 'Amb_WaterRiver1Loop')]:
        add_object(m, sound, x, y, layer='Sounds')
