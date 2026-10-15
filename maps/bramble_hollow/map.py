"""Bramble Hollow: a small, cozy two-player valley in the Shire.

A gentle green valley ringed by low wooded hills. A brook winds in from the
north edge, fills a millpond in the middle and leaves by the south edge; it
can be waded only at two shallow gravel fords. Around the pond lies a little
hamlet: cottages and a barn on both banks, gardens, haystacks, carts and an
orchard, with hedges and flowers along the lanes. Below the gardens on each
bank a lower lane leaves the start lane, lined with more cottages.

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
from mapworkshop.mapkit.lines import nearest, polyline_distance
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
           'DirtShire07', 'DirtShire10', 'CropsType1', 'CropsType3', 'DirtShire08', 'DirtShire11']
(MEADOW, MEADOW_MOTTLED, MEADOW_DRY, MEADOW_LUSH, HILL_GRASS, WOOD_FLOOR, MOSSY_ROCK, SILT, MUD,
 BANK, FORD_GRAVEL, FLOWERS_WHITE, FLOWERS_YELLOW, LANE_EDGE, LANE, GARDEN, GARDEN_SPROUTS,
 CROPS, CROPS_DENSE, SEEDLINGS, STUBBLE) = range(len(PALETTE))

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
# A dead tree fallen across the creek's gorge high on the ridge (between the
# viewer's pins 1 and 2), wedged between the walls where the gorge is about
# 270 wide: its base point, the angle across the gorge (radians) and its
# scale (TreeFallDead01 is 90 long, so about 290). It stands in the border,
# so it is scenery only.
GORGE_LOG = (-70, 3188, 290)
GORGE_LOG_ANGLE, GORGE_LOG_SCALE = 1.18, 3.2
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
# A lower hamlet below the gardens, at the viewer's marks 1 and 3 (one on
# each bank, so it is laid out in (u, v) and turned like the hamlet): a lane
# leaves the start lane and runs east to a dead end, with a link north to
# the bank lane between the cottages there, and cottages either side of it.
LOWER_LANE = [(-15, -930), (200, -935), (420, -950), (640, -985), (860, -990), (1040, -930), (1110, -840)]
LOWER_LINK = [(445, -950), (440, -800), (455, -640), (450, -480), (440, -355)]
# Template, u, v, pad radius, solid radius. Each turns its door to the
# nearest lower lane, with a footpath to it.
LOWER_HOUSES = [('ShireGeneric02', 150, -830, 75, 50), ('CBHobbitBldg01', 620, -840, 95, 70),
                ('ShireGeneric03', 990, -800, 80, 50), ('ShireGeneric01', 200, -1050, 105, 85),
                ('CBHobbitBldg02', 400, -1090, 95, 70), ('ShireGeneric03', 600, -1130, 80, 50),
                ('ShireGeneric01', 840, -1130, 105, 85), ('ShireGeneric02', 1060, -1030, 75, 50)]
# The side each cottage's door is on, as the angle of that side's outward
# direction from the model's local +x (`mw items ... --views`): the round
# door or steps of the hobbit houses and ShireGeneric03 on +x, the door and
# porch of ShireGeneric01 and 02 on -y.
DOOR_SIDES = {'CBHobbitBldg01': 0, 'CBHobbitBldg02': 0, 'ShireGeneric03': 0,
              'ShireGeneric01': -math.pi/2, 'ShireGeneric02': -math.pi/2}
GARDENS = [(-600, -690), (-270, -650), (290, -715)]     # fenced vegetable plots behind the cottages
ORCHARD = dict(u=(-900, -560), v=(-150, -270), step=62)

# A big farm north of player 1's base, at the viewer's mark 1: a farmhouse
# and barn round a yard, a paddock beside them, and a patchwork of fields
# either side of a track from the start lane up to the yard. Placed as
# marked, so not turned onto the other bank. The crop rows in the field
# textures run east-west, so the fields are axis-aligned: x0, y0, x1, y1,
# texture, and what grows on them ('corn' stalks, 'hay' stacks).
FARM_TRACK = [(1095, 2180), (1100, 1950), (1108, 1720), (1160, 1560), (1290, 1450), (1469, 1386)]
FARM_FIELDS = [(680, 1890, 850, 2110, CROPS, 'corn'), (870, 1890, 1040, 2110, CROPS_DENSE, None),
               (680, 1670, 1040, 1870, STUBBLE, 'hay'), (720, 1500, 1040, 1650, GARDEN, None),
               (1170, 1910, 1560, 2120, SEEDLINGS, None), (1170, 1670, 1380, 1890, CROPS_DENSE, None),
               (1400, 1670, 1560, 1890, GARDEN_SPROUTS, None)]
# Template, x, y, angle, pad radius, solid radius. Both face the yard: the
# farmhouse's door (with its well) is on its local -y side, the barn's
# gabled front on its local +x side (`mw items ... --views`).
FARMHOUSE = ('ShireMaggotsFarm', 960, 2300, 1.17, 80, 55)
BARN = ('ShireMill', 1240, 2310, math.pi, 95, 70)
FARM_YARD = dict(x=1100, y=2240, rx=230, ry=105)
PADDOCK = (690, 2180, 870, 2370)
# A lake at the viewer's mark 2, in the wooded hills by the east edge: a
# long oval along the edge with a bay at each end (x, y, radius east, radius
# north), merged into one wobbling shore. The hills give way close round it.
# Placed as marked, so not turned.
LAKE = [(4420, 2480, 300, 560), (4590, 2930, 210, 170), (4250, 2110, 230, 160)]
# Its details: a low wooded island off the middle (x, y, radius); the south
# bay (LAKE[2]) silted up into a reedy shallow; a deep middle; a pebble beach
# by the dock with nets drying and a boat pulled up, and a footpath to it
# from the nearest lane; mossy stones and a fallen tree where the woods come
# down to the east shore; trees leaning over the water at both ends.
LAKE_ISLAND = (4480, 2650, 62)


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


def lake(x, y):
    """The lake's signed distance in map units (negative in the water): its
    ovals, each measured across its shore, merged with rounded fillets, the
    shore wobbling in coves and points, and its island (positive: land)."""
    d = None
    for cx, cy, rx, ry in LAKE:
        dx, dy = (x-cx)/rx, (y-cy)/ry
        r = np.hypot(dx, dy)
        grad = np.hypot(dx/rx, dy/ry)/np.maximum(r, 1e-6)
        oval = (r-1)/np.maximum(grad, 1e-9)
        d = oval if d is None else smooth_min(d, oval, 120)
    ix, iy, ir = LAKE_ISLAND
    island = ir+10*np.sin(3*np.arctan2(y-iy, x-ix)+.8)-np.hypot(x-ix, y-iy)
    return np.maximum(d+55*fbm(x, y, scale=240, seed=SEED+40, octaves=3), island)


def marsh(x, y):
    """How far into the lake's reedy south bay: 1 inside it, 0 well clear of it."""
    mx, my, mrx, mry = LAKE[2]
    return 1-smooth(.7, 1.25, np.hypot((x-mx)/mrx, (y-my)/mry))


