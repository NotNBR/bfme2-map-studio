"""The Hollin Dales: a 3 vs 3 map in autumn Eregion, under the Misty Mountains.

Every player holds a dale of their own: a closed valley under high ridges,
with a bowl at its head for the base. A team's three dales open only into its
gate-court, a long walled hollow in front of them, so teammates reach each
other only through the court and never from behind. The court opens onto the
shared field through three gates. The field is the ruined heart of Hollin:
the Sirannon winds down it from the north edge to the south, with a ford at
each team's north and south gates and a broad ford through the ruins of
Ost-in-Edhil in the middle.

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
# The Sirannon: an S-bend through the centre, crossing the centre line at
# the middle and FORD_SPACING north and south of it, where its fords are.
STREAM_BEND, FORD_SPACING = 260*S, 1500*S
CITY_GRID = .32                # Ost-in-Edhil's street grid, radians from north

# Terrain textures. Higher entries blend over lower ones at their edges.
PALETTE = ['GrassEregion01', 'GrassEregion08', 'GrassEregion07', 'GrassEregion04', 'GrassEregion10',
           'GrassEregion03', 'GrassEregion09', 'GrassRivendell01', 'DirtRivendell03', 'LothlorienDirt07',
           'RockEregion02', 'RockEregion01', 'CliffCaradhras05', 'RockCaradhras05',
           'CliffEttenmoors01', 'SnowCaradhras04', 'SnowCaradhras06', 'DirtEregion04', 'DirtEregion02',
           'DirtEregion01', 'DirtEregion03', 'CliffErebor05']
# The cliff texture comes last: steep faces are cliff-mapped and keep no
# blend, so it blends over its neighbours instead.
(OCHRE, MIXED, DRY, RED, RUST, GOLD, LEAVES, GREEN, MUD, SILT, ROCKY_GRASS, ROCK, CLIFF_HIGH,
 SCREE, CLIFF_SNOW, SNOW, SNOW_DEEP, TRODDEN, LANE_EDGE, LANE, PAVING, CLIFF) = range(len(PALETTE))


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


def stream_line():
    """The Sirannon from beyond the north edge to beyond the south edge,
    point-symmetric: its bend is an odd function of the distance from the centre."""
    ys = np.linspace(SPAN_Y+600, -600, 140)
    v = ys-CY
    xs = CX+STREAM_BEND*np.sin(2*math.pi*v/(2*FORD_SPACING))+40*np.sin(2*math.pi*v/700)
    return list(zip(xs, ys))


def fords():
    return [(CX, CY+FORD_SPACING), (CX, CY), (CX, CY-FORD_SPACING)]


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
        parts.append((smooth_min(d-width, bowl(x, y, bx, by, line, k), 160), COURT_Z+(BASE_Z-COURT_Z)*smooth(0, .8, s)))
    cx, cy, hx, hy = COURT
    for px, py in ((cx, cy), (SPAN_X-cx, SPAN_Y-cy)):
        parts.append((rounded_box(x, y, px, py, hx, hy, 320), np.full(x.shape, COURT_Z)))
    for line, width in gate_lines():
        d, along = polyline_distance(line, x, y)
        parts.append((d-width, COURT_Z+(FIELD_Z-COURT_Z)*smooth(.1, .95, along/length(line))))
    parts.append((rounded_box(x, y, CX, CY, *FIELD, 520), np.full(x.shape, FIELD_Z)))

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

    # The Sirannon: a narrow stream in a shallow valley, too deep to wade
    # but at its three fords. It comes down from the mountains through a
    # ravine of its own at each end.
    line = stream_line()
    stream_d, _ = polyline_distance(line, x, y)
    stream_sd = stream_d-(34+8*fbm(x, y, scale=500, seed=SEED+6, octaves=2))
    ravine = smooth(60, 700+200*fbm(x, y, scale=600, seed=SEED+12, octaves=2), stream_d)

    # Mountains, none alike: a cliff wall of uneven height at the edge of
    # the open ground, buttresses and gullies cut into it, then high ridges
    # and snowy peaks behind it with ridged crests.
    ridged = 1-np.abs(fbm(x+3000, y-1000, scale=900, seed=SEED+2, octaves=5))
    crags = 1-np.abs(fbm(x-2100, y+1700, scale=260, seed=SEED+13, octaves=4))
    warp = fbm(x-500, y+700, scale=260, seed=SEED+3, octaves=3)
    wall_height = 230+90*fbm(x+400, y-900, scale=700, seed=SEED+14, octaves=2)
    wall = wall_height*smooth(0, 280+80*warp, sd+60*warp)
    peaks = 560*smooth(150, 1300, sd)*(.4+.8*ridged**2)+90*smooth(100, 600, sd)*crags**3
    foothills = 34*smooth(-260, 0, sd)*(.7+.6*fbm(x, y, scale=300, seed=SEED+4, octaves=2))
    # Rock faces broken into ribs, ledges and gullies, strongest mid-height
    # on the walls; nothing of it reaches the open ground.
    ribs = fbm(x*1.6+y*.3, y*.7-x*.2, scale=240, seed=SEED+16, octaves=4)
    ledges = np.round(fbm(x+800, y+800, scale=500, seed=SEED+17, octaves=2)*4)/4
    faces = (55*ribs+30*ledges+25*crags)*smooth(20, 200, sd)
    # The knolls between a court's gates stand in open ground on most
    # sides: they are no mountains but broken rocky hills, lower, with a
    # crest of crags and spurs running out from it.
    knoll = smooth(.55, .72, box_blur((sd < 0).astype(float), 60))
    tors = 150*smooth(.5, .85, crags+.25*ribs)+45*fbm(x+3300, y-2700, scale=180, seed=SEED+18, octaves=3)
    skirt = 70*smooth(0, 160, sd)
    knolls = skirt+smooth(60, 220, sd)*tors
    mountains = ((wall+faces)*(1-knoll)+knolls*knoll+peaks)*(.25+.75*ravine)

    # Gentle rolls on the open ground, stronger in the field than in the
    # dales, with knolls and hollows of their own on each half.
    rolls = symmetric(fbm(x+1200, y-600, scale=900, seed=SEED+5, octaves=3))
    rolls = (16*rolls+7*fbm(x-300, y+1500, scale=380, seed=SEED+15, octaves=3))*(1-smooth(-400, 0, sd))
    land = floor+rolls+foothills+mountains
    land -= 22*(1-smooth(0, 520, stream_sd))*(1-smooth(-50, 300, sd))
    # Scree and talus: the mountains settle under their own weight, the open ground keeps its shape.
    settled = thermal_erosion(land, iterations=24, spacing=10, talus=.95)
    land = land+(settled-land)*smooth(-30, 120, sd)*(1-.8*knoll)
    bank = np.clip(stream_sd/80, 0, 1)
    z = np.where(stream_sd > 0, WATER-1+(land-WATER+1)*bank**1.4, WATER-3-10*smooth(0, 20, -stream_sd))
    ford_d = np.min([np.hypot(x-fx, y-fy) for fx, fy in fords()], axis=0)
    shelf = 1-smooth(110, 190, ford_d)
    z = np.where(stream_sd <= 0, z*(1-shelf)+(WATER-FORD_DEPTH)*shelf, z)
    ramp = 1-smooth(150, 360, ford_d)
    z = np.where(stream_sd > 0, z*(1-ramp)+np.minimum(z, WATER-FORD_DEPTH+.09*np.maximum(stream_sd, 0))*ramp, z)

    # Construction areas: level, at one height, easing into the bowl.
    for px, py in start_positions():
        blend = (1-smooth(BASE_FLAT, BASE_BLEND, np.hypot(x-px, y-py)))**.8
        z = z*(1-blend)+BASE_Z*blend
    return dict(x=x, y=y, z=z, sd=sd, knoll=knoll, stream=stream_sd, ford_d=ford_d, shelf=shelf, line=line)


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
    for (gate, _), ford in zip(GATES, fords()):
        end = gate[-1]
        out.append([end, ((end[0]+ford[0])/2, (end[1]+ford[1])/2+(ford[1]-CY)*.08), ford])
    lines = []
    for k, p in enumerate(out):
        lines.append(chaikin(wander(p, SEED+400+k), 3))
        lines.append(chaikin(wander(turned(p), SEED+500+k), 3))
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
    # Autumn grass: ochre, with drier, redder and rust-brown drifts, and
    # golden patches in the open.
    labels = np.full(z.shape, OCHRE, dtype='u2')
    labels[v < -.1] = MIXED
    labels[v > .15] = DRY
    labels[(mid > .25) & (fine > -.1)] = RED
    labels[(v < -.3) & (fine > -.2)] = RUST
    labels[(mid < -.3) & (broad > 0) & (fine > -.05)] = GOLD
    # Green by the water: the stream keeps its banks lush.
    edge = fbm(x, y, scale=70, seed=SEED+23, octaves=2)
    stream = t['stream']
    labels[(stream < 55+45*mid+20*fine) & (fine > -.2)] = GREEN
    labels[(stream > 30) & (stream < 140+60*mid) & (fine > .25) & (mid > 0)] = GREEN
    labels[(stream < 18+8*edge) & (stream > -3)] = MUD
    labels[z < WATER-1.5] = SILT
    labels[(t['shelf'] > .3) & (z < WATER+1.5)] = TRODDEN
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
    labels[(t['lanes'] < 34+8*fine) & dry & (fine > -.35) & fade] = LANE_EDGE
    labels[(t['lanes'] < 17+5*fine) & dry & fade] = LANE
    # The ruins of Ost-in-Edhil: old paving round the middle ford.
    ruins = np.hypot(x-CX-40, (y-CY+30)*.8) < 300+180*mid+90*fine
    labels[ruins & dry & (fine > .15) & (slope < .3)] = PAVING
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
            scale=None, z=0, mountain=False):
        """Place one object if the spot is clear: dry (unless `wet`), no
        steeper than `slope`, off the tracks, away from the bases and sites,
        on open ground (unless `mountain`) and `gap` from everything placed."""
        if not (60 < x < SPAN_X-60 and 60 < y < SPAN_Y-60):
            return False
        iy, ix = round(y/10)+BORDER, round(x/10)+BORDER
        if self.slope[iy, ix] > slope or self.t['lanes'][iy, ix] < lane:
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
    banks = 1-smooth(60, 380, t['stream'])
    openness = smooth(500*S, 900*S, np.abs(x-CX))*.25+.75
    w = smooth(.05, .45, groves+.45*foot+.25*banks-.1)*openness
    w *= smooth(40, 120, t['lanes'])
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


def ruins(s, t, rng):
    """Ost-in-Edhil round the middle ford: a fountain court and a tower on
    the west bank, a broken hall and a second tower on the east, walls of
    arcades breaking off between them, and rubble. Then a broken gatehouse
    at most of the courts' gates, and a lone ruin up some of the dales."""
    # The city's streets ran on one grid, turned CITY_GRID from north: its
    # walls and towers still keep to it, except what has fallen. Positions
    # are (across the grid, along it); walls run along u (ALONG_U) or v.
    g = CITY_GRID; along_u, along_v = g-math.pi/2, g
    centre = [('HarlindonRuin13', -330, 120, along_v), ('HarlindonRuin05', -560, 380, along_v),
              ('HarlindonRuin10', -420, 380, along_u), ('HarlindonRuin12', -600, 200, along_v),
              ('HarlindonRuin11', -600, -120, along_v+math.pi), ('HarlindonRuin07', -420, -300, along_v+math.pi),
              ('HarlindonRuin09', -250, -380, along_u), ('HarlindonRuin01', 380, -180, along_v+math.pi/2),
              ('HarlindonRuin14', 560, 260, along_v+math.pi), ('HarlindonRuin16', 620, -420, along_v+.6),
              ('HarlindonRuin11', 330, -480, along_u), ('HarlindonRuin12', 650, 0, along_v),
              ('HarlindonRuin08', 260, 420, along_v), ('HarlindonRuin10', 450, 520, along_u+math.pi),
              ('HarlindonRuin03', -120, 680, along_v), ('HarlindonRuin17', 150, -700, along_v+math.pi/2)]
    for template, u, v, angle in centre:
        dx, dy = u*math.cos(g)-v*math.sin(g), u*math.sin(g)+v*math.cos(g)
        for _try in range(8):
            if s.put(template, CX+1.15*dx+rng.uniform(-20, 20), CY+1.15*dy+rng.uniform(-20, 20),
                     angle=angle+rng.uniform(-.05, .05), layer='OstInEdhil', gap=60, lane=30, base=0, slope=.35, z=-2):
                break
    for _ in range(40):
        a = rng.random()*math.tau; r = rng.uniform(150, 750)
        s.put(rng.choice(STONES+['HarlindonRuin07']), CX+math.cos(a)*r, CY+math.sin(a)*r, layer='OstInEdhil',
              gap=25, lane=20, base=0, slope=.4, z=-1)
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
            if rng.random() < .85:
                s.put(rng.choice(['HarlindonRuin10', 'HarlindonRuin11', 'HarlindonRuin12']), mx-dy*side*r, my+dx*side*r,
                      angle=across+rng.uniform(-.06, .06), layer='Gatehouses', gap=40, lane=0, base=0, slope=2,
                      z=-3, mountain=True)
            pick = rng.random()
            if pick < .55:
                r = width-55
                s.put('HarlindonRuin05' if pick < .3 else 'HarlindonRuin16', mx-dy*side*r, my+dx*side*r,
                      angle=across+rng.choice([0, math.pi])+rng.uniform(-.1, .1), layer='Gatehouses', gap=40,
                      lane=0, base=0, slope=.8, z=-3, mountain=True)
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
                     base=BASE_FLAT+60, slope=.35, z=-2):
                break
    for k, (line, (bx, by)) in enumerate(dale_lines()):
        if rng.random() < .3:
            continue
        for _try in range(30):
            f = rng.uniform(.3, .7); px, py = line[int(f*(len(line)-1))]
            a = rng.random()*math.tau; r = rng.uniform(150, 260)
            if s.put(rng.choice(['HarlindonRuin02', 'HarlindonRuin03', 'HarlindonRuin17', 'HarlindonRuin19',
                                 'HarlindonRuin15']), px+math.cos(a)*r, py+math.sin(a)*r,
                     layer='DaleRuins', gap=80, lane=60, slope=.3, z=-2):
                break


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
    skirts = np.column_stack(np.nonzero((t['knoll'] > .4) & (t['sd'] > -40) & (s.slope < .5)))
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
    # Rushes on the stream's banks, and a few lone trees in the open.
    bank = np.column_stack(np.nonzero((t['stream'] > 4) & (t['stream'] < 45) & (t['z'] > WATER-1)))
    order = np.random.default_rng(SEED+35).permutation(len(bank))
    for iy, ix in bank[order][:4000]:
        if rng.random() > .25:
            continue
        s.put(rng.choice(['GladdenFieldsShrub01', 'GladdenFieldsShrub02', 'OptGrass02']), (ix-BORDER)*10,
              (iy-BORDER)*10, layer='StreamBanks', gap=16, lane=30, wet=True, slope=.6)
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
    for template, (px, py), angle in [('Outpost', (CX-470*S, CY+1750*S), -.4), ('Inn', (CX-380, CY-300), .9)]:
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
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    t['woods'] = woods_field(t)
    placed = sites(m, t)
    level_sites(t, placed)
    keep = [(px, py, 70 if template == 'CaptureFlag' else 190) for template, px, py in placed]
    s = Scenery(m, t, b.assets, keep)
    rng = random.Random(SEED+300)
    print('Raising the ruins, planting the woods...', flush=True)
    ruins(s, t, rng)
    woods(s, t, rng)
    labels = materials(t)
    sounds(m, t)

    gy, gx = np.gradient(t['z'], 10)
    blocked = (t['z'] < WATER-5) | (t['sd'] > 60) | (np.hypot(gx, gy) > .9)
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
    water_plane(m, 'Sirannon', WATER)
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
    path = b.save(data, ini=ini)
    report.update(title=b.project.title, seed=SEED, starts=start_positions(), sites=placed, walking=walking, sky=sky,
                  layers=dict(s.counts), vegetation=dict(s.vegetation))
    b.report.update(report)
    print(f'{path.name}: {sum(s.counts.values())} objects {dict(s.vegetation)}, heights {t["z"].min():.0f}..{t["z"].max():.0f}')
    print(f'  nearest enemy: {walking["nearest_enemy"]}')
    for row in walking['base_distances']:
        print('  ', row)
