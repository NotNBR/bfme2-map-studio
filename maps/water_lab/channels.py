"""The north band: channels down a slope, for water on sloping ground.

Eleven channels side by side, west to east, each falling south from its head
(water HEAD at TOP_Y) at its own gradient, then ending in a bowl:

  Strip        a river strip (RiverAreas) at HEAD over a channel falling 10%.
               Result: drawn flat at its height, floating over the low end.
  Water road   a road of a map-local Road type with a water texture, 10%
  Stock road   the stock road type WagonTraveled, the control.
               Result: neither road drew (nor did anything change in Fords
               of Isen II with its road objects removed), unlike an earlier
               capture of DaleRoad01 roads.
  Particle streams, each a different look or gradient (STREAMS):
  Plain        one layer of river water and foam, 6%: square sprite edges
  Shaded       a MULTIPLY shade under the water, the soft edge over it:
               too dark, every overlapping sprite darkens again
  Over         the soft edge over the water: smooth banks, pale water
  Soft         the soft edge under the water and glints: the best, at 6%,
  Soft 2..20   and at 2, 12 and 20% (at 20% the flat sprites step and break up)
  Steep        the Hollin Dales torrent's look at 45%: smaller flat sprites,
               upright soft white water

A particle stream (docs/research/water.md#particle-water): its course is cut
into equal straight segments; at the top of each, a carrier object turned
down the segment carries the stream's effects, each emitting along a line
from the segment's top to its foot, so the water slopes. A carrier is a stock
object this map places nowhere else, changed in map.ini to draw the
invisible haze model with the effects on its bone; each stream needs its own
(CARRIERS), because the effects' slope and segment are fixed.
"""
import math

import numpy as np

from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.lines import polyline_distance
from mapworkshop.mapkit.rivers import add_river, point_along

from maps.water_lab.common import GRASS, GRAVEL, LUSH, MEADOW, MUD, ROCK, length, smooth

SEED = 4411
TOP_Y = 5850                   # every channel's head
HEAD = 400                     # its water there
SPACING, FIRST_X = 380, 190    # the channels' x
# Name, kind, gradient, and for a stream its look; for the water road, its texture.
CHANNELS = [('Strip', 'strip', .10, None), ('Water road', 'road', .10, 'TWWater01.tga'),
            ('Stock road', 'road', .10, None),
            ('Plain', 'stream', .06, 'plain'), ('Shaded', 'stream', .06, 'shaded'), ('Over', 'stream', .06, 'over'),
            ('Soft', 'stream', .06, 'soft'), ('Soft 2', 'stream', .02, 'soft'), ('Soft 12', 'stream', .12, 'soft'),
            ('Soft 20', 'stream', .20, 'soft'), ('Steep', 'stream', .45, 'steep')]
# Stock props alike (one draw module, ModuleTag_Draw, nothing else to do or
# sound); not WaterRippleSpawn*, which the toolkit's renderer skips.
CARRIERS = ['LakeRipple', 'WtrflHaze', 'WtrflSteam', 'LakeCoast01', 'LakeCoast02', 'LakeCoast03',
            'AtmoClouds', 'BigDustCloud']
WATER_ROAD = 'LabWaterRoad'


def steep(g):
    return g > .3


def segment(g):
    """A stream's segment length: shorter on steep ground."""
    return 80 if steep(g) else 160


