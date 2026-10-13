"""Bramble Hollow: a small, cozy two-player valley in the Shire.

A gentle green valley ringed by low wooded hills. A brook winds in from the
north edge, fills a millpond in the middle and leaves by the south edge; it
can be waded only at two shallow gravel fords. Around the pond lies a little
hamlet: cottages and a barn on both banks, gardens, haystacks, carts and an
orchard, with hedges and flowers along the lanes.

The playable layout is point-symmetric about the map centre: the second half
of the brook, the hamlet's far bank, the hills and both starts are the first
half turned through 180 degrees. Both fords lie on the line halfway between
the starts, so each start is equally far from the hamlet and from each ford.
The build measures those walking distances and refuses an unfair result.

Positions are map units, 10 per terrain cell: x east, y north from the
playable area's south-west corner. Hamlet layouts are written in (u, v):
u runs along the brook towards the south-east, v across it towards player 2.
"""
from collections import Counter
import math
import random
import numpy as np

from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, add_object, terrain_cell_sizes, water_plane
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.variety import spot_random
from mapworkshop.mapkit.weather import add_sky, ini_block, apply_weather

WIDTH, HEIGHT = 500, 500       # playable size in cells
BORDER = 30                    # cells of unplayable border around it
SEED = 41027                   # title, description, players and weather are in map.toml
SPAN = (WIDTH-1)*10            # 4990: the last height sample; the map mirrors onto x -> SPAN-x
C = SPAN/2                     # map centre and centre of symmetry, also the pond's centre
WATER = 150.0                  # one water plane; only the brook and pond lie below it
GROUND = 166.0                 # valley floor
BASE = 168.0                   # level of both construction areas
FORD_DEPTH = 2.5               # units wade through water up to 5 deep (docs/reference/mapping/navigation)
STARTS = [(1000, 1000), (SPAN-1000, SPAN-1000)]
BASE_FLAT, BASE_BLEND = 420, 820

# The brook's upstream half, from beyond the north edge to the pond; the
# downstream half is the same turned about the centre. Three collinear points
# put the first ford on the line halfway between the starts (x + y = SPAN).
UPSTREAM = [(1300, 5500), (1360, 4960), (1500, 4540), (1360, 4150), (1420, 3780),
            (1580, 3443), (1700, 3290), (1820, 3137), (2030, 3060), (2260, 2790), (C, C)]

# Terrain textures. Higher entries blend over lower ones at their edges.
PALETTE = ['GrassShire01', 'GrassShire02', 'GrassShire03', 'GrassShire13', 'GrassShire10',
           'GrassOldForest04', 'CliffShire03', 'DirtShire06', 'LothlorienDirt07', 'DirtShire12',
           'StoneShire03', 'GrassShire08', 'GrassShire12', 'GrassShire15', 'DirtShire04',
           'DirtShire07', 'DirtShire10']
(MEADOW, MEADOW_MOTTLED, MEADOW_DRY, MEADOW_LUSH, HILL_GRASS, WOOD_FLOOR, MOSSY_ROCK, SILT, MUD,
 BANK, FORD_GRAVEL, FLOWERS_WHITE, FLOWERS_YELLOW, LANE_EDGE, LANE, GARDEN, GARDEN_SPROUTS) = range(len(PALETTE))

# --- The hamlet, one bank in (u, v); the other bank is (-u, -v). ----------
# Lanes: the bank lane arcs round the pond from bridge to bridge, curving
# into each crossing so it meets the far bank's lane in one smooth bend; each
# start's lane meets it on that player's bank.
BANK_LANE = [(-1124, 0), (-1124, -130), (-1090, -215), (-990, -305), (-800, -365), (-500, -375),
             (-220, -350), (0, -335), (220, -350), (500, -375), (800, -365), (990, -305),
             (1090, -215), (1124, -130), (1124, 0)]
START_LANE = [(0, -1750), (90, -1400), (-40, -1050), (40, -650), (0, -335)]
# A high ridge along the north-west border, marked in the viewer: its crest
# runs from pin 1 through pin 3 to pin 2, rising to RIDGE_HEIGHT above the
# hill band and fading out at both ends and into the border.
RIDGE = [(581, 5031), (-61, 3963), (-158, 1470)]
RIDGE_HEIGHT = 500
# A creek on player 1's bank, marked in the viewer (mark 1): from the brook
# just above the pond west through the orchard, under the bank lane and out
# through a gorge it cuts in the hills and the ridge. Only on this bank: it
# is not turned onto the other. Where it crosses the bank lane it gets a
# shallow ford and a footbridge, like the brook's.
# A footbridge slung across the creek's gorge high on the ridge, between
# the viewer's pins 1 and 2: both ends of its deck, which sags SPAN_SAG at
# the middle. It stands in the border, so it is scenery only.
SPAN_ENDS = [(-72, 2928), (-68, 3446)]
SPAN_SAG = 36
CREEK = [(2245, 2798), (2186, 2831), (2116, 2838), (2045, 2829), (1973, 2811), (1908, 2787), (1843, 2763),
         (1777, 2743), (1715, 2717), (1650, 2689), (1583, 2668), (1516, 2656), (1446, 2673), (1377, 2699),
         (1309, 2704), (1242, 2718), (1168, 2721), (1098, 2733), (1033, 2747), (972, 2778), (907, 2818),
         (843, 2839), (768, 2882), (696, 2902), (644, 2951), (593, 2996), (494, 3026), (428, 3038),
         (333, 3062), (257, 3093), (187, 3116), (122, 3137), (53, 3152), (-19, 3161), (-89, 3198),
         (-151, 3228), (-212, 3259), (-450, 3360)]
BRIDGE = 'GenericTreeBridge'   # wooden footbridge over each ford; deck along its local y
# Its model (nbtreebrdge.w3d) reaches 139 each way along the deck, and the
# ramp ends sit 31.5 above the object's base: the base belongs in the bed.
BRIDGE_REACH, BRIDGE_RAMP_END = 139, 31.5
BRIDGE_SCALE = .72
# The millpond: an oval along the brook with a wooded island, a dock and a
# rowboat on each bank. Radii along and across the brook, island radius.
POND = dict(along=240, across=150, island=58)
DOCK_U = -190                  # where along the pond each bank's dock stands (marked in the viewer)
# Buildings: template, u, v, the direction they face in (u, v) degrees (90:
# towards the pond), pad radius, solid radius. Most line the outside of the
# bank lane; one cottage stands inside it, between the lane and the brook.
BUILDINGS = [('CBHobbitBldg01', -600, -520, 90, 95, 70), ('ShireGeneric03', -270, -490, 90, 80, 50),
             ('ShireGeneric01', 290, -530, 90, 105, 85), ('CBHobbitBldg02', 640, -520, 90, 95, 70),
             ('ShireGeneric02', 620, -255, 270, 75, 50)]