def lake_dock(sd):
    """The point on the lake's west shore level with its middle, where its dock stands."""
    lx, ly = LAKE[0][:2]
    for dx in range(0, 700, 4):
        if sd[round(ly/10)+BORDER, round((lx-dx)/10)+BORDER] >= 0:
            return lx-dx, ly
    raise ValueError('The lake has no west shore')


def lake_path(sd, lane_lines):
    """A footpath from the lake's dock to the nearest lane, wandering a little."""
    bx, by = lake_dock(sd)
    start = np.array((bx-25, by))
    points = np.concatenate([np.array(line) for line in lane_lines])
    end = points[np.argmin(np.hypot(*(points-start).T))]
    ax, ay = (end-start)/np.hypot(*(end-start))
    side = np.array((-ay, ax))
    bends = [start+(end-start)*.3+side*55, start+(end-start)*.65-side*45]
    return chaikin([tuple(start)]+[tuple(p) for p in bends]+[tuple(end)], 3)


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
    lake_sd = lake(x, y)
    # A low island in the middle (positive: land).
    island = POND['island']+7*np.sin(2*theta+1.3)-r
    # The creek: narrower than the brook, joining it in a rounded mouth. The
    # hills and the ridge give way close beside it, so it runs at the brook's
    # own level through a deep, steep-sided gorge.
    creek_d, creek_along = polyline_distance(creek_line(), x, y)
    creek_sd = creek_d-(20+5*fbm(creek_along, np.zeros_like(creek_along), scale=400, seed=SEED+7, octaves=2))
    notch = smooth(90, 420, np.maximum(water, island))*smooth(30, 200, creek_sd)*smooth(60, 340, lake_sd)
    sd = np.minimum(np.maximum(smooth_min(water, creek_sd, 50), island), lake_sd)

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
    # The valley floor is no level plain (the viewer's marks 8 and 9, round
    # the lower hamlets): it climbs gently from the brook towards the hills
    # and rolls in broad swells with flat-bottomed hollows between them, so
    # lanes, fields and cottages lie on long gentle slopes. Both halves match;
    # it flattens out at the water's edge and towards the bases, and runs
    # into the hills rather than piling onto them.
    climb = 60*smooth(150, 1800, water)
    roll = fbm(x+1500, y+800, scale=1200, seed=SEED+8, octaves=3)
    roll = 85*smooth(-.8, .8, roll+mirror(roll))
    ripple = fbm(x-700, y+1900, scale=420, seed=SEED+9, octaves=2)
    ripple = 7*(ripple+mirror(ripple))
    relief = (climb+roll+ripple)*smooth(60, 600, sd)
    for p in STARTS:
        relief *= smooth(BASE_BLEND-150, BASE_BLEND+650, np.hypot(x-p[0], y-p[1]))
    land = GROUND-smooth_min(-hills, -relief, 30)+swell-valley
    # Fine relief, left out near water and the bases so both sides stay alike.
    calm = smooth(60, 160, sd)
    for p in STARTS:
        calm *= smooth(BASE_BLEND-100, BASE_BLEND+150, np.hypot(x-p[0], y-p[1]))
    land += 1.6*fbm(x, y, scale=140, seed=SEED+5, octaves=2)*calm
    land += 10*(1-smooth(0, POND['island'], r))    # the island rises a little higher in the middle
    ix, iy, ir = LAKE_ISLAND                       # and so does the lake's
    land += 16*(1-smooth(0, ir+10, np.hypot(x-ix, y-iy)))

    # Banks ease down to the waterline; the bed falls to about 18 deep.
    bank_width = 70+35*smooth(-.3, .3, .5*(fbm(x, y, scale=600, seed=SEED+6, octaves=2)
                                          + mirror(fbm(x, y, scale=600, seed=SEED+6, octaves=2))))
    t = np.clip(sd/bank_width, 0, 1)
    edge_z = WATER-1
    z = np.where(sd > 0, edge_z+(land-edge_z)*t**1.5, WATER-2-16*smooth(0, 35, -sd))
    # The lake shelves down to a deep middle, but its south bay has silted
    # up into a shallow, uneven reed bed that can be waded.
    deep = WATER-2-34*smooth(0, 220, -lake_sd)
    reeds = marsh(x, y)
    bed = deep*(1-reeds)+(WATER-1.8+.9*fbm(x, y, scale=60, seed=SEED+41, octaves=2))*reeds
    z = np.where(lake_sd < 0, np.minimum(bed, WATER-.6), z)

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
    return dict(x=x, y=y, z=z, sd=sd, lake=lake_sd, hills=hills, brook=line, fords=fords, ford_d=ford_d, shelf=shelf)


