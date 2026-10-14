"""Brightwater Fold: a two-player dale in Rohan.

Open golden downs round a river, the Brightwater, that comes in from the
north edge and leaves by the south edge. In the middle of the map it parts
round an island knoll and meets again below it. Chalk escarpments flank the
river where it enters and leaves; the two players hold the south-west and
north-east corners.

The playable layout is point-symmetric about the map centre: the river's
lower half, the hills and both starts are the upper half turned through 180
degrees, so both players stand equally far from the island and from every
crossing.

Positions are map units, 10 per terrain cell: x east, y north from the
playable area's south-west corner. Some layouts are written in (u, v): u
runs along the river towards the south-east, v across it towards player 2.
"""
from collections import Counter
import math
import random

import numpy as np

from mapworkshop.mapkit.blank import (add_object, create, set_heights, set_materials, starts, terrain_cell_sizes,
                                      water_plane)
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.variety import spot_random
from mapworkshop.mapkit.ambient import ambient, along
from mapworkshop.mapkit.rivers import add_river, bank_width, point_along
from mapworkshop.mapkit.sites import creep_lair, gollum_spawns, neutral_site, spread
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

WIDTH, HEIGHT = 480, 480       # playable size in cells
BORDER = 30                    # cells of unplayable border around it
SEED = 52203                   # title, description, players and weather are in map.toml
SPAN = (WIDTH-1)*10            # 4790: the last height sample; the map turns onto x -> SPAN-x
C = SPAN/2                     # map centre and centre of symmetry, also the island's centre
WATER = 150.0                  # one water plane; only the river lies below it
GROUND = 172.0                 # the dale floor
BASE = 176.0                   # level of both construction areas
STARTS = [(950, 950), (SPAN-950, SPAN-950)]
BASE_FLAT, BASE_BLEND = 430, 850

# The river's upper half, from beyond the north edge to the island; the lower
# half is the same turned about the centre.
UPSTREAM = [(640, 5400), (720, 4790), (1080, 4420), (960, 3990), (1240, 3620), (1600, 3580),
            (1720, 3180), (2000, 2790), (C, C)]
# The island: an oval along the river (u) with the two arms round it.
ISLAND = dict(along=560, across=300, arm=95)

# Roads. The north road runs from player 1 up the west side, over the upper
# river and east to player 2; the south road is it turned. The island road
# leaves each start for its ford onto the island (u, v).
NORTH_ROAD = [(950, 950), (820, 1650), (930, 2450), (1180, 3080), (1420, 3420), (1420, 3820),
              (1900, 3990), (2650, 3990), (3300, 3930), (SPAN-950, SPAN-950)]
ISLAND_ROAD = [(0, -2043), (0, -1650), (90, -1300), (-60, -950), (40, -620), (0, -348), (0, -40)]
# A creek from the western downs into the river, marked in the viewer (mark 1,
# a freehand path), carried on into the river at one end and out past the
# map's west edge at the other; turned onto player 2's side as well. It cuts a gully through the hills, and where the north road
# crosses it there is a ford with a footbridge.
CREEK = [(-450, 3470), (85, 3403), (156, 3382), (252, 3345), (350, 3313), (445, 3274), (544, 3243), (642, 3217), (742, 3196),
         (843, 3184), (944, 3187), (1045, 3202), (1146, 3224), (1248, 3238), (1348, 3259), (1450, 3263),
         (1548, 3255), (1591, 3246), (1700, 3236)]

# Round hills out on the downs, each turned onto the other half as well,
# crowned with a rock tor and a copse on one flank: x, y, radius, height.
# They stand in the open wedges between the roads, as cover and high ground.
HILLS = [(1450, 2050, 300, 130), (2560, 1430, 280, 115), (520, 2650, 260, 100)]

# Terrain textures. Higher entries blend over lower ones at their edges.
PALETTE = ['GrassRohan04', 'GrassRohan01', 'GrassRohan14', 'GrassRohan21', 'GrassRohan03', 'GrassRohan12',
           'GrassRohan02', 'GrassRohan06', 'GrassRohan22', 'RockRohan03', 'RockRohan01', 'CliffRohan03',
           'DirtRohan05', 'DirtRohan07', 'RockRohan10', 'DirtRohan01', 'RohanDirt01']
(DOWNS, DOWNS_MOTTLED, DOWNS_DRY, STRAW, MEADOW, LUSH, TUSSOCK, FLOWERS, STONY, ROCKY, ROCK, CLIFF,
 MUD, BANK, GRAVEL, LANE_EDGE, LANE) = range(len(PALETTE))

# --- Crossings -----------------------------------------------------------
# A gravel ford on each arm where the island road crosses it, and a wooden
# bridge where each of the north and south roads crosses the river.
FORD_DEPTH = 2.5               # units wade through water up to 5 deep (docs/reference/mapping/navigation)
BRIDGE = 'GenericTreeBridge'   # deck along its local y
# Its model (nbtreebrdge.w3d) reaches 139 each way along the deck, and the
# ramp ends sit 31.5 above the object's base: the base belongs in the bed.
BRIDGE_REACH, BRIDGE_RAMP_END = 139, 31.5
BRIDGE_SCALE = .95
CREEK_BRIDGE_SCALE = .55       # the footbridges over the creek

# --- The hold on the island ---------------------------------------------
# The knoll rises steeply from the water to a level top that reaches to
# within KNOLL_EDGE of the shore. The top is walled round, with a gateway
# where each island road comes up a cutting from its ford. In (u, v); each
# building is turned onto the other half as well. Two golden halls face each
# other across a plaza with a well, and longhouses stand either side of the
# plaza, facing it, all inside the wall's inner face.
KNOLL_EDGE = 74
HALL = ('RohanGoldenHall', -245, 0)
HOLD_HOUSES = [('RohanHouse01', -118, -66), ('RohanHouse04', 122, -66)]
# The side each building's door is on, as the angle of that side's outward
# direction from the model's local +x (`mw items ... --views`): the hall's
# stairs and RohanHouse01's carved gable on -y, the porches of RohanHouse03
# and 04 on -x, RohanHouse05's steps on +y.
DOOR_SIDES = {'RohanGoldenHall': -math.pi/2, 'RohanHouse01': -math.pi/2, 'RohanHouse03': math.pi,
              'RohanHouse04': math.pi, 'RohanHouse05': math.pi/2}
# The wall: a curtain of RohanEdorasWall sections (100 along their local x,
# 71 deep, 74 high) along the island's own contour WALL_LINE in from the
# shore, its outer face on the level top's edge, with a RohanWallTower on
# every corner. The tower is T-shaped (`mw items RohanWallTower --views`
# and its top view): a bar about 52 deep and 121 long along its local x, and
# from it a stem about 49 long and 40 wide to its local -y, the tall,
# carved part of the tower. Each stands as a bastion: turned to the bisector
# of its two runs, its stem pointing out with its front on the wall's outer
# face, its bar astride the wall walk inside. The sections run up to the
# stem's sides. The corners are spaced so that whole sections, scaled close
# to 1, fill each run between two towers; the run across each island road is
# left open for the gateway.
WALL, WALL_LENGTH, WALL_DEPTH = 'RohanEdorasWall', 100, 71
WALL_TOWER, FLAG = 'RohanWallTower', 'RohanFlag'
TOWER_ALONG, TOWER_DEPTH, TOWER_HEIGHT = 121, 101, 115
TOWER_STEM = 40                                # the stem's width, where the sections meet it
GATE_SHARE = .85                               # the gateway's run, as a share of the others: about 80 open between the towers' bars
WALL_LINE = 110

# --- What to hold -------------------------------------------------------
# A signal fire in the hold's plaza; one outpost for each player, placed
# where the walk from that player's start is about OUTPOST_WALK and at least
# OUTPOST_MARGIN shorter than from the other start; and a warg lair in each
# creek pocket (between the creek, the river and the map edge), each guarding
# a flank road's far side. The signal fire and outposts are captured at their
# flag (mapkit.sites): the beacon's stands 76 from it along the river (u), so
# it is as far from either gateway.
BEACON = 'SignalFire'
BEACON_ANGLE = -math.pi/4                       # its flag along +u (mapkit.sites.LINKED)
OUTPOST_WALK, OUTPOST_MARGIN = 1900, 900
LAIR = (650, 3850)                              # turned onto the other side as well
# Gollum's spawn points: three on each half, out on the open downs 850 to
# 2,000 from the starts, as on the stock maps.
GOLLUM_PER_HALF, GOLLUM_CLEAR, GOLLUM_REACH = 3, 850, 2000

