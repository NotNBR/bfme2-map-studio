"""The middle band: a river that flows downhill and looks it, with flat water.

The river descends as real mountain streams do, in pools and riffles:

  pools    flat stretches, each with its own water area and strip at its
           own height, as long as the valley's fall allows
  lips     at each pool's downstream end the bed rises into a low rocky lip
           LIP above the water, across the whole channel: the pool's water
           area and strip end on it, so no straight water edge shows
  rapids   below the lip the bed falls to the next pool over a face: long
           and gentle for a small drop (a riffle, foam and stones), short
           and steep for a big one (a chute, small falls across it)

The valley floor and the banks follow the water down continuously; only
the water steps. The river meanders, its width swells and narrows, each
pool's water area is drawn round its own stretch of the river.

Result, BFME2 1.06 in game at Medium: a river that visibly descends, with no
water edges showing, as long as the banks stand above each pool up to its
lip (where they dipped, the pool's water showed as a straight-edged slab).
"""
import math
import random

import numpy as np

from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.lines import polyline_distance
from mapworkshop.mapkit.rivers import add_river, point_along

from maps.water_lab.common import (GRASS, GRAVEL, LUSH, MEADOW, MUD, POOLS_Y, ROCK, SAND, SPAN_X, chaikin, length,
                                   smooth, water_area)

SEED = 7301
TOP, BOTTOM = 290, 150         # the water at the river's head and foot
LIP = 1.5                      # a lip's crest above its pool
MIDDLE = sum(POOLS_Y)/2        # the valley's middle line (map y)
SWING = 220                    # how far the river meanders from it


def course():
    """The river's line, west (its head) to east, meandering down the valley."""
    rng = random.Random(SEED)
    points, y = [], MIDDLE
    for x in np.linspace(-300, SPAN_X+300, 16):
        y = .5*y+.5*(MIDDLE+rng.uniform(-SWING, SWING))
        points.append((float(x), y))
    return chaikin(points)


def pools(total):
    """The pools along the river: (start, crest, face, water) in distance
    along it. A pool runs from `start` to the crest of its lip; its rapid
    falls over `face` beyond the crest to the next pool's water."""
    rng = random.Random(SEED+1)
    stretches, s = [], 0.
    while s < total:
        stretches.append([s, min(s+rng.uniform(240, 460), total+400)])
        s = stretches[-1][1]
    drops = [rng.uniform(4, 16) for _ in stretches[:-1]]
    scale = (TOP-BOTTOM)/sum(drops)
    out, w = [], TOP
    for k, (a, c) in enumerate(stretches):
        drop = drops[k]*scale if k < len(drops) else 0
        face = 20+60*(1-smooth(6, 14, drop)) if drop else 0      # gentle riffles for small drops, chutes for big
        out.append(dict(start=a, crest=c, face=face, water=round(w), drop=drop))
        w -= drop
    for k in range(1, len(out)):
        out[k]['start'] = out[k-1]['crest']                        # each pool's water starts on the lip above it
    return out