# Cottages added at the viewer's pins 4-9, beyond the hamlet's ends, in map
# units: template, x, y, pad radius, solid radius. Each faces its nearest
# lane, with a footpath to it. Placed as marked, so not turned onto the
# other bank: four stand on player 1's bank, two on player 2's.
MARKED_HOUSES = [('ShireGeneric01', 2036.5, 3563.4, 105, 85), ('CBHobbitBldg02', 1565.2, 2776.5, 95, 70),
                 ('ShireGeneric03', 1442.2, 3051.5, 80, 50), ('CBHobbitBldg01', 2808.8, 1532.9, 95, 70),
                 ('ShireGeneric01', 3121.8, 1453.3, 105, 85), ('ShireGeneric03', 3509.8, 2051.4, 80, 50)]
GARDENS = [(-600, -690), (-270, -650), (290, -715)]     # fenced vegetable plots behind the cottages
ORCHARD = dict(u=(-900, -560), v=(-150, -270), step=62)


def smooth(a, b, v):
    t = np.clip((v-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def mirror(field):
    """The field turned about the map centre (the height grid is symmetric)."""
    return field[::-1, ::-1]


def xy(u, v):
    return C+(u+v)/math.sqrt(2), C+(v-u)/math.sqrt(2)


def uv(x, y):
    return ((x-C)-(y-C))/math.sqrt(2), ((x-C)+(y-C))/math.sqrt(2)


def turned(points):
    return [(SPAN-x, SPAN-y) for x, y in points]


def chaikin(points, rounds=3):
    for _ in range(rounds):
        out = [points[0]]
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            out += [(.75*ax+.25*bx, .75*ay+.25*by), (.25*ax+.75*bx, .25*ay+.75*by)]
        out.append(points[-1]); points = out
    return points


def smooth_min(a, b, k):
    """The smaller of two distances with a rounded fillet of size k where they meet."""
    h = np.clip(.5+.5*(b-a)/k, 0, 1)
    return b*(1-h)+a*h-k*h*(1-h)


def polyline_distance(points, x, y):
    """Distance from every sample to the polyline, and the arc length of its nearest point."""
    best = np.full(x.shape, np.inf); along = np.zeros(x.shape); s = 0.
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx-ax, by-ay; length2 = dx*dx+dy*dy
        if length2 == 0:
            continue
        t = np.clip(((x-ax)*dx+(y-ay)*dy)/length2, 0, 1)
        d = np.hypot(x-ax-t*dx, y-ay-t*dy)
        closer = d < best
        best = np.where(closer, d, best); along = np.where(closer, s+t*math.sqrt(length2), along)
        s += math.sqrt(length2)
    return best, along


def brook_line():
    """The whole brook, smoothed, and its two fords where it crosses x + y = SPAN."""
    full = UPSTREAM[:-1]+[(C, C)]+turned(UPSTREAM[:-1])[::-1]
    line = chaikin(full, 4)
    ford = None
    for (ax, ay), (bx, by) in zip(line, line[1:]):
        fa, fb = ax+ay-SPAN, bx+by-SPAN
        if fa*fb <= 0 and fa != fb and math.dist((ax, ay), (C, C)) > 800:
            t = fa/(fa-fb); ford = (ax+t*(bx-ax), ay+t*(by-ay)); break
    if ford is None:
        raise ValueError('The brook does not cross the line between the starts')
    return line, [ford, (SPAN-ford[0], SPAN-ford[1])]


def lanes():
    """Every lane as a smoothed polyline in map units, both banks."""
    out = []
    for points in (BANK_LANE, START_LANE):
        line = [xy(u, v) for u, v in points]
        out += [chaikin(line, 3), chaikin(turned(line), 3)]
    return out


def creek_line():
    return chaikin(CREEK, 3)


def creek_crossing():
    """Where the creek crosses player 1's bank lane, and the lane's direction there."""
    lane = lanes()[0]
    for (ax, ay), (bx, by) in zip(lane, lane[1:]):
        for (cx, cy), (dx, dy) in zip(creek_line(), creek_line()[1:]):
            rx, ry, sx, sy = bx-ax, by-ay, dx-cx, dy-cy
            cross = rx*sy-ry*sx
            if cross == 0:
                continue
            p = ((cx-ax)*sy-(cy-ay)*sx)/cross; q = ((cx-ax)*ry-(cy-ay)*rx)/cross
            if 0 <= p <= 1 and 0 <= q <= 1:
                return (ax+p*rx, ay+p*ry), math.atan2(ry, rx)
    raise ValueError('The creek does not cross the bank lane')


def ridge(x, y, notch):
    """The north-west ridge: a crest along RIDGE that swells towards its middle
    and tapers to nothing at both ends, with flanks that fall in rounded
    shoulders. Noise bends the contours into spurs and gullies and varies the
    crest, so it reads as a worn natural hill rather than a raised line."""
    crest, along = polyline_distance(RIDGE, x, y)
    length = sum(math.dist(a, b) for a, b in zip(RIDGE, RIDGE[1:]))
    s = along/length
    rise = smooth(0, .35, s)*(1-smooth(.75, 1, s))
    rise *= .85+.25*fbm(x+3100, y-1700, scale=700, seed=SEED+31, octaves=2)
    folds = crest+140*fbm(x, y, scale=520, seed=SEED+32, octaves=3)
    width = 880+200*fbm(x-900, y+400, scale=1300, seed=SEED+33, octaves=2)
    flank = (1-smooth(0, 1, np.maximum(folds, 0)/width))**1.35
    knolls = 1+.12*fbm(x, y, scale=180, seed=SEED+34, octaves=2)
    return RIDGE_HEIGHT*rise*flank*knolls*notch


def terrain():
    rows, cols = HEIGHT+2*BORDER, WIDTH+2*BORDER
    y, x = (np.mgrid[0:rows, 0:cols]-BORDER)*10.0
    line, fords = brook_line()

    # Water: the brook's and the pond's signed distance (negative in the water).
    brook_d, along = polyline_distance(line, x, y)
    total = sum(math.dist(a, b) for a, b in zip(line, line[1:]))
    middle = np.abs(along-total/2)
    half_width = 36+9*fbm(middle, np.zeros_like(middle), scale=700, seed=SEED+1, octaves=2)
    r = np.hypot(x-C, y-C); theta = np.arctan2(y-C, x-C)
    half_width += 22*(1-smooth(220, 650, r))       # the brook widens as it nears the pond
    # The pond: an oval along the brook, its outline wobbling with even
    # harmonics only (point-symmetric). The brook flows into it through a
    # rounded fillet rather than meeting it at a corner.
    pu, pv = uv(x, y)
    oval = (np.sqrt((pu/POND['along'])**2+(pv/POND['across'])**2)-1)*POND['across']
    oval -= 14*np.sin(2*theta+.7)+9*np.sin(4*theta+1.9)
    water = smooth_min(brook_d-half_width, oval, 110)
    # A low island in the middle (positive: land).
    island = POND['island']+7*np.sin(2*theta+1.3)-r
    # The creek: narrower than the brook, joining it in a rounded mouth. The
    # hills and the ridge give way close beside it, so it runs at the brook's
    # own level through a deep, steep-sided gorge.
    creek_d, creek_along = polyline_distance(creek_line(), x, y)
    creek_sd = creek_d-(20+5*fbm(creek_along, np.zeros_like(creek_along), scale=400, seed=SEED+7, octaves=2))
    notch = smooth(90, 420, np.maximum(water, island))*smooth(30, 200, creek_sd)
    sd = np.maximum(smooth_min(water, creek_sd, 50), island)

    # Low wooded hills along the edge: a rising band and separate hilltops,
    # combined with their turned copy so both halves of the map match.
    edge = np.minimum(np.minimum(x, SPAN-x), np.minimum(y, SPAN-y))
    reach = 700+200*fbm(x, y, scale=1400, seed=SEED+2, octaves=2)
    band = (1-smooth(0, 1, edge/reach))**1.4
    hills = band*(45+35*fbm(x, y, scale=500, seed=SEED+3, octaves=3))
    rng = np.random.default_rng(SEED)
    for _ in range(22):
        p = rng.uniform(0, 4*SPAN); inset = rng.uniform(40, 380)
        side, at = divmod(p, SPAN)
        hx, hy = [(at, inset), (SPAN-inset, at), (SPAN-at, SPAN-inset), (inset, SPAN-at)][int(side)]
        radius = rng.uniform(220, 430); height = rng.uniform(35, 90)
        hills += height*np.exp(-((x-hx)**2+(y-hy)**2)/(2*radius**2))*(1-smooth(500, 1100, edge))
    hills = np.maximum(hills, mirror(hills))
    hills *= notch                                 # the brook and creek cut their own notches through the hills
    hills = np.maximum(hills, ridge(x, y, notch))
    for p in STARTS:                               # the hills give way to each base: no cut scarp
        hills *= smooth(BASE_BLEND-100, BASE_BLEND+450, np.hypot(x-p[0], y-p[1]))

    swell = 7*fbm(x+900, y-400, scale=1100, seed=SEED+4, octaves=3)
    swell = .5*(swell+mirror(swell))
    valley = 10*(1-smooth(60, 650, sd))            # the floor sinks gently towards the water
    land = GROUND+hills+swell-valley
    # Fine relief, left out near water and the bases so both sides stay alike.
    calm = smooth(60, 160, sd)
    for p in STARTS:
        calm *= smooth(BASE_BLEND-100, BASE_BLEND+150, np.hypot(x-p[0], y-p[1]))
    land += 1.6*fbm(x, y, scale=140, seed=SEED+5, octaves=2)*calm
    land += 10*(1-smooth(0, POND['island'], r))    # the island rises a little higher in the middle

    # Banks ease down to the waterline; the bed falls to about 18 deep.
    bank_width = 70+35*smooth(-.3, .3, .5*(fbm(x, y, scale=600, seed=SEED+6, octaves=2)
                                          + mirror(fbm(x, y, scale=600, seed=SEED+6, octaves=2))))
    t = np.clip(sd/bank_width, 0, 1)
    edge_z = WATER-1
    z = np.where(sd > 0, edge_z+(land-edge_z)*t**1.5, WATER-2-16*smooth(0, 35, -sd))

    # Fords under the bridges: a wide gravel shelf 2.5 deep, with long gentle
    # ramps down the banks, so the crossing holds even off the bridge deck.
    crossing, _ = creek_crossing()
    ford_d = np.min([np.hypot(x-fx, y-fy) for fx, fy in fords+[crossing]], axis=0)
    shelf = 1-smooth(85, 165, ford_d)
    ramp = 1-smooth(150, 330, ford_d)
    z = np.where(sd <= 0, z*(1-shelf)+(WATER-FORD_DEPTH)*shelf, z)
    ramp_z = WATER-FORD_DEPTH+.09*np.maximum(sd, 0)
    z = np.where(sd > 0, z*(1-ramp)+np.minimum(z, ramp_z)*ramp, z)

    # Both construction areas: level, at the same height, easing into the valley.
    for p in STARTS:
        blend = (1-smooth(BASE_FLAT, BASE_BLEND, np.hypot(x-p[0], y-p[1])))**.8
        z = z*(1-blend)+BASE*blend
    return dict(x=x, y=y, z=z, sd=sd, hills=hills, brook=line, fords=fords, ford_d=ford_d, shelf=shelf)


def level_pads(t, pads):
    """Level each building's footprint at its own ground height, leaving
    nearby water alone."""
    for px, py, radius in pads:
        d = np.hypot(t['x']-px, t['y']-py)
        target = float(np.median(t['z'][(d < radius) & (t['sd'] > 0)]))
        blend = (1-smooth(radius, radius+80, d))*smooth(0, 30, t['sd'])
        t['z'] = t['z']*(1-blend)+target*blend


def lane_field(t, lane_lines):
    d = np.full(t['z'].shape, np.inf)
    for line in lane_lines:
        d = np.minimum(d, polyline_distance(line, t['x'], t['y'])[0])
    return d


def footpaths(lane_lines):
    """A narrow path from each building's door to the nearest point of a lane,
    with a slight bend so it does not look ruled."""
    paths = []
    points = np.concatenate([np.array(line) for line in lane_lines])
    for _, u, v, facing, pad, _ in BUILDINGS:
        front = 1 if facing == 90 else -1
        for sign in (1, -1):
            door = np.array(xy(sign*u, sign*(v+front*.62*pad)))
            lane = points[np.argmin(np.hypot(*(points-door).T))]
            middle = (door+lane)/2+np.array(xy(sign*14, 0))-np.array((C, C))
            paths.append(chaikin([tuple(door), tuple(middle), tuple(lane)], 3))
    for _, door, lane in marked_house_fronts(lane_lines):
        ax, ay = (lane-door)/np.hypot(*(lane-door))
        middle = (door+lane)/2+np.array((-ay, ax))*14
        paths.append(chaikin([tuple(door), tuple(middle), tuple(lane)], 3))
    return paths


def marked_house_fronts(lane_lines):
    """Each marked house's angle, door and the lane point its front faces."""
    points = np.concatenate([np.array(line) for line in lane_lines])
    fronts = []
    for _, x, y, pad, _ in MARKED_HOUSES:
        lane = points[np.argmin(np.hypot(*(points-(x, y)).T))]
        dx, dy = (lane-(x, y))/np.hypot(*(lane-(x, y)))
        # Buildings face +y at angle 0.
        fronts.append((math.atan2(dy, dx)-math.pi/2, np.array((x+dx*.62*pad, y+dy*.62*pad)), lane))
    return fronts


def materials(t, gardens, orchard_area):
    x, y, z, sd = t['x'], t['y'], t['z'], t['sd']
    gy, gx = np.gradient(z, 10); slope = np.hypot(gx, gy)
    broad = fbm(x, y, scale=1000, seed=SEED+20, octaves=3)
    mid = fbm(x+2000, y, scale=300, seed=SEED+21, octaves=3)
    fine = fbm(x, y+2000, scale=90, seed=SEED+22, octaves=2)
    v = .65*broad+.35*mid+.1*fine
    labels = np.full(z.shape, MEADOW, dtype='u2')
    labels[v < -.12] = MEADOW_MOTTLED
    labels[v > .18] = MEADOW_DRY
    labels[(sd < 260+120*mid) & (v < .05) & (fine > -.05)] = MEADOW_LUSH
    # Hills: darker tufted grass, woodland floor under the trees, moss on rock.
    hill = t['hills'] > 18+10*mid
    labels[hill & (fine > -.25)] = HILL_GRASS
    labels[t['woods'] > .5+.15*fine] = WOOD_FLOOR
    labels[slope > .42+.08*fine] = MOSSY_ROCK
    # Above the treeline: tufted grass, with rock breaking through on the steeper crest.
    high = t['hills'] > 230+40*mid
    labels[high & (slope > .28+.1*fine)] = MOSSY_ROCK
    labels[high & (slope <= .28+.1*fine) & (fine > .1)] = MEADOW_MOTTLED
    # Flower meadow round the hamlet and in the orchard.
    hamlet = np.hypot(x-C, y-C) < 820+120*mid
    labels[hamlet & (mid > .18) & (sd > 30)] = FLOWERS_WHITE
    labels[hamlet & (mid < -.22) & (sd > 30)] = FLOWERS_YELLOW
    labels[orchard_area & (fine > -.1)] = MEADOW_LUSH
    labels[orchard_area & (fine > .25)] = FLOWERS_WHITE
    # Banks: dark mud at the water's edge, a broken earthy fringe, silt below.
    edge = fbm(x, y, scale=70, seed=SEED+23, octaves=2)
    labels[(sd < 26+14*edge) & (sd > -2) & (fine > -.2)] = BANK
    labels[(sd < 10+6*edge) & (sd > -2)] = MUD
    labels[z < WATER-1.5] = SILT
    labels[(t['shelf'] > .25) & (z < WATER+1.5)] = FORD_GRAVEL
    # Lanes: packed earth with a trampled grassy fringe, fading out in the bases.
    worn = t['lanes'] < 30+8*fine
    core = t['lanes'] < 15+5*fine
    fade = np.ones(z.shape, bool)
    for p in STARTS:
        fade &= np.hypot(x-p[0], y-p[1]) > BASE_FLAT-40+60*fine
    dry = z > WATER+.5
    labels[worn & fade & dry & (fine > -.35)] = LANE_EDGE
    labels[core & fade & dry] = LANE
    # Footpaths to the doors: a narrow worn strip.
    labels[(t['paths'] < 13+4*fine) & dry & (fine > -.25)] = LANE_EDGE
    labels[(t['paths'] < 6+3*fine) & dry] = LANE
    for plot, crop in gardens:
        labels[plot & dry] = crop
    return labels


class Scenery:
    """Object placement with spacing, water, lane and base checks."""

    TREE_LIMIT, SHRUB_LIMIT = 1200, 2000      # the game's optimized vegetation buffers

    def __init__(self, m, t, assets):
        self.m, self.t, self.assets = m, t, assets
        self.buckets = {}; self.counts = Counter(); self.kinds = {}; self.vegetation = Counter()
        self.solids = []

    def kind(self, template):
        if template not in self.kinds:
            if template.lower() not in self.assets.templates:
                raise ValueError('Unknown template: '+template)
            r = self.assets.template_model(template)
            self.kinds[template] = None if not r or not r['tree'] else \
                'tree' if 'TREE' in r['kinds'] else 'shrub' if 'SHRUB' in r['kinds'] else None
        return self.kinds[template]

    def ground(self, x, y, paths=True):
        """Height, distance to the nearest lane (or footpath), and distance from the water."""
        iy, ix = round(y/10)+BORDER, round(x/10)+BORDER
        lane = min(self.t['lanes'][iy, ix], self.t['paths'][iy, ix]) if paths else self.t['lanes'][iy, ix]
        return float(self.t['z'][iy, ix]), float(lane), float(self.t['sd'][iy, ix])

    def put(self, template, x, y, angle=None, layer='', gap=20, lane=40, wet=False, base=600,
            scale=None, solid=0, z=0, extra=(), paths=True):
        """Place one object if the spot is clear; `paths=False` lets a
        building stand at the end of its own footpath. Its size (trees and
        shrubs) and rotation, unless given, come from its own spot_random, so
        they do not change when other placements do."""
        if not (80 < x < SPAN-80 and 80 < y < SPAN-80):
            return False
        height, lane_d, sd = self.ground(x, y, paths)
        if lane_d < lane or (not wet and (height < WATER+1.5 or sd < 6)):
            return False
        if any(math.dist((x, y), p) < base for p in STARTS):
            return False
        cx, cy = int(x//100), int(y//100)
        for bx in range(cx-2, cx+3):
            for by in range(cy-2, cy+3):
                for ox, oy, og in self.buckets.get((bx, by), ()):
                    if math.dist((x, y), (ox, oy)) < max(gap, og):
                        return False
        kind = self.kind(template)
        local = spot_random(SEED, template, x, y)
        if kind:
            if self.vegetation[kind] >= (self.TREE_LIMIT if kind == 'tree' else self.SHRUB_LIMIT):
                return False
            if scale is None:
                low, mode, high = (.8, 1., 1.25) if kind == 'tree' else (.85, 1., 1.15)
                scale = local.triangular(low, high, mode)
            self.vegetation[kind] += 1
        if scale is not None:
            extra = list(extra)+[('objectPrototypeScale', 2, round(scale, 3))]
        if angle is None:
            angle = local.random()*math.tau
        add_object(self.m, template, x, y, angle, layer=layer, extra=extra, z=z)
        self.buckets.setdefault((cx, cy), []).append((x, y, gap))
        if solid:
            self.solids.append((x, y, solid))
        self.counts[layer] += 1
        return True

    def pair(self, template, u, v, facing=None, **kw):
        """Place at (u, v) on player 1's bank and turned onto player 2's bank.
        `facing` is the direction the front faces, in (u, v) degrees."""
        placed = 0
        for sign in (1, -1):
            x, y = xy(sign*u, sign*v)
            angle = None
            if facing is not None:
                # Buildings face +y at angle 0; turn them to face the given direction.
                angle = math.radians(facing)-math.pi/4-math.pi/2+(0 if sign > 0 else math.pi)
            placed += self.put(template, x, y, angle=angle, **kw)
        return placed


def hamlet(s, t):
    """Cottages, barn, gardens, orchard, carts and hay on both banks."""
    rng = random.Random(SEED+100)
    for template, u, v, facing, pad, solid in BUILDINGS:
        if s.pair(template, u, v, facing=facing, layer='Hamlet', gap=pad, lane=75, solid=solid, paths=False) != 2:
            raise ValueError('Could not place '+template)
    # Dooryard flowers and a shade tree beside each cottage.
    for template, u, v, facing, pad, solid in BUILDINGS:
        front = 1 if facing == 90 else -1
        for _ in range(9):
            for _try in range(10):
                fu, fv = u+rng.uniform(-pad, pad), v+front*rng.uniform(.55*pad, .9*pad)
                if s.pair(rng.choice(['PTFlower05', 'PTFlower09', 'ElvenWoodFlowerGrassOpt', 'PTFlower01']), fu, fv,
                          layer='Dooryards', gap=12, lane=30):
                    break
        if template.startswith('Shire'):
            s.pair(rng.choice(['TreeShire02', 'TreeShire03']), u+pad*rng.choice([-1, 1]), v-front*pad*.5,
                   layer='Dooryards', gap=40, lane=50, scale=rng.uniform(.85, 1.05))
    # Garden plots: fenced, with rows of vegetables and a few crop bundles.
    # A fence's rails run across the direction it faces.
    for gu, gv in GARDENS:
        for i in range(4):
            fu = gu-55+i*36.7
            s.pair('ShireFence01', fu, gv-38, facing=90, layer='Gardens', gap=10, lane=40)
            s.pair('ShireFence01', fu, gv+38, facing=90, layer='Gardens', gap=10, lane=40)
        for j in range(2):
            s.pair('ShireFence03', gu-70, gv-19+j*38, facing=0, layer='Gardens', gap=10, lane=40)
            s.pair('ShireFence03', gu+70, gv-19+j*38, facing=0, layer='Gardens', gap=10, lane=40)
        s.pair(rng.choice(['CropBundle3', 'CropBundle2', 'CropPile']), gu+rng.uniform(-30, 30), gv+rng.uniform(-15, 15),
               layer='Gardens', gap=20, lane=40)
    # The orchard: fruit trees in loose rows on player 1's bank and its turned copy.
    du, dv = ORCHARD['u'], ORCHARD['v']; step = ORCHARD['step']
    for u in np.arange(du[0], du[1]+1, step):
        for v in np.arange(dv[0], dv[1]-1, -step):
            ju, jv = rng.uniform(-7, 7), rng.uniform(-7, 7)
            template = rng.choice(['TreeShire01', 'TreeShire02', 'TreeShire02', 'TreeShire03'])
            s.pair(template, u+ju, v+jv, layer='Orchard', gap=40, lane=55, scale=rng.uniform(.72, .9))
    # Hay, carts and stores round the barn and the cottages.
    for template, u, v, spread, n in [('Haystack', 790, -640, 40, 5), ('CropBundle3', 560, -660, 25, 2),
                                      ('Barrel', -470, -440, 15, 3), ('Crate01', 450, -440, 15, 2),
                                      ('Barrel', 160, -450, 15, 2), ('CropPile', -400, -560, 15, 2),
                                      ('Crate01', 720, -170, 12, 1), ('Barrel', 540, -190, 12, 2)]:
        for _ in range(n):
            for _try in range(12):
                if s.pair(template, u+rng.gauss(0, spread), v+rng.gauss(0, spread), layer='HamletProps', gap=22, lane=45):
                    break
    for template, u, v, facing in [('Cart01', -440, -430, 20), ('Cart02', 520, -440, 160), ('Cart01', 820, -540, 70)]:
        s.pair(template, u, v, facing=facing, layer='HamletProps', gap=40, lane=45)
    # The village green between the lane and the pond.
    s.pair('TreeShire01', 190, -245, layer='Green', gap=60, lane=50, scale=1.15)
    s.pair('Bench01', -130, -255, facing=90, layer='Green', gap=30, lane=40)
    s.pair('Shiresign01', 75, -410, facing=90, layer='Green', gap=20, lane=32)
    s.pair('FeedingTroughs', 790, -470, facing=0, layer='HamletProps', gap=30, lane=45)
    for _ in range(4):
        s.pair('Sheep', 780+rng.gauss(0, 60), -800+rng.gauss(0, 40), layer='Animals', gap=30, lane=40)
        s.pair('Chicken', -500+rng.gauss(0, 40), -420+rng.gauss(0, 20), layer='Animals', gap=15, lane=30)
    s.pair('Amb_VillageChickens', -500, -430, layer='Animals', gap=0, lane=0)


def marked_houses(s, lane_lines):
    """The cottages at the viewer's pins, each with flowers by its door."""
    rng = random.Random(SEED+150)
    for (template, x, y, pad, solid), (angle, door, _) in zip(MARKED_HOUSES, marked_house_fronts(lane_lines)):
        if not s.put(template, x, y, angle=angle, layer='MarkedHouses', gap=pad, lane=75, solid=solid, paths=False):
            raise ValueError(f'Could not place {template} at ({x}, {y})')
        ax, ay = (door-(x, y))/np.hypot(*(door-(x, y)))
        for _ in range(9):
            for _try in range(10):
                across, out = rng.uniform(-pad, pad), rng.uniform(.55*pad, .9*pad)
                if s.put(rng.choice(['PTFlower05', 'PTFlower09', 'ElvenWoodFlowerGrassOpt', 'PTFlower01']),
                         x+ax*out-ay*across, y+ay*out+ax*across, layer='MarkedHouses', gap=12, lane=30):
                    break


def hedgerows(s, t, lane_lines):
    """Hedges along both sides of every lane, broken by gaps and gateways,
    with flowers spilling out between hedge and lane."""
    rng = random.Random(SEED+200)
    hedges = ['ShrubShireHedge01', 'ShrubShireHedge01', 'ShrubShireHedge02', 'ShrubShireHedge03']
    flowers = ['PTFlower05', 'PTFlower09', 'ElvenWoodFlowerGrassOpt', 'PTFlower05']
    for index, line in enumerate(lane_lines):
        pts = np.array(line); seg = np.diff(pts, axis=0); lengths = np.hypot(seg[:, 0], seg[:, 1])
        cumulative = np.concatenate([[0], np.cumsum(lengths)])
        for side in (-1, 1):
            gaps = random.Random(SEED+300+index*2+(side > 0))
            s_pos = gaps.uniform(0, 60); run = gaps.uniform(140, 320)
            while s_pos < cumulative[-1]:
                k = min(np.searchsorted(cumulative, s_pos)-1, len(seg)-1); k = max(k, 0)
                f = (s_pos-cumulative[k])/max(lengths[k], 1e-9)
                px, py = pts[k]+f*seg[k]; dx, dy = seg[k]/max(lengths[k], 1e-9)
                nx, ny = -dy*side, dx*side
                if run <= 0:
                    s_pos += gaps.uniform(50, 120); run = gaps.uniform(140, 320); continue
                ford = min(math.dist((px, py), f_) for f_ in t['fords'])
                if ford > 300:
                    hx, hy = px+nx*44, py+ny*44
                    s.put(rng.choice(hedges), hx, hy, angle=math.atan2(dy, dx)+rng.uniform(-.15, .15),
                          layer='Hedgerows', gap=18, lane=36, base=650)
                    if rng.random() < .65:
                        fx, fy = px+nx*rng.uniform(28, 34), py+ny*rng.uniform(28, 34)
                        s.put(rng.choice(flowers), fx+rng.uniform(-8, 8), fy+rng.uniform(-8, 8),
                              layer='LaneFlowers', gap=12, lane=24, base=650)
                s_pos += 24; run -= 24


def woods(s, t):
    """Woods on the hills: dense cores, open edges, and understorey."""
    rng = random.Random(SEED+400)
    x, y = t['x'], t['y']
    clump = fbm(x+500, y-300, scale=320, seed=SEED+401, octaves=3)
    density = smooth(12, 45, t['hills'])*np.clip(.65+1.2*clump, 0, 1)*smooth(110, 220, t['sd'])
    # A ragged treeline: the ridge's upper slopes stay open grass and rock.
    density *= 1-smooth(190, 290, t['hills']+60*clump)
    density *= smooth(70, 160, t['lanes'])
    for p in STARTS:
        density *= smooth(BASE_BLEND-150, BASE_BLEND+100, np.hypot(x-p[0], y-p[1]))
    t['woods'] = density
    broadleaf = ['TreeOldForest01', 'TreeOldForest02', 'TreeOldForest03', 'TreeShire01', 'TreeShire02',
                 'Tree01_L', 'Tree03a_L', 'TreeOldForest01']
    understorey = ['OldForestShrub01', 'OldForestShrub02', 'OldForestShrub04', 'OldForestShrub06', 'OptBushLG06', 'Fern01']
    trees = 0
    for _ in range(60000):
        if trees >= 760:
            break
        px, py = rng.uniform(80, SPAN-80), rng.uniform(80, SPAN-80)
        iy, ix = round(py/10)+BORDER, round(px/10)+BORDER
        d = density[iy, ix]
        if d < .2 or rng.random() > d:
            continue
        if s.put(rng.choice(broadleaf), px, py, layer='HillWoods', gap=40 if d > .6 else 60, lane=70, base=700):
            trees += 1
            if rng.random() < .35:
                a = rng.random()*math.tau; r = rng.uniform(30, 60)
                s.put(rng.choice(understorey), px+math.cos(a)*r, py+math.sin(a)*r, layer='Understorey',
                      gap=24, lane=50, base=700)
    # A few mossy stones and logs in the woods.
    for _ in range(4000):
        if s.counts['WoodStones'] >= 50:
            break
        px, py = rng.uniform(80, SPAN-80), rng.uniform(80, SPAN-80)
        if density[round(py/10)+BORDER, round(px/10)+BORDER] > .4:
            s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey18', 'TreeLog', 'PTStump01']), px, py,
                  layer='WoodStones', gap=70, lane=60, base=700, z=-1)
    return trees


def bridges(s, t):
    """A small wooden footbridge over each ford, its deck along the lane's
    crossing (towards player 2: map angle 45 degrees). Both landings are
    levelled to one height and the base is sunk so the ramp ends lie flush
    on them. A third crosses the creek where the bank lane meets it."""
    s.kind(BRIDGE)
    crossing, along = creek_crossing()
    for i, ((fx, fy), axis) in enumerate([(f, math.pi/4) for f in t['fords']]+[(crossing, along)]):
        reach = BRIDGE_REACH*BRIDGE_SCALE
        ends = [(fx+math.cos(axis)*d, fy+math.sin(axis)*d) for d in (-reach, reach)]
        landing = float(np.mean([s.ground(*e)[0] for e in ends]))
        for ex, ey in ends:
            d = np.hypot(t['x']-ex, t['y']-ey)
            blend = (1-smooth(35, 85, d))*(t['z'] > WATER)
            t['z'] = t['z']*(1-blend)+landing*blend
        base = landing-BRIDGE_RAMP_END*BRIDGE_SCALE-.5
        add_object(s.m, BRIDGE, fx, fy, axis-math.pi/2, layer='Bridges', z=base-s.ground(fx, fy)[0],
                   extra=[('objectName', 3, f'Bramble_Bridge_{i+1}'),
                          ('objectPrototypeScale', 2, BRIDGE_SCALE)])
        s.buckets.setdefault((int(fx//100), int(fy//100)), []).append((fx, fy, 110))
        s.counts['Bridges'] += 1


def suspension_bridge(s, t):
    """The rope bridge over the gorge, built from pieces since the game has
    no hanging bridge and objects cannot tilt:

    - the deck: Erebor's rickety slat walkways, stepped into a sag;
    - hand ropes: a chain fence along each side, one bay to a deck piece,
      each drooping between its posts as a rope does;
    - main cables: smaller chain bays draped from each tower's top down to
      the hand rope at mid-span;
    - a scaffold tower either side of each end, a log-block anchor behind
      it, and timber and a short fence at each landing.

    Both landings are levelled to one height."""
    (ax, ay), (bx, by) = SPAN_ENDS
    axis = math.atan2(by-ay, bx-ax)
    ux, uy = math.cos(axis), math.sin(axis)
    span = math.dist(*SPAN_ENDS)
    landing = float(np.mean([s.ground(*e)[0] for e in SPAN_ENDS]))
    for ex, ey in SPAN_ENDS:
        blend = 1-smooth(35, 105, np.hypot(t['x']-ex, t['y']-ey))
        t['z'] = t['z']*(1-blend)+landing*blend

    def at(f, side=0., along=0.):
        """The point a fraction f along the span, `side` to its left and `along` past it."""
        return ax+(bx-ax)*f-uy*side+ux*along, ay+(by-ay)*f+ux*side+uy*along

    def deck(f):
        return landing-SPAN_SAG*math.sin(math.pi*min(max(f, 0), 1))

    def place(template, x, y, angle, z, scale=1.):
        extra = [('objectPrototypeScale', 2, round(scale, 3))] if scale != 1 else []
        add_object(s.m, template, x, y, angle, layer='SuspensionBridge', z=z-s.ground(x, y)[0], extra=extra)
        s.counts['SuspensionBridge'] += 1

    # The deck. EreborBridge's slats run along local y at its base's height,
    # centred 12 along local x.
    pieces, half_width = 5, 20
    for i in range(pieces):
        f = (i+.5)/pieces
        place('EreborBridge', *at(f, side=-12), axis-math.pi/2, deck(f))
    # ChainFence: posts 48 apart along local x, the chain hanging 3-8 above the base.
    chain = 44
    rail = span/pieces/chain                        # hand-rope bays fill each deck piece
    cable = rail/2
    top = landing+80                                # where the main cables leave the towers
    for side in (-1, 1):
        for i in range(pieces):
            f = (i+.5)/pieces
            place('ChainFence', *at(f, side*half_width), axis, deck(f), rail)
        bays = 2*pieces
        for i in range(bays):
            f = (i+.5)/bays
            hand = deck(f)+6*rail                    # the hand rope's height
            drop = (1-math.sin(math.pi*f))**1.5      # 1 at the towers, 0 at mid-span
            height = hand+(top-hand)*drop
            if height-hand > 10:
                place('ChainFence', *at(f, side*(half_width+2)), axis, height-6*cable, cable)
    # Towers, anchors and landings, at each end.
    for f, back in ((0, -1), (1, 1)):
        for side in (-1, 1):
            place('IsengardScaffolding05', *at(f, side*(half_width+10), back*6), axis, landing)
            place('LogBlock02', *at(f, side*(half_width+14), back*60), axis, landing)
            place('ShireFence05', *at(f, side*(half_width+6), back*34), axis, landing)
        place('TimberPile01', *at(f, half_width+52, back*40), axis+.4*back, landing)


def millpond(s, t):
    """The pond's island with an old shade tree, and on each bank a dock with
    a rowboat moored beside it and a bench looking out over the water."""
    rng = random.Random(SEED+700)
    if not s.put('TreeShire04', C, C, angle=.6, layer='Island', gap=30, lane=0, base=0, scale=.5):
        raise ValueError('No room for the island tree')
    for k in range(4):
        a = .4+k*math.pi/2+rng.uniform(-.3, .3)
        s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey18']), C+math.cos(a)*44, C+math.sin(a)*44,
              layer='Island', gap=20, lane=0, base=0, wet=True, z=-1)
    for _ in range(14):
        a = rng.random()*math.tau; r = rng.uniform(25, 45)
        s.put(rng.choice(['PTFlower05', 'PTFlower09', 'ElvenWoodFlowerGrassOpt']), C+math.cos(a)*r, C+math.sin(a)*r,
              layer='Island', gap=10, lane=0, base=0)
    for sign in (1, -1):
        # From the pond's middle, walk out across this bank to the waterline.
        for v in range(40, 400, 4):
            x, y = xy(sign*DOCK_U, -sign*v)
            if s.ground(x, y)[2] >= 0:
                break
        into = math.atan2(*reversed(np.subtract(xy(0, sign), (C, C))))   # towards the water
        cx, cy = x+math.cos(into)*22, y+math.sin(into)*22
        # The dock's deck lies 9 above its base (sbdock.w3d): sink the legs so
        # the deck rides just above the water.
        s.put('SBDock', cx, cy, angle=into-math.pi/2, layer='Docks', gap=40, lane=30, base=0, wet=True,
              z=WATER+2.5-9-s.ground(cx, cy)[0])
        along = np.subtract(xy(sign, 0), (C, C))                           # along the pond
        bx, by = cx+along[0]*42+math.cos(into)*14, cy+along[1]*42+math.sin(into)*14
        s.put('Celduin_Boat01', bx, by, angle=into-math.pi/2+.15, layer='Docks', gap=20, lane=30, base=0,
              wet=True, z=WATER-s.ground(bx, by)[0])
        ex, ey = x-math.cos(into)*45-along[0]*55, y-math.sin(into)*45-along[1]*55
        s.put('Bench01', ex, ey, angle=into+math.pi/2, layer='Docks', gap=25, lane=30, base=0)


def waterside(s, t):
    """Rushes along the brook and pond, stones flanking the fords, ducks on the bank."""
    rng = random.Random(SEED+500)
    z, x, y = t['z'], t['x'], t['y']
    shore = (np.abs(z-WATER) < 2.5) & (t['ford_d'] > 220)
    seeds = np.column_stack(np.nonzero(shore))
    seeds = seeds[np.random.default_rng(SEED+501).permutation(len(seeds))]
    clumps = []
    for iy, ix in seeds:
        if len(clumps) >= 95:
            break
        cx, cy = float(x[iy, ix]), float(y[iy, ix])
        if any(math.dist((cx, cy), c) < 130 for c in clumps):
            continue
        clumps.append((cx, cy))
        for _ in range(rng.randint(3, 7)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 22))
            s.put(rng.choice(['GladdenFieldsShrub01', 'GladdenFieldsShrub02', 'OptGrass02']), cx+math.cos(a)*r,
                  cy+math.sin(a)*r, layer='Rushes', gap=12, lane=40, wet=True, base=650)
    # Stepping stones along the downstream edge of each ford, and a few on its banks.
    line = np.array(t['brook'])
    for fx, fy in t['fords']:
        k = int(np.argmin(np.hypot(line[:, 0]-fx, line[:, 1]-fy)))
        dx, dy = line[min(k+1, len(line)-1)]-line[max(k-1, 0)]; n = math.hypot(dx, dy); dx, dy = dx/n, dy/n
        for along in (-150, 150):
            for across in range(-70, 71, 35):
                px, py = fx+dx*along-dy*across+rng.uniform(-10, 10), fy+dy*along+dx*across+rng.uniform(-10, 10)
                s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey18', 'DarkRockGrey02']), px, py,
                      layer='FordStones', gap=26, lane=40, wet=True, base=650, z=-2)
    # Ducks on the pond's edge, the creek's sound along the brook.
    for a in (.4, 1.3, 2.2):
        for sign in (1, -1):
            r = 205
            px, py = C+sign*r*math.cos(a+.6), C+sign*r*math.sin(a+.6)
            s.put('Duck', px, py, layer='Animals', gap=15, lane=30, wet=True, base=650)
    for frac in (.18, .38, .62, .82):
        px, py = line[int(frac*(len(line)-1))]
        s.put('Amb_WaterCreek2Loop', float(px), float(py), layer='Sounds', gap=0, lane=0, wet=True, base=0)
    creek = creek_line()
    for frac in (.25, .6):
        px, py = creek[int(frac*(len(creek)-1))]
        s.put('Amb_WaterCreek2Loop', float(px), float(py), layer='Sounds', gap=0, lane=0, wet=True, base=0)


def meadows(s, t):
    """Loose drifts of tufts and wildflowers, and a few lone trees in the meadows."""
    rng = random.Random(SEED+600)
    x, y = t['x'], t['y']
    drift = fbm(x-1700, y+900, scale=260, seed=SEED+601, octaves=3)
    open_ground = (t['woods'] < .1) & (t['sd'] > 40) & (t['lanes'] > 60) & (drift > .15)
    seeds = np.column_stack(np.nonzero(open_ground))
    seeds = seeds[np.random.default_rng(SEED+602).permutation(len(seeds))]
    drifts = []
    for iy, ix in seeds:
        if len(drifts) >= 120:
            break
        cx, cy = float(x[iy, ix]), float(y[iy, ix])
        if any(math.dist((cx, cy), d) < 200 for d in drifts):
            continue
        drifts.append((cx, cy))
        for _ in range(rng.randint(4, 8)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 40))
            template = rng.choice(['OptGrass02', 'OptGrass03', 'GladdenFieldsShrub02', 'PTFlower05', 'PTFlower09', 'OptBushLG06'])
            s.put(template, cx+math.cos(a)*r, cy+math.sin(a)*r, layer='MeadowDrifts', gap=18, lane=40)
    lone = 0
    for _ in range(3000):
        if lone >= 26:
            break
        px, py = rng.uniform(300, SPAN-300), rng.uniform(300, SPAN-300)
        iy, ix = round(py/10)+BORDER, round(px/10)+BORDER
        if t['woods'][iy, ix] > .05 or math.dist((px, py), (C, C)) < 1000:
            continue
        if s.put(rng.choice(['TreeShire01', 'TreeShire02', 'TreeOldForest02']), px, py, layer='LoneTrees',
                 gap=300, lane=80, base=750):
            lone += 1


def fairness(t, solids):
    """Walking distances from each start to the hamlet and to each ford.

    Walkable: ground and water up to 5 deep, outside the buildings. The
    hamlet distance is to the nearest walkable ground within 400 of the pond.
    """
    from mapworkshop.mapkit.checks.strategy import distance_field, STEP
    z = t['z'][BORDER:BORDER+HEIGHT, BORDER:BORDER+WIDTH]
    blocked = z < WATER-5
    yy, xx = np.indices(z.shape); px, py = xx*10., yy*10.
    for sx, sy, r in solids:
        blocked |= np.hypot(px-sx, py-sy) < r
    s = int(STEP/10); gh, gw = HEIGHT//s, WIDTH//s
    walk = blocked[:gh*s, :gw*s].reshape(gh, s, gw, s).mean(axis=(1, 3)) < .5
    gy, gx = np.indices(walk.shape); wx, wy = (gx+.5)*STEP, (gy+.5)*STEP
    hamlet = walk & (np.hypot(wx-C, wy-C) < 400)
    def at(field, p):
        return float(field[int(p[1]//STEP), int(p[0]//STEP)])
    report = []
    for i, p in enumerate(STARTS):
        field = distance_field(walk, p)
        values = dict(hamlet=float(field[hamlet].min()), fords=[at(field, f) for f in t['fords']],
                      opponent=at(field, STARTS[1-i]))
        if not np.isfinite([values['hamlet'], *values['fords'], values['opponent']]).all():
            raise ValueError(f'Unreachable hamlet, ford or opponent from {p}: {values}')
        report.append(dict(start=p, hamlet=round(values['hamlet']), fords=[round(f) for f in values['fords']],
                           opponent=round(values['opponent'])))
    a, b = report
    if abs(a['hamlet']-b['hamlet']) > 40 or abs(sorted(a['fords'])[0]-sorted(b['fords'])[0]) > 40:
        raise ValueError(f'Unfair layout: {report}')
    return report


def build(b):
    from mapworkshop.render.assets import GameAssets
    weather = b.project.weather
    if b.project.players != len(STARTS):
        raise ValueError(f'map.toml has {b.project.players} players, but the valley has {len(STARTS)} starts')
    print('Shaping the valley, brook and fords...', flush=True)
    t = terrain()
    lane_lines = lanes()
    t['lanes'] = lane_field(t, lane_lines)
    t['paths'] = lane_field(t, footpaths(lane_lines[:2]))

    # Level the building pads before anything stands on them.
    pads = []
    for _, u, v, _, pad, _ in BUILDINGS:
        for sign in (1, -1):
            pads.append((*xy(sign*u, sign*v), pad))
    pads += [(x, y, pad) for _, x, y, pad, _ in MARKED_HOUSES]
    level_pads(t, pads)

    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    t['woods'] = np.zeros(t['z'].shape)
    s = Scenery(m, t, GameAssets())
    print('Building the hamlet...', flush=True)
    bridges(s, t)
    suspension_bridge(s, t)
    millpond(s, t)
    hamlet(s, t)
    marked_houses(s, lane_lines[:2])
    hedgerows(s, t, lane_lines)
    print('Planting woods, rushes and meadows...', flush=True)
    trees = woods(s, t)
    waterside(s, t)
    meadows(s, t)

    # Garden plots and the orchard floor, then the textures.
    gardens = []
    for gu, gv in GARDENS:
        for sign in (1, -1):
            gx_, gy_ = xy(sign*gu, sign*gv)
            u_, v_ = uv(t['x'], t['y'])
            local_u, local_v = sign*(u_-sign*gu), sign*(v_-sign*gv)
            for half, crop in ((local_u < 0, GARDEN), (local_u >= 0, GARDEN_SPROUTS)):
                gardens.append(((np.abs(local_u) < 62) & (np.abs(local_v) < 32) & half, crop))
    u_, v_ = uv(t['x'], t['y'])
    du, dv = ORCHARD['u'], ORCHARD['v']
    orchard = np.zeros(t['z'].shape, bool)
    for sign in (1, -1):
        orchard |= (sign*u_ > du[0]-50) & (sign*u_ < du[1]+50) & (sign*v_ < dv[0]+50) & (sign*v_ > dv[1]-50)
    labels = materials(t, gardens, orchard)

    blocked = t['z'] < WATER-5            # deeper than units can wade
    set_heights(m, t['z'])
    set_materials(m, PALETTE, labels, blocked, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    water_plane(m, 'Bramble brook', WATER)
    starts(m, STARTS)

    sky = add_sky(m, weather, WIDTH*10, HEIGHT*10, BORDER*10)
    # Warm afternoon sun and a cool sky fill, as on the Greywater Marches.
    apply_weather(m, weather, sun=dict(ambient=(.17, .17, .15), diffuse=(.92, .84, .68)),
                  fill=dict(ambient=(0., 0., 0.), diffuse=(.17, .25, .33), direction=(-.64, -.54, -.55)))

    data = m.encode()
    from mapworkshop.mapkit.checks.analyze import analyze
    report = analyze(data)
    if report['unresolved_sections']:
        raise ValueError(report['unresolved_sections'])
    # Both construction areas: level and dry.
    for p in STARTS:
        area = np.hypot(t['x']-p[0], t['y']-p[1]) <= 380
        if np.ptp(t['z'][area]) > .01 or (t['z'][area] < WATER+3).any():
            raise ValueError(f'Uneven or wet construction area at {p}')
    walking = fairness(t, s.solids)
    ini = ini_block(weather)+f'WaterTransparency\n  ReflectionPlaneZ = {WATER:g}\n  ReflectionOn = No\nEnd\n'
    path = b.save(data, ini=ini)
    report.update(title=b.project.title, seed=SEED, starts=STARTS, fords=t['fords'], walking=walking, sky=sky,
                  layers=dict(s.counts), vegetation=dict(s.vegetation), trees_in_woods=trees)
    b.report.update(report)
    print(f'{path.name}: {sum(s.counts.values())} objects, {dict(s.vegetation)}, heights {t["z"].min():.0f}..{t["z"].max():.0f}')
    for w in walking:
        print(f'  start {w["start"]}: hamlet {w["hamlet"]}, fords {w["fords"]}, opponent {w["opponent"]}')