# The last details, from the viewer's pins 1 and 2 on the hold's gateways:
# standing torches either side of each gateway, lanterns round the plaza,
# and the hold's ground worn to earth on the plaza and on the paths from the
# doors. TownLamp4 is an iron stand with a burning torch (57 high),
# TownLamp5 a lantern hung from a post (45 high); both are props.
GATE_TORCH, LANTERN = 'TownLamp4', 'TownLamp5'
LANTERNS = [(40, 70), (-40, 70)]               # (u, v) round the plaza, each turned as well
# Warm late-afternoon light: a low golden sun and a cool fill from the sky.
SUN = dict(ambient=(.19, .18, .15), diffuse=(1.0, .86, .62))
FILL = dict(ambient=(0., 0., 0.), diffuse=(.17, .24, .34), direction=(-.64, -.54, -.55))

# --- The horse paddock ---------------------------------------------------
# A paddock on the open downs east of player 1's base, marked in the viewer
# (mark 1, a circle: centre x, y and radius), turned onto player 2's side as
# well. Its fence is not the circle: straight runs between uneven corner
# posts round a lopsided oval inside it, with a gate on the west side, the
# stable just outside the gate with its doors towards it, horses, troughs
# and hay.
PADDOCK = (2060, 1240, 300)
DOOR_SIDES['RohanStable'] = math.pi            # its arched stable doors are on local -x
RAIL, RAIL_LENGTH, RAIL_SCALE = 'ShireFence06', 41, 1.5    # rails along local x, scaled up to read at range
HORSES = ['HorseGrazing', 'HorseGrazing1', 'HorseGrazing2', 'HorseGrazing3']


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


def river_line():
    """The whole river, smoothed."""
    return chaikin(UPSTREAM[:-1]+[(C, C)]+turned(UPSTREAM[:-1])[::-1], 4)


def creek_lines():
    """The creek and its turned copy, smoothed."""
    line = chaikin(CREEK, 2)
    return [line, turned(line)]


def island(x, y):
    """The island's signed distance (negative on it): an oval along the river
    whose shore wobbles with even harmonics only, so it stays point-symmetric."""
    u, v = uv(x, y)
    theta = np.arctan2(v, u)
    oval = (np.sqrt((u/ISLAND['along'])**2+(v/ISLAND['across'])**2)-1)*ISLAND['across']
    return oval-18*np.sin(2*theta+.4)-10*np.sin(4*theta+1.1)


def terrain():
    rows, cols = HEIGHT+2*BORDER, WIDTH+2*BORDER
    y, x = (np.mgrid[0:rows, 0:cols]-BORDER)*10.0
    line = river_line()

    # Water: the river's signed distance (negative in the water). Round the
    # island the channel becomes two arms; the island itself stays land.
    river_d, along = polyline_distance(line, x, y)
    total = sum(math.dist(a, b) for a, b in zip(line, line[1:]))
    middle = np.abs(along-total/2)
    half_width = 62+14*fbm(middle, np.zeros_like(middle), scale=900, seed=SEED+1, octaves=2)
    isle = island(x, y)
    arms = np.abs(isle-ISLAND['arm']/2)-ISLAND['arm']/2
    sd = np.maximum(smooth_min(river_d-half_width, arms, 50), -isle)

    # Rolling downs: broad swells over the whole dale, rising into hills along
    # the edges, combined with their turned copy so both halves match.
    swell = 44*fbm(x+700, y-300, scale=1700, seed=SEED+2, octaves=3)+12*fbm(x, y, scale=480, seed=SEED+3, octaves=3)
    edge = np.minimum(np.minimum(x, SPAN-x), np.minimum(y, SPAN-y))
    reach = 650+220*fbm(x, y, scale=1300, seed=SEED+4, octaves=2)
    downs = (1-smooth(0, 1, edge/reach))**1.3*(70+60*fbm(x-500, y+800, scale=700, seed=SEED+5, octaves=3))
    land = GROUND+.5*(swell+mirror(swell))+np.maximum(downs, mirror(downs))
    # The round hills, their outlines wobbling a little, each with its turned twin.
    for hx, hy, r, h in HILLS:
        d = np.hypot(x-hx, y-hy)+.18*r*fbm(x, y, scale=220, seed=SEED+11, octaves=2)
        hill = h*np.exp(-.5*(d/(.55*r))**2)
        land += hill+mirror(hill)
    for p in STARTS:                               # the hills give way to each base
        land = GROUND+(land-GROUND)*smooth(BASE_BLEND-150, BASE_BLEND+500, np.hypot(x-p[0], y-p[1]))
    # The river's own valley: the downs fall in a long slope towards it, and
    # the escarpments open into a gorge where it passes between them.
    floor = WATER+5
    reach = 520+180*fbm(x+300, y, scale=900, seed=SEED+8, octaves=2)
    land = floor+(land-floor)*smooth(0, 1, np.maximum(sd, 0)/reach)**.75
    # Chalk escarpments either side of the river's gap at the north edge
    # (and, turned, the south edge): ridges that rise behind the valley and
    # end in a steep face where the river cuts through them.
    scarp = np.zeros(x.shape)
    for side in (-1, 1):
        cx, cy = 900+side*760, 4790
        d = np.hypot((x-cx)/1.35, (y-cy)*1.25)
        scarp = np.maximum(scarp, 330*(1-smooth(150, 1150, d+160*fbm(x, y, scale=380, seed=SEED+6+side, octaves=3))))
    scarp = np.maximum(scarp, mirror(scarp))
    land += scarp*smooth(40, 200, sd)
    # The creeks: narrow and of varying width, in a gully of their own with steep sides.
    creek_d = np.min([polyline_distance(c, x, y)[0] for c in creek_lines()], axis=0)
    creek_sd = creek_d-(18+8*fbm(x, y, scale=420, seed=SEED+9, octaves=2))
    land = floor+(land-floor)*smooth(0, 1, np.maximum(creek_sd, 0)/(140+40*fbm(x, y, scale=400, seed=SEED+10,
                                                                                    octaves=2)))**.8
    sd = smooth_min(sd, creek_sd, 40)
    # The island rises into a knoll with a level top for the hold.
    knoll = 1-smooth(-KNOLL_EDGE, -8, isle)
    land = land*(1-knoll)+(GROUND+64)*knoll

    # Banks: easing down to the waterline, steep round the knoll; the bed
    # falls to about 22 deep.
    bank_width = 60+30*smooth(-.3, .3, fbm(x, y, scale=600, seed=SEED+7, octaves=2))
    bank_width = np.where(isle < 0, 28, bank_width)
    t = np.clip(sd/bank_width, 0, 1)
    z = np.where(sd > 0, (WATER-1)+(land-(WATER-1))*t**1.4, WATER-2-20*smooth(0, 45, -sd))

    # The knoll's edge, from the shore in: a scree apron at the waterline
    # steepening into the face, which rounds over into the level top by
    # KNOLL_EDGE in, so the wall stands on level ground. Nothing about it is
    # even: where the face begins and ends wanders along the shore in
    # buttresses and bays, the apron dips under the water in coves and stands
    # out of it as rocky shelves, rock ribs and gullies run down the face, and
    # the face is rough. Every noise is made symmetric, like the map.
    sym = lambda a: .5*(a+mirror(a))
    inward = -isle
    u, v = uv(x, y)
    theta = np.arctan2(v, u)
    wander = sym(fbm(x, y, scale=130, seed=SEED+12, octaves=3))
    foot = np.clip(9+16*wander, 0, 28)
    brow = np.clip(foot+46+14*sym(fbm(x+400, y-300, scale=60, seed=SEED+13, octaves=2)), 38, KNOLL_EDGE-3)
    f = np.clip((inward-foot)/(brow-foot), 0, 1)
    rise = f*f*(3-2*f)                              # flatter at the apron and the lip, steepest between
    top = GROUND+64
    shore = WATER-2.5+8*sym(fbm(x, y, scale=85, seed=SEED+15, octaves=2))   # coves below the water, shelves above
    warp = 2.2*sym(fbm(x, y, scale=160, seed=SEED+16, octaves=2))
    ribs = np.cos(18*theta+warp)*(.6+.4*sym(fbm(x-700, y, scale=90, seed=SEED+17, octaves=2)))
    rough = sym(fbm(x, y, scale=22, seed=SEED+14, octaves=2))
    edge = shore+(top-shore)*rise+(9*ribs+7*rough)*np.sin(np.pi*f)
    z = np.where((isle < 0) & (inward < KNOLL_EDGE), edge, z)
    t_edge = dict(foot=foot, brow=brow)

    # Both construction areas: level, at the same height, easing into the dale.
    for p in STARTS:
        blend = (1-smooth(BASE_FLAT, BASE_BLEND, np.hypot(x-p[0], y-p[1])))**.8
        z = z*(1-blend)+BASE*blend
    return dict(x=x, y=y, z=z, sd=sd, isle=isle, river=line, **t_edge)


def roads():
    """Every road as a smoothed polyline in map units, both halves."""
    north = chaikin(NORTH_ROAD, 3)
    island_road = chaikin([xy(u, v) for u, v in ISLAND_ROAD], 3)
    return [north, chaikin(turned(NORTH_ROAD), 3), island_road, turned(island_road)]


def road_field(t, lines):
    d = np.full(t['z'].shape, np.inf)
    for line in lines:
        d = np.minimum(d, polyline_distance(line, t['x'], t['y'])[0])
    return d