def terrain(x, y):
    rows, cols = x.shape
    line = course()
    total = length(line)
    d, s = polyline_distance(line, x, y)
    stretch = pools(total)
    noise = fbm(x, y, scale=200, seed=SEED+2, octaves=3)
    # The water's level along the river, stepping at each lip, and the same
    # eased across each rapid for the banks and the valley floor.
    water = np.zeros(x.shape); eased = np.zeros(x.shape)
    for k, p in enumerate(stretch):
        inside = (s >= p['start']) & (s < p['crest']+(p['face'] if k < len(stretch)-1 else 1e9))
        water = np.where(inside & (s < p['crest']), p['water'], water)
        eased = np.where(inside, p['water'], eased)
        if k < len(stretch)-1:
            on = (s >= p['crest']) & (s < p['crest']+p['face'])
            f = smooth(p['crest'], p['crest']+p['face'], s)
            low = stretch[k+1]['water']
            water = np.where(on, low, water)
            eased = np.where(on, p['water']+(low-p['water'])*f, eased)
    # Ease the banks' level over a longer reach, so the valley slopes smoothly.
    flat = eased.copy()
    for r in (8, 8):
        c = np.cumsum(np.cumsum(np.pad(flat, r+1, mode='edge'), 0), 1); n = 2*r+1
        flat = (c[n:, n:]-c[:-n, n:]-c[n:, :-n]+c[:-n, :-n])[:rows, :cols]/(n*n)
    # Never below the pool's own water up to its lip: the step in the banks
    # comes on the rapid, where the water steps too.
    near = 1-smooth(140, 320, d)
    flat = flat+(np.maximum(flat, water)-flat)*near
    half = 70+18*fbm(s, np.zeros_like(s), scale=500, seed=SEED+3, octaves=2)
    edge = d-half-6*noise
    # The valley: banks a few above the water, the floor rising gently to
    # hills on either side.
    valley = flat+3+9*smooth(0, 160, edge)+40*smooth(300, 900, edge)+120*smooth(800, 1400, edge)+6*noise
    # The bed: a pool's bed drops to 8 to 12 below its water across the
    # channel; towards its crest it rises to the lip; on a rapid's face it
    # falls from the lip to the next pool, broken with stones.
    across = np.clip(1-(np.maximum(d, 0)/np.maximum(half, 1))**2, 0, 1)
    bed = water-(8+4*smooth(-.3, .3, noise))*across
    for k, p in enumerate(stretch[:-1]):
        rise = smooth(p['crest']-45, p['crest'], s)*(s < p['crest'])
        bed = np.where((s >= p['start']) & (s < p['crest']), bed*(1-rise)+(p['water']+LIP)*rise, bed)
        on = (s >= p['crest']) & (s < p['crest']+p['face'])
        f = smooth(p['crest'], p['crest']+p['face'], s)
        low = stretch[k+1]['water']
        face = p['water']+LIP+(low-1.5-p['water']-LIP)*f+1.2*noise*(1-np.abs(2*f-1))
        bed = np.where(on, face, bed)
        sink = smooth(p['crest']+p['face'], p['crest']+p['face']+45, s)*(s >= p['crest']+p['face'])
        nxt = (s >= p['crest']+p['face']) & (s < stretch[k+1]['crest']-45)
        bed = np.where(nxt, (low-1.5)*(1-sink)+bed*sink, bed)
    z = np.where(edge < 0, np.minimum(bed, valley), valley)
    bank = smooth(-6, 22, edge)
    z = np.where((edge > -6) & (edge < 22), np.minimum(bed, valley)*(1-bank)+valley*bank, z)
    return dict(x=x, y=y, z=z, d=d, s=s, edge=edge, half=half, line=line, pools=stretch, total=total)


def materials(t, slope):
    z, edge, s = t['z'], t['edge'], t['s']
    fine = fbm(t['x'], t['y'], scale=80, seed=SEED+5, octaves=2)
    labels = np.full(z.shape, GRASS, 'u2')
    labels[fbm(t['x']+900, t['y'], scale=500, seed=SEED+6, octaves=3) > .1] = MEADOW
    labels[(edge < 90+40*fine) & (edge > 10)] = LUSH
    labels[(edge <= 12+5*fine) & (edge > -4)] = MUD
    labels[edge <= -4] = SAND
    on_rapid = np.zeros(z.shape, bool)
    for p in t['pools'][:-1]:
        on_rapid |= (s > p['crest']-50) & (s < p['crest']+p['face']+30) & (edge < 14+6*fine)
    labels[on_rapid & (fine > -.4)] = GRAVEL
    labels[slope > .5] = ROCK
    return labels