def level_pads(t, pads):
    """Level each building's footprint at its own ground height, leaving
    nearby water alone. The pad eases into the ground round it over a wide
    margin, so one on a slope sits on a soft shelf rather than in a cut."""
    for px, py, radius in pads:
        d = np.hypot(t['x']-px, t['y']-py)
        target = float(np.median(t['z'][(d < radius) & (t['sd'] > 0)]))
        blend = (1-smooth(radius, radius+170, d))*smooth(0, 30, t['sd'])
        t['z'] = t['z']*(1-blend)+target*blend


def lane_field(t, lane_lines):
    """Distance to the nearest of the lines, exact within 500 (every use compares
    it against less); inf beyond."""
    return nearest(lane_lines, t['x'], t['y'], reach=500)


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
        paths.append(door_path(door, lane))
    return paths


def door_path(door, lane):
    """A footpath from a door to a lane point, bent slightly to one side."""
    ax, ay = (lane-door)/np.hypot(*(lane-door))
    middle = (door+lane)/2+np.array((-ay, ax))*14
    return chaikin([tuple(door), tuple(middle), tuple(lane)], 3)


def lower_lanes():
    """The lower lane and its link to the bank lane, smoothed, both banks."""
    out = []
    for points in (LOWER_LANE, LOWER_LINK):
        line = [xy(u, v) for u, v in points]
        out += [chaikin(line, 3), chaikin(turned(line), 3)]
    return out


def lower_house_fronts():
    """Each lower cottage on both banks: position, angle, the direction its
    door faces, the door and the lane point it faces."""
    points = np.concatenate([np.array(line) for line in lower_lanes()])
    houses = []
    for template, u, v, pad, solid in LOWER_HOUSES:
        banks = []
        for sign in (1, -1):
            x, y = xy(sign*u, sign*v)
            lane = points[np.argmin(np.hypot(*(points-(x, y)).T))]
            out = (lane-(x, y))/np.hypot(*(lane-(x, y)))
            banks.append((x, y, math.atan2(out[1], out[0])-DOOR_SIDES[template], out, (x, y)+out*.62*pad, lane))
        houses.append((template, pad, solid, banks))
    return houses


def marked_house_fronts(lane_lines):
    """Each marked house's angle, door and the lane point its front faces."""
    points = np.concatenate([np.array(line) for line in lane_lines])
    fronts = []
    for _, x, y, pad, _ in MARKED_HOUSES:
        lane = points[np.argmin(np.hypot(*(points-(x, y)).T))]
        dx, dy = (lane-(x, y))/np.hypot(*(lane-(x, y)))
        # Turns the model's local +y side towards the lane. That is not every
        # cottage's door side: ShireGeneric03's +y side has only windows.
        fronts.append((math.atan2(dy, dx)-math.pi/2, np.array((x+dx*.62*pad, y+dy*.62*pad)), lane))
    return fronts


def cottages(lane_lines, lower_houses):
    """Every cottage's centre, pad radius, door, and whether it gets a
    kitchen garden (the hamlet's have their fenced plots already)."""
    out = []
    for _, u, v, facing, pad, _ in BUILDINGS:
        front = 1 if facing == 90 else -1
        for sign in (1, -1):
            out.append((*xy(sign*u, sign*v), pad, np.array(xy(sign*u, sign*(v+front*.62*pad))), False))
    out += [(x, y, pad, door, True) for (_, x, y, pad, _), (_, door, _)
            in zip(MARKED_HOUSES, marked_house_fronts(lane_lines))]
    out += [(x, y, pad, door, True) for _, pad, _, banks in lower_houses for x, y, _, _, door, _ in banks]
    return out


