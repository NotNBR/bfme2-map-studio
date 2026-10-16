"""The Hollin Dales: a 3 vs 3 map in autumn Eregion, under the Misty Mountains.

Every player holds a dale of their own: a closed valley under high ridges,
with a bowl at its head for the base. A team's three dales open only into its
gate-court, a long walled hollow in front of them, so teammates reach each
other only through the court and never from behind. The court opens onto the
shared field through three gates. The field is the ruined heart of Hollin:
the Sirannon winds down it from the north edge to the south, with a ford at
each team's north and south gates and a stone bridge through the ruins of
Ost-in-Edhil in the middle. Shallow dale floors open into rolling courts;
low spurs descend into the field, divided by dry drainage hollows opening
onto uneven river terraces and alternating shallow and cut banks.

The layout is point-symmetric about the map centre: the east team's dales,
court and gates are the west team's turned through 180 degrees, and so are
the field's ruins, sites and stream. Players 1-3 (north-west, west,
south-west) are the west team; players 4-6 (south-east, east, north-east)
are their turned copies, the east team. The build measures walking distances
and refuses a layout that is unfair or that lets a dale reach another other
than through its court.

Positions are map units, 10 per terrain cell: x east, y north from the
playable area's south-west corner.
"""
from collections import Counter
import math
import random

import numpy as np

from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, add_object, terrain_cell_sizes, water_plane
from mapworkshop.mapkit.lines import nearest, polyline_distance
from mapworkshop.mapkit.earth import fbm, thermal_erosion
from mapworkshop.mapkit.ambient import ambient, along
from mapworkshop.mapkit.cliffs import steep_cells
from mapworkshop.mapkit.rivers import add_river, bank_width
from mapworkshop.mapkit.sites import neutral_site, creep_lair, gollum_spawns
from mapworkshop.mapkit.variety import spot_random
from mapworkshop.mapkit.weather import add_sky, ini_block, apply_weather

WIDTH, HEIGHT = 1092, 754      # playable size in cells
BORDER = 30                    # cells of unplayable border around it
SEED = 52113                   # title, description, players and weather are in map.toml
SPAN_X, SPAN_Y = (WIDTH-1)*10, (HEIGHT-1)*10
CX, CY = SPAN_X/2, SPAN_Y/2    # the map centre and centre of symmetry
WATER = 165.0                  # one water plane; only the Sirannon lies below it
FIELD_Z = 188.0                # the field's floor
COURT_Z = 212.0                # each gate-court's floor
BASE_Z = 245.0                 # every construction area, at the head of its dale
FORD_DEPTH = 2.5               # units wade through water up to 5 deep
BASE_FLAT, BASE_BLEND = 520, 760
# The layout below was drawn at 840 x 580 cells; S scales it to the map's size.
S = 1.3


def scaled(points):
    return [(x*S, y*S) for x, y in points]


# --- The west team; the east team is the same turned about the centre. ----
# Each dale from where it leaves the court to its base, and the base bowl's
# radius. The middle dale is the longest: its gate is the nearest, so all
# three bases are about as far from the field.
DALES = [scaled([(2250, 3950), (1800, 4250), (1350, 4380), (1000, 4380)]),      # north-west
         scaled([(2200, 2895), (1700, 2760), (1200, 2830), (800, 2895)]),       # west
         scaled([(2250, 1840), (1800, 1540), (1350, 1410), (1000, 1410)])]      # south-west
BOWL = 780                     # wide enough for a full base round the construction area
# The gate-court: centre and half-size of a rounded box.
COURT = (2560*S, 2895*S, 430*S, 1200*S)
# Its three gates, through the ridge between the court and the field, and
# their half-widths.
GATES = [(scaled([(2900, 3800), (3250, 3880), (3620, 3950)]), 240*S),
         (scaled([(2950, 2895), (3300, 2870), (3620, 2820)]), 200*S),
         (scaled([(2900, 1990), (3250, 1910), (3620, 1840)]), 240*S)]
# The field: half-size of a rounded box about the centre.
FIELD = (700*S, 2350*S)
# The Sirannon: a river in an S-bend through the centre, crossing the centre
# line at the middle and FORD_SPACING north and south of it. Too deep to
# wade, it is crossed by a great stone bridge in the middle, among the ruins
# of Ost-in-Edhil, and by a shallow gravel ford at the north and south
# crossings.
STREAM_BEND, FORD_SPACING = 260*S, 1500*S
RIVER_HALF = 105              # half its width
BRIDGE = 'GondorIthilienBridge2'   # deck along its local y, walkable; 545 long, ramps 275 from its middle
BRIDGE_BANK = WATER+12        # the banks under each bridge's ramps; the origin goes 1 below
CITY_GRID = .32                # Ost-in-Edhil's street grid, radians from north
# The rocky knolls between each court's gates (the west team's; the east
# team's are turned) are buttes: steep rocky sides round a gently domed top,
# crags along its field-side rim. A narrow goat path climbs the court-facing
# face to the top, room for archers and siege engines over the gates; every
# other side stays sheer, so a knoll is no way into the court. Centre, and
# where round the face from the way to the court the path starts (radians;
# its sign picks the side it climbs from).
KNOLLS = [((4220, 3146), -1.25), ((4232, 4357), 1.25)]
KNOLL_RISE = 125              # the top above the ground round it
TRAIL_WIDTH = 24              # the path's half-width

# Terrain textures. Higher entries blend over lower ones at their edges.
PALETTE = ['GrassEregion01', 'GrassEregion08', 'GrassEregion07', 'GrassEregion04', 'GrassEregion10',
           'GrassEregion03', 'GrassEregion09', 'GrassRivendell01', 'DirtRivendell03', 'SandType3wet',
           'RockEregion02', 'RockEregion01', 'CliffCaradhras05', 'RockCaradhras05',
           'CliffEttenmoors01', 'SnowCaradhras04', 'SnowCaradhras06', 'DirtEregion04', 'DirtEregion02',
           'DirtEregion01', 'StoneErebor08', 'StoneShire03', 'CliffErebor05']
# The cliff texture comes last: steep faces are cliff-mapped and keep no
# blend, so it blends over its neighbours instead.
(OCHRE, MIXED, DRY, RED, RUST, GOLD, LEAVES, GREEN, MUD, SILT, ROCKY_GRASS, ROCK, CLIFF_HIGH,
 SCREE, CLIFF_SNOW, SNOW, SNOW_DEEP, TRODDEN, LANE_EDGE, LANE, PAVING, RUBBLE, CLIFF) = range(len(PALETTE))


def smooth(a, b, v):
    t = np.clip((v-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def mirror(field):
    """The field turned about the map centre (the height grid is symmetric)."""
    return field[::-1, ::-1]


def turned(points):
    return [(SPAN_X-x, SPAN_Y-y) for x, y in points]


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


def length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def rounded_box(x, y, cx, cy, hx, hy, r):
    """Signed distance to a box with rounded corners (negative inside)."""
    qx, qy = np.abs(x-cx)-hx+r, np.abs(y-cy)-hy+r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))+np.minimum(np.maximum(qx, qy), 0)-r


def box_blur(a, r):
    """The mean of `a` over a (2r+1)-sample square round every sample."""
    c = np.cumsum(np.cumsum(np.pad(a, r+1, mode='edge'), 0), 1)
    n = 2*r+1
    return (c[n:, n:]-c[:-n, n:]-c[n:, :-n]+c[:-n, :-n])[:a.shape[0], :a.shape[1]]/(n*n)


def symmetric(field):
    return .5*(field+mirror(field))


def dale_lines():
    """Every dale, smoothed, west team first: (line, base)."""
    west = [(chaikin(d, 3), d[-1]) for d in DALES]
    return west+[(chaikin(turned(d), 3), turned(d)[-1]) for d in DALES]


def gate_lines():
    west = [(chaikin(g, 3), w) for g, w in GATES]
    return west+[(chaikin(turned(g), 3), w) for g, w in GATES]


def start_positions():
    west = [d[-1] for d in DALES]
    return west+turned(west)


# The river's course north of the centre, as (east of the centre, north of
# it): bends of uneven length and depth, as a river wanders. South of the
# centre it runs the same way turned, so both teams meet the same river.
COURSE = [(0, 0), (25, 380), (220, 760), (210, 1230), (-110, 1640), (-250, 2060), (-130, 2520),
          (130, 2960), (170, 3420), (70, 3900), (40, 4500)]


def stream_line():
    """The Sirannon from beyond the north edge to beyond the south edge,
    point-symmetric about the centre, which it crosses."""
    north = [(CX+dx, CY+dy) for dx, dy in COURSE]
    return chaikin(north[::-1]+turned(north)[1:], 4)


def fords():
    """Where the river is crossed, north to south: the north ford, the
    bridge (the centre) and the south ford, each where the river crosses
    FORD_SPACING north or south of the centre."""
    line = stream_line()
    def crossing(y0):
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            if (ay-y0)*(by-y0) <= 0 and ay != by:
                return ax+(bx-ax)*(y0-ay)/(by-ay), y0
        raise ValueError(f'The river does not cross y = {y0}')
    return [crossing(CY+FORD_SPACING), (CX, CY), crossing(CY-FORD_SPACING)]


def across(px, py):
    """The unit vector square to the river at the point nearest (px, py),
    pointing east (towards the east team)."""
    line = stream_line()
    k = min(range(len(line)-1), key=lambda i: math.dist(line[i], (px, py)))
    (ax, ay), (cx, cy) = line[max(k-2, 0)], line[min(k+3, len(line)-1)]
    n = math.dist((ax, ay), (cx, cy))
    ux, uy = (cy-ay)/n, -(cx-ax)/n
    return (ux, uy) if ux > 0 else (-ux, -uy)


def bridges():
    """The bridge's middle and the direction of its deck (square to the river)."""
    bx, by = fords()[1]
    return [((bx, by), across(bx, by))]