def materials(t):
    x, y, z, sd = t['x'], t['y'], t['z'], t['sd']
    gy, gx = np.gradient(z, 10); slope = np.hypot(gx, gy)
    broad = fbm(x, y, scale=1100, seed=SEED+20, octaves=3)
    mid = fbm(x+2000, y, scale=320, seed=SEED+21, octaves=3)
    fine = fbm(x, y+2000, scale=90, seed=SEED+22, octaves=2)
    v = .65*broad+.35*mid+.1*fine
    # The downs: golden grass in broad drifts, drier and paler in places.
    base_d = np.min([np.hypot(x-px, y-py) for px, py in STARTS], axis=0)
    labels = np.full(z.shape, DOWNS, dtype='u2')
    labels[(v < -.32) & (base_d > BASE_BLEND)] = DOWNS_MOTTLED
    labels[v > .2] = DOWNS_DRY
    labels[v > .48] = STRAW
    # Paler straw on the crests, greener grass in the hollows.
    labels[(t['relief'] > 4+2*fine) & (fine > -.3)] = STRAW
    labels[(t['relief'] < -4+2*fine) & (sd > 150) & (fine > -.2)] = MEADOW
    # Greener grass in the river's valley, lush by the water.
    labels[(sd < 320+140*mid) & (fine > -.15)] = MEADOW
    labels[(sd < 150+60*mid) & (fine > .05)] = LUSH
    # Tussocks on the hills, flowers in patches on the lower downs.
    hill = z > GROUND+60+25*mid
    labels[hill & (fine > -.2)] = TUSSOCK
    labels[~hill & (mid > .38) & (fine > 0) & (sd > 200)] = FLOWERS
    # Steeper ground turns stony, then rocky; the scarps' faces are cliff.
    labels[slope > .32+.06*fine] = STONY
    labels[slope > .5+.08*fine] = ROCKY
    labels[slope > .78+.1*fine] = ROCK
    labels[slope > 1.15] = CLIFF
    # Banks: a grassy earth fringe, dark mud at the waterline and below.
    edge = fbm(x, y, scale=70, seed=SEED+23, octaves=2)
    labels[(sd < 26+14*edge) & (sd > -2) & (fine > -.25)] = BANK
    labels[(sd < 9+6*edge) & (sd > -2)] = MUD
    labels[z < WATER-1.5] = MUD
    # The knoll's edge: scree on the apron, rock on the face (the streakier
    # cliff texture only on its steepest cells), tussock grass on the rounded lip.
    knoll = t['isle'] < 2
    inward = -t['isle']
    scree = fbm(x+900, y-200, scale=55, seed=SEED+24, octaves=2)
    apron = knoll & (inward < t['foot']+5+4*fine) & (z > WATER+.3)
    labels[apron & (scree > -.15)] = GRAVEL
    labels[apron & (scree > .35)] = STONY
    labels[apron & (scree <= -.15)] = BANK
    labels[knoll & (z <= WATER+.3)] = MUD
    labels[knoll & (slope > .5+.1*fine) & (inward >= t['foot']+2)] = ROCK
    labels[knoll & (slope > 1.8+.2*fine)] = CLIFF
    # Grassy ledges where the face eases, tussock grass over the lip.
    face = knoll & (inward > t['foot']+6) & (inward < t['brow']-4)
    labels[face & (slope < .42+.08*fine) & (fine > -.2)] = TUSSOCK
    labels[knoll & (inward > t['brow']-5+3*fine) & (inward < KNOLL_EDGE+6) & (slope > .12)] = TUSSOCK
    # The fords: gravel on the shelf and up the road on both banks.
    labels[(t['shelf'] > .25) & (z < WATER+1.5)] = GRAVEL
    # The hold's top: worn grass, a trodden plaza round the well and paths to the doors.
    top = t['isle'] < -100
    labels[top & (fine > -.2)] = BANK
    plaza = np.hypot(*uv(x, y))
    labels[top & ((plaza < 115+20*fine) | (t['hold_paths'] < 18+6*fine))] = LANE_EDGE
    labels[top & ((plaza < 80+15*fine) | (t['hold_paths'] < 9+4*fine))] = LANE
    # Each construction area: one even golden grass.
    home = base_d < BASE_FLAT+80+40*fine
    labels[home & ~np.isin(labels, [DOWNS, DOWNS_DRY])] = DOWNS
    # The paddocks: grazed grass, worn along the fence where the horses walk
    # and bare at the gate.
    labels[(np.abs(t['paddock']) < 16+6*fine) & (fine > -.3)] = BANK
    gate_d = np.min([np.hypot(x-gx, y-gy) for gx, gy in t['paddock_gates']], axis=0)
    labels[gate_d < 85+20*fine] = BANK
    labels[gate_d < 50+15*fine] = LANE
    # Trodden yards round the outposts and lairs.
    dry = z > WATER+.5
    labels[(t['sites'] < 130+30*fine) & dry & (fine > -.3)] = BANK
    labels[(t['sites'] < 80+20*fine) & dry] = LANE
    # Roads: packed earth with a worn grassy fringe, a little wider and
    # narrower along their length, tapering away into each base.
    taper = smooth(BASE_FLAT-300, BASE_FLAT+150, base_d)*(1+.3*mid)
    labels[(t['roads'] < (34+9*fine)*taper) & dry & (fine > -.35)] = LANE_EDGE
    labels[(t['roads'] < (17+5*fine)*taper) & dry] = LANE
    # Tracks from each stable to the road.
    labels[(t['paths'] < 13+4*fine) & dry & (fine > -.3)] = LANE_EDGE
    labels[(t['paths'] < 6+3*fine) & dry] = LANE
    # The fords' gravel runs up the road on both banks.
    labels[(t['ford_d'] < 170) & (t['roads'] < 22+5*fine) & dry & (t['isle'] > 0)] = GRAVEL
    return labels


def relief(t):
    """How far each sample stands above (positive: crests) or below
    (negative: hollows) the ground about 150 round it."""
    def blur(a, k):
        for _ in range(4):
            a = (a+np.roll(a, k, 0)+np.roll(a, -k, 0)+np.roll(a, k, 1)+np.roll(a, -k, 1))/5
        return a
    z = t['z']
    t['relief'] = blur(z, 1)-blur(z, 6)


def ford_points():
    """Where the island road crosses each arm: the middle of the arm on the
    line u = 0, found from the island's own shore. Player 1's ford first."""
    fords = []
    for sign in (-1, 1):
        v = np.arange(0, 700, .5)
        x, y = xy(0, sign*v)
        k = int(np.argmin(np.abs(island(np.asarray(x), np.asarray(y))-ISLAND['arm']/2)))
        fords.append(xy(0, sign*float(v[k])))
    return fords


def road_crossings(waters):
    """Where the north and south roads cross any of the given water lines:
    (point, the road's direction there) for each crossing."""
    found = []
    for road in roads()[:2]:
        for water in waters:
            for (ax, ay), (bx, by) in zip(road, road[1:]):
                for (cx, cy), (dx, dy) in zip(water, water[1:]):
                    rx, ry, sx, sy = bx-ax, by-ay, dx-cx, dy-cy
                    cross = rx*sy-ry*sx
                    if cross == 0:
                        continue
                    p = ((cx-ax)*sy-(cy-ay)*sx)/cross; q = ((cx-ax)*ry-(cy-ay)*rx)/cross
                    if 0 <= p <= 1 and 0 <= q <= 1:
                        found.append(((ax+p*rx, ay+p*ry), math.atan2(ry, rx)))
    return found


def crossings(t):
    """Shape the fords and the island's ramps: a wide gravel shelf FORD_DEPTH
    deep with long ramps down the banks, and a cutting up the knoll's side
    along each island road, so the climb to the hold stays gentle."""
    x, y = t['x'], t['y']
    fords = ford_points()                         # the creeks are crossed only on their footbridges
    ford_d = np.min([np.hypot(x-fx, y-fy) for fx, fy in fords], axis=0)
    shelf = 1-smooth(70, 140, ford_d)
    ramp = 1-smooth(130, 300, ford_d)
    z = t['z']
    z = np.where(t['sd'] <= 0, z*(1-shelf)+(WATER-FORD_DEPTH)*shelf, z)
    off_island = t['isle'] > 0                    # the island side is the cutting's
    z = np.where((t['sd'] > 0) & off_island,
                 z*(1-ramp)+np.minimum(z, WATER-FORD_DEPTH+.09*np.maximum(t['sd'], 0))*ramp, z)
    # The cutting: from the ford's island bank, through the gateway, up to
    # the level top inside it, narrow at the gate to leave the towers whole
    # and opening out towards the water.
    top = GROUND+64
    u, v = uv(x, y)
    for sign in (-1, 1):
        along = sign*v                                    # from the gateway (about 200) out to the ford (about 348)
        level = top+(WATER+2-top)*smooth(110, 330, along)
        half = 22+38*smooth(200, 330, along)
        width = 1-smooth(half, half+22, np.abs(u))
        inside = (along > 90) & (along < 360) & (t['isle'] < 10)
        z = np.where(inside, z*(1-width)+np.minimum(z, level)*width, z)
    t['z'] = z
    t['fords'], t['ford_d'], t['shelf'] = fords, ford_d, shelf


