"""Water Lab's size, bands, palette and shape helpers, shared by its stations."""
import math

import numpy as np

WIDTH, HEIGHT, BORDER = 420, 611, 30
SPAN_X, SPAN_Y = (WIDTH-1)*10, (HEIGHT-1)*10
# The stations' bands, south to north (map y): each meets the next on a ridge
# RIDGE high, which map.py blends both sides up to.
FALLS_Y = (0, 2700)
POOLS_Y = (2700, 4500)
CHANNELS_Y = (4500, SPAN_Y)
RIDGE = 480

PALETTE = ['GrassEregion01', 'GrassEregion08', 'GrassRivendell01', 'DirtRivendell03', 'SandType3wet',
           'RocksMordorPebble', 'RockEregion02', 'CliffErebor05']
GRASS, MEADOW, LUSH, MUD, SAND, GRAVEL, ROCK, CLIFF = range(len(PALETTE))


def smooth(a, b, v):
    t = np.clip((v-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def chaikin(points, rounds=4):
    for _ in range(rounds):
        out = [points[0]]
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            out += [(.75*ax+.25*bx, .75*ay+.25*by), (.25*ax+.75*bx, .25*ay+.75*by)]
        out.append(points[-1]); points = out
    return points


def length(line):
    return sum(math.dist(a, b) for a, b in zip(line, line[1:]))


def water_area(name, points, height):
    """A standing water area as the stock rivers' (map.py numbers them)."""
    return dict(name=name, layer='Water', uv_speed=.03, additive=0, bump_texture='WaterRippleBump.tga',
                sky_texture='SkyEnv.tga', shader='wtr_Riv03.W3D', depth_colors='LUTDepthTint.tga',
                water_height=height, points=points)