def approach(crossing, side, start):
    """A track's last stretch from `start` to a crossing: it swings round to
    meet the river square on, running straight in for the last 450 on the
    west (side -1) or east (side 1) bank, onto the bridge deck or into the ford."""
    cx, cy = crossing
    ux, uy = across(cx, cy)
    near, far = (cx+side*ux*170, cy+side*uy*170), (cx+side*ux*620, cy+side*uy*620)
    return [far, (cx+side*ux*400, cy+side*uy*400), near, (cx, cy)]


def bowl(x, y, bx, by, line, k):
    """Signed distance to the base bowl at the head of dale k: no circle
    but a cirque of its own, its rim swinging in and out in broad bays and
    buttresses, and one or two side coves cut back into the mountain away
    from the dale's mouth. Every bowl keeps clear ground well beyond its
    construction area."""
    rng = random.Random(SEED+60+k)
    r, a = np.hypot(x-bx, y-by), np.arctan2(y-by, x-bx)
    # Towards a neighbouring bowl the rim may only swing inwards, so the
    # ridge between them stays whole.
    neighbours = [math.atan2(py-by, px-bx) for px, py in start_positions()
                  if 0 < math.dist((px, py), (bx, by)) < 2600]
    toward = sum(np.maximum(np.cos(a-n), 0)**2 for n in neighbours)
    swing = sum(amp*np.sin(n*a+rng.uniform(0, math.tau)) for n, amp in ((2, 150), (3, 105), (4, 60), (6, 35), (9, 22)))
    rim = BOWL+np.where(swing > 0, swing*np.clip(1-1.5*toward, 0, 1), swing)
    # Buttresses: narrow spurs of rock jutting into the bowl.
    for _ in range(rng.randint(2, 3)):
        at = rng.uniform(0, math.tau)
        gap = np.abs((a-at+np.pi) % (2*np.pi)-np.pi)
        rim = rim-rng.uniform(160, 260)*np.exp(-(gap/rng.uniform(.1, .18))**2)
    rim = np.maximum(rim, BASE_FLAT+150)        # never into the building ground
    sd = r-rim
    mx, my = line[len(line)//2]
    mouth = math.atan2(my-by, mx-bx)           # the way out, down the dale
    for _ in range(rng.choice([1, 2])):
        for _try in range(50):
            turn = mouth+math.pi+rng.uniform(-1.6, 1.6)
            if all(abs((turn-n+math.pi) % math.tau-math.pi) > 1.1 for n in neighbours):
                break
        else:
            continue
        reach = rng.uniform(540, 660); radius = rng.uniform(230, 320)
        cove = np.hypot(x-bx-math.cos(turn)*reach, y-by-math.sin(turn)*reach)-radius
        sd = smooth_min(sd, cove, 140)
    return sd


def lowland_relief(x, y, sd, stream):
    """Broad open-ground relief, with long spurs and shallow intervening hollows.

    The west's three crests have turned counterparts for equal opportunities.
    Smaller variation breaks their regular outlines. River margins fade to
    lower ground; the build grades the crossings and construction pads later.
    """
    warp = symmetric(fbm(x+1700, y-900, scale=700, seed=SEED+80, octaves=2))
    broad = symmetric(fbm(x+1200, y-600, scale=1050, seed=SEED+5, octaves=2))
    folds = symmetric(fbm(x-300, y+1500, scale=420, seed=SEED+15, octaves=2))
    relief = 38*broad+13*folds
    # Centre, long and short radii, heading and rise, all in map units.
    # The first two are spurs from the field's west wall towards the river;
    # the third is a low shoulder in the court between the dale mouths.
    crests = [(4810, 4510, 660, 300, -.65, 48),
              (4780, 2840, 720, 320, .55, 42),
              (3290, 4370, 600, 270, 1.15, 26)]
    for px, py, long, short, angle, rise in crests:
        for cx, cy in ((px, py), (SPAN_X-px, SPAN_Y-py)):
            dx, dy = x-cx, y-cy
            along = (dx*math.cos(angle)+dy*math.sin(angle))/long
            across = (-dx*math.sin(angle)+dy*math.cos(angle)+65*warp)/short
            relief += rise*np.exp(-2*(along*along+across*across))
    # Texture-scale irregularity stays small beside the authored landforms.
    relief += 1.8*fbm(x+450, y-700, scale=110, seed=SEED+81, octaves=2)
    return relief*(1-smooth(-220, 40, sd))*smooth(25, 230, stream)


def drainage_hollows(land, x, y, sd, stream):
    """Dry swales descend between the field's spurs into the river terraces.

    Authored grades connect the landforms; their turned counterparts retain
    equivalent terrain for both teams. Their mouths stay above standing water.
    """
    hollows = [([(4500, 4930), (4790, 4850), (5100, 4660), (5520, 4500)], 225, 212),
               ([(4540, 3420), (4790, 3250), (5030, 3150), (5260, 3090)], 180, 209),
               ([(4830, 6210), (4960, 5980), (5090, 5820)], 150, 204)]
    wet_ground = np.zeros(x.shape)
    for points, width, head in hollows:
        for route in (points, turned(points)):
            route = chaikin(route, 2)
            d, along = polyline_distance(route, x, y)
            progress = np.clip(along/length(route), 0, 1)
            grade = head+(WATER+5-head)*progress
            influence = (1-smooth(width*.2, width, d))
            influence *= smooth(0, .15, progress)*(1-smooth(-100, 30, sd))
            influence *= smooth(10, 65, stream)
            land = land-influence*np.maximum(land-grade, 0)
            wet_ground = np.maximum(wet_ground, influence)
    return land, wet_ground


def terrain():
    rows, cols = HEIGHT+2*BORDER, WIDTH+2*BORDER
    y, x = (np.mgrid[0:rows, 0:cols]-BORDER)*10.0

    # The open ground: dales, bowls, courts, gates and the field, each with
    # its own signed distance (negative inside) and floor height.
    parts = []
    for k, (line, (bx, by)) in enumerate(dale_lines()):
        d, along = polyline_distance(line, x, y)
        s = along/length(line)
        width = (265+105*smooth(0, .5, s))*S
        # A broad trough down the dale, rising gradually towards its sides.
        shoulders = 19*smooth(35, width, d)
        parts.append((smooth_min(d-width, bowl(x, y, bx, by, line, k), 160),
                      COURT_Z+(BASE_Z-COURT_Z)*smooth(0, .8, s)+shoulders))
    # Long, unequal shoulders interrupt the box outlines, while the authored
    # gate corridors below retain their full width. The warp turns with the map.
    contour_x = x+105*np.sin((y-CY)/610)+45*np.sin((y-CY)/260)
    contour_y = y+70*np.sin((x-CX)/530)
    cx, cy, hx, hy = COURT
    for px, py in ((cx, cy), (SPAN_X-cx, SPAN_Y-cy)):
        parts.append((rounded_box(contour_x, contour_y, px, py, hx, hy, 380), np.full(x.shape, COURT_Z)))
    for line, width in gate_lines():
        d, along = polyline_distance(line, x, y)
        parts.append((d-width, COURT_Z+(FIELD_Z-COURT_Z)*smooth(.1, .95, along/length(line))))
    field_width = FIELD[0]+135*np.cos((y-CY)/740)+65*np.cos((y-CY)/310)
    parts.append((rounded_box(contour_x, y, CX, CY, field_width, FIELD[1], 620), np.full(x.shape, FIELD_Z)))

    sd = parts[0][0]
    for d, _ in parts[1:]:
        sd = smooth_min(sd, d, 110)
    # The cliff line wanders in spurs and bays. Half of the wander is the
    # same on both halves, so the open ground stays fair; the other half
    # is not, so the two halves do not look alike.
    sd = sd+symmetric(45*fbm(x, y, scale=420, seed=SEED+1, octaves=3))+30*fbm(x-900, y+300, scale=300, seed=SEED+11, octaves=3)
    lowest = np.min([d for d, _ in parts], axis=0)
    weights = [np.exp(-(d-lowest)/60) for d, _ in parts]
    floor = sum(w*h for w, (_, h) in zip(weights, parts))/sum(weights)

    # The Sirannon: a river in a broad valley, too deep to wade but at its
    # two fords. It comes down from the mountains through a ravine of its
    # own at each end.
    line = stream_line()
    # Its width swells and narrows along its course, the same either side of
    # the centre; the banks are ragged in small coves and spits.
    stream_d, stream_along = polyline_distance(line, x, y)
    middle = np.abs(stream_along-length(line)/2)
    half = RIVER_HALF+28*fbm(middle, np.zeros_like(middle), scale=900, seed=SEED+6, octaves=2)
    stream_sd = stream_d-half-11*fbm(x, y, scale=150, seed=SEED+8, octaves=2)-4*fbm(x, y, scale=50, seed=SEED+11, octaves=2)
    ravine = smooth(160, 850+200*fbm(x, y, scale=600, seed=SEED+12, octaves=2), stream_d)

    # Mountains, none alike: a cliff wall of uneven height at the edge of
    # the open ground, buttresses and gullies cut into it, then high ridges
    # and snowy peaks behind it with ridged crests.
    ridged = 1-np.abs(fbm(x+3000, y-1000, scale=900, seed=SEED+2, octaves=5))
    crags = 1-np.abs(fbm(x-2100, y+1700, scale=260, seed=SEED+13, octaves=4))
    warp = fbm(x-500, y+700, scale=260, seed=SEED+3, octaves=3)
    wall_height = 230+90*fbm(x+400, y-900, scale=700, seed=SEED+14, octaves=2)
    wall = wall_height*smooth(0, 280+80*warp, sd+60*warp)
    peaks = 560*smooth(150, 1300, sd)*(.4+.8*ridged**2)+90*smooth(100, 600, sd)*crags**3
    foothills = 34*smooth(-500, 0, sd)*(.7+.6*fbm(x, y, scale=450, seed=SEED+4, octaves=2))
    # Rock faces broken into ribs, ledges and gullies, strongest mid-height
    # on the walls; nothing of it reaches the open ground.
    ribs = fbm(x*1.6+y*.3, y*.7-x*.2, scale=240, seed=SEED+16, octaves=4)
    ledges = np.round(fbm(x+800, y+800, scale=500, seed=SEED+17, octaves=2)*4)/4
    faces = (55*ribs+30*ledges+25*crags)*smooth(20, 200, sd)
    # The knolls between a court's gates stand in open ground on most
    # sides: buttes, no mountains. Steep broken sides rise to a gently
    # domed top; crags crown its field-side rim.
    knoll = smooth(.55, .72, box_blur((sd < 0).astype(float), 60))
    # Their footprints keep the gates' shape; above the ground their sides
    # bulge and recede, so no butte follows the box the gates leave.
    sd = sd+knoll*smooth(0, 60, sd)*60*fbm(x+4100, y-3900, scale=170, seed=SEED+19, octaves=3)
    fieldward = np.zeros(x.shape); near_knoll = np.zeros(x.shape, bool)
    for (kx, ky), _ in KNOLLS:
        for ox, oy, side in ((kx, ky, 1), (SPAN_X-kx, SPAN_Y-ky, -1)):
            near = 1-smooth(350, 550, np.hypot(x-ox, y-oy))
            fieldward = np.maximum(fieldward, near*smooth(-60, 160, side*(x-ox)))
            near_knoll |= np.hypot(x-ox, y-oy) < 500
    rim = 60*smooth(.45, .8, crags+.3*ribs)*smooth(110, 150, sd)*(1-smooth(200, 260, sd))*fieldward**2
    sides = 28*crags*smooth(10, 110, sd)*(1-smooth(100, 140, sd))
    knolls = KNOLL_RISE*smooth(5, 150, sd)+35*smooth(140, 330, sd)+sides+rim
    mountains = ((wall+faces)*(1-knoll)+knolls*knoll+peaks*(1-knoll))*(.25+.75*ravine)

    land = floor+lowland_relief(x, y, sd, stream_sd)+foothills+mountains
    # Wide depositional shelves alternate with narrow cut banks. Opposite
    # banks have different profiles rather than one continuous raised lip.
    stations = np.r_[0., np.cumsum(np.hypot(np.diff(np.array(line)[:, 0]), np.diff(np.array(line)[:, 1])))]
    river_x = np.interp(stream_along, stations, np.array(line)[:, 0])
    river_y = np.interp(stream_along, stations, np.array(line)[:, 1])
    side = np.tanh((x-river_x)/65)
    deposit = .5-.5*side*np.sin((river_y-CY)/650)
    shelf_width = 65+340*deposit+30*symmetric(fbm(x, y, scale=650, seed=SEED+82, octaves=2))
    shelf_floor = WATER+4+7*(1-deposit)+1.5*fbm(x, y, scale=320, seed=SEED+83, octaves=2)
    valley = (1-smooth(5, shelf_width, stream_sd))*(1-smooth(-80, 160, sd))
    land = land*(1-valley)+shelf_floor*valley
    land, hollows = drainage_hollows(land, x, y, sd, stream_sd)
    land = np.maximum(land, WATER+3)
    # Scree and talus: the mountains settle under their own weight, the open ground keeps its shape.
    settled = thermal_erosion(land, iterations=24, spacing=10, talus=.95)
    land = land+(settled-land)*smooth(-30, 120, sd)*(1-.8*knoll)
    # The goat paths: each climbs evenly from the ground at its foot to the
    # top, cut into the face on its uphill side and built out a little on
    # the other. The paths and the knolls' tops, inside their rims, are
    # walkable; the knolls' sides are not.
    trails = knoll_trails(sd)
    climb = near_knoll & (knoll > .5) & (sd > 145) & (rim < 6)
    for trail in trails:
        d, along = polyline_distance(trail, x, y)
        (ax, ay), (bx, by) = trail[0], trail[-1]
        foot, top = land[round(ay/10)+BORDER, round(ax/10)+BORDER], land[round(by/10)+BORDER, round(bx/10)+BORDER]
        grade = foot+(top-foot)*np.clip(along/length(trail), 0, 1)
        cut = 1-smooth(TRAIL_WIDTH, TRAIL_WIDTH+30, d)
        land = land*(1-cut)+grade*cut
        climb |= d < TRAIL_WIDTH+6
    # Banks: a short, firm bank up from the water to the meadow, steeper in
    # places, gentler in others; under water the bed drops away quickly.
    # A little variety along it: the bank's run and steepness, how fast the
    # bed drops and how deep it goes all wander a little.
    vary = fbm(x-600, y, scale=300, seed=SEED+7, octaves=3)
    bank = np.clip(stream_sd/(25+95*deposit+12*vary), 0, 1)
    steep = .85+1.1*deposit+.1*fbm(x+1300, y, scale=350, seed=SEED+14, octaves=2)
    deep = 12+3*fbm(x, y+700, scale=260, seed=SEED+15, octaves=3)
    drop = 40+14*vary
    z = np.where(stream_sd > 0, WATER+.5+(land-WATER-.5)*bank**steep, WATER-4-.8*vary-deep*smooth(0, drop, -stream_sd))
    # The bridges' banks: level under the ramps, so each deck meets them.
    for (bx, by), (ax, ay) in bridges():
        along = np.abs((x-bx)*ax+(y-by)*ay); across = np.abs(-(x-bx)*ay+(y-by)*ax)
        pad = (1-smooth(110, 190, across))*smooth(150, 185, along)*(1-smooth(330, 470, along))
        z = z*(1-pad)+BRIDGE_BANK*pad
    # The fords: a gravel riffle across the river where it runs shallow, and
    # the banks either side worn down into gentle ramps to it.
    fx, fy = fords()[0]
    ford_middle = abs(float(polyline_distance(line, np.array([fx]), np.array([fy]))[1][0])-length(line)/2)
    ford_d = np.abs(middle-ford_middle)
    shelf = 1-smooth(70, 150, ford_d+20*fbm(x, y, scale=120, seed=SEED+9, octaves=2))
    riffle = WATER-FORD_DEPTH+.6*fbm(x, y, scale=60, seed=SEED+10, octaves=2)
    z = np.where(stream_sd <= 0, z*(1-shelf)+riffle*shelf, z)
    ramp = 1-smooth(90, 190, ford_d)
    z = np.where(stream_sd > 0, z*(1-ramp)+np.minimum(z, WATER+.8+.1*np.maximum(stream_sd, 0))*ramp, z)

    # Construction areas: level, at one height, easing into the bowl.
    for px, py in start_positions():
        angle = np.arctan2(y-py, x-px)
        transition = BASE_BLEND+55*np.cos(2*angle)+35*np.sin(4*angle)
        blend = (1-smooth(BASE_FLAT, transition, np.hypot(x-px, y-py)))**.8
        z = z*(1-blend)+BASE_Z*blend
    return dict(x=x, y=y, z=z, sd=sd, knoll=knoll, climb=climb, trails=trails, stream=stream_sd, ford_d=ford_d, shelf=shelf,
                line=line, stream_d=stream_d, hollows=hollows, deposit=deposit)


def wander(points, seed, amount=70, step=200):
    """The line resampled every `step` and pushed sideways by a seeded
    random walk, ends kept, so tracks bend like trodden ones."""
    rng = random.Random(seed)
    out = [points[0]]; offset = 0.
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        n = max(1, round(math.dist((ax, ay), (bx, by))/step))
        nx, ny = (ay-by)/math.dist((ax, ay), (bx, by)), (bx-ax)/math.dist((ax, ay), (bx, by))
        for k in range(1, n+1):
            f = k/n
            offset = .6*offset+rng.uniform(-amount, amount)
            last = (k == n and (bx, by) == points[-1])
            o = 0 if last else offset
            out.append((ax+(bx-ax)*f+nx*o, ay+(by-ay)*f+ny*o))
    return out


def knoll_trails(sd):
    """Each knoll's goat path, both teams: up the knoll's court-facing face
    from the court floor to its top, at a steady angle across the face. Each
    point lies where the face reaches a given depth into the rock (`sd`),
    going deeper and round the face together."""
    cx, cy = COURT[:2]
    def depth(px, py):
        return sd[min(max(round(py/10)+BORDER, 0), sd.shape[0]-1), min(max(round(px/10)+BORDER, 0), sd.shape[1]-1)]
    out = []
    for (kx, ky), swing in KNOLLS:
        for (ox, oy), (tx, ty) in (((kx, ky), (cx, cy)), (turned([(kx, ky)])[0], turned([(cx, cy)])[0])):
            court = math.atan2(ty-oy, tx-ox)
            line = []
            for k in range(13):
                f = k/12
                a = court+swing*(1-f)-.25*swing*f
                target = -40+215*f
                r = 0
                while r < 900 and depth(ox+r*math.cos(a), oy+r*math.sin(a)) > target:
                    r += 5
                line.append((ox+r*math.cos(a), oy+r*math.sin(a)))
            out.append(chaikin(line, 3))
    return out


def bend(points, radius=180, step=20, keep=0):
    """The line resampled every `step` and smoothed over about `radius`, so
    its corners become long curves as a trodden track takes them. Both ends
    stay; the last `keep` units also stay straight (a crossing's approach)."""
    pts = np.array(points, float)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(int(s[-1]//step), 2)
    u = np.linspace(0, s[-1], n+1)
    line = np.column_stack([np.interp(u, s, pts[:, 0]), np.interp(u, s, pts[:, 1])])
    sigma = radius/step
    k = np.arange(-int(3*sigma), int(3*sigma)+1)
    w = np.exp(-.5*(k/sigma)**2); w /= w.sum()
    pad = np.concatenate([np.repeat(line[:1], len(k)//2, 0), line, np.repeat(line[-1:], len(k)//2, 0)])
    smooth_line = np.column_stack([np.convolve(pad[:, i], w, 'valid') for i in (0, 1)])
    # Fade the smoothing out towards both ends, so the ends stay where they are.
    f = np.minimum(u, s[-1]-u)
    hold = np.clip(np.minimum(f/radius, 1), 0, 1)[:, None]
    if keep:
        hold *= np.clip((s[-1]-u-keep)/radius, 0, 1)[:, None]
    return [tuple(p) for p in line*(1-hold)+smooth_line*hold]


def lanes():
    """Tracks: down each dale to its own gate, a track along each court
    joining the three, and from each gate to its ford. Each half's tracks
    wander in their own way."""
    out = []
    cx, cy, _, hy = COURT
    for dale, (gate, _) in zip(DALES, GATES):
        out.append(dale[::-1]+[((dale[0][0]+gate[0][0])/2, (dale[0][1]+gate[0][1])/2)]+gate)
    out.append([(cx-60*S, DALES[0][0][1]-40*S), (cx+110*S, cy+520*S), (cx+150*S, cy+90*S), (cx-30*S, cy-480*S),
                (cx-60*S, DALES[2][0][1]+40*S)])
    lines = []
    for k, p in enumerate(out):
        lines.append(bend(wander(p, SEED+400+k, 170, 380)))
        lines.append(bend(wander(turned(p), SEED+500+k, 170, 380)))
    # From each gate out to its crossing: wandering over the field, then
    # straight in square to the river, unwandered, so it meets the crossing.
    for k, ((gate, _), crossing) in enumerate(zip(GATES, fords())):
        for team, (end, cross, side) in enumerate(((gate[-1], crossing, -1), (turned(gate)[-1], turned([crossing])[0], 1))):
            straight = approach(cross, side, end)
            lead = wander([end, ((end[0]+straight[0][0])/2, (end[1]+straight[0][1])/2), straight[0]], SEED+600+2*k+team, 150, 380)
            lines.append(bend(lead[:-1]+straight, keep=400))
    return lines


def lane_field(t, lines):
    """Distance to the nearest of the lines, exact within 500 (every use compares
    it against less); inf beyond."""
    return nearest(lines, t['x'], t['y'], reach=500)


def materials(t):
    x, y, z, sd = t['x'], t['y'], t['z'], t['sd']
    gy, gx = np.gradient(z, 10); slope = np.hypot(gx, gy)
    broad = fbm(x, y, scale=1100, seed=SEED+20, octaves=3)
    mid = fbm(x+2000, y, scale=320, seed=SEED+21, octaves=3)
    fine = fbm(x, y+2000, scale=90, seed=SEED+22, octaves=2)
    v = .65*broad+.35*mid+.1*fine
    # Quiet meadow is continuous; autumn colour gathers in broad drifts and
    # under groves. Damp hollows and dry shoulders explain the transitions.
    labels = np.full(z.shape, MIXED, dtype='u2')
    labels[(v > .04) & (z > WATER+16) & (t['hollows'] < .25)] = DRY
    labels[(broad > .08) & (mid > -.12) & (t['hollows'] < .3)] = OCHRE
    labels[(t['woods'] > .35) & (mid > .18)] = RED
    labels[(t['woods'] > .5) & (broad < -.12)] = RUST
    labels[(broad > .18) & (mid < -.25) & (z > WATER+18)] = GOLD
    # Damp, gently sloping deposits grow grass in patches. Steep cut banks
    # and exposed shores interrupt it, rather than outlining the whole river.
    edge = fbm(x, y, scale=70, seed=SEED+23, octaves=2)
    stream = t['stream']
    damp = ((stream < 30+170*t['deposit']) & (z < WATER+12)) | (t['hollows'] > .45)
    labels[damp & (slope < .24) & (mid+.35*broad > -.03)] = GREEN
    labels[(stream > 0) & (stream < 25+55*t['deposit']) & (z < WATER+4) & (labels != GREEN)] = SILT
    labels[(stream < 9+5*edge) & (stream > -3) & (z > WATER-.3)] = MUD      # a thin wet rim
    labels[z < WATER-.3] = SILT
    labels[(t['shelf'] > .3+.25*fine) & (z < WATER+.4+.6*edge)] = TRODDEN      # the fords' gravel, under water
    # Foothills and mountains: rocky grass at the cliff foot, grey cliffs,
    # rust-red rock higher up, scree, then snow-streaked crags and snowfields.
    labels[(slope > .22+.1*mid+.06*fine) & (slope < .5)] = ROCKY_GRASS
    labels[(sd > 200+150*broad) & (slope <= .5) & (fine+.6*mid > .15)] = ROCKY_GRASS
    labels[slope > .45+.08*fine] = ROCK
    labels[slope > .75+.1*fine] = CLIFF
    labels[(slope > .75+.1*fine) & (broad+.25*mid > .05)] = CLIFF_HIGH
    # High up, broad sweeps rather than speckle: rust-red or grey crags by
    # the broad noise, scree on the gentler shoulders, snow-streaked rock
    # only near the summits, and snow lying where it can settle.
    high = z > 470+60*broad
    labels[high & (slope > .6) & (broad > -.05)] = CLIFF_HIGH
    labels[high & (slope > .6) & (broad <= -.05)] = CLIFF
    labels[(z > 560+60*broad) & (slope <= .6) & (mid > -.15)] = SCREE
    labels[(z > 780+70*broad) & (slope > .55)] = CLIFF_SNOW
    labels[(z > 690+70*broad+25*mid) & (slope <= .5)] = SNOW
    labels[(z > 800+60*broad) & (slope <= .45)] = SNOW_DEEP
    labels[(z > 900+60*broad) & (slope < .85) & (fine > -.25)] = SNOW         # caps on the highest tops
    labels[(z > 1000+50*broad) & (slope < .6)] = SNOW_DEEP
    # Tracks: packed earth with a speckled fringe.
    dry = z > WATER+.5
    # They fade out as they reach each base's building ground.
    fade = np.ones(z.shape, bool)
    for px, py in start_positions():
        fade &= np.hypot(x-px, y-py) > BASE_FLAT-60+80*fine
    # Old tracks across wild country: a worn, grassy band of uneven width
    # with bare earth only in patches where the ground is trodden most, and
    # gaps where the grass has taken them back.
    wear = fbm(x-2600, y+1400, scale=220, seed=SEED+24, octaves=3)
    width = 16+8*wear+5*fine
    # Busier near the crossings and the courts' gates, where every army passes.
    busy = np.zeros(z.shape)
    for px, py in fords()+turned(fords()):
        busy = np.maximum(busy, 1-smooth(250, 700, np.hypot(x-px, y-py)))
    worn = wear+.5*busy
    edge_width = width+6*fbm(x+900, y-500, scale=40, seed=SEED+25, octaves=2)
    labels[(t['lanes'] < edge_width) & dry & (fine > -.5) & fade] = LANE_EDGE
    labels[(t['lanes'] < .35*edge_width) & dry & (worn > -.1) & (fine > -.1) & fade] = LANE
    # The goat paths: a thin line of trodden earth, broken where grass grows over it.
    labels[(t['trail'] < 10+4*fine) & dry & (fine > -.3)] = LANE_EDGE
    labels[(t['trail'] < 4+3*fine) & dry & (fine > -.1)] = LANE
    # The ruins of Ost-in-Edhil: old paving round the middle ford.
    # Under the constructs: old paving, broken up and grown over at its edge,
    # with rubble round it; trodden earth round the inns and outposts.
    chip = fbm(x, y, scale=60, seed=SEED+26, octaves=2)
    for fx, fy, r, kind in t.get('footings', []):
        # Only the window round each footing.
        r0, r1 = max(round((fy-r-90)/10)+BORDER, 0), round((fy+r+90)/10)+BORDER+1
        c0, c1 = max(round((fx-r-90)/10)+BORDER, 0), round((fx+r+90)/10)+BORDER+1
        w = (slice(r0, r1), slice(c0, c1))
        d = np.hypot(x[w]-fx, y[w]-fy)+r*.35*chip[w]
        sub, ok, f, mm = labels[w], dry[w], fine[w], mid[w]
        if kind == 'stone':
            # Broken slabs among grass and stones: never one solid floor.
            c = chip[w]
            sub[ok & (d < r+55) & (f+.4*mm > -.05)] = RUBBLE
            sub[ok & (d < r) & (f+.5*c > .05)] = PAVING
        else:
            sub[ok & (d < r+40) & (f > -.2)] = LANE_EDGE
            sub[ok & (d < .7*r) & (f > -.3)] = TRODDEN
    # Fallen leaves under the woods, red and gold.
    labels[(t['woods'] > .6+.2*fine) & dry & (slope < .45) & (fine > -.1)] = LEAVES
    labels[(t['woods'] > .75+.2*fine) & dry & (slope < .45) & (mid > .15)] = RUST
    return labels


class Scenery:
    """Object placement with spacing, water, slope, lane, base and site checks."""

    TREE_LIMIT, SHRUB_LIMIT = 1150, 1950      # the game's optimized vegetation buffers, less a margin

    def __init__(self, m, t, assets, keep_clear):
        self.m, self.t, self.assets = m, t, assets
        self.keep_clear = keep_clear              # (x, y, radius): sites and their flags
        self.buckets = {}; self.counts = Counter(); self.kinds = {}; self.vegetation = Counter()
        self.footings = []                         # (x, y, radius, kind): ground worn under constructs
        gy, gx = np.gradient(t['z'], 10); self.slope = np.hypot(gx, gy)

    def kind(self, template):
        if template not in self.kinds:
            if template.lower() not in self.assets.templates:
                raise ValueError('Unknown template: '+template)
            r = self.assets.template_model(template)
            self.kinds[template] = None if not r or not r['tree'] else \
                'tree' if 'TREE' in r['kinds'] else 'shrub' if 'SHRUB' in r['kinds'] else None
        return self.kinds[template]

    def at(self, field, x, y):
        return float(self.t[field][round(y/10)+BORDER, round(x/10)+BORDER])

    def put(self, template, x, y, angle=None, layer='', gap=20, lane=40, base=700, slope=.5, wet=False,
            scale=None, z=0, mountain=False, footing=None):
        """Place one object if the spot is clear: dry (unless `wet`), no
        steeper than `slope`, off the tracks, away from the bases and sites,
        on open ground (unless `mountain`) and `gap` from everything placed."""
        if not (60 < x < SPAN_X-60 and 60 < y < SPAN_Y-60):
            return False
        iy, ix = round(y/10)+BORDER, round(x/10)+BORDER
        if self.slope[iy, ix] > slope or self.t['ways'][iy, ix] < lane:
            return False
        if not wet and (self.t['z'][iy, ix] < WATER+1.5 or self.t['stream'][iy, ix] < 8):
            return False
        if not mountain and self.t['sd'][iy, ix] > 40:
            return False
        if any(math.dist((x, y), p) < base for p in start_positions()):
            return False
        if any(math.dist((x, y), (px, py)) < r for px, py, r in self.keep_clear):
            return False
        cx, cy = int(x//100), int(y//100)
        for bx in range(cx-2, cx+3):
            for by in range(cy-2, cy+3):
                for ox, oy, og in self.buckets.get((bx, by), ()):
                    if math.dist((x, y), (ox, oy)) < max(gap, og):
                        return False
        kind = self.kind(template)
        local = spot_random(SEED, template, x, y)
        extra = []
        if kind:
            if self.vegetation[kind] >= (self.TREE_LIMIT if kind == 'tree' else self.SHRUB_LIMIT):
                return False
            if scale is None:
                low, mode, high = (.8, 1., 1.3) if kind == 'tree' else (.85, 1., 1.15)
                scale = local.triangular(low, high, mode)
            self.vegetation[kind] += 1
        if scale is not None:
            extra.append(('objectPrototypeScale', 2, round(scale, 3)))
        if angle is None:
            angle = local.random()*math.tau
        add_object(self.m, template, x, y, angle, layer=layer, extra=extra, z=z)
        if footing:
            self.footings.append((x, y)+tuple(footing))
        self.buckets.setdefault((cx, cy), []).append((x, y, min(gap, 200)))
        self.counts[layer] += 1
        return True


def woods_field(t):
    """Where the woods grow, 0 to 1: groves in the dales and the field,
    thickest at the cliff foot and along the stream, thin on the open
    middle of the field. Not mirrored: each half has its own woods."""
    x, y, sd = t['x'], t['y'], t['sd']
    groves = fbm(x+700, y-2300, scale=520, seed=SEED+30, octaves=4)
    foot = smooth(-420, -120, sd)*(1-smooth(30, 120, sd))
    banks = (1-smooth(60, 380, t['stream']))*(.25+.75*t['deposit'])
    openness = smooth(500*S, 900*S, np.abs(x-CX))*.25+.75
    w = smooth(.05, .45, groves+.45*foot+.2*banks+.18*t['hollows']-.1)*openness
    w *= smooth(40, 120, t['ways'])
    # Round each base the trees keep to the bowl's rim, clear of the building ground.
    for px, py in start_positions():
        r = np.hypot(x-px, y-py)
        w = np.where(r < BOWL+300, np.maximum(w, .7*smooth(-260, -60, sd)), w)*smooth(BASE_FLAT+130, BASE_FLAT+330, r)
    return np.clip(w, 0, 1)


AUTUMN = ['TreeIronHills03', 'TreeIronHills03', 'TreeIronHills04', 'TreeDiospyros2', 'TreeDiospyros2',
          'TreeDiospyros2', 'PTree10_Large', 'PTree10_Large', 'TreeEvergreen03', 'TreeEvergreen03', 'TreeHopea']
CONIFERS = ['TreeLothlorien09', 'TreeLothlorien10', 'TreeEvergreen01', 'TreeIronHills01']
UNDERGROWTH = ['OptGrass02', 'OptGrass03', 'GladdenFieldsShrub01', 'GladdenFieldsShrub02', 'OptBushLG06']
BOULDERS = ['DarkRockGrey05', 'DarkRockGrey06', 'DarkRockGrey07', 'DarkRockGrey14', 'DarkRockGrey16', 'DarkRockGrey18']
STONES = ['DarkRockGrey02', 'DarkRockGrey17', 'RockGrey02', 'RockGrey17', 'DarkRockGrey19']


def fallen(s, rng, x, y, layer):
    """Masonry fallen from a ruin: a few blocks and stones round it."""
    for _ in range(rng.randint(4, 8)):
        a = rng.random()*math.tau; r = rng.uniform(55, 110)
        s.put(rng.choice(STONES+['HarlindonRuin07']), x+math.cos(a)*r, y+math.sin(a)*r, layer=layer, gap=18, lane=30,
              base=BASE_FLAT+20, slope=.6, z=-1)


def ruins(s, t, rng):
    """Ost-in-Edhil round the middle ford: a fountain court and a tower on
    the west bank, a broken hall and a second tower on the east, walls of
    arcades breaking off between them, and rubble. Then a broken gatehouse
    at most of the courts' gates, and a lone ruin up some of the dales."""
    # Ost-in-Edhil's bridgeheads: at each end of the bridge the road passes
    # between two gate towers through a broken wall along the riverbank;
    # beyond it a ruined square on one side of the road and a great hall on
    # the other, and rubble everywhere. Each bank's quarter is its own.
    (bx, by), (ux, uy) = bridges()[0]
    quarters = {-1: dict(square=('HarlindonRuin13', 'HarlindonRuin15', 'HarlindonRuin07'), hall='HarlindonRuin17'),
                1: dict(square=('HarlindonRuin08', 'HarlindonRuin19', 'HarlindonRuin02'), hall='HarlindonRuin01')}
    for side, quarter in quarters.items():
        ox, oy = ux*side, uy*side                      # outward along the road
        rx, ry = -oy, ox                               # along the river
        # The square goes on the side away from the inn.
        inn = min(((px, py) for px, py, _ in s.keep_clear if math.dist((px, py), (bx, by)) < 1200),
                  key=lambda p: math.dist(p, (bx, by)), default=(bx+rx, by+ry))
        north = 1 if (inn[0]-bx)*rx+(inn[1]-by)*ry < 0 else -1
        def at(d, c):
            return bx+ox*d+rx*c, by+oy*d+ry*c
        facing = math.atan2(oy, ox)
        def put(template, d, c, angle, r, kind='stone', **kw):
            px, py = at(d+rng.uniform(-8, 8), c+rng.uniform(-8, 8))
            return s.put(template, px, py, angle=angle+rng.uniform(-.06, .06), layer='OstInEdhil', gap=30, lane=0,
                         base=0, slope=1, z=-2, footing=(r, kind), **kw)
        for c in (-95, 95):                            # the gate towers
            put('HarlindonRuin05', 380, c, facing-math.pi/2, 55)
        for sign in (-1, 1):                           # the riverbank wall, broken
            for k, c in enumerate((200, 375, 550)):
                if k == 2 and rng.random() < .5:
                    continue
                put(rng.choice(['HarlindonRuin10', 'HarlindonRuin11', 'HarlindonRuin12']), 370+rng.uniform(-10, 10),
                    sign*c, facing, 50)
        centre, second, third = quarter['square']
        put(centre, 700, north*300, facing, 120)
        put(second, 640, north*470, facing+math.pi, 70)
        put(third, 800, north*190, facing+math.pi/2, 50)
        put(quarter['hall'], 720, -north*330, facing+math.pi/2, 120)
        # The road through the quarter was paved, from the bridge to beyond the square.
        for dd in range(300, 900, 60):
            s.footings.append(at(dd, rng.uniform(-6, 6))+(42, 'stone'))
        for _ in range(26):
            d, c = rng.uniform(380, 900), rng.uniform(-650, 650)
            px, py = at(d, c)
            s.put(rng.choice(STONES+['HarlindonRuin07']), px, py, layer='OstInEdhil', gap=25, lane=30, base=0,
                  slope=.6, z=-1)
    # Gatehouses: where each gate is narrowest, a broken arcade wall runs
    # across it from each cliff, leaving the middle open; some keep a
    # tower at the gap, some only its fallen stump, some nothing.
    for line, width in gate_lines():
        k = len(line)//2
        (ax, ay), (bx, by) = line[k-3], line[k+3]
        dx, dy = (bx-ax)/math.dist((ax, ay), (bx, by)), (by-ay)/math.dist((ax, ay), (bx, by))
        mx, my = line[k]
        across = math.atan2(dy, dx)             # turns a wall's local y (its length) across the gate
        for side in (-1, 1):
            r = width+45+rng.uniform(-15, 25)
            # A wall is long: none stands within reach of a knoll's path.
            clear = s.at('trail', mx-dy*side*r, my+dx*side*r) > 140
            if rng.random() < .85 and clear:
                s.put(rng.choice(['HarlindonRuin10', 'HarlindonRuin11', 'HarlindonRuin12']), mx-dy*side*r, my+dx*side*r,
                      angle=across+rng.uniform(-.06, .06), layer='Gatehouses', gap=40, lane=0, base=0, slope=2,
                      z=-3, mountain=True, footing=(55, 'stone'))
            pick = rng.random()
            if pick < .55 and clear:
                r = width-55
                s.put('HarlindonRuin05' if pick < .3 else 'HarlindonRuin16', mx-dy*side*r, my+dx*side*r,
                      angle=across+rng.choice([0, math.pi])+rng.uniform(-.1, .1), layer='Gatehouses', gap=40,
                      lane=0, base=0, slope=.8, z=-3, mountain=True, footing=(50, 'stone'))
    # Each base's bowl keeps one old Elven building against its cliff, out
    # of the building ground; no two bowls the same.
    keepsakes = ['HarlindonRuin05', 'HarlindonRuin15', 'HarlindonRuin16', 'HarlindonRuin13', 'HarlindonRuin19',
                 'HarlindonRuin14']
    rng.shuffle(keepsakes)
    for template, (px, py) in zip(keepsakes, start_positions()):
        for _try in range(60):
            a = rng.random()*math.tau; r = rng.uniform(BOWL-150, BOWL-40)
            qx, qy = px+math.cos(a)*r, py+math.sin(a)*r
            if s.at('sd', qx, qy) > -30 or s.at('lanes', qx, qy) < 120:
                continue
            if s.put(template, qx, qy, angle=a+math.pi/2+rng.uniform(-.3, .3), layer='BowlRuins', gap=90, lane=60,
                     base=BASE_FLAT+60, slope=.35, z=-2, footing=(60, 'stone')):
                fallen(s, rng, qx, qy, 'BowlRuins')
                break
    for k, (line, (bx, by)) in enumerate(dale_lines()):
        if rng.random() < .3:
            continue
        for _try in range(30):
            f = rng.uniform(.3, .7); px, py = line[int(f*(len(line)-1))]
            a = rng.random()*math.tau; r = rng.uniform(150, 260)
            if s.put(rng.choice(['HarlindonRuin02', 'HarlindonRuin03', 'HarlindonRuin17', 'HarlindonRuin19',
                                 'HarlindonRuin15']), px+math.cos(a)*r, py+math.sin(a)*r,
                     layer='DaleRuins', gap=80, lane=60, slope=.3, z=-2, footing=(60, 'stone')):
                fallen(s, rng, px+math.cos(a)*r, py+math.sin(a)*r, 'DaleRuins')
                break


def riverside(s, t, rng):
    """The Sirannon's banks, decorated in patches rather than evenly: reed
    beds that come and go along the water's edge, gathering where the bank is
    low; rocks heaped where it is steep, some out in the shallows; driftwood
    caught against the shore; small groves of trees leaning over the water;
    stepping stones on each ford's downstream side; ripples along the
    waterline; ducks in the quiet reaches and fish in the deep."""
    x, y, river = t['x'], t['y'], t['stream']
    rows, cols = river.shape
    gy, gx = np.gradient(t['z'], 10); slope = np.hypot(gx, gy)
    patch = fbm(x+5100, y-2300, scale=320, seed=SEED+70, octaves=3)      # where reeds grow, where rocks lie
    crossing = np.min([np.hypot(x-fx, y-fy) for fx, fy in fords()+turned(fords())], axis=0)
    away = crossing > 230                                                   # the crossings stay clear

    def cell(px, py):
        return min(max(round(py/10)+BORDER, 0), rows-1), min(max(round(px/10)+BORDER, 0), cols-1)

    def flow(px, py):
        """The river's direction at the nearest bank point, as an angle."""
        ux, uy = across(px, py)
        return math.atan2(ux, -uy)

    def seeds(mask, seed, count, apart):
        cells = np.column_stack(np.nonzero(mask))
        cells = cells[np.random.default_rng(seed).permutation(len(cells))]
        chosen = []
        for iy, ix in cells:
            if len(chosen) >= count:
                break
            p = ((ix-BORDER)*10., (iy-BORDER)*10.)
            if all(math.dist(p, q) > apart for q in chosen):
                chosen.append(p)
        return chosen

    REEDS = ['GladdenFieldsShrub01', 'GladdenFieldsShrub01', 'GladdenFieldsShrub02', 'OptGrass02']
    # Reed beds: along the edge where the bank is low, each a long clump
    # lying along the water, thick in the middle and thinning out.
    reed_banks = away & (river > -12) & (river < 4) & (patch > 0) & (t['deposit'] > .45)
    for cx, cy in seeds(reed_banks, SEED+71, 45, 150):
        a = flow(cx, cy); ax, ay = math.cos(a), math.sin(a)
        size = rng.uniform(.7, 1.5)
        for _ in range(int(rng.uniform(12, 24)*size)):
            along, out = rng.gauss(0, 38*size), rng.gauss(0, 12)
            px, py = cx+ax*along-ay*out, cy+ay*along+ax*out
            if -28 < river[cell(px, py)] < 18:
                s.put(rng.choice(REEDS), px, py, layer='Riverside', gap=9, lane=25, base=500, slope=.9, wet=True,
                      scale=rng.uniform(.8, 1.25))
    # Rocks where the bank is steep or the current strong: a boulder or two,
    # stones round them, a few out in the shallows.
    rocky_banks = away & (river > -25) & (river < 30) & (patch < -.15) & (t['deposit'] < .6)
    for cx, cy in seeds(rocky_banks, SEED+72, 26, 260):
        for _ in range(rng.randint(1, 2)):
            px, py = cx+rng.gauss(0, 18), cy+rng.gauss(0, 18)
            under = river[cell(px, py)] < 0
            s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey18', 'DarkRockGrey06', 'DarkRockGrey14']), px, py,
                  layer='Riverside', gap=30, lane=40, base=500, slope=1.5, wet=True,
                  scale=rng.uniform(.35, .7), z=-4 if under else -2)
        for _ in range(rng.randint(3, 7)):
            px, py = cx+rng.gauss(0, 35), cy+rng.gauss(0, 35)
            s.put(rng.choice(STONES), px, py, layer='Riverside', gap=12, lane=30, base=500, slope=1.5, wet=True, z=-1)
    # Driftwood caught on the shore, lying along the flow.
    for cx, cy in seeds(away & (river > -10) & (river < 6), SEED+73, 9, 700):
        s.put(rng.choice(['TreeLog', 'PTrunk_S', 'TreeFallDead01']), cx, cy, angle=flow(cx, cy)+rng.uniform(-.5, .5),
              layer='Riverside', gap=40, lane=40, base=500, slope=1.2, wet=True, scale=rng.uniform(.6, .9), z=-2)
    # Small groves on the banks, some leaning out over the water.
    for cx, cy in seeds(away & (river > 25) & (river < 90) & (t['ways'] > 70) & (patch > -.05), SEED+74, 14, 450):
        for _ in range(rng.randint(2, 4)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 45))
            s.put(rng.choice(AUTUMN[:7]+CONIFERS[:2]), cx+math.cos(a)*r, cy+math.sin(a)*r, layer='Riverside',
                  gap=38, lane=50, base=600, slope=.8)
        for _ in range(rng.randint(3, 6)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 55))
            s.put(rng.choice(UNDERGROWTH), cx+math.cos(a)*r, cy+math.sin(a)*r, layer='Riverside', gap=16, lane=30,
                  slope=.8)
    # Stepping stones along each ford's downstream edge.
    for fx, fy in (fords()[0], fords()[2])+tuple(turned([fords()[0], fords()[2]])):
        if river[cell(fx, fy)] > 0:
            continue
        ux, uy = across(fx, fy)
        down = 1 if fy > CY else -1                    # the river flows south: downstream is south
        dx, dy = uy*down, -ux*down
        if dy > 0:
            dx, dy = -dx, -dy
        for k in range(-4, 5):
            if rng.random() < .3:
                continue                                # gaps where the current has rolled a stone away
            px, py = fx+ux*k*42+dx*55+rng.uniform(-10, 10), fy+uy*k*42+dy*55+rng.uniform(-14, 14)
            ground = float(t['z'][cell(px, py)])
            if ground < WATER-4:
                continue
            # Each stone's top just breaks the surface of the ford.
            s.put(rng.choice(['DarkRockGrey17', 'DarkRockGrey02', 'RockGrey17']), px, py, layer='Riverside', gap=20,
                  lane=0, base=0, slope=2, wet=True, z=WATER-1.5-ground, scale=rng.uniform(.8, 1.15))
    # Ripples where the water meets the shore, turned along it.
    for px, py in seeds(away & (river > -14) & (river < -4), SEED+75, 70, 150):
        s.put('WaterRipples', px, py, angle=flow(px, py), layer='Riverside', gap=12, lane=0, base=500, slope=3,
              wet=True, z=WATER+.3-float(t['z'][cell(px, py)]))
    # Ducks in the quiet reaches by the reeds, fish in the deep water.
    for px, py in seeds(away & (river > -40) & (river < -20) & (patch > .3), SEED+76, 7, 600):
        s.put('Duck', px, py, layer='Riverside', gap=20, lane=0, base=500, slope=3, wet=True)
    for px, py in seeds(away & (river < -70), SEED+77, 6, 900):
        s.put('Fish', px, py, layer='Riverside', gap=20, lane=0, base=500, slope=3, wet=True)


def woods(s, t, rng):
    """Trees by the woods field, in loose clumps; conifers higher up on the
    mountains' ledges; undergrowth at the woods' edges and boulders at the
    cliff foot. Every half is planted separately."""
    # Boulders fallen from the cliffs, lying in loose spills at their foot.
    foot = np.column_stack(np.nonzero((t['sd'] > -120) & (t['sd'] < 40)))
    order = np.random.default_rng(SEED+34).permutation(len(foot))
    spills = 0; heaps = []
    for iy, ix in foot[order]:
        if spills >= 150:
            break
        cx, cy = (ix-BORDER)*10, (iy-BORDER)*10
        if any(math.dist((cx, cy), p) < 260 for p in heaps):
            continue
        if not s.put(rng.choice(BOULDERS), cx, cy, layer='Boulders', gap=50, lane=50, slope=.7, z=-4,
                     scale=rng.uniform(.7, 1.4)):
            continue
        spills += 1; heaps.append((cx, cy))
        for _ in range(rng.randint(2, 6)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 50))
            s.put(rng.choice(STONES), cx+math.cos(a)*r, cy+math.sin(a)*r, layer='Boulders', gap=14, lane=35, slope=.7)
    w = t['woods']
    rows, cols = w.shape
    cells = np.column_stack(np.nonzero(w > .15))
    order = np.random.default_rng(SEED+31).permutation(len(cells))
    for iy, ix in cells[order]:
        if s.counts['Woods'] >= 720:
            break
        if w[iy, ix] < .35 or rng.random() > w[iy, ix]**3:
            continue
        x, y = (ix-BORDER)*10+rng.uniform(-5, 5), (iy-BORDER)*10+rng.uniform(-5, 5)
        s.put(rng.choice(AUTUMN), x, y, layer='Woods', gap=30, lane=35, slope=.6, base=BASE_FLAT+120)
    # Conifers on the mountains' gentler ledges, below the snow.
    ledges = np.column_stack(np.nonzero((t['sd'] > 30) & (t['z'] < 560) & (s.slope < .55)))
    order = np.random.default_rng(SEED+32).permutation(len(ledges))
    for iy, ix in ledges[order]:
        if s.counts['MountainTrees'] >= 220:
            break
        if rng.random() > .25:
            continue
        x, y = (ix-BORDER)*10, (iy-BORDER)*10
        s.put(rng.choice(CONIFERS), x, y, layer='MountainTrees', gap=45, lane=0, base=600, slope=.55, mountain=True)
    # A few trees clinging to the knolls' skirts between the crags.
    skirts = np.column_stack(np.nonzero((t['knoll'] > .4) & (t['sd'] > -40) & (s.slope < .5) & ~t['climb']))
    order = np.random.default_rng(SEED+36).permutation(len(skirts))
    for iy, ix in skirts[order]:
        if s.counts['KnollTrees'] >= 110:
            break
        if rng.random() > .3:
            continue
        s.put(rng.choice(CONIFERS+AUTUMN[:6]), (ix-BORDER)*10, (iy-BORDER)*10, layer='KnollTrees', gap=40, lane=40,
              base=600, slope=.5, mountain=True)
    # Undergrowth along the woods' edges, and tufts across the open grass.
    edge = np.column_stack(np.nonzero((w > .05) & (w < .45)))
    order = np.random.default_rng(SEED+33).permutation(len(edge))
    for iy, ix in edge[order][:20000]:
        if s.counts['Undergrowth'] >= 1300:
            break
        if rng.random() > .2:
            continue
        s.put(rng.choice(UNDERGROWTH), (ix-BORDER)*10, (iy-BORDER)*10, layer='Undergrowth', gap=22, lane=30, slope=.5)
    # Drifts of tussocks and bushes out in the open grass, each its own clump.
    drift = fbm(t['x']-1700, t['y']+900, scale=260, seed=SEED+37, octaves=3)
    open_ground = (w < .1) & (t['sd'] < -120) & (t['lanes'] > 60) & (drift > .15) & (t['stream'] > 120)
    seeds = np.column_stack(np.nonzero(open_ground))
    seeds = seeds[np.random.default_rng(SEED+38).permutation(len(seeds))]
    drifts = []
    for iy, ix in seeds:
        if len(drifts) >= 110 or s.vegetation['shrub'] >= s.SHRUB_LIMIT:
            break
        cx, cy = (ix-BORDER)*10., (iy-BORDER)*10.
        if any(math.dist((cx, cy), q) < 240 for q in drifts):
            continue
        drifts.append((cx, cy))
        for _ in range(rng.randint(4, 9)):
            a = rng.random()*math.tau; r = abs(rng.gauss(0, 45))
            s.put(rng.choice(UNDERGROWTH+['OptGrass02', 'OptGrass03']), cx+math.cos(a)*r, cy+math.sin(a)*r,
                  layer='Drifts', gap=18, lane=40, base=BASE_FLAT+40)
    # Lone trees out in the open, well apart from each other.
    lone = []
    for _ in range(6000):
        if len(lone) >= 45:
            break
        x, y = rng.uniform(300, SPAN_X-300), rng.uniform(300, SPAN_Y-300)
        if s.at('woods', x, y) > .2 or s.at('sd', x, y) > -150 or any(math.dist((x, y), q) < 450 for q in lone):
            continue
        if s.put(rng.choice(AUTUMN[:7]), x, y, layer='LoneTrees', gap=40, lane=70, slope=.3, scale=rng.uniform(1.15, 1.45)):
            lone.append((x, y))


def fairness(m):
    """Walking distances from the map's own walking grid (mapkit.checks.strategy).

    Every player's nearest enemy must be about as far; within a team, the
    bases reach each other only through their court, so no two teammates
    may be much closer than the way through it."""
    from mapworkshop.mapkit.checks.strategy import analyse
    report = analyse(m, [[1, 2, 3], [4, 5, 6]])[0]
    matrix = report['base_distances']
    rush = [min(matrix[i][j] for j in range(6) if (i < 3) != (j < 3)) for i in range(6)]
    if not np.isfinite(rush).all():
        raise ValueError(f'A start cannot reach the enemy: {rush}')
    if max(rush)-min(rush) > 300:
        raise ValueError(f'Unfair layout: nearest enemy {rush}')
    court = COURT[:2]
    for team, centre in (([0, 1, 2], court), ([3, 4, 5], turned([court])[0])):
        for i in team:
            for j in team:
                if i < j:
                    a, b = start_positions()[i], start_positions()[j]
                    through = math.dist(a, centre)+math.dist(centre, b)
                    if matrix[i][j] < .8*through:
                        raise ValueError(f'Players {i+1} and {j+1} meet outside their court: {matrix[i][j]} < {through:.0f}')
    return dict(nearest_enemy=rush, base_distances=matrix, teams=report['teams'],
                territory_share=[p['territory_share'] for p in report['players']])


def sites(m, t):
    """Neutral sites in the field, each with its turned copy: an outpost by
    each team's north ford, an inn on the ruins beside the middle ford, a
    creep lair at the field's far ends, and Gollum's spawn points."""
    placed = []
    for template, (px, py), angle in [('Outpost', (CX-470*S, CY+1750*S), -.4), ('Inn', (CX-560, CY-380), .9)]:
        for (sx, sy), a in (((px, py), angle), ((SPAN_X-px, SPAN_Y-py), angle+math.pi)):
            fx, fy = neutral_site(m, template, sx, sy, angle=a, layer='Sites')
            placed.append((template, sx, sy))
            placed.append(('CaptureFlag', fx, fy))
    for px, py in [(CX+360*S, CY+2050*S)]:
        for sx, sy in ((px, py), (SPAN_X-px, SPAN_Y-py)):
            creep_lair(m, 'WargLair', sx, sy, angle=math.atan2(CY-sy, CX-sx), layer='Sites')
            placed.append(('WargLair', sx, sy))
    gollum_spawns(m, [(CX-400*S, CY+700*S), (CX+400*S, CY-700*S), (CX+450*S, CY+1100*S), (CX-450*S, CY-1100*S)])
    return placed


def sounds(m, t):
    """A woodland bed, the Sirannon along its course, birds in the woods
    and over the open grass, wind and falling stones on the heights."""
    def cells(mask, step=20):
        iy, ix = np.nonzero(mask[::step, ::step])
        return [(float((x*step-BORDER)*10), float((y*step-BORDER)*10)) for y, x in zip(iy, ix)]
    inside = (t['x'] > 200) & (t['x'] < SPAN_X-200) & (t['y'] > 200) & (t['y'] < SPAN_Y-200)
    stream = [(x, y) for x, y in along(t['line'], 500) if 0 < y < SPAN_Y]
    return ambient(m, 'forest', (CX, CY), dict(
        creek=stream, woods=cells(inside & (t['woods'] > .6)),
        open=cells(inside & (t['sd'] < -200) & (t['woods'] < .1) & (t['stream'] > 200)),
        heights=cells(inside & (t['sd'] > 250) & (t['sd'] < 700))), limits=dict(heights=14, open=10, woods=12))


def bridge_water(m, t, assets):
    """Water around the bridge at viewer mark (5442.1, 3780.6).

    Measure the four separate masonry sections at WATER, not the deck's
    top-down silhouette. Small upstream disturbances divide round their
    edges; narrow side foam feeds two broken wakes below the downstream
    supports. This is authored surface motion, not a fluid simulation.
    """
    from mapworkshop.render.footprint import section

    # Local +x is downstream, +y follows the deck towards the east bank.
    # The bridge's origin is BRIDGE_BANK-1; currently the water cut is -11.
    rings = section(BRIDGE, WATER-(BRIDGE_BANK-1), assets=assets)
    counts = Counter()
    for (bx, by), (ax, ay) in bridges():
        fx, fy = ay, -ax
        angle = math.atan2(fy, fx)

        def place(template, down, across, direction=0.):
            x, y = bx+fx*down+ax*across, by+fy*down+ay*across
            ground = float(t['z'][round(y/10)+BORDER, round(x/10)+BORDER])
            if ground >= WATER-2:
                return                            # no foam emitters on dry banks
            add_object(m, template, x, y, angle+direction, layer='BridgeWater',
                       z=WATER+1.6-ground)
            counts[template] += 1

        for ring in rings:
            downstream = max(x for x, y in ring) > 0
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]+ring[:1]):
                dx, dy = x2-x1, y2-y1
                length = math.hypot(dx, dy)
                nx, ny = dy/length, -dx/length      # outward from CCW solid
                if nx < -.8 and not downstream:
                    # Nose: foam slips sideways away from the stagnation
                    # point, just outside the measured upstream stone face.
                    middle = (y1+y2)/2
                    for f in (.2, .5, .8):
                        x, y = x1+dx*f+nx*3, y1+dy*f+ny*3
                        # Increasing local y is a positive turn from +x.
                        place('LakeRipple', x, y, math.copysign(math.pi/2, y-middle))
                elif abs(nx) < .25 and length > 12:
                    # Short-lived flecks follow the actual stepped flanks.
                    # Sample from upstream so their drift exits each edge.
                    n = max(1, int(length/14))
                    for k in range(n):
                        f = (k+.3)/n
                        if dx < 0:
                            f = 1-f
                        place('WtrflHaze', x1+dx*f+nx*3, y1+dy*f+ny*3)
                elif nx > .8 and downstream and max(x1, x2) > 80:
                    # Two sparse filaments leave each exposed downstream
                    # face, gently spreading and fading over 70-110 units.
                    for f, turn in ((.28, -.10), (.72, .10)):
                        y = min(y1, y2)+abs(dy)*f
                        place('WtrflSteam', max(x1, x2)+5, y, turn)

        # A few smaller, faster flecks carry the clear central jet out from
        # the 62-unit arch opening; no full-width band of white water.
        for u in (-13, 13):
            place('LakeCoast01', 91, u)

    def effect(name, size, life, speed, alpha, delay, spread, spin):
        return f"""FXParticleSystem {name}
  System
    Priority = ALWAYS_RENDER
    Shader = ALPHA
    ParticleName = EXwaterpuddle2.tga
    Lifetime = {life} {life+12}
    Size = {size} {size+3}
    BurstDelay = {delay} {delay+2}
    BurstCount = 1 1
    IsGroundAligned = Yes
    SortLevel = 2
  End
  Color = DefaultColor
    Color1 = R:215 G:225 B:220 0
    Color2 = R:170 G:190 B:190 {life}
  End
  Alpha = DefaultAlpha
    Alpha1 = 0 0 0
    Alpha2 = {alpha} {alpha} 6
    Alpha3 = {alpha*.65:.3f} {alpha*.65:.3f} {life//2}
    Alpha4 = 0 0 {life}
  End
  Update = DefaultUpdate
    AngleZ = -3 3
    AngularRateZ = -{spin} {spin}
    AngularDamping = 1 1
    SizeRate = 0.025 0.055
    SizeRateDamping = 1 1
  End
  Physics = DefaultPhysics
    VelocityDamping = 1 1
  End
  EmissionVelocity = OrthoEmissionVelocity
    X = {speed} {speed*1.35:.3f}
    Y = -{spread} {spread}
    Z = 0 0
  End
  EmissionVolume = LineEmissionVolume
    StartPoint = X:0 Y:-2 Z:0
    EndPoint = X:0 Y:2 Z:0
  End
  Draw = DefaultDraw
  End
End

"""

    # Stock carriers used nowhere else on this map. Replace their draws
    # and flags; NO_COLLIDE keeps these visual details out of pathfinding.
    ini = ''
    for carrier, tag, args in (
        ('LakeRipple', 'Bow', (6, 28, .32, .50, 3, .04, .015)),
        ('WtrflHaze', 'Side', (4, 26, .55, .42, 4, .025, .012)),
        ('WtrflSteam', 'Wake', (10, 68, 1.15, .48, 2, .12, .018)),
        ('LakeCoast01', 'Current', (4, 42, 1.7, .25, 5, .035, .008)),
    ):
        name = 'HollinBridge'+tag
        ini += effect(name, *args)
        ini += (f'Object {carrier}\n  KindOf = IMMOBILE NO_COLLIDE OPTIMIZED_PROP UNATTACKABLE\n'
                '  ReplaceModule ModuleTag_Draw\n'
                '    Draw = W3DScriptedModelDraw ModuleTag_DrawHollinWater\n'
                '      DefaultModelConditionState\n        Model = P_WtrflHaze\n'
                f'        ParticleSysBone = HazeBone {name}\n'
                '      End\n    End\n  End\nEnd\n\n')
    return ini, dict(water_height=WATER, solid_sections=len(rings), emitters=dict(counts))


def level_sites(t, places, radius=120):
    for template, px, py in places:
        if template == 'CaptureFlag':
            continue
        d = np.hypot(t['x']-px, t['y']-py)
        target = float(np.median(t['z'][d < radius]))
        blend = 1-smooth(radius, radius+150, d)
        t['z'] = t['z']*(1-blend)+target*blend


def build(b):
    weather = b.project.weather
    if b.project.players != len(start_positions()):
        raise ValueError(f'map.toml has {b.project.players} players, but the map has {len(start_positions())} dales')
    print('Shaping the dales, courts and field...', flush=True)
    t = terrain()
    t['lanes'] = lane_field(t, lanes())
    t['trail'] = lane_field(t, t['trails'])
    t['ways'] = np.minimum(t['lanes'], t['trail'])     # what scenery keeps off
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    t['woods'] = woods_field(t)
    placed = sites(m, t)
    level_sites(t, placed)
    keep = [(px, py, 70 if template == 'CaptureFlag' else 190) for template, px, py in placed]
    for i, ((bx, by), (ax, ay)) in enumerate(bridges()):
        # The deck's walking surface follows its model, from an origin 1 below the banks.
        add_object(m, BRIDGE, bx, by, math.atan2(ay, ax)-math.pi/2, layer='Bridges',
                   z=BRIDGE_BANK-1-float(t['z'][round(by/10)+BORDER, round(bx/10)+BORDER]),
                   extra=[('objectName', 3, f'Sirannon_Bridge_{i+1}')])
        keep += [(bx+ax*d, by+ay*d, r) for d, r in ((-320, 70), (-170, 130), (0, 130), (170, 130), (320, 70))]
    bridge_ini, bridge_report = bridge_water(m, t, b.assets)
    s = Scenery(m, t, b.assets, keep)
    rng = random.Random(SEED+300)
    print('Raising the ruins, planting the woods...', flush=True)
    ruins(s, t, rng)
    riverside(s, t, rng)
    woods(s, t, rng)
    t['footings'] = s.footings+[(px, py, 150 if template != 'WargLair' else 110, 'earth')
                                for template, px, py in placed if template != 'CaptureFlag']
    labels = materials(t)
    sounds(m, t)

    gy, gx = np.gradient(t['z'], 10)
    # Steep ground is blocked, but not the river's short banks: units walk down them into the fords.
    steep = (np.hypot(gx, gy) > .9) & (t['stream'] > 70)
    blocked = ((t['z'] < WATER-5) | (t['sd'] > 60) | steep) & ~t['climb']
    set_heights(m, t['z'])
    # Steep rock faces take one cliff texture, mapped along the faces so it
    # does not stretch down them (mapkit.cliffs).
    # The snow on the ridges and its streaked rock keep their own textures
    # and blends, with a margin round them.
    snowy = np.isin(labels, [CLIFF_SNOW, SNOW, SNOW_DEEP]).astype(float)
    near_snow = np.zeros(snowy.shape, bool)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near_snow |= np.roll(snowy, (dy, dx), (0, 1)) > 0
    cliffs = steep_cells(t['z'], 1.0) & np.isin(labels, [ROCK, CLIFF, CLIFF_HIGH, SCREE]) & ~near_snow
    labels[cliffs] = CLIFF
    set_materials(m, PALETTE, labels, blocked, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True, cliffs=cliffs,
                  cliff_scale=1.6)
    water_plane(m, 'Sirannon', WATER, shader='wtr_Moat.W3D')
    # The river's flowing surface over the standing water, out onto both banks.
    rows, cols = t['z'].shape
    def height_at(px, py):
        return float(t['z'][min(max(round(py/10)+BORDER, 0), rows-1), min(max(round(px/10)+BORDER, 0), cols-1)])
    # Its width is measured from the finished terrain at every cross-section,
    # out to the shoreline on both sides and a little onto the bank, so the
    # strip covers the water exactly and its pale edge meets the shore.
    course = [p for p in t['line'] if -250 < p[1] < SPAN_Y+250]
    add_river(m, 'Sirannon', course, width=bank_width(course, height_at, WATER, rise=1.5, least=120, reach=300, step=40),
              height=WATER+1, step=60)
    starts(m, start_positions())

    sky = add_sky(m, weather, WIDTH*10, HEIGHT*10, BORDER*10)
    # A low autumn sun, warm and golden, with a cool fill from the mountains.
    apply_weather(m, weather, sun=dict(ambient=(.21, .19, .16), diffuse=(1., .86, .64)),
                  fill=dict(ambient=(0., 0., 0.), diffuse=(.16, .22, .32), direction=(-.64, -.54, -.55)))

    data = m.encode()
    from mapworkshop.mapkit.checks.analyze import analyze
    from mapworkshop.formats.map import Map
    report = analyze(data)
    if report['unresolved_sections']:
        raise ValueError(report['unresolved_sections'])
    for p in start_positions():
        area = np.hypot(t['x']-p[0], t['y']-p[1]) <= 380
        if np.ptp(t['z'][area]) > .01 or blocked[area].any():
            raise ValueError(f'Uneven or blocked construction area at {p}')
    walking = fairness(Map(data))
    ini = ini_block(weather)+f'WaterTransparency\n  ReflectionPlaneZ = {WATER:g}\n  ReflectionOn = No\nEnd\n'
    ini += bridge_ini
    b.report['bridge_water'] = bridge_report
    path = b.save(data, ini=ini)
    report.update(title=b.project.title, seed=SEED, starts=start_positions(), sites=placed, walking=walking, sky=sky,
                  layers=dict(s.counts), vegetation=dict(s.vegetation))
    b.report.update(report)
    print(f'{path.name}: {sum(s.counts.values())} objects {dict(s.vegetation)}, heights {t["z"].min():.0f}..{t["z"].max():.0f}')
    print(f'  nearest enemy: {walking["nearest_enemy"]}')
    for row in walking['base_distances']:
        print('  ', row)