def yards(t, houses):
    """Worn ground round each cottage, so none stands on untouched grass: a
    trodden yard reaching out further on the door side, bare earth along the
    walls and at the doorstep, drier grass in patches beyond, and behind most
    a third of the cottages that have no fenced plot a small kitchen garden
    against the back wall. Noise breaks every edge. Returns the texture masks, lowest
    first, the whole area (for keeping meadow tufts and trees off it) and
    the kitchen gardens (x, y, half width, half height)."""
    x, y = t['x'], t['y']
    wobble = .7*fbm(x+700, y-1300, scale=70, seed=SEED+24, octaves=3)+.5*fbm(x-200, y+300, scale=180, seed=SEED+26, octaves=2)
    patchy = fbm(x-400, y+900, scale=30, seed=SEED+25, octaves=2)
    rng = random.Random(SEED+180)
    halo, worn, bare, area = (np.zeros(x.shape, bool) for _ in range(4))
    plots, gardens = [], []
    for cx, cy, pad, door, garden in houses:
        # Only the samples near this cottage.
        near = (np.abs(x-cx) < 3*pad+120) & (np.abs(y-cy) < 3*pad+120)
        dx, dy = (door-(cx, cy))/np.hypot(*(door-(cx, cy)))
        along, across = ((x-cx)*dx+(y-cy)*dy)/pad, ((y-cy)*dx-(x-cx)*dy)/pad
        oval = np.hypot((along-.3)/1.45, across/1.2)+.3*wobble     # pushed out towards the door
        walls = np.hypot(x-cx, y-cy)/pad+.25*wobble
        step = np.hypot(x-door[0], y-door[1])/pad+.3*wobble
        halo |= near & (oval < 1.6) & (patchy > .05)
        worn |= near & ((oval < .8) | ((oval < 1.1) & (patchy > -.4)))
        bare |= near & (((walls < .68) & (patchy > -.1)) | (step < .35) | ((step < .6) & (patchy > .25)))
        area |= near & (oval < 1.7)
        if garden and rng.random() < .35:
            # Axis-aligned, since the garden textures' rows run east-west,
            # and just clear of the back wall.
            w, h = rng.uniform(38, 52), rng.uniform(24, 34)
            back = .55*pad+abs(dx)*w+abs(dy)*h+12
            gx, gy = cx-dx*back, cy-dy*back
            gardens.append((gx, gy, w, h))
            box = np.maximum(np.abs(x-gx)/w, np.abs(y-gy)/h)+.04*wobble
            plots += [((box < 1) & (x < gx), GARDEN), ((box < 1) & (x >= gx), GARDEN_SPROUTS)]
            worn |= (box < 1.35) & (patchy > -.2)
            area |= box < 1.5
    return [(halo, MEADOW_DRY), (worn, LANE_EDGE), (bare, LANE)]+plots, area, gardens


def materials(t, gardens, orchard_area, yard_masks=()):
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
    # The lake: lush grass and mud round the reed bed, a pebble beach by the
    # dock, and mossy stones along the east shore where the woods come down.
    lake = t['lake']; reeds = marsh(x, y)
    labels[(reeds > .05) & (lake > 0) & (lake < 70+30*edge) & (fine > -.3)] = MEADOW_LUSH
    labels[(reeds > .05) & (lake > -40) & (lake < 22+10*edge)] = MUD
    shore = (lake > -16) & (lake < 26+12*edge)
    bx, by = lake_dock(sd)
    labels[shore & (np.hypot(x-bx, y-by) < 170+50*mid)] = FORD_GRAVEL
    ix, iy, ir = LAKE_ISLAND
    labels[shore & (x > LAKE[0][0]+110+60*mid) & (np.hypot(x-ix, y-iy) > ir+50) & (fine > -.15)] = MOSSY_ROCK
    # Yards and kitchen gardens round the cottages, under the lanes and paths.
    for mask, label in yard_masks:
        labels[mask & (sd > 20) & (z > WATER+.5)] = label
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
                # Turn the model's local +y side to the given direction. Which
                # side is a model's front differs by template (AGENTS.md).
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