def sub_line(line, a, b, step=40):
    a, b = max(a, 0), min(b, length(line))
    n = max(2, int((b-a)//step)+1)
    return [point_along(line, a+(b-a)*i/(n-1)) for i in range(n)]


def outline(line, a, b, half):
    """A polygon round the river from a to b along it, `half` either side."""
    core = sub_line(line, a, b)
    left, right = [], []
    for i, (px, py) in enumerate(core):
        (ax, ay), (bx, by) = core[max(i-1, 0)], core[min(i+1, len(core)-1)]
        n = math.hypot(bx-ax, by-ay) or 1
        nx, ny = -(by-ay)/n, (bx-ax)/n
        left.append((px+nx*half, py+ny*half)); right.append((px-nx*half, py-ny*half))
    return left+right[::-1]


def stretches(t):
    """Each pool's reach along the river, from the lip above to its own lip."""
    last = len(t['pools'])-1
    return [(max(p['start']-(10 if k else 300), 0), min(p['crest']+(0 if k < last else 300), t['total']))
            for k, p in enumerate(t['pools'])]


def water(t):
    """Each pool's water area, drawn round its own stretch of the river."""
    return [water_area(f'Pool {k+1}', outline(t['line'], a, c, 115), p['water'])
            for k, (p, (a, c)) in enumerate(zip(t['pools'], stretches(t)))]


def decorate(m, t, ground):
    line, stretch = t['line'], t['pools']
    # Each pool's flowing strip 1 above its water, crest to crest.
    for k, (p, (a, c)) in enumerate(zip(stretch, stretches(t))):
        add_river(m, f'Pool {k+1}', sub_line(line, a, c), width=lambda _: 190, height=p['water']+1, step=60)
    rng = random.Random(SEED+9)
    def frame(sa):
        (ax, ay), (bx, by) = point_along(line, sa-10), point_along(line, sa+10)
        n = math.hypot(bx-ax, by-ay) or 1
        return point_along(line, sa), ((bx-ax)/n, (by-ay)/n)
    STONES = ['DarkRockGrey02', 'DarkRockGrey17', 'RockGrey02', 'RockGrey17']
    BOULDERS = ['DarkRockGrey06', 'DarkRockGrey14', 'DarkRockGrey18']
    # Each rapid: stones along its lip and down its face, foam at its foot,
    # and on a steep chute small falls across it.
    for k, p in enumerate(stretch[:-1]):
        low = stretch[k+1]['water']
        for _ in range(int(10+p['face']/5)):
            sa = rng.uniform(p['crest']-20, p['crest']+p['face'])
            (cx, cy), (ux, uy) = frame(sa)
            c = rng.uniform(-1, 1)*75
            px, py = cx-uy*c, cy+ux*c
            add_object(m, rng.choice(STONES), px, py, angle=rng.random()*math.tau, layer='Rapids', z=-1,
                       extra=[('objectPrototypeScale', 2, round(rng.uniform(.6, 1.4), 2))])
        for side in (-1, 1):
            (cx, cy), (ux, uy) = frame(p['crest']+rng.uniform(-20, p['face']))
            c = side*rng.uniform(60, 90)
            add_object(m, rng.choice(BOULDERS), cx-uy*c, cy+ux*c, angle=rng.random()*math.tau, layer='Rapids', z=-3,
                       extra=[('objectPrototypeScale', 2, round(rng.uniform(.4, .7), 2))])
        (fx, fy), (ux, uy) = frame(p['crest']+p['face']+10)
        for c in range(-60, 61, 30):
            px, py = fx-uy*(c+rng.uniform(-8, 8)), fy+ux*(c+rng.uniform(-8, 8))
            add_object(m, 'WaterRipples', px, py, angle=math.atan2(uy, ux), layer='Rapids', z=low+.3-ground(px, py))
        if p['drop'] >= 9:
            # A chute: small falls at uneven places across it, lip upstream.
            (cx, cy), (ux, uy) = frame(p['crest']+p['face']*.6)
            for c in rng.sample(range(-60, 61, 20), 4):
                px, py = cx-uy*c, cy+ux*c
                add_object(m, 'WaterfallC04', px, py, angle=math.atan2(-uy, -ux)-math.pi/2, layer='Rapids',
                           z=low-ground(px, py), extra=[('objectPrototypeScale', 2, round(p['drop']/72*1.1, 3))])
    for i in range(6):
        px, py = point_along(line, t['total']*(i+.5)/6)
        add_object(m, 'Amb_WaterCreek2Loop', px, py, layer='Sounds')