class Scenery:
    """Object placement with spacing, water, road and base checks."""

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

    def ground(self, x, y):
        """Height, distance to the nearest road, and distance from the water."""
        iy, ix = round(y/10)+BORDER, round(x/10)+BORDER
        return float(self.t['z'][iy, ix]), float(self.t['roads'][iy, ix]), float(self.t['sd'][iy, ix])

    def put(self, template, x, y, angle=None, layer='', gap=20, road=40, wet=False, base=600,
            scale=None, solid=0, z=0, extra=()):
        """Place one object if the spot is clear. Its size (trees and shrubs)
        and rotation, unless given, come from its own spot_random, so they do
        not change when other placements do."""
        if not (80 < x < SPAN-80 and 80 < y < SPAN-80):
            return False
        height, road_d, sd = self.ground(x, y)
        if road_d < road or (not wet and (height < WATER+1.5 or sd < 6)):
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
                low, mode, high = (.8, 1., 1.3) if kind == 'tree' else (.85, 1., 1.15)
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

    def pair(self, template, u, v, toward=None, **kw):
        """Place at (u, v) and turned onto the other half. `toward` (u, v): the
        point the building's door faces (DOOR_SIDES)."""
        placed = 0
        for sign in (1, -1):
            x, y = xy(sign*u, sign*v)
            angle = None
            if toward is not None:
                tx, ty = xy(sign*toward[0], sign*toward[1])
                angle = math.atan2(ty-y, tx-x)-DOOR_SIDES[template]
            placed += self.put(template, x, y, angle=angle, **kw)
        return placed