def lower_hamlet(s):
    """The lower hamlet's cottages on both banks, each with flowers by its
    door, a shade tree beside it and a few stores against its wall."""
    rng = random.Random(SEED+170)
    houses = lower_house_fronts()
    for template, pad, solid, banks in houses:
        for x, y, angle, *_ in banks:
            if not s.put(template, x, y, angle=angle, layer='LowerHamlet', gap=pad, lane=75, solid=solid, paths=False):
                raise ValueError(f'Could not place {template} at ({x:.0f}, {y:.0f})')

    for template, pad, solid, banks in houses:
        def both(name, out, across, **kw):
            """At `out` along the door's direction and `across` to its left, on both banks."""
            return sum(s.put(name, x+dx*out-dy*across, y+dy*out+dx*across, layer='LowerHamlet', **kw)
                       for x, y, _, (dx, dy), _, _ in banks)
        for _ in range(7):
            for _try in range(10):
                if both(rng.choice(['PTFlower05', 'PTFlower09', 'ElvenWoodFlowerGrassOpt', 'PTFlower01']),
                        rng.uniform(.55*pad, .9*pad), rng.uniform(-pad, pad), gap=12, lane=30):
                    break
        side = rng.choice([-1, 1])
        both(rng.choice(['TreeShire02', 'TreeShire03']), -.3*pad, side*(pad+20), gap=40, lane=50,
             scale=rng.uniform(.85, 1.05))
        for k in range(rng.randint(1, 3)):
            both(rng.choice(['Barrel', 'Barrel', 'Crate01', 'CropPile', 'TimberPile01']), .1*pad-k*22,
                 -side*(.75*pad+12), gap=18, lane=30)


def kitchen_gardens(s, t):
    """A rail fence round each cottage's kitchen garden, a gap or two in it,
    and a crop pile or bundle on the beds."""
    rng = random.Random(SEED+190)
    for gx, gy, w, h in t['kitchen_gardens']:
        w, h = w+6, h+6
        corners = [(gx-w, gy-h), (gx+w, gy-h), (gx+w, gy+h), (gx-w, gy+h)]
        for a, b in zip(corners, corners[1:]+corners[:1]):
            farm_row(s, rng, ['ShireFence01'], a, b, 36.7, 10, .15, layer='KitchenGardens')
        s.put(rng.choice(['CropBundle3', 'CropBundle2', 'CropPile']), gx+rng.uniform(-.5, .5)*w,
              gy+rng.uniform(-.4, .4)*h, layer='KitchenGardens', gap=20, lane=30)


def farm_distance(t):
    """Distance from every sample to the farm's fields, yard and paddock."""
    x, y = t['x'], t['y']
    yard = FARM_YARD
    boxes = [f[:4] for f in FARM_FIELDS]+[PADDOCK, (yard['x']-yard['rx'], yard['y']-yard['ry'],
                                                    yard['x']+yard['rx'], yard['y']+yard['ry'])]
    d = np.full(x.shape, np.inf)
    for x0, y0, x1, y1 in boxes:
        d = np.minimum(d, np.hypot(np.maximum(np.maximum(x0-x, x-x1), 0), np.maximum(np.maximum(y0-y, y-y1), 0)))
    return d


def farm_plots(t):
    """The farm's ground textures: each field, the trodden yard and paddock."""
    x, y = t['x'], t['y']
    fine = fbm(x, y+2000, scale=90, seed=SEED+22, octaves=2)
    plots = [((x >= x0) & (x <= x1) & (y >= y0) & (y <= y1), crop) for x0, y0, x1, y1, crop, _ in FARM_FIELDS]
    yard = np.hypot((x-FARM_YARD['x'])/FARM_YARD['rx'], (y-FARM_YARD['y'])/FARM_YARD['ry'])+.15*fine
    x0, y0, x1, y1 = PADDOCK
    paddock = (x > x0) & (x < x1) & (y > y0) & (y < y1)
    return plots+[(yard < 1, LANE_EDGE), (yard < .6, LANE), (paddock & (fine > -.2), LANE_EDGE)]