def course(k):
    """Channel k's line from its head south, meandering a little."""
    name, kind, g, _ = CHANNELS[k]
    cx, run = FIRST_X+k*SPACING, 550 if steep(g) else 1100
    swing = 20 if steep(g) else 45
    return [(cx+swing*math.sin(2*math.pi*i*20/700), TOP_Y-i*20) for i in range(run//20+1)]


def run(k):
    """How far along channel k its water falls: whole segments of a stream."""
    g, line = CHANNELS[k][2], course(k)
    if CHANNELS[k][1] != 'stream':
        return length(line)
    return int(length(line)//segment(g))*segment(g)


def terrain(x, y):
    """Each channel carves a valley falling with its water; where two
    valleys meet they leave a ridge."""
    noise = fbm(x, y, scale=250, seed=SEED+1, octaves=3)
    z = np.full(x.shape, np.inf); near = np.full(x.shape, np.inf); roads = np.full(x.shape, np.inf)
    for k, (name, kind, g, look) in enumerate(CHANNELS):
        d, s = polyline_distance(course(k), x, y)
        water = HEAD-g*np.minimum(s, run(k))
        half = (28 if steep(g) else 40)+6*noise
        # The bed a little under the water, deeper on steep ground, where
        # the flat water sprites tilt away from the slope.
        bed = water-2.5-(10*g if steep(g) else 0)-3*(1-np.clip(d/half, 0, 1))
        bank = water-2.5+8.5*smooth(half, half+40, d)+.5*np.maximum(d-half-40, 0)*(1+.3*noise)
        z = np.minimum(z, np.where(d < half, bed, bank))
        near = np.minimum(near, d-half)
        if kind == 'road':
            roads = np.minimum(roads, d-half)
    return dict(x=x, y=y, z=z, near=near, roads=roads)


def materials(t, slope):
    near = t['near']
    fine = fbm(t['x'], t['y'], scale=80, seed=SEED+2, octaves=2)
    labels = np.full(near.shape, GRASS, 'u2')
    labels[fbm(t['x']+700, t['y'], scale=500, seed=SEED+3, octaves=3) > .1] = MEADOW
    labels[near < 90+30*fine] = LUSH
    labels[near < 18+6*fine] = MUD
    labels[near < 0] = GRAVEL
    labels[slope > .5] = ROCK
    # The road channels plain grass, so that a road drawn there shows.
    labels[t['roads'] < 90] = GRASS
    return labels


def system(name, g, texture, size, count, life, speed, alpha, colors, z, shader='ALPHA', sort=0, spin=.01,
           flat=True, grow='', fade=(12, 15), delay='0 0'):
    """One layer: sprites emitted along the segment from its top to its foot,
    drifting downstream along the slope; alpha fades in by `fade[0]` and out
    over the last `fade[1]` frames of the shortest life."""
    seg = segment(g)
    return (f'FXParticleSystem {name}\n  System\n    Priority = ALWAYS_RENDER\n    Shader = {shader}\n'
            f'    ParticleName = {texture}\n    Lifetime = {life[0]} {life[1]}\n    Size = {size[0]} {size[1]}\n'
            f'    SortLevel = {sort}\n    BurstDelay = {delay}\n    BurstCount = {count[0]} {count[1]}\n'
            f'    IsGroundAligned = {"Yes" if flat else "No"}\n  End\n'
            f'  Color = DefaultColor\n    Color1 = {colors[0]} 0\n    Color2 = {colors[1]} {life[0]}\n  End\n'
            f'  Alpha = DefaultAlpha\n    Alpha1 = 0 0 0\n    Alpha2 = {alpha} {alpha} {fade[0]}\n'
            f'    Alpha3 = {alpha} {alpha} {life[0]-fade[1]}\n    Alpha4 = 0 0 {life[1]}\n  End\n'
            f'  Update = DefaultUpdate\n    AngleZ = -3 3\n    AngularRateZ = -{spin} {spin}\n    AngularDamping = 1 1\n'
            f'{grow}  End\n  Physics = DefaultPhysics\n    VelocityDamping = 1 1\n  End\n'
            f'  EmissionVelocity = OrthoEmissionVelocity\n    X = {speed[0]:g} {speed[1]:g}\n    Y = -0.15 0.15\n'
            f'    Z = {-g*speed[1]:.3f} {-g*speed[0]:.3f}\n  End\n'
            f'  EmissionVolume = LineEmissionVolume\n    StartPoint = X:-10 Y:0 Z:{z}\n'
            f'    EndPoint = X:{seg+10} Y:0 Z:{z-(seg+20)*g:.2f}\n  End\n  Draw = DefaultDraw\n  End\nEnd\n\n')


RIVER_WATER = ('R:200 G:210 B:210', 'R:180 G:195 B:200')
WHITE = ('R:235 G:242 B:245', 'R:210 G:220 B:225')
GLINT = ('R:160 G:180 B:190', 'R:60 G:70 B:80')


def layers(look, g):
    """(layer name, system arguments) of a look at gradient g:

      Water  ALPHA, TWWater01, the game's river water (opaque, square)
      Edge   ALPHA, EXWaterPuddle (ragged transparent edges): a soft margin,
             dark blue under the water or pale over it
      Shade  MULTIPLY, ShadowI (white round a soft grey blob)
      Foam   ALPHA, white water lying on it
      White  ALPHA, upright (camera-facing) soft white water, for steep ground
      Glint  ADDITIVE, EXHPWaterTwinkel (bright on black): sparkles"""
    foam = ('Foam', dict(texture='EXWaterfallB.tga', size=(18, 30), count=(1, 1), life=(30, 45), speed=(2.0, 3.0),
                         alpha=.35, colors=WHITE, z=2.2, sort=3))
    glint = ('Glint', dict(texture='EXHPWaterTwinkel.tga', size=(14, 24), count=(1, 1), life=(20, 35), speed=(1.5, 2.5),
                           alpha=.6, colors=GLINT, z=2.6, shader='ADDITIVE', sort=4, spin=.05))
    water = ('Water', dict(texture='TWWater01.tga', size=(45, 55), count=(3, 3), life=(50, 70), speed=(1.0, 1.6),
                           alpha=.85, colors=RIVER_WATER, z=1.5, sort=1))
    over = ('Edge', dict(texture='EXWaterPuddle.tga', size=(80, 100), count=(2, 2), life=(50, 70), speed=(1.0, 1.6),
                         alpha=.7, colors=('R:150 G:175 B:185', 'R:130 G:160 B:175'), z=1.8, sort=2))
    under = ('Edge', dict(texture='EXWaterPuddle.tga', size=(80, 100), count=(2, 2), life=(50, 70), speed=(1.0, 1.6),
                          alpha=.75, colors=('R:70 G:115 B:150', 'R:60 G:100 B:135'), z=1.0, sort=0))
    if look == 'plain':
        return [('Water', dict(texture='TWWater01.tga', size=(60, 80), count=(2, 3), life=(50, 70), speed=(1.0, 1.6),
                               alpha=.8, colors=RIVER_WATER, z=1.5)),
                ('Foam', dict(texture='PCAWhiteWater.tga', size=(25, 45), count=(1, 1), life=(35, 50), speed=(2.0, 3.0),
                              alpha=.5, colors=('R:230 G:240 B:240', 'R:200 G:215 B:220'), z=2.2))]
    if look == 'shaded':
        # Few large, slow sprites at a nearly white tint, since MULTIPLY compounds.
        shade = ('Shade', dict(texture='ShadowI.tga', size=(170, 200), count=(1, 1), life=(160, 200), speed=(.2, .4),
                               alpha=1, colors=('R:238 G:242 B:240', 'R:238 G:242 B:240'), z=.6, shader='MULTIPLY',
                               delay='25 35'))
        return [shade, water, over, foam, glint]
    if look == 'over':
        return [water, over, foam, glint]
    if look == 'soft':
        return [water, under, foam, glint]
    # 'steep': smaller flat sprites (each tilts less far from the slope),
    # more of them, faster; streaky foam, and upright white water.
    k = 1-.45*(g-.22)/.78
    flat = lambda w, h: (round(w*k), round(h*k))
    many = lambda a, b: (round(a/k), round(b/k))
    fast = lambda a, b: (round(a*(1+g), 2), round(b*(1+g), 2))
    keys = dict(fade=(8, 10))
    grow = '    SizeRate = 0.3 0.6\n    SizeRateDamping = 0.97 0.97\n'
    return [('Edge', dict(texture='EXWaterPuddle.tga', size=flat(46, 56), count=many(2, 2), life=(40, 55), speed=fast(1.0, 1.6),
                          alpha=.75, colors=('R:70 G:115 B:150', 'R:60 G:100 B:135'), z=1.0, sort=0, spin=.02, **keys)),
            ('Water', dict(texture='TWWater01.tga', size=flat(28, 34), count=many(3, 3), life=(40, 55), speed=fast(1.0, 1.6),
                           alpha=.85, colors=RIVER_WATER, z=1.5, sort=1, spin=.02, **keys)),
            ('Foam', dict(texture='EXwaterpuddle2.tga', size=flat(20, 30), count=many(1, 1), life=(25, 40), speed=fast(2.0, 3.0),
                          alpha=.5, colors=WHITE, z=2.2, sort=3, spin=.02, **keys)),
            ('White', dict(texture='EXWaterPuddle.tga', size=(14, 24), count=(1, 2), life=(20, 30), speed=fast(2.5, 4.0),
                           alpha=round(.25+.5*(g-.22)/.78, 2), colors=('R:245 G:250 B:252', 'R:225 G:235 B:240'), z=6,
                           sort=5, spin=.02, flat=False, grow=grow, **keys)),
            ('Glint', dict(texture='EXHPWaterTwinkel.tga', size=flat(12, 20), count=(1, 1), life=(20, 35), speed=fast(1.5, 2.5),
                           alpha=.6, colors=GLINT, z=2.6, shader='ADDITIVE', sort=4, spin=.05, **keys))]


def streams():
    """(channel index, carrier, effect names) of each particle stream."""
    out = []
    for k, (name, kind, g, look) in enumerate(CHANNELS):
        if kind == 'stream':
            tag = 'MW' + name.replace(' ', '')
            out.append((k, CARRIERS[len(out)], [tag+layer for layer, _ in layers(look, g)]))
    return out


def ini():
    """map.ini: the streams' effects and carriers, and the water road's type."""
    text = ''
    for k, carrier, names in streams():
        g, look = CHANNELS[k][2], CHANNELS[k][3]
        text += ''.join(system(n, g, **args) for n, (_, args) in zip(names, layers(look, g)))
        text += (f'Object {carrier}\n  ReplaceModule ModuleTag_Draw\n    Draw = W3DScriptedModelDraw ModuleTag_DrawMW\n'
                 '      DefaultModelConditionState\n        Model = P_WtrflHaze\n'
                 + ''.join(f'        ParticleSysBone = HazeBone {n}\n' for n in names)
                 + '      End\n    End\n  End\nEnd\n\n')
    texture = next(look for _, kind, _, look in CHANNELS if kind == 'road' and look)
    return text + f'Road {WATER_ROAD}\n  Texture = {texture}\n  RoadWidth = 130\n  RoadWidthInTexture = 1.0\nEnd\n\n'


def road(m, template, line, step=100):
    """A road along `line` as a chain of short segments, written as the stock
    maps write theirs (80 long at the median, 954 at most), every standard
    property on each end point."""
    base = [('objectInitialHealth', 1, 100), ('objectEnabled', 0, 1), ('objectIndestructible', 0, 0),
            ('objectUnsellable', 0, 0), ('objectPowered', 0, 1), ('objectRecruitableAI', 0, 1),
            ('objectTargetable', 0, 0), ('exportWithScript', 0, 0), ('originalOwner', 3, '/team')]
    points = [point_along(line, s) for s in np.arange(0, length(line)+1, step)]
    for k, (a, c) in enumerate(zip(points, points[1:])):
        for (px, py), flag, end in ((a, 2, 'a'), (c, 4, 'b')):
            o = dict(template=template, x=float(px), y=float(py), z=0., angle=0., flags=flag,
                     properties=base+[('uniqueID', 3, f'{template} {k}{end}'), ('objectLayer', 3, 'Roads')])
            m.chunk('ObjectsList').data += m.encode_object(o).encode()


def decorate(m, ground):
    for k, (name, kind, g, look) in enumerate(CHANNELS):
        line = course(k)
        if kind == 'strip':
            add_river(m, 'Strip on a slope', line, width=150, height=HEAD, step=60, look='water')
        elif kind == 'road':
            road(m, WATER_ROAD if look else 'WagonTraveled', line)
    for k, carrier, _ in streams():
        g, line = CHANNELS[k][2], course(k)
        seg = segment(g)
        for i in range(int(run(k)//seg)):
            (ax, ay), (bx, by) = point_along(line, i*seg), point_along(line, (i+1)*seg)
            add_object(m, carrier, ax, ay, angle=math.atan2(by-ay, bx-ax), layer='Streams',
                       z=HEAD-g*i*seg-ground(ax, ay))
        mx, my = point_along(line, run(k)/2)
        add_object(m, 'Amb_WaterCreek2Loop', mx, my, layer='Sounds')