def bridges(s, t):
    """A wooden bridge where each road crosses the river or a creek, its deck
    along the road. Both landings are levelled to one height and the base is
    sunk so the ramp ends lie flush on them. Each river bridge has standing
    torches at both ends, and the wedge between it and the creek's footbridge
    a cart and hay: the bridgehead. The decks are kept for the walking checks."""
    s.kind(BRIDGE)
    river = road_crossings([river_line()])
    creek = road_crossings(creek_lines())
    spans = [(p, axis, BRIDGE_SCALE) for p, axis in river]+[(p, axis, CREEK_BRIDGE_SCALE) for p, axis in creek]
    t['decks'] = []
    for i, ((fx, fy), axis, scale) in enumerate(spans):
        reach = BRIDGE_REACH*scale
        ends = [(fx+math.cos(axis)*d, fy+math.sin(axis)*d) for d in (-reach, reach)]
        landing = float(np.mean([s.ground(*e)[0] for e in ends]))
        for ex, ey in ends:
            d = np.hypot(t['x']-ex, t['y']-ey)
            blend = (1-smooth(40, 95, d))*(t['z'] > WATER)
            t['z'] = t['z']*(1-blend)+landing*blend
        base = landing-BRIDGE_RAMP_END*scale-.5
        add_object(s.m, BRIDGE, fx, fy, axis-math.pi/2, layer='Bridges', z=base-s.ground(fx, fy)[0],
                   extra=[('objectName', 3, f'Brightwater_Bridge_{i+1}'),
                          ('objectPrototypeScale', 2, scale)])
        s.buckets.setdefault((int(fx//100), int(fy//100)), []).append((fx, fy, 140*scale))
        s.counts['Bridges'] += 1
        t['decks'].append((fx, fy, axis, reach, 30*scale+10))
    torches = 0
    rng = random.Random(SEED+50)
    for ((fx, fy), axis), ((cx, cy), _) in zip(river, creek):
        nx, ny = -math.sin(axis), math.cos(axis)
        aside = 30*BRIDGE_SCALE+10+20               # past the deck's half-width
        for d in (-1.05, 1.05):
            for side in (-1, 1):
                torches += s.put(GATE_TORCH, fx+math.cos(axis)*d*BRIDGE_REACH*BRIDGE_SCALE+nx*side*aside,
                                 fy+math.sin(axis)*d*BRIDGE_REACH*BRIDGE_SCALE+ny*side*aside, layer='Bridgeheads',
                                 gap=10, road=0, base=0, wet=True)
        mx, my = (fx+cx)/2, (fy+cy)/2
        for k, (template, off, along) in enumerate([('Cart01', 70, 0), ('Haystack', 100, 22), ('Haystack', 112, -16)]):
            s.put(template, mx+nx*off+math.cos(axis)*along, my+ny*off+math.sin(axis)*along,
                  angle=axis+rng.uniform(-1, 1), layer='Bridgeheads', gap=14, road=40, base=0,
                  scale=1.4 if template == 'Haystack' else None)
    if torches != 4*len(river):
        raise ValueError(f'Only {torches} of {4*len(river)} bridge torches found room')


def hold(s, t):
    """The walled hold on the knoll: halls, longhouses, the well, its stores,
    and the wall round the level top with a gateway at each island road."""
    rng = random.Random(SEED+100)
    template, u, v = HALL
    if s.pair(template, u, v, toward=(0, 0), layer='Hold', gap=90, road=0, base=0, solid=70) != 2:
        raise ValueError('No room for the halls')
    for template, u, v in HOLD_HOUSES:
        if s.pair(template, u, v, toward=(u, 0), layer='Hold', gap=75, road=30, base=0, solid=50) != 2:
            raise ValueError(f'No room for {template} at ({u}, {v})')
    fx, fy = neutral_site(s.m, BEACON, C, C, angle=BEACON_ANGLE)
    s.solids.append((C, C, 45))
    s.buckets.setdefault((int(C//100), int(C//100)), []).append((C, C, 55))
    s.buckets.setdefault((int(fx//100), int(fy//100)), []).append((fx, fy, 22))
    s.counts['Objectives'] += 2
    # Flags either side of each hall's steps (inside the hall's own spacing, so placed as they are).
    for side in (-1, 1):
        for sign in (1, -1):
            x, y = xy(sign*(HALL[1]+70), sign*side*48)
            add_object(s.m, FLAG, x, y, rng.uniform(0, math.tau), layer='HoldFlags')
            s.counts['HoldFlags'] += 1
    corners = wall_corners()
    for template, (x, y), angle, scale, z in wall_pieces(corners):
        extra = [('objectPrototypeScale', 2, round(scale, 3))] if scale != 1 else []
        add_object(s.m, template, x, y, angle, layer='HoldWall', extra=extra, z=z)
        s.counts['HoldWall'] += 1
        if template == WALL_TOWER:
            s.buckets.setdefault((int(x//100), int(y//100)), []).append((x, y, 70))
    # Torches either side of each gateway, just inside the towers' stems,
    # clear of the cutting: from the gateway's own corners (either side of u = 0).
    gate_v = max(abs(v) for u, v in corners if abs(u) < 160)-(TOWER_DEPTH-WALL_DEPTH/2)-14
    for side in (-1, 1):
        s.pair(GATE_TORCH, side*30, -gate_v, layer='HoldLights', gap=10, road=0, base=0)
    for u, v in LANTERNS:
        s.pair(LANTERN, u, v, layer='HoldLights', gap=10, road=0, base=0)
    for template, u, v, spread, n in [('Haystack', -200, -110, 12, 3), ('Barrel', 45, -125, 8, 3),
                                      ('Crate01', -45, -125, 8, 2), ('Cart01', 200, -80, 0, 1)]:
        for _ in range(n):
            for _try in range(12):
                if s.pair(template, u+rng.gauss(0, spread), v+rng.gauss(0, spread), layer='HoldStores', gap=18,
                          road=22, base=0, scale=1.4 if template == 'Haystack' else None):
                    break


def wall_corners():
    """The wall's corner posts (towers) in (u, v): on the island's contour
    WALL_LINE in from its shore, so that the straight runs between them are
    all the same length, except the run across each island road, the
    gateway, which is GATE_SHARE of one. An even count, so the halves match."""
    angles = np.linspace(0, math.tau, 2880, endpoint=False)
    r = np.linspace(0, 900, 1801)
    line = []
    for a in angles:
        x, y = xy(r*math.cos(a), r*math.sin(a))
        f = island(np.asarray(x), np.asarray(y))
        k = int(np.argmax(f > -WALL_LINE))
        reach = float(np.interp(-WALL_LINE, f[k-1:k+1], r[k-1:k+1]))
        line.append((reach*math.cos(a), reach*math.sin(a)))
    line = np.array(line)
    ring = np.vstack([line, line[:1]])
    arc = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(ring, axis=0).T))])
    perimeter = arc[-1]

    def point(at):
        at = at % perimeter
        return np.array([np.interp(at, arc, ring[:, 0]), np.interp(at, arc, ring[:, 1])])
    count = 2*round(perimeter/(2*.9*WALL_LENGTH+TOWER_STEM)/2)
    gate = arc[len(angles)//4]                     # where the contour crosses +v (90 degrees)
    share = np.array([GATE_SHARE if k in (0, count//2) else 1.0 for k in range(count)])
    spans = share/share.sum()*perimeter
    for _ in range(40):                            # even out the straight runs, run 0 centred on the gateway
        bounds = gate-spans[0]/2+np.concatenate([[0], np.cumsum(spans)[:-1]])
        corners = [point(b) for b in bounds]
        chords = np.array([np.linalg.norm(corners[(k+1) % count]-corners[k]) for k in range(count)])
        spans *= share*chords.sum()/share.sum()/chords
        spans *= perimeter/spans.sum()
    return [(float(u), float(v)) for u, v in corners]


def wall_pieces(corners):
    """Every piece of the wall: (template, map position, angle, scale, z
    offset). A tower and its flag on each corner, and on each run between
    two towers whole sections end to end, scaled to fill it. The runs that
    straddle u = 0 are the gateways."""
    pts = [np.array(xy(u, v)) for u, v in corners]
    n = len(pts)
    gate = [corners[i][0]*corners[(i+1) % n][0] < 0 and abs(corners[i][1]) > abs(corners[i][0]) for i in range(n)]
    out = []
    for k in range(n):
        prev, here, nxt = pts[(k-1) % n], pts[k], pts[(k+1) % n]
        d1, d2 = (here-prev)/np.linalg.norm(here-prev), (nxt-here)/np.linalg.norm(nxt-here)
        along = (d1+d2)/np.linalg.norm(d1+d2)
        outward = np.array([along[1], -along[0]])   # the corners run counter-clockwise: right is out
        # Local -y outward (angle = the run's direction), the stem's front on
        # the wall's outer face; the flag on the stem's top.
        centre = here+outward*(WALL_DEPTH/2-TOWER_DEPTH/2)
        angle = math.atan2(along[1], along[0])
        out.append((WALL_TOWER, (float(centre[0]), float(centre[1])), angle, 1, 0))
        top = centre+outward*TOWER_DEPTH/4
        out.append((FLAG, (float(top[0]), float(top[1])), angle, 1, TOWER_HEIGHT-6))
    for i in range(n):
        if gate[i]:
            continue
        a, b = pts[i], pts[(i+1) % n]
        d = (b-a)/np.linalg.norm(b-a)
        start, end = a+d*(TOWER_STEM/2-2), b-d*(TOWER_STEM/2-2)
        length = float(np.linalg.norm(end-start))
        count = max(1, round(length/WALL_LENGTH))
        for k in range(count):
            mid = start+d*length*(k+.5)/count
            out.append((WALL, (float(mid[0]), float(mid[1])), math.atan2(d[1], d[0]), length/count/WALL_LENGTH, 0))
    return out


def walk_grid(t, solids=()):
    """Walkable 20-unit cells (mapkit.checks.strategy): ground and water up to
    5 deep, the bridge decks, not the buildings."""
    from mapworkshop.mapkit.checks.strategy import STEP
    z = t['z'][BORDER:BORDER+HEIGHT, BORDER:BORDER+WIDTH]
    blocked = z < WATER-5
    yy, xx = np.indices(z.shape); px, py = xx*10., yy*10.
    for fx, fy, axis, reach, half in t.get('decks', ()):
        along = (px-fx)*math.cos(axis)+(py-fy)*math.sin(axis)
        across = -(px-fx)*math.sin(axis)+(py-fy)*math.cos(axis)
        blocked &= ~((np.abs(along) < reach) & (np.abs(across) < half))
    for sx, sy, r in solids:
        blocked |= np.hypot(px-sx, py-sy) < r
    k = int(STEP/10); gh, gw = HEIGHT//k, WIDTH//k
    walk = blocked[:gh*k, :gw*k].reshape(gh, k, gw, k).mean(axis=(1, 3)) < .5
    gy, gx = np.indices(walk.shape)
    return walk, (gx+.5)*STEP, (gy+.5)*STEP


def neutral_sites(t):
    """Each player's outpost site (player 1's chosen by walking distance, player
    2's its turned copy) and the two lairs; their ground is levelled and
    t['sites'] holds the distance to the nearest one."""
    from mapworkshop.mapkit.checks.strategy import distance_field
    walk, wx, wy = walk_grid(t)
    own, other = (distance_field(walk, p) for p in STARTS)
    def sample(field):
        iy = np.clip((wy/10).astype(int)+BORDER, 0, field.shape[0]-1)
        ix = np.clip((wx/10).astype(int)+BORDER, 0, field.shape[1]-1)
        return field[iy, ix]
    gz = sample(t['z'])
    gy, gx = np.gradient(gz, 20.0)
    level = np.hypot(gx, gy) < .08
    for _ in range(3):                             # level for about 60 round, not just at the point
        level &= np.roll(level, 1, 0) & np.roll(level, -1, 0) & np.roll(level, 1, 1) & np.roll(level, -1, 1)
    base_d = np.hypot(wx-STARTS[0][0], wy-STARTS[0][1])
    with np.errstate(invalid='ignore'):            # cells reached from neither start are inf - inf
        margin = other-own
    ok = (walk & level & np.isfinite(own) & (margin > OUTPOST_MARGIN) & (base_d > 1100) & (wx+wy < SPAN-400)
          & (sample(t['sd']) > 220) & (sample(t['roads']) > 170) & (sample(t['paddock']) > 230))
    if not ok.any():
        raise ValueError('No outpost site for player 1')
    cost = np.where(ok, np.abs(own-OUTPOST_WALK), np.inf)
    k = np.unravel_index(int(np.argmin(cost)), cost.shape)
    outpost = (float(wx[k]), float(wy[k]))
    sites = dict(outposts=[outpost, (SPAN-outpost[0], SPAN-outpost[1])], lairs=[LAIR, (SPAN-LAIR[0], SPAN-LAIR[1])])
    pads = [(x, y, 130) for x, y in sites['outposts']]+[(x, y, 90) for x, y in sites['lairs']]
    x, y = t['x'], t['y']
    for px, py, radius in pads:
        d = np.hypot(x-px, y-py)
        target = float(np.median(t['z'][d < radius]))
        blend = (1-smooth(radius, radius+120, d))*smooth(0, 30, t['sd'])
        t['z'] = t['z']*(1-blend)+target*blend
    t['sites'] = np.min([np.hypot(x-px, y-py) for px, py, _ in pads], axis=0)
    return sites


def objectives(s, t, sites):
    """The outposts with their flags and a little homestead round each, and
    the warg lairs among rocks."""
    rng = random.Random(SEED+900)
    for (x, y), (px, py) in zip(sites['outposts'], STARTS):
        facing = math.atan2(py-y, px-x)+math.pi/2  # its local -y side towards its player
        fx, fy = neutral_site(s.m, 'Outpost', x, y, angle=facing)
        s.buckets.setdefault((int(x//100), int(y//100)), []).append((x, y, 130))
        s.buckets.setdefault((int(fx//100), int(fy//100)), []).append((fx, fy, 22))
        s.solids.append((x, y, 75))
        s.counts['Objectives'] += 2
    for (x, y) in sites['lairs']:
        creep_lair(s.m, 'WargLair', x, y, rng.uniform(0, math.tau))
        s.buckets.setdefault((int(x//100), int(y//100)), []).append((x, y, 110))
        s.solids.append((x, y, 55))
        s.counts['Objectives'] += 1
    # Homesteads and rocks: the same round each site of a pair, turned.
    (ox, oy), (lx, ly) = sites['outposts'][0], sites['lairs'][0]
    yard = [('Haystack', 150, .4), ('Haystack', 168, .65), ('Haystack', 160, .9), ('Cart01', 160, 2.3),
            ('Barrel', 145, 3.4), ('Barrel', 150, 3.6), ('Crate01', 155, 4.0)]
    for template, r, a in yard:
        for sign in (1, -1):
            x, y = ox+r*math.cos(a), oy+r*math.sin(a)
            if sign < 0:
                x, y = SPAN-x, SPAN-y
            s.put(template, x, y, layer='Homesteads', gap=14, road=30, base=0,
                  scale=1.4 if template == 'Haystack' else None)
    rocks = [f'EdorasRock{k:02d}' for k in (2, 3, 6, 9, 11, 16)]
    for k in range(7):
        a, r = k*math.tau/7+rng.uniform(-.3, .3), rng.uniform(95, 140)
        template, scale = rng.choice(rocks), rng.uniform(.6, 1.1)
        for sign in (1, -1):
            x, y = lx+r*math.cos(a), ly+r*math.sin(a)
            if sign < 0:
                x, y = SPAN-x, SPAN-y
            s.put(template, x, y, layer='LairRocks', gap=40, road=40, base=0, z=-2, scale=scale)


def paddock_outline():
    """The fence's corner posts round player 1's paddock: eleven at uneven
    angles on a lopsided oval within the marked circle. The other paddock's
    are these turned."""
    cx, cy, r = PADDOCK
    rng = random.Random(SEED+610)
    corners = []
    for k in range(11):
        a = (k+rng.uniform(-.3, .3))*math.tau/11
        reach = r*(.84+.1*math.cos(2*(a-.6))+.05*math.sin(3*a+1.3))
        corners.append((cx+reach*math.cos(a), cy+reach*math.sin(a)))
    return corners


def hold_paths(t):
    """Distance from every sample to the paths from the hold's doors to its
    well, both halves."""
    doors = [(HALL[1]+60, 0)]+[(u, v+50) for _, u, v in HOLD_HOUSES]
    lines = []
    for u, v in doors:
        line = [xy(u, v), xy(u*.5, v*.35), xy(0, 0)]
        lines += [line, turned(line)]
    return road_field(t, lines)


def paddock_distance(t):
    """Distance from every sample to the nearest paddock's fence (negative inside)."""
    x, y = t['x'], t['y']
    best = np.full(x.shape, np.inf)
    for corners in (paddock_outline(), turned(paddock_outline())):
        ring = corners+corners[:1]
        d = polyline_distance(ring, x, y)[0]
        inside = np.zeros(x.shape, bool)
        for (ax, ay), (bx, by) in zip(ring, ring[1:]):
            crosses = (ay > y) != (by > y)
            inside ^= crosses & (x < ax+(y-ay)*(bx-ax)/np.where(by == ay, 1e-9, by-ay))
        best = np.minimum(best, np.where(inside, -d, d))
    return best


def paddock(s, t):
    """The paddock at mark 1 and its turned twin: rails round the circle with
    a gate towards the stable, horses grazing, troughs and haystacks."""
    rng = random.Random(SEED+600)
    cx, cy, r = PADDOCK
    t['paddock_gates'], tracks = [], []
    for sign in (1, -1):
        ox, oy = (cx, cy) if sign > 0 else (SPAN-cx, SPAN-cy)
        west = math.pi if sign > 0 else 0.0        # the gate's side, turned with the paddock
        corners = paddock_outline() if sign > 0 else turned(paddock_outline())
        gate = (ox+math.cos(west)*r, oy+math.sin(west)*r)
        bays = []
        for (ax, ay), (bx, by) in zip(corners, corners[1:]+corners[:1]):
            # Each straight run filled with whole bays, stretched a little to fit.
            length = math.dist((ax, ay), (bx, by))
            n = max(1, round(length/(RAIL_LENGTH*RAIL_SCALE)))
            for k in range(n):
                f = (k+.5)/n
                bays.append((ax+(bx-ax)*f, ay+(by-ay)*f, math.atan2(by-ay, bx-ax), length/n/RAIL_LENGTH))
        nearest = min(range(len(bays)), key=lambda k: math.dist(bays[k][:2], gate))
        for k, (bx, by, angle, scale) in enumerate(bays):
            if k == nearest:
                continue                           # the gate
            add_object(s.m, RAIL, bx, by, angle+rng.uniform(-.03, .03), layer='Paddock',
                       extra=[('objectPrototypeScale', 2, round(scale, 3))])
            s.counts['Paddock'] += 1
        gate = bays[nearest][:2]
        t['paddock_gates'].append(gate)
        s.buckets.setdefault((int(ox//100), int(oy//100)), []).append((ox, oy, r+20))
        gx, gy = gate[0]+math.cos(west)*85, gate[1]+math.sin(west)*85
        # A worn track from the stable's side to the nearest road.
        lane = np.concatenate([np.array(line) for line in roads()])
        start = np.array((gx, gy))+np.array((-math.sin(west), math.cos(west)))*60
        end = lane[np.argmin(np.hypot(*(lane-start).T))]
        middle = (start+end)/2+np.array((math.cos(west), math.sin(west)))*25
        tracks.append(chaikin([tuple(start), tuple(middle), tuple(end)], 3))
        t.setdefault('stables', []).append((gx, gy))
        if not s.put('RohanStable', gx, gy, angle=west+math.pi-DOOR_SIDES['RohanStable'], layer='Paddock',
                     gap=70, road=60, base=0, solid=60):
            raise ValueError(f'No room for the stable at ({gx:.0f}, {gy:.0f})')
        # Three small herds, each grazing roughly the same way.
        for herd in range(3):
            a, d = west+math.pi+(herd-1)*1.1+rng.uniform(-.3, .3), r*rng.uniform(.25, .6)
            hx, hy, facing = ox+d*math.cos(a), oy+d*math.sin(a), rng.uniform(0, math.tau)
            for k in range(rng.randint(3, 5)):
                add_object(s.m, HORSES[(herd+k) % 4], hx+rng.gauss(0, 28), hy+rng.gauss(0, 28),
                           facing+rng.uniform(-.7, .7), layer='Paddock')
                s.counts['Paddock'] += 1
        for k, (a, d) in enumerate([(west+.5, .55), (west-.6, .5)]):
            add_object(s.m, 'FeedingTroughs', ox+d*r*math.cos(a), oy+d*r*math.sin(a), a, layer='Paddock')
        # Hay stacked beside the stable, on the side away from the gate's path.
        side = (-math.sin(west), math.cos(west))
        for k in range(4):
            off, back = 80+k*22+rng.uniform(-5, 5), rng.uniform(-25, 25)
            add_object(s.m, 'Haystack', gx+side[0]*off+math.cos(west)*back, gy+side[1]*off+math.sin(west)*back,
                       rng.uniform(0, math.tau), layer='Paddock',
                       extra=[('objectPrototypeScale', 2, round(rng.uniform(1.3, 1.6), 3))])
        s.counts['Paddock'] += 2+4
    t['paths'] = road_field(t, tracks)


def scenery(s, t):
    """Pine copses on the hills, the round hills' crowns, rock outcrops, drifts
    of bushes in the hollows, reeds by the water and boulders at the knoll's foot."""
    rng = random.Random(SEED+400)
    x, y, z = t['x'], t['y'], t['z']
    clump = fbm(x+500, y-300, scale=380, seed=SEED+401, octaves=3)
    rise = 25*fbm(x-900, y+400, scale=600, seed=SEED+406, octaves=2)
    density = smooth(20+rise, 90+rise, z-GROUND)*np.clip(2.4*clump-.05, 0, 1)*smooth(90, 200, t['sd'])
    keep_off = smooth(70, 160, t['roads'])*(t['isle'] > 60)*smooth(60, 200, t['paddock'])*smooth(120, 260, t['sites'])
    density *= keep_off
    density = np.maximum(density, mirror(density))
    for p in STARTS:
        density *= smooth(BASE_BLEND-150, BASE_BLEND+150, np.hypot(x-p[0], y-p[1]))
    t['woods'] = density
    pines = ['PTreePine01', 'PTreePine02', 'PTreePine01']

    def copse(cx, cy, n, spread, layer='Copses'):
        placed = 0
        for _ in range(n*6):
            if placed >= n:
                break
            a, r = rng.random()*math.tau, abs(rng.gauss(0, spread))
            placed += s.put(rng.choice(pines), cx+math.cos(a)*r, cy+math.sin(a)*r, layer=layer, gap=22, road=70,
                            base=700)
        return placed
    # Copses: tight clusters of pines with open ground between them.
    seeds = np.column_stack(np.nonzero(density > .22))
    seeds = seeds[np.random.default_rng(SEED+407).permutation(len(seeds))]
    centres, trees = [], 0
    for iy, ix in seeds:
        if len(centres) >= 70:
            break
        cx, cy = float(x[iy, ix]), float(y[iy, ix])
        if any(math.dist((cx, cy), c) < 250 for c in centres):
            continue
        centres.append((cx, cy))
        t.setdefault('copse_centres', []).append((cx, cy))
        trees += copse(cx, cy, rng.randint(8, 18), 50)
    # The round hills: a tor of rocks on the top, a copse on the flank away from the centre.
    rocks = [f'EdorasRock{k:02d}' for k in (1, 2, 3, 5, 6, 9, 10, 11, 12, 15, 16, 18)]
    for hx, hy, r, h in HILLS:
        for sign in (1, -1):
            cx, cy = (hx, hy) if sign > 0 else (SPAN-hx, SPAN-hy)
            for k in range(4):
                a, d = k*math.tau/4+rng.uniform(-.4, .4), rng.uniform(0, 45)
                s.put(rng.choice(rocks), cx+d*math.cos(a), cy+d*math.sin(a), layer='HillTors', gap=35, road=60,
                      base=650, z=-3, scale=rng.uniform(.8, 1.4))
            away = math.atan2(cy-C, cx-C)
            trees += copse(cx+math.cos(away)*.5*r, cy+math.sin(away)*.5*r, rng.randint(8, 12), 40, 'HillCopses')
    # A few lone trees out on the open downs.
    lone = 0
    for _ in range(3000):
        if lone >= 24:
            break
        px, py = rng.uniform(300, SPAN-300), rng.uniform(300, SPAN-300)
        iy, ix = round(py/10)+BORDER, round(px/10)+BORDER
        if density[iy, ix] > .05 or keep_off[iy, ix] < .9 or t['sd'][iy, ix] < 150:
            continue
        lone += s.put(rng.choice(['Tree05', 'PTreePine02']), px, py, layer='LoneTrees', gap=350, road=80, base=900)
    # Rock outcrops on the hills' steeper flanks and their tops, clear of the river.
    gy, gx = np.gradient(z, 10); slope = np.hypot(gx, gy)
    rocky = ((slope > .3) & (z > GROUND+35)) | (z > GROUND+150)
    seeds = np.column_stack(np.nonzero(rocky & (t['sd'] > 240) & (t['roads'] > 80)))
    seeds = seeds[np.random.default_rng(SEED+402).permutation(len(seeds))]
    for iy, ix in seeds:
        if s.counts['Outcrops'] >= 105:
            break
        s.put(rng.choice(rocks), float(x[iy, ix]), float(y[iy, ix]), layer='Outcrops', gap=110, road=70, base=650,
              z=-2, scale=rng.uniform(.8, 1.5))
    # Bushes and grass in fewer, fuller drifts, in the hollows and along the creeks.
    drift = fbm(x-1700, y+900, scale=280, seed=SEED+403, octaves=3)
    open_ground = ((density < .1) & (t['sd'] > 50) & (t['roads'] > 60) & (t['isle'] > 60) & (t['paddock'] > 80)
                   & (t['sites'] > 160) & ((t['relief'] < -2) | (t['sd'] < 260)) & (drift > 0))
    seeds = np.column_stack(np.nonzero(open_ground))
    seeds = seeds[np.random.default_rng(SEED+404).permutation(len(seeds))]
    drifts = []
    for iy, ix in seeds:
        if len(drifts) >= 75:
            break
        cx, cy = float(x[iy, ix]), float(y[iy, ix])
        if any(math.dist((cx, cy), d) < 260 for d in drifts):
            continue
        drifts.append((cx, cy))
        for _ in range(rng.randint(6, 12)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 38))
            s.put(rng.choice(['OptBushLG06', 'GladdenFieldsShrub02', 'OptGrass02', 'OptBushLG06', 'PTFlower05']),
                  cx+math.cos(a)*r, cy+math.sin(a)*r, layer='Tufts', gap=16, road=40)
    # Reeds along the banks, away from the fords.
    shore = (np.abs(z-WATER) < 2.5) & (t['ford_d'] > 200) & (t['isle'] > 0)
    seeds = np.column_stack(np.nonzero(shore))
    seeds = seeds[np.random.default_rng(SEED+405).permutation(len(seeds))]
    clumps = []
    for iy, ix in seeds:
        if len(clumps) >= 110:
            break
        cx, cy = float(x[iy, ix]), float(y[iy, ix])
        if any(math.dist((cx, cy), c) < 140 for c in clumps):
            continue
        clumps.append((cx, cy))
        for _ in range(rng.randint(3, 7)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 22))
            s.put(rng.choice(['GladdenFieldsShrub01', 'GladdenFieldsShrub02', 'OptGrass02']), cx+math.cos(a)*r,
                  cy+math.sin(a)*r, layer='Reeds', gap=12, road=40, wet=True, base=650)
    # The knoll's slopes: rock clusters on the face, shrubs and a few clinging
    # pines on its ledges and under its lip, thickest at the island's broad
    # tips; clear of the cuttings and the wall, the same on both sides.
    srng = random.Random(SEED+460)
    shrubs = ['OptBushLG06', 'GladdenFieldsShrub02', 'OldForestShrub02', 'OptBushLG06', 'OptGrass03']
    clusters = 0
    for _ in range(3000):
        if clusters >= 30:
            break
        a = srng.uniform(math.pi, math.tau)          # player 1's half of the island (v < 0)
        r = srng.uniform(.55, 1.0)*ISLAND['across']
        u, v = r*math.cos(a)*ISLAND['along']/ISLAND['across'], r*math.sin(a)
        if abs(u) < 140:                           # the cutting
            continue
        cx, cy = xy(u, v)
        iy, ix = round(cy/10)+BORDER, round(cx/10)+BORDER
        inward = -float(t['isle'][iy, ix])
        foot, brow = float(t['foot'][iy, ix]), float(t['brow'][iy, ix])
        if not foot+4 < inward < KNOLL_EDGE-8:
            continue
        clusters += 1
        upper = inward > (foot+brow)/2
        kind = srng.random()
        for k in range(srng.randint(3, 6)):
            du, dv = srng.gauss(0, 16), srng.gauss(0, 10)
            if kind < .35:                         # a rock cluster, partly sunk in the face
                template, scale, z = srng.choice(rocks), srng.uniform(.35, .7), -4
            elif kind < .62 or not upper:          # shrubs
                template, scale, z = srng.choice(shrubs), None, 0
            else:                                  # pines clinging under the lip, with a shrub or two
                template = srng.choice(['PTreePine01', 'PTreePine02']) if k < 2 else srng.choice(shrubs)
                scale, z = (srng.uniform(.6, .85) if k < 2 else None), 0
            s.pair(template, u+du, v+dv, layer='KnollSlopes', gap=14, road=45, base=0, wet=True, z=z, scale=scale)
    # A small stand of pines on each of the island's broad tips, outside the wall.
    for k in range(7):
        a = math.pi+srng.uniform(-.25, .25)
        r = srng.uniform(.62, .8)*ISLAND['across']
        s.pair(srng.choice(['PTreePine01', 'PTreePine02', 'PTreePine01']),
               r*math.cos(a)*ISLAND['along']/ISLAND['across'], r*math.sin(a), layer='KnollSlopes', gap=20, road=45,
               base=0, scale=srng.uniform(.65, .9))
    # Boulders round the knoll's foot, clear of the cuttings, the same on both sides.
    for k in range(14):
        a = math.pi+(k+.5)*math.pi/14             # round player 1's half of the island (v < 0)
        for r in np.arange(ISLAND['across'], 900, 2):
            u, v = r*math.cos(a)*ISLAND['along']/ISLAND['across'], r*math.sin(a)
            if island(np.asarray(xy(u, v)[0]), np.asarray(xy(u, v)[1])) > -6:
                break
        if abs(u) < 110 or abs(u) > 430:          # clear of the cuttings and the island's tips
            continue
        template, scale = rng.choice(rocks[:6]), rng.uniform(.45, .8)
        s.pair(template, u, v, layer='KnollRocks', gap=40, road=50, base=0, wet=True, z=-4, scale=scale)
    return trees


def island_contour(a, side, offset):
    """The point (u, v) `offset` off the island's shore at angle `a` from its
    upstream tip (0) to its downstream tip (pi), on the arm at `side` (1 east, -1 west)."""
    r = np.linspace(0, 900, 1801)
    u, v = -r*math.cos(a), side*r*math.sin(a)
    k = int(np.argmax(island(*xy(u, v)) > offset))
    return float(u[k]), float(v[k])


def sub_line(line, start, end):
    """The part of a polyline between two arc lengths."""
    out, s = [point_along(line, start)], 0.
    for p, q in zip(line, line[1:]):
        s += math.dist(p, q)
        if start < s < end:
            out.append(q)
    return out+[point_along(line, end)]


def flowing_water(m, t):
    """The river's and creeks' flowing surface (mapkit.rivers), 1 above the
    standing water as in the stock maps: the river from the north edge to the
    island, along both arms round it and on to the south edge, and both
    creeks into it.

    Where the river parts, each arm leaves the main strip ARM_LEAD above the
    island's tip on its own side of the channel (ARM_OFFSET off the middle)
    and curves into its arm, and rejoins the same way below the other tip.
    As where stock strips chain, the main strip runs on into the arms for
    ARM_OVERLAP, so the flow carries through without a seam.

    Each strip reaches out onto both banks (mapkit.rivers.bank_width), as the
    stock strips do, so the pale fringe of its alpha edge meets the shore
    instead of running over open water. The dale floor lies only 5 above the
    water, so the banks are flat: each strip stops where the ground is 1 above
    it, and at most REACH from its line (ARM_REACH for an arm, which leaves
    the main channel, CREEK_REACH for a creek, which opens into it), so no
    strip spans a channel it joins."""
    ARM_LEAD, ARM_OFFSET, ARM_OVERLAP = 160, 40, 70
    REACH, ARM_REACH, CREEK_REACH = 130, 90, 50
    rows, cols = t['z'].shape

    def height_at(x, y):
        return float(t['z'][min(max(round(y/10)+BORDER, 0), rows-1), min(max(round(x/10)+BORDER, 0), cols-1)])

    def river(name, points, reach=REACH, **kw):
        add_river(m, name, points, width=bank_width(points, height_at, WATER+1, rise=1, reach=reach),
                  height=WATER+1, **kw)

    line = river_line()
    middle = ISLAND['arm']/2
    along = [float(polyline_distance(line, *map(np.asarray, xy(*island_contour(a, 1, middle))))[1])
             for a in (0, math.pi)]
    river('Brightwater north', sub_line(line, 0, along[0]-ARM_LEAD+ARM_OVERLAP))
    for name, side in (('Brightwater east arm', 1), ('Brightwater west arm', -1)):
        ends = [uv(*point_along(line, s)) for s in (along[0]-ARM_LEAD, along[1]+ARM_LEAD)]
        arm = ([(ends[0][0], ends[0][1]+side*ARM_OFFSET)]
               + [island_contour(a, side, middle) for a in np.linspace(.12, math.pi-.12, 70)]
               + [(ends[1][0], ends[1][1]+side*ARM_OFFSET)])
        river(name, [xy(u, v) for u, v in chaikin(arm, 3)], reach=ARM_REACH, step=90)
    total = sum(math.dist(p, q) for p, q in zip(line, line[1:]))
    river('Brightwater south', sub_line(line, along[1]+ARM_LEAD-ARM_OVERLAP, total))
    for name, creek in zip(('North creek', 'South creek'), creek_lines()):
        river(name, creek, reach=CREEK_REACH, step=90)


def open_ground(t, step=100):
    """Points on the open downs every `step`: dry, level, clear of water, roads,
    copses, paddocks, sites and the island."""
    gy, gx = np.gradient(t['z'], 10)
    slope = np.hypot(gx, gy)
    points = []
    for y in np.arange(300, SPAN-300, step):
        for x in np.arange(300, SPAN-300, step):
            iy, ix = round(y/10)+BORDER, round(x/10)+BORDER
            if (t['sd'][iy, ix] > 200 and t['isle'][iy, ix] > 250 and t['roads'][iy, ix] > 90
                    and t['paddock'][iy, ix] > 150 and t['sites'][iy, ix] > 250 and t['woods'][iy, ix] < .05
                    and slope[iy, ix] < .2):
                points.append((float(x), float(y)))
    return points


def gollum_points(t):
    """Gollum's spawn points: GOLLUM_PER_HALF spread over player 1's half of
    the open downs, within GOLLUM_CLEAR..GOLLUM_REACH of a start, and the
    same turned onto player 2's half."""
    half = [(x, y) for x, y in open_ground(t) if x+y < SPAN-150
            and GOLLUM_CLEAR <= min(math.dist((x, y), p) for p in STARTS) <= GOLLUM_REACH]
    chosen = spread(half, GOLLUM_PER_HALF, avoid=STARTS+[(C, C)], clear=GOLLUM_CLEAR, apart=900)
    if len(chosen) < GOLLUM_PER_HALF:
        raise ValueError(f'Only {len(chosen)} places for Gollum on a half')
    return chosen+[(SPAN-x, SPAN-y) for x, y in chosen]


def sounds(m, t, sites):
    """The Plains of Rohan bed over the map, and emitters: water along the
    river (not over the island) and the creeks, birds and creaking trees in the
    copses, wind and falcons on the hills and scarps, birds out on the downs,
    voices in the hold and at the outposts, horses at the stables."""
    river = [p for p in along(river_line(), 300) if island(np.asarray(p[0]), np.asarray(p[1])) > 0]
    creeks = [p for line in creek_lines() for p in along(line, 300)]
    hills = [(x, y) for x, y, _, _ in HILLS]+[(SPAN-x, SPAN-y) for x, y, _, _ in HILLS]
    high = np.argwhere(t['z'][::20, ::20] > GROUND+190)
    heights = hills+[(float(t['x'][::20, ::20][i, j]), float(t['y'][::20, ::20][i, j])) for i, j in high]
    hold = [xy(170, 0), xy(-170, 0)]
    return ambient(m, 'rohan', (C, C), dict(
        river=river, creek=creeks, woods=t.get('copse_centres', []), heights=heights, open=open_ground(t, 200),
        settlement=hold+list(sites['outposts']), stable=t.get('stables', [])),
        limits=dict(river=8, creek=4, woods=8, heights=6, open=8, settlement=4, stable=2))


def fairness(t, solids, sites):
    """Walking distances from each start to the hold, to the other start and
    to each outpost.

    Walkable: ground and water up to 5 deep and the bridge decks, outside the
    buildings. The hold distance is to the nearest walkable ground on its top."""
    from mapworkshop.mapkit.checks.strategy import distance_field, STEP
    walk, wx, wy = walk_grid(t, solids)
    top = walk & (island(wx, wy) < -120)
    cell = lambda p: (min(int(p[1]//STEP), walk.shape[0]-1), min(int(p[0]//STEP), walk.shape[1]-1))

    def near(field, p):
        """The distance to the nearest reached cell within 200 of p (its footprint is blocked)."""
        r = int(200//STEP); cy, cx = cell(p)
        box = field[max(cy-r, 0):cy+r+1, max(cx-r, 0):cx+r+1]
        return float(box.min())
    report = []
    for i, p in enumerate(STARTS):
        field = distance_field(walk, p)
        values = dict(hold=float(field[top].min()), opponent=float(field[cell(STARTS[1-i])]),
                      own_outpost=near(field, sites['outposts'][i]), other_outpost=near(field, sites['outposts'][1-i]),
                      lair_near=near(field, sites['lairs'][i]), lair_far=near(field, sites['lairs'][1-i]))
        if not np.isfinite(list(values.values())).all():
            raise ValueError(f'Something cannot be reached from {p}: {values}')
        report.append(dict(start=p, **{k: round(v) for k, v in values.items()}))
    a, b = report
    for key in ('hold', 'own_outpost', 'other_outpost'):
        if abs(a[key]-b[key]) > 40:
            raise ValueError(f'Unfair layout ({key}): {report}')
    if a['other_outpost']-a['own_outpost'] < OUTPOST_MARGIN*.8:
        raise ValueError(f'The outposts are not clearly owned: {report}')
    return report


def build(b):
    from mapworkshop.render.assets import GameAssets
    if b.project.players != len(STARTS):
        raise ValueError(f'map.toml has {b.project.players} players, but the dale has {len(STARTS)} starts')
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    t = terrain()
    t['roads'] = road_field(t, roads())
    crossings(t)
    t['paddock'] = paddock_distance(t)
    t['hold_paths'] = hold_paths(t)
    s = Scenery(m, t, GameAssets())
    bridges(s, t)
    sites = neutral_sites(t)
    relief(t)
    hold(s, t)
    objectives(s, t, sites)
    paddock(s, t)
    trees = scenery(s, t)
    labels = materials(t)

    set_heights(m, t['z'])
    # Impassable: deep water, and the knoll outside the wall with the shallow
    # fringe off its shore (scree, rock face, ledges and lip are scenery, which
    # no unit could reach), except at the fords and where the cuttings climb
    # to the gateways.
    inward, (u, _) = -t['isle'], uv(t['x'], t['y'])
    face = (inward > -30) & (inward < WALL_LINE-WALL_DEPTH/2-1) & (np.abs(u) > 90) & (t['ford_d'] > 150)
    set_materials(m, PALETTE, labels, (t['z'] < WATER-5) | face, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    water_plane(m, 'Brightwater', WATER)
    flowing_water(m, t)
    starts(m, STARTS)
    gollum = gollum_points(t)
    gollum_spawns(m, gollum)
    emitters = sounds(m, t, sites)
    add_sky(m, b.project.weather, WIDTH*10, HEIGHT*10, BORDER*10)
    apply_weather(m, b.project.weather, sun=SUN, fill=FILL)
    walking = fairness(t, s.solids, sites)
    # Reflections on: at WaterLOD High the river's model (wtr_Riv03) takes 80% of
    # its colour from the reflection, which is black without them.
    ini = ini_block(b.project.weather)+f'WaterTransparency\n  ReflectionPlaneZ = {WATER:g}\n  ReflectionOn = Yes\nEnd\n'
    b.save(m, ini=ini)
    b.report.update(seed=SEED, starts=STARTS, fords=t['fords'], sites=sites, gollum=gollum,
                    sounds=[e[0] for e in emitters], walking=walking, layers=dict(s.counts),
                    vegetation=dict(s.vegetation), trees_in_copses=trees)
    print(f'{sum(s.counts.values())} objects, {dict(s.vegetation)}, heights {t["z"].min():.0f}..{t["z"].max():.0f}')
    print(f'  outposts {[tuple(round(v) for v in p) for p in sites["outposts"]]}, '
          f'Gollum {[tuple(round(v) for v in p) for p in gollum]}, {len(emitters)} sounds')
    for w in walking:
        print(f'  start {w["start"]}: hold {w["hold"]}, opponent {w["opponent"]}, own outpost {w["own_outpost"]}, '
              f'other outpost {w["other_outpost"]}, lairs {w["lair_near"]}/{w["lair_far"]}')