def farm_row(s, rng, templates, a, b, step, gap, skip=.08, layer='Farm'):
    """Hedges or fence bays along a field edge from a to b, with a few gaps."""
    length = math.dist(a, b); angle = math.atan2(b[1]-a[1], b[0]-a[0])
    for k in range(int(length//step)+1):
        if rng.random() < skip:
            continue
        f = (k*step+step/2)/length
        if f <= 1:
            s.put(rng.choice(templates), a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f,
                  angle=angle+rng.uniform(-.06, .06), layer=layer, gap=gap, lane=36)


def farm(s, t):
    """The farm at the viewer's mark 1: farmhouse and barn facing the yard,
    stores and carts in it, a fenced paddock with livestock, corn and
    haystacks in the fields, and hedges and rail fences round them."""
    rng = random.Random(SEED+800)
    for template, x, y, angle, pad, solid in (FARMHOUSE, BARN):
        if not s.put(template, x, y, angle=angle, layer='Farm', gap=pad, lane=60, solid=solid):
            raise ValueError(f'Could not place {template} at ({x}, {y})')
    for template, n, spread, (px, py) in [('Haystack', 4, 30, (1350, 2180)), ('CropBundle3', 3, 25, (1160, 2180)),
                                          ('CropPile', 2, 20, (880, 2180)), ('Barrel', 4, 18, (1040, 2200)),
                                          ('Crate01', 3, 18, (1150, 2230)), ('TimberPile01', 1, 10, (1350, 2300))]:
        for _ in range(n):
            for _try in range(12):
                if s.put(template, px+rng.gauss(0, spread), py+rng.gauss(0, spread), layer='Farm', gap=22, lane=30):
                    break
    s.put('Cart01', 1010, 2170, angle=.3, layer='Farm', gap=40, lane=30)
    s.put('Cart02', 1260, 2190, angle=2.2, layer='Farm', gap=40, lane=30)
    s.put('Shiresign01', 1145, 2120, angle=-.4, layer='Farm', gap=20, lane=28)
    for template, x, y in [('TreeShire02', 1010, 2430), ('TreeShire03', 1380, 2400), ('TreeShire01', 640, 2300)]:
        s.put(template, x, y, layer='Farm', gap=50, lane=50, scale=rng.uniform(.95, 1.1))
    # The paddock: rail fences with a gate towards the yard, a trough and stock.
    x0, y0, x1, y1 = PADDOCK
    rails = ['ShireFence06']
    farm_row(s, rng, rails, (x0, y0), (x1, y0), 40, 8, 0)
    farm_row(s, rng, rails, (x0, y1), (x1, y1), 40, 8, 0)
    farm_row(s, rng, rails, (x0, y0), (x0, y1), 40, 8, 0)
    farm_row(s, rng, rails, (x1, y0), (x1, (y0+y1)/2-25), 40, 8, 0)
    farm_row(s, rng, rails, (x1, (y0+y1)/2+25), (x1, y1), 40, 8, 0)
    s.put('FeedingTroughs', x0+60, y1-35, angle=0, layer='Farm', gap=30, lane=30)
    for template, n in [('Cow', 5), ('Pig', 3), ('Sheep', 3)]:
        for _ in range(n):
            for _try in range(12):
                if s.put(template, rng.uniform(x0+25, x1-25), rng.uniform(y0+25, y1-25), layer='Farm', gap=25, lane=30):
                    break
    # The fields: corn in rows, haystacks on the mown field.
    for fx0, fy0, fx1, fy1, _, grows in FARM_FIELDS:
        if grows == 'corn':
            for y in np.arange(fy0+12, fy1-5, 20):
                for x in np.arange(fx0+12, fx1-5, 15):
                    s.put('CornStalk', x+rng.uniform(-3, 3), y+rng.uniform(-3, 3), layer='FarmCrops', gap=8, lane=30,
                          scale=rng.uniform(1.2, 1.45))
        elif grows == 'hay':
            for y in np.arange(fy0+30, fy1-20, 55):
                for x in np.arange(fx0+30, fx1-20, 60):
                    if rng.random() < .7:
                        s.put('Haystack', x+rng.uniform(-12, 12), y+rng.uniform(-12, 12), layer='FarmCrops', gap=30,
                              lane=36, scale=rng.uniform(1.3, 1.6))
    # Hedges along the farm's west and south sides, rails along the fields' tops.
    hedges = ['ShrubShireHedge01', 'ShrubShireHedge01', 'ShrubShireHedge02', 'ShrubShireHedge03']
    farm_row(s, rng, hedges, (655, 1480), (655, 2130), 24, 18)
    farm_row(s, rng, hedges, (700, 1480), (1060, 1480), 24, 18)
    farm_row(s, rng, hedges, (1585, 1660), (1585, 2130), 24, 18)
    farm_row(s, rng, rails, (680, 2132), (1040, 2132), 40, 8, .1)
    farm_row(s, rng, rails, (1170, 2140), (1560, 2140), 40, 8, .1)


def lake_shore(s, t):
    """A dock with a rowboat on the lake's west shore, facing the meadows, and ducks along its edge."""
    lx, ly, rx, ry = LAKE[0]
    x, y = lake_dock(t['sd'])
    cx, cy = x+22, y
    s.put('SBDock', cx, cy, angle=-math.pi/2, layer='Lake', gap=40, lane=30, base=0, wet=True,
          z=WATER+2.5-9-s.ground(cx, cy)[0])
    s.put('Celduin_Boat01', cx+14, cy+42, angle=-math.pi/2+.15, layer='Lake', gap=20, lane=30, base=0, wet=True,
          z=WATER-s.ground(cx+14, cy+42)[0])
    for a in (.5, 1.9, 3.4, 4.6):
        for r in np.arange(0, 1.6, .01):           # out from the middle to just short of the shore
            x, y = lx+r*rx*math.cos(a), ly+r*ry*math.sin(a)
            if s.ground(x, y)[2] > -12:
                break
        s.put('Duck', x, y, layer='Lake', gap=15, lane=30, wet=True, base=650)


def lake_details(s, t):
    """The lake's island, reed bed, beach, stones, fallen tree and waterside
    trees, and the life on it (see LAKE_ISLAND)."""
    rng = random.Random(SEED+750)
    lx, ly = LAKE[0][:2]
    ix, iy, ir = LAKE_ISLAND
    bx, by = lake_dock(t['sd'])

    def at(field, px, py):
        return float(t[field][round(py/10)+BORDER, round(px/10)+BORDER])

    def spots(mask, n, spacing):
        """Up to n cells of the mask, at least `spacing` apart, in a fixed random order."""
        cells = np.column_stack(np.nonzero(mask))
        cells = cells[np.random.default_rng(rng.randrange(1 << 30)).permutation(len(cells))]
        out = []
        for iy_, ix_ in cells:
            p = (float(t['x'][iy_, ix_]), float(t['y'][iy_, ix_]))
            if all(math.dist(p, q) >= spacing for q in out):
                out.append(p)
                if len(out) >= n:
                    break
        return out

    # The island: an old tree and a younger one, stones at the waterline, flowers.
    s.put('TreeShire01', ix-8, iy+6, angle=2.1, layer='LakeIsland', gap=30, lane=0, base=0, scale=.75)
    s.put('TreeOldForest02', ix+24, iy-22, layer='LakeIsland', gap=25, lane=0, base=0, scale=.6)
    for k in range(5):
        a = k*math.tau/5+rng.uniform(-.3, .3)
        s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey18', 'OldForestRock02']), ix+math.cos(a)*ir*.85,
              iy+math.sin(a)*ir*.85, layer='LakeIsland', gap=18, lane=0, base=0, wet=True, z=-1)
    for _ in range(16):
        a = rng.random()*math.tau; r = rng.uniform(10, ir*.7)
        s.put(rng.choice(['PTFlower05', 'PTFlower09', 'OptGrass02', 'Fern01']), ix+math.cos(a)*r, iy+math.sin(a)*r,
              layer='LakeIsland', gap=10, lane=0, base=0)

    # The reed bed: dense stands of rushes in the south bay's shallows, with
    # open channels of water winding between them.
    mx, my, mrx, mry = LAKE[2]
    x, y, lake = t['x'], t['y'], t['lake']
    shallows = (marsh(x, y) > .25) & (lake < 12) & (t['z'] > WATER-3)
    for cx, cy in spots(shallows, 26, 55):
        n = rng.randint(7, 14); spread = rng.uniform(12, 22)
        for _ in range(n):
            px, py = cx+rng.gauss(0, spread), cy+rng.gauss(0, spread*.8)
            s.put(rng.choice(['GladdenFieldsShrub01', 'GladdenFieldsShrub01', 'GladdenFieldsShrub02']), px, py,
                  layer='LakeReeds', gap=7, lane=30, wet=True, base=650)
    # Clumps of rushes along the rest of the west and north shores, clear of the beach.
    edge = (lake > -12) & (lake < 4) & (marsh(x, y) < .05) & (x < lx+80) & (np.hypot(x-bx, y-by) > 220) & \
           (np.hypot(x-ix, y-iy) > ir+30)
    for cx, cy in spots(edge, 14, 110):
        for _ in range(rng.randint(4, 8)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 16))
            s.put(rng.choice(['GladdenFieldsShrub01', 'GladdenFieldsShrub02', 'OptGrass02']), cx+math.cos(a)*r,
                  cy+math.sin(a)*r, layer='LakeReeds', gap=10, lane=30, wet=True, base=650)

    # The east shore, where the woods come down: mossy stones, boulders in the shallows.
    east = (x > lx+120) & (np.hypot(x-ix, y-iy) > ir+60)
    for px, py in spots(east & (lake > -10) & (lake < 30), 12, 70):
        s.put(rng.choice(['OldForestROck07', 'OldForestRock02']), px, py, layer='LakeStones', gap=40, lane=30,
              wet=True, base=650, z=-1)
    for px, py in spots(east & (lake > -30) & (lake < -6), 8, 60):
        s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey18']), px, py, layer='LakeStones', gap=30, lane=30,
              wet=True, base=650, z=-3)
    # A dead tree fallen from the east shore into the water: its trunk runs
    # along local x, the raised root plate at the +x end, so with the roots
    # on the bank the crown lies out in the lake, half sunk.
    for dx in range(0, 600, 4):
        if at('lake', lx+dx, ly-260) >= 0:
            break
    fx, fy = lx+dx-25, ly-260
    s.put('TreeFallDead01', fx, fy, angle=.35, layer='LakeStones', gap=40, lane=0, wet=True, base=650,
          scale=1.3, z=WATER-5-at('z', fx, fy))

    # Trees leaning over the water at the lake's north and south ends.
    ends = (lake > 10) & (lake < 30) & (np.abs(y-ly) > 330) & (marsh(x, y) < .3)
    for px, py in spots(ends, 7, 90):
        s.put(rng.choice(['TreeShire02', 'TreeShire03', 'TreeOldForest01']), px, py, layer='LakeTrees', gap=50,
              lane=50, base=650)

    # The fishing spot by the dock: nets drying, a boat pulled up on the beach, a bench.
    for template, ox, oy, angle in [('Celduin_FishNet01', -45, 75, math.pi/2), ('Celduin_FishNet03', -25, 105, .4),
                                    ('Daleprops4', -60, -65, 1.1), ('Celduin_Boat02', 2, -95, -.5),
                                    ('Bench01', -70, 30, math.pi/2)]:
        s.put(template, bx+ox, by+oy, angle=angle, layer='LakeBeach', gap=20, lane=20, wet=True, base=650)

    # Ripples lapping along the waterline, as on the stock maps' shores
    # (WaterRipples: a foam model with a ripple effect), turned along the
    # shore and floated on the surface; none inside the reed bed.
    gy, gx = np.gradient(lake, 10)
    waterline = (lake > -16) & (lake < -5) & (marsh(x, y) < .3) & (t['z'] < WATER-.5)
    for px, py in spots(waterline, 70, 60):
        iy_, ix_ = round(py/10)+BORDER, round(px/10)+BORDER
        along = math.atan2(gx[iy_, ix_], -gy[iy_, ix_])
        s.put('WaterRipples', px, py, angle=along, layer='LakeRipples', gap=12, lane=0, wet=True, base=650,
              z=WATER+.3-at('z', px, py))

    # Fish, more ducks in the north bay, and the lapping of the water.
    for px, py in spots(lake < -80, 6, 120):
        s.put('Fish', px, py, layer='LakeLife', gap=20, lane=0, wet=True, base=650)
    nx, ny = LAKE[1][:2]
    for _ in range(5):
        s.put('Duck', nx+rng.gauss(0, 50), ny+rng.gauss(0, 40), layer='LakeLife', gap=15, lane=30, wet=True, base=650)
    for px, py in [(lx, ly), (nx, ny), (mx, my)]:
        s.put('Amb_WaterLakeLight1', px, py, layer='Sounds', gap=0, lane=0, wet=True, base=0)


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
    density *= smooth(60, 180, t['farm'])*~t['yards']
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


def gorge_log(s):
    """A dead tree fallen across the gorge, wedged between its walls about
    halfway down where they close in. Its trunk runs along local x."""
    x, y, z = GORGE_LOG
    add_object(s.m, 'TreeFallDead01', x, y, GORGE_LOG_ANGLE, layer='GorgeLog', z=z-s.ground(x, y)[0],
               extra=[('objectPrototypeScale', 2, GORGE_LOG_SCALE)])
    s.counts['GorgeLog'] += 1


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
        if len(clumps) >= 125:                 # brook, pond and lake
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
    open_ground = (t['woods'] < .1) & (t['sd'] > 40) & (t['lanes'] > 60) & (t['farm'] > 30) & ~t['yards'] & (drift > .15)
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
        if t['woods'][iy, ix] > .05 or t['farm'][iy, ix] < 100 or t['yards'][iy, ix] or math.dist((px, py), (C, C)) < 1000:
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
    weather = b.project.weather
    if b.project.players != len(STARTS):
        raise ValueError(f'map.toml has {b.project.players} players, but the valley has {len(STARTS)} starts')
    print('Shaping the valley, brook and fords...', flush=True)
    t = terrain()
    lane_lines = lanes()+[chaikin(FARM_TRACK, 3)]+lower_lanes()
    lower_houses = lower_house_fronts()
    t['lanes'] = lane_field(t, lane_lines)
    t['paths'] = lane_field(t, footpaths(lane_lines[:2])+[door_path(door, lane) for *_, banks in lower_houses
                                                          for *_, door, lane in banks]
                            + [lake_path(t['sd'], lane_lines)])
    t['farm'] = farm_distance(t)
    yard_masks, t['yards'], t['kitchen_gardens'] = yards(t, cottages(lane_lines[:2], lower_houses))

    # Level the building pads before anything stands on them.
    pads = []
    for _, u, v, _, pad, _ in BUILDINGS:
        for sign in (1, -1):
            pads.append((*xy(sign*u, sign*v), pad))
    pads += [(x, y, pad) for _, x, y, pad, _ in MARKED_HOUSES]
    pads += [(x, y, pad) for _, x, y, _, pad, _ in (FARMHOUSE, BARN)]
    pads += [(x, y, pad) for _, pad, _, banks in lower_houses for x, y, *_ in banks]
    level_pads(t, pads)

    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    t['woods'] = np.zeros(t['z'].shape)
    s = Scenery(m, t, b.assets)
    print('Building the hamlet...', flush=True)
    bridges(s, t)
    gorge_log(s)
    millpond(s, t)
    lower_hamlet(s)              # before the hamlet's scattered props, so they make room for it
    hamlet(s, t)
    marked_houses(s, lane_lines[:2])
    kitchen_gardens(s, t)
    farm(s, t)
    lake_shore(s, t)
    lake_details(s, t)
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
    gardens += farm_plots(t)
    u_, v_ = uv(t['x'], t['y'])
    du, dv = ORCHARD['u'], ORCHARD['v']
    orchard = np.zeros(t['z'].shape, bool)
    for sign in (1, -1):
        orchard |= (sign*u_ > du[0]-50) & (sign*u_ < du[1]+50) & (sign*v_ < dv[0]+50) & (sign*v_ > dv[1]-50)
    labels = materials(t, gardens, orchard, yard_masks)

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
