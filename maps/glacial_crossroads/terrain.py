"""Alpine terrain around Glacial Crossroads' connected movement network.

The geography has three scales: broken summit chains with descending spurs,
glacial basins and carved passes, then drainage incision and talus. Route
cores and level construction ground are protected at the native resolution.
No mesh rocks are used to substitute for mountain landforms.
"""
import numpy as np

from mapworkshop.mapkit.earth import fbm, thermal_erosion
from mapworkshop.mapkit.lines import polyline_distance
from mapworkshop.mapkit.relief import distance_to, smooth
from mapworkshop.mapkit.walkable import flood
from .design import (BASES, BORDER, CENTRE, EXTENT, HEIGHT, ICE, PAD_HALF,
                     RIDGES, ROUTES, SCALE, WIDTH, floor_height)
from .features import (BATTLE_HOLLOWS, CAPTURE_LINKS, CHECKPOINTS,
                       CHECKPOINT_SHELF, CREVASSES)

PALETTE = ['SnowLargeType1', 'SnowType6', 'SnowCaradhras07', 'SnowCaradhras05',
           'SnowCaradhras08', 'SnowCaradhras09', 'SnowType4',
           'SnowCaradhras21', 'StoneCaradhras03', 'CliffCaradhras02',
           'SnowCaradhras04', 'CliffCaradhras03']
DRIFT, WIND, SCREE, DEPTH = 6, 7, 8, 9
TALUS = len(PALETTE)-2
CLIFF = len(PALETTE)-1
# Sheet fractures are surface material, never gaps in the walkable ice.
# Coordinates are offsets from the field centre, in world units.
ICE_SEAMS = [
    [(-800, -2200), (-610, -1410), (-180, -990), (-310, -270),
     (80, 230), (430, 670), (350, 1160), (720, 2200)],
    [(-2200, 400), (-1470, 380), (-1040, 140), (-550, 230), (-310, -270),
     (390, -660), (980, -1110), (1790, -1570)],
    [(430, 670), (1100, 820), (1370, 1210), (2100, 1400)],
    [(-1040, 140), (-1180, -330), (-1670, -640), (-2130, -1140)],
]
SNOW_TONGUES = [
    ([(-1660, 1580), (-1370, 1210), (-1430, 690)], 360.),
    ([(2400, 900), (1530, 700), (980, 470)], 350.),
    ([(-600, -2070), (-360, -1550), (-580, -1080)], 330.),
]

# Each basin has its own glacial axis, proportions and off-centre headwall.
# Values: turn from the inward bearing, length, breadth, along/across offset.
# These shape the surrounding land; the 1,500-unit construction squares and
# all route cores remain separately reserved, including the four rear entries.
CIRQUES = {
    1: (-.38, 1.55, 1.02, 220, -110),
    2: (.47, 1.30, 1.18, -110, 170),
    3: (-.28, 1.62, 1.01, 240, -120),
    4: (.30, 1.20, 1.22, -100, 120),
    5: (-.45, 1.48, 1.08, 200, 100),
    6: (.32, 1.22, 1.17, -130, -140),
    7: (-.24, 1.60, 1.02, 180, 120),
    8: (.42, 1.36, 1.10, 120, -180),
    9: (-.36, 1.30, 1.03, 80, 100),
    10: (.46, 1.28, 1.20, -80, -170),
    11: (-.30, 1.27, 1.18, -120, 130),
    12: (.28, 1.25, 1.08, 70, -100),
    13: (-.30, 1.56, 1.03, 210, -70),
    14: (-.25, 1.20, .97, 70, -120),
    15: (.22, 1.45, 1.06, 180, -100),
    16: (-.38, 1.27, 1.05, 60, -70),
}

# Rock feet on the inside of two capture-approach bends. These shape the
# terrain cross-section itself: reopening the former broad blocked aprons
# otherwise lets base 8 cut the southeast bend and base 9 cut the south
# saddle approach. Protected route floors still have zero mountain depth.
# Centre, elliptical reach, increase in cross-section steepness, foot reach.
PASS_BUTTRESSES = [
    ((18880., 8620.), (900., 850.), 1.30, 0.),
    ((12900., 4600.), (1500., 600.), .45, 35.),
]


def glacier(x, y, shore, ice):
    """Two deep, impassable ruptures with frost lips and tapered snow tongues.

    The unsigned native height range leaves 112 units beneath the ice datum.
    Raised fracture lips add relief above it without reaching the low bases.
    The solid sheet around the ruptures is open; map.py fills their deep beds.
    Work on the basin crop so local detail does not allocate full-map fields.
    """
    rows, cols = np.nonzero(ice)
    crop = (slice(rows.min(), rows.max()+1), slice(cols.min(), cols.max()+1))
    xx, yy = x[crop]-CENTRE[0], y[crop]-CENTRE[1]
    inset = smooth(-shore[crop]/200)*ice[crop]
    grain = fbm(xx, yy, scale=340, octaves=2, seed=5810)

    def curve(controls):
        a, b, c = np.asarray(controls, float)
        u = np.linspace(0, 1, 40)[:, None]
        return (1-u)**2*a+2*u*(1-u)*b+u*u*c

    cut_depth = np.zeros(xx.shape)
    lips = np.zeros(xx.shape)
    rupture = np.zeros(xx.shape, np.uint8)
    frost = np.zeros(xx.shape)
    for index, feature in enumerate(CREVASSES, 1):
        for branch, axis in enumerate([feature['points']]+feature['branches']):
            points = np.asarray(axis)-np.asarray(CENTRE)
            arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
            length = arc[-1]
            d, along = polyline_distance(points, xx, yy, reach=370)
            ends = smooth((length-along)/(230 if branch == 0 else 180))
            if branch == 0:
                ends *= smooth(along/230)
            width = (feature['half_width'] if branch == 0 else 48.)*(.12+.88*ends)
            # Broad broken bays and short chips interrupt the excavated,
            # constant-width appearance without encroaching on the crossing.
            width *= 1+.28*np.sin(along/237+index)+.13*np.sin(along/73+.8)+.25*grain
            cavity = (1-smooth((d-width+30)/47))*ends
            depth = (ICE-feature['floor'])*(1-.10*(.5+.5*np.sin(along/145)))*cavity
            # One wind-scoured bank and one broken cornice, with unequal
            # bulges, instead of two continuous white rails around the hole.
            near_x = np.interp(along, arc, points[:, 0])
            near_y = np.interp(along, arc, points[:, 1])
            side = np.tanh(((yy-near_y)-.35*(xx-near_x))/35)
            crest = (38+13*np.sin(along/160+.7)+7*np.sin(along/61))*(.78+.22*side)
            cornice = .42+.58*smooth(.48+.70*np.sin(along/290+index)+grain)
            lip = crest*cornice*np.exp(-((d-width-24)/(54+22*cornice))**2)*ends*(1+.17*grain)
            cut_depth = np.maximum(cut_depth, depth)
            lips = np.maximum(lips, lip)
            frost = np.maximum(frost, (1-smooth((d-width-50)/115))*ends)
            rupture[(d < width+165) & (ends > .025) & ice[crop]] = index
    snow = np.zeros(xx.shape)
    for controls, width in SNOW_TONGUES:
        points = curve(controls)
        length = np.linalg.norm(np.diff(points, axis=0), axis=1).sum()
        d, along = polyline_distance(points, xx, yy, reach=width*1.2)
        taper = np.clip(1-along/length, 0, 1)
        reach = 45+width*taper**.8+25*grain
        tongue = (1-smooth(d/np.maximum(reach, 20)))*smooth((length-along)/150)
        snow = np.maximum(snow, tongue)
    lips *= 1-smooth(cut_depth/45)
    relief = (lips-cut_depth+9*snow*(1-frost))*inset
    return dict(crop=crop, relief=relief, lips=lips*inset, depth=cut_depth,
                snow=snow, frost=frost, rupture=rupture, grain=grain)


def paint_glacier_margin(materials, x, y, shore, z, slope, rupture, basin):
    """Interleave wind-drifted snow and exposed ice across the basin margin.

    The geological ice boundary reserves movement ground; it is not a paint
    outline. Snow sweeps across it in broad lobes and frayed tongues, while
    bare ice reaches between them onto the low, gently sloping approaches.
    Rupture walls and their frost lips retain their own surface treatment.
    """
    rows, cols = basin['crop']
    crop = (slice(max(rows.start-65, 0), min(rows.stop+65, x.shape[0])),
            slice(max(cols.start-65, 0), min(cols.stop+65, x.shape[1])))
    xx, yy = x[crop]-CENTRE[0], y[crop]-CENTRE[1]
    broad = fbm(xx, yy, scale=720, octaves=2, seed=5821)
    # Wind stretches smaller drifts along a common direction. They fray the
    # broad snow lobes instead of forming a uniform ring or scattered dots.
    along, across = .86*xx+.51*yy, -.51*xx+.86*yy
    fringe = fbm(along*.48+180*broad, across, scale=190, octaves=2, seed=5822)
    snowline = shore[crop]+130+620*broad+180*fringe
    width = 360+180*smooth(.5+1.5*broad)
    cover = smooth((snowline+width*.5)/width)
    inner = (slice(rows.start-crop[0].start, rows.stop-crop[0].start),
             slice(cols.start-crop[1].start, cols.stop-crop[1].start))
    tongue = smooth((basin['snow']*(1+.45*fringe[inner])-.04)/.58)
    cover[inner] = np.maximum(cover[inner], tongue)
    wisps = fbm(along*.30+100*broad, across+50*fringe,
                scale=95, octaves=2, seed=5823)
    # Fine wind-stretched remnants occur only within the transition. Their
    # broken edges and occasional detached tips soften the large snow lobes.
    cover = np.clip(cover+.65*wisps*4*cover*(1-cover), 0, 1)
    margin = (shore[crop] > -850) & (shore[crop] < 650)
    margin[inner] |= tongue > .02
    area = (margin
            & (z[crop] < ICE+55) & (slope[crop] < .30) & (rupture[crop] == 0))
    surface = materials[crop]
    # The thin coat is blue-white frost, then compacted snow, then the same
    # soft snow as the valley. Unequal thresholds break up parallel bands.
    surface[area & (cover < .12)] = 2
    surface[area & (cover >= .12)] = 5
    surface[area & (cover > .34+.10*fringe)] = 1
    surface[area & (cover > .62+.12*broad)] = 0


def upscale(values, cx, cy, x, y):
    """Cubic reconstruction avoids regular creases between geology samples.

    Navigation and the protected construction/route floors remain native
    10-unit fields; only the geological and snow fields are reconstructed.
    """
    def axis(data, source, target, direction):
        at = np.clip((target-source[0])/(source[1]-source[0]), 0, len(source)-1)
        cell = np.floor(at).astype(int)
        u = at-cell
        weights = (-.5*u+u*u-.5*u**3, 1-2.5*u*u+1.5*u**3,
                   .5*u+2*u*u-1.5*u**3, -.5*u*u+.5*u**3)
        shape = [1, 1]
        shape[direction] = len(target)
        result = None
        for offset, weight in zip((-1, 0, 1, 2), weights):
            term = np.take(data, np.clip(cell+offset, 0, len(source)-1), axis=direction)
            term *= weight.reshape(shape)
            if result is None:
                result = term
            else:
                result += term
        return result
    rows = axis(values, cx[0], x[0], 1)
    return axis(rows, cy[:, 0], y[:, 0], 0)


def blur(values, radius):
    """A box mean with closed, repeated edges, used at geological resolution."""
    n = 2*radius+1
    padded = np.pad(values, radius, mode='edge')
    summed = np.pad(padded, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return (summed[n:, n:]-summed[:-n, n:]-summed[n:, :-n]+summed[:-n, :-n])/(n*n)


def summit_chains():
    """Interpret the sketch as uneven crests with connected downslope ribs."""
    chains = []
    for i, ridge in enumerate(RIDGES):
        rng = np.random.default_rng(5600+i)
        p = np.asarray(ridge['points'])
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        stations = np.linspace(0, arc[-1], max(3, round(arc[-1]/650)+1))
        xy = np.column_stack([np.interp(stations, arc, p[:, k]) for k in range(2)])
        tangent = np.gradient(xy, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1)[:, None], 1)
        normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
        xy += normal*rng.uniform(-110, 110, (len(xy), 1))
        rad = np.linalg.norm(xy-np.asarray(CENTRE), axis=1)
        bed = floor_height(rad)
        peak = np.minimum(bed+ridge['rise']*1.45, 2480)
        # Deep cols and a few dominant summits, without equal-sized teeth.
        shape = rng.uniform(.55, 1., len(xy))
        shape[len(xy)//2] = 1
        z = bed+(peak-bed)*shape
        z[[0, -1]] -= 120
        xyz = np.column_stack((xy, z))
        grade = .65 if 'outer' in ridge['name'] else .85
        chains.append((ridge['name'], xyz, grade))
        for j in range(1, len(xy)-1):
            if z[j] < max(z[j-1], z[j+1]):
                continue
            for side in (-1, 1):
                reach = rng.uniform(500, 1100)*SCALE
                direction = normal[j]*side+tangent[j]*rng.uniform(-.35, .35)
                start = xyz[j].copy()
                mid = start.copy(); end = start.copy()
                mid[:2] += direction*reach*.5+tangent[j]*rng.uniform(-100, 100)
                end[:2] += direction*reach
                mid[2] -= rng.uniform(160, 300)
                end[2] -= rng.uniform(500, 850)
                chains.append((ridge['name']+' spur', np.array([start, mid, end]), grade*1.1))
    # Broad backing ranges continue out to the map edge. Varying cols and
    # descending backs replace the blockout's flat-topped perimeter frame.
    north = np.array([[-600, 27200, 2020], [1600, 28000, 2460],
                      [4600, 26700, 1810], [7800, 27800, 2420],
                      [10900, 26400, 1740], [14200, 27800, 2480],
                      [17900, 27000, 1830], [21300, 28200, 2440],
                      [24700, 26900, 1780], [29100, 27500, 2310]], float)
    for sector in range(4):
        rng = np.random.default_rng(5700+sector)
        p = north.copy()
        for _ in range(sector):
            p[:, :2] = np.column_stack((EXTENT-p[:, 1], p[:, 0]))
        p[1:-1, :2] += rng.uniform(-520, 520, (len(p)-2, 2))
        p[:, 2] -= rng.uniform(0, 240, len(p))
        chains.append((f'Outer backbone {sector}', p, [.30, .37, .28, .34][sector]))
    return chains


def ridge_envelope(bed, chains, x, y, noise, crags):
    """Join each descending ridge segment by its continuous rock envelope.

    Using the nearest segment's elevation makes a height jump where two
    unequal crests are equally distant. Taking their envelopes instead
    forms a continuous saddle and lets the higher summit support its flanks.
    """
    rock = bed.copy()
    incision = np.zeros(bed.shape)
    for index, (name, points, grade) in enumerate(chains):
        reach = (float(points[:, 2].max())-ICE+400)/(grade*.60)
        arc = 0.
        for a, b in zip(points[:-1], points[1:]):
            lo = np.minimum(a, b)[:2]-reach
            hi = np.maximum(a, b)[:2]+reach
            c0, c1 = np.searchsorted(x[0], [lo[0], hi[0]])
            r0, r1 = np.searchsorted(y[:, 0], [lo[1], hi[1]])
            crop = (slice(r0, r1), slice(c0, c1))
            dx, dy = b[:2]-a[:2]
            length = max(np.hypot(dx, dy), 1)
            projection = ((x[crop]-a[0])*dx+(y[crop]-a[1])*dy)/length
            t = np.clip(projection/length, 0, 1)
            d = np.hypot(x[crop]-a[0]-t*dx, y[crop]-a[1]-t*dy)
            crest = a[2]+t*(b[2]-a[2])
            side = ((x[crop]-a[0])*dy-(y[crop]-a[1])*dx)/length
            asymmetry = 1+.16*np.cos(index*2.4)*np.tanh(side/350)
            shoulder = d*grade*(.92+.16*noise[crop])*asymmetry
            face = crest-shoulder+130*smooth((d-200)/1300)
            face -= (40+30*smooth(d/700))*np.maximum(crags[crop], 0)
            # Flute both the main crest and its buttresses. Omitting spurs
            # leaves their winning envelopes as large unbroken wall faces.
            # Narrow across the face, extended downhill, with warped axes.
            grooves = fbm(arc+projection+120*crags[crop], d*.22+80*noise[crop],
                          scale=330, octaves=3, seed=5606+index*19)
            channels = 240*np.clip(.35+2.2*grooves, 0, 1)*smooth(d/120)
            face -= channels
            # Preserve downhill channels when the valley profile cuts below
            # this envelope; otherwise it exposes a smooth, ruled cliff.
            incision[crop] = np.where(face > rock[crop], channels, incision[crop])
            rock[crop] = np.maximum(rock[crop], face)
            arc += length
    return rock, blur(incision, 2)


def drainage_incision(z, spacing, protected):
    """Cut converging gullies using downhill contributing area.

    This is a deterministic landform operator, not a water simulation. Flow
    divides between downhill neighbours; tributaries join before the cut is
    limited on floors, divides and the gently sloping talus at each foot.
    """
    z = z.copy()
    h, w = z.shape
    for _ in range(4):
        directions = []
        total = np.zeros(z.shape)
        neighbours = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1),
                      (-2,-1), (-2,1), (2,-1), (2,1), (-1,-2), (-1,2), (1,-2), (1,2)]
        for dy, dx in neighbours:
            ys = slice(max(0, -dy), min(h, h-dy))
            xs = slice(max(0, -dx), min(w, w-dx))
            yt = slice(max(0, dy), min(h, h+dy))
            xt = slice(max(0, dx), min(w, w+dx))
            slope = (z[ys, xs]-z[yt, xt])/(spacing*np.hypot(dx, dy))
            weight = np.maximum(slope, 0)**2/np.hypot(dx, dy)
            total[ys, xs] += weight
            directions.append((ys, xs, yt, xt, weight))
        directions = [(ys, xs, yt, xt, weight/np.maximum(total[ys, xs], 1e-10))
                      for ys, xs, yt, xt, weight in directions]
        area = np.ones(z.shape)
        for _ in range(90):
            new = np.ones(z.shape)
            for ys, xs, yt, xt, fraction in directions:
                new[yt, xt] += area[ys, xs]*fraction
            area = new
        grade = np.hypot(*np.gradient(z, spacing))
        cut = 115*(1-np.exp(-area/65))
        # Spread the incision into a channel of finite width, avoiding
        # single-cell grooves along otherwise continuous mountain faces.
        for _ in range(3):
            cut[1:-1, 1:-1] = (cut[1:-1, 1:-1]*4+cut[:-2, 1:-1]+cut[2:, 1:-1]
                                +cut[1:-1, :-2]+cut[1:-1, 2:])/8
        cut *= smooth((grade-.2)/.7)*(1-protected)
        z -= cut
    return thermal_erosion(z, iterations=10, spacing=spacing, talus=1.25)


def landscape():
    """Build natural massifs and narrow, continuous alpine approaches."""
    y, x = (np.mgrid[:HEIGHT+2*BORDER, :WIDTH+2*BORDER]-BORDER)*10.
    radius = np.hypot(x-CENTRE[0], y-CENTRE[1])
    floor = floor_height(radius)
    # The virtual bed falls again beyond the outer bases, giving the border
    # ranges ravines and descending backs instead of a level raised frame.
    floor -= 650*smooth((radius-15800)/6200)
    cx, cy = x[::3, ::3], y[::3, ::3]
    noise = fbm(cx, cy, scale=2600, octaves=3, seed=5601)
    crags = fbm(cx+180*noise, cy-120*noise, scale=600, octaves=4, seed=5602)
    # Two scales of snow-filled recesses move the foot of the mountains,
    # independently on either bank. The route width is only a minimum.
    recess = upscale(fbm(cx, cy, scale=1150, octaves=3, seed=5611), cx, cy, x, y)
    scallop = upscale(fbm(cx, cy, scale=370, octaves=2, seed=5612), cx, cy, x, y)
    main_edge = np.full(x.shape, np.inf)
    route_core = np.zeros(x.shape, bool)
    valleys = np.zeros(x.shape, bool)
    for route_index, route in enumerate(ROUTES+CAPTURE_LINKS):
        points = np.asarray(route['points'])
        reach = route['width']/2+500
        c0, c1 = np.searchsorted(x[0], [points[:, 0].min()-reach, points[:, 0].max()+reach])
        r0, r1 = np.searchsorted(y[:, 0], [points[:, 1].min()-reach, points[:, 1].max()+reach])
        crop = (slice(r0, r1), slice(c0, c1))
        xx, yy = x[crop], y[crop]
        d, along = polyline_distance(points, xx, yy, reach=reach)
        route_core[crop] |= d <= route['width']/2
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        tangent = np.gradient(points, arc, axis=0)
        turning = np.gradient(tangent, arc, axis=0)
        curvature = tangent[:, 0]*turning[:, 1]-tangent[:, 1]*turning[:, 0]
        nx = xx-np.interp(along, arc, points[:, 0])
        ny = yy-np.interp(along, arc, points[:, 1])
        side = np.sign(ny*np.interp(along, arc, tangent[:, 0])
                       -nx*np.interp(along, arc, tangent[:, 1]))
        # The narrow spurs beside capture sites keep their existing approach
        # topology. Wider recesses belong farther along the valley, while
        # each beacon gets a separate hollow on its path-facing side below.
        setback = np.ones(xx.shape)
        for site in CHECKPOINTS:
            px, py = site['position']
            setback = np.minimum(setback, smooth((np.hypot(xx-px, yy-py)-900)/1400))
        # Widen the outside of bends, retaining the inner mountain toes
        # that prevent corner-cutting. Taper into shared route junctions.
        outside_bend = .5-.5*np.tanh(side*np.interp(along, arc, curvature)*12000)
        ends = smooth(np.minimum(along, arc[-1]-along)/800)
        # Long independent bank profiles alternate rock noses and sheltered
        # snow bays. Opposite banks need not widen or narrow together.
        left = fbm(arc, np.full_like(arc, route_index*3700.),
                   scale=1300, octaves=2, seed=5641)
        right = fbm(arc, np.full_like(arc, route_index*3700.),
                    scale=1300, octaves=2, seed=5642)
        bank = np.where(side > 0, np.interp(along, arc, left),
                        np.interp(along, arc, right))
        extra = (420 if route['main'] else 190)*smooth(.55+1.8*bank+.25*scallop[crop])
        # The crowded glacier spokes retain their compact bank envelope;
        # the larger outer valleys have room for independent shoulders.
        compact = (180 if route['main'] else 80)*smooth(.43+1.15*recess[crop]+.5*scallop[crop])
        regional = smooth((radius[crop]-6000)/2000)
        extra = compact*(1-regional)+extra*regional
        extra *= setback*outside_bend*ends
        # Keep the inner mountain toes between converging glacier mouths.
        # Even a small recess there can join two routes before their saddle.
        extra *= smooth((radius[crop]-4500)/1800)
        if route['name'].startswith(('inner-rear-access', 'saddle-', 'North saddle',
                                     'East saddle', 'South saddle', 'West saddle')):
            extra *= 0
        valleys[crop] |= d <= route['width']/2+extra
        if route['main']:
            # Worn snow wanders within the open valley, disappearing under
            # broad drifts. It must not trace the minimum-clearance boundary.
            offset = 140*recess[crop]+65*scallop[crop]
            width = 55+100*smooth(.22+1.7*recess[crop]-.65*scallop[crop])
            wear_edge = np.abs(np.copysign(d, side)-offset)-width
            main_edge[crop] = np.minimum(main_edge[crop], wear_edge)
    lower = np.full(x.shape, ICE)
    upper = np.full(x.shape, 2550.)
    pads = np.zeros(x.shape, bool)
    basins = np.zeros(x.shape, bool)
    cirque_shoulders = np.zeros(x.shape)
    for base in BASES:
        dx, dy = x-base['x'], y-base['y']
        angle = np.arctan2(dy, dx)
        # Preserve the level construction square inside an irregular cirque.
        toward_ice = np.arctan2(CENTRE[1]-base['y'], CENTRE[0]-base['x'])
        turn, length, breadth, advance, offset = CIRQUES[base['number']]
        axis = toward_ice+turn
        along = dx*np.cos(axis)+dy*np.sin(axis)-advance
        across = -dx*np.sin(axis)+dy*np.cos(axis)-offset
        # One curved, elongated side opens onto a snow shoulder; the other
        # retains an uneven rock headwall. This is more than a noisy circle.
        bent = across-160*np.sin(along/1100+base['number'])*smooth(np.abs(along)/700)
        radial = np.hypot(along/length, bent/breadth)
        rim = 1080+110*np.cos(angle-axis)+100*np.sin(2*angle+base['number']*.8)+55*np.cos(5*angle-.7)
        box = np.hypot(np.maximum(np.abs(dx)-PAD_HALF, 0),
                       np.maximum(np.abs(dy)-PAD_HALF, 0))
        # Convert the elliptical radius back to world distance before
        # grading height. Otherwise a long basin flattens distant bases.
        metric = np.hypot(along, bent)/np.maximum(radial, 1)
        d = np.maximum(0, np.minimum(box, (radial-rim)*metric))
        lee_shoulder = .30+.70*smooth(.5+.6*np.sin(angle-axis+base['number']*.9))
        cirque_shoulders = np.maximum(cirque_shoulders, (1-smooth(d/1000))*lee_shoulder)
        # Local cirque shaping must not regrade distant saddle approaches.
        # Retain their established broad height envelope outside this basin.
        grade_axis = toward_ice+.28*np.sin(base['number']*1.7)
        grade_length = (1.23 if base['number'] >= 13 else 1.10)+.06*np.sin(base['number']*2.3)
        grade_radius = np.hypot((dx*np.cos(grade_axis)+dy*np.sin(grade_axis))/grade_length,
                                -dx*np.sin(grade_axis)+dy*np.cos(grade_axis))
        grade_rim = 1140+150*np.cos(angle-toward_ice)+90*np.sin(3*angle+base['number']*.8)+65*np.cos(5*angle-.7)
        far = np.maximum(0, np.minimum(box, grade_radius-grade_rim))
        blend = smooth((np.hypot(dx, dy)-2000)/1000)
        graded = d*(1-blend)+far*blend
        allowance = np.where(graded < 850, .00018*graded*graded, 130.05+.30*(graded-850))
        lower = np.maximum(lower, base['height']-allowance)
        upper = np.minimum(upper, base['height']+allowance)
        pads |= (np.abs(dx) <= PAD_HALF) & (np.abs(dy) <= PAD_HALF)
        basins |= d <= 0
    floor = np.clip(floor, lower, upper)
    angle = np.arctan2(y-CENTRE[1], x-CENTRE[0])
    # A slightly elongated, uneven basin joins the valley mouths without
    # turning their central meeting ground into a circular pond outline.
    shore = radius-(2020+220*np.cos(2*angle+.25)
                    +130*np.sin(3*angle+.4)+85*np.sin(7*angle-.5))
    ice = shore <= 0
    floor = floor*(smooth(shore/650))+ICE*(1-smooth(shore/650))
    checkpoints = np.zeros(x.shape, bool)
    tower_hollows = np.zeros(x.shape, bool)
    for hollow in BATTLE_HOLLOWS:
        px, py = hollow['center']
        reach = hollow['length']+250
        c0, c1 = np.searchsorted(x[0], [px-reach, px+reach])
        r0, r1 = np.searchsorted(y[:, 0], [py-reach, py+reach])
        crop = (slice(r0, r1), slice(c0, c1))
        dx, dy = x[crop]-px, y[crop]-py
        angle = np.radians(hollow['bearing'])
        along = dx*np.cos(angle)+dy*np.sin(angle)
        across = -dx*np.sin(angle)+dy*np.cos(angle)
        station = along/hollow['length']
        # A curved glacier tongue, broadest off-centre, tapers into the
        # existing pass. Independent banks leave uneven rock promontories.
        across -= hollow['bend']*np.sin(station*2.4+.4)
        taper = np.sqrt(np.maximum(1-station**2, 0))
        breadth = hollow['breadth']*(1+.13*np.sin(station*3.2+hollow['mark']))
        breadth *= 1+hollow['bias']*np.tanh(across/180)
        breadth += 100*recess[crop]+45*scallop[crop]
        tower_hollows[crop] |= (np.abs(station) < 1) & (np.abs(across) < breadth*taper)
    route_clearance = distance_to(route_core)*10
    for site in CHECKPOINTS:
        px, py = site['position']
        jx, jy = site['junction']
        crop = (slice(round(min(py, jy)/10)+BORDER-80, round(max(py, jy)/10)+BORDER+81),
                slice(round(min(px, jx)/10)+BORDER-80, round(max(px, jx)/10)+BORDER+81))
        xx, yy = x[crop], y[crop]
        ox, oy = site['outward']
        along, across = (xx-px)*ox+(yy-py)*oy, -(xx-px)*oy+(yy-py)*ox
        along /= 1.15 if site['template'] == 'Inn' else site['shelf_scale']
        across /= site['shelf_scale']
        # A compact angular shelf is cut into the spur's toe. Only its
        # foundation is level; the mountain comes down directly behind it.
        # Signed half-plane distances preserve the unequal rock shoulders.
        outside = np.full(xx.shape, -np.inf)
        for a, b in zip(CHECKPOINT_SHELF, CHECKPOINT_SHELF[1:]+CHECKPOINT_SHELF[:1]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            outside = np.maximum(outside, ((along-a[0])*dy-(across-a[1])*dx)/np.hypot(dx, dy)*site['shelf_scale'])
        shelf = outside <= 0
        spur, _ = polyline_distance([site['junction'], site['position']], xx, yy, reach=75)
        # Keep the raised foundation compact inside the wider natural hollow.
        checkpoints[crop] |= shelf | (spur < 65)
        foundation = ((1-smooth(np.maximum(outside, 0)/180))
                      * smooth((route_clearance[crop]-20)/70))
        if site['template'] == 'Inn':
            # Begin the ascent ahead of the flag, rather than letting the
            # shelf's flat nose compress all the rise against the road.
            ramp = smooth(((xx-px)*ox+(yy-py)*oy+260)/135)
            foundation = np.minimum(foundation, ramp)
        # Inns need width for their wings, not a long flat platform cutting
        # across the slope. Grade their shelf from the forecourt datum so
        # the short approach remains gentle even on a steep valley grade.
        fx, fy = (px-109*ox, py-109*oy) if site['template'] == 'Inn' else (px, py)
        level = float(floor[round(fy/10)+BORDER, round(fx/10)+BORDER])+(6 if site['template'] == 'Inn' else 24)
        floor[crop] = floor[crop]*(1-foundation)+level*foundation
    reserved = valleys | basins | ice | checkpoints | tower_hollows
    edge = distance_to(reserved)*10
    # A raster boundary has a regular staircase along diagonal banks. Smooth
    # its signed distance before sculpting, including inside the valley, so
    # those grid steps cannot turn into repeating scallops on the rock foot.
    signed_edge = (edge-distance_to(~reserved)*10)[::3, ::3]
    land_edge = blur(blur(signed_edge, 2), 2)
    for (px, py), (rx, ry), strength, foot_reach in PASS_BUTTRESSES:
        land_edge += foot_reach*np.exp(-((cx-px)/rx)**2-((cy-py)/ry)**2)
    small = fbm(cx, cy, scale=260, octaves=2, seed=5603)
    cfloor = floor[::3, ::3]
    # Regional rock supplies broad supporting volume beneath each crest.
    raw, channels = ridge_envelope(cfloor+150+180*noise, summit_chains(), cx, cy, noise, crags)
    raw += 45*crags+12*small
    # Carve U-shaped passes from their uneven valley margins, with changing
    # side slopes and snow-filled recesses between the buttress feet.
    depth = np.maximum(land_edge-30, 0)
    # A shallow snow-loaded flank and a steeper opposing face give each
    # divide a direction, rather than the same U-shaped cut on both sides.
    ey, ex = np.gradient(blur(land_edge, 4), 30)
    aspect = (ex-.65*ey)/np.maximum(np.hypot(ex, ey), .1)
    apron = depth*np.clip(1+.7*noise+.35*crags+.24*aspect, .50, 1.65)
    for (px, py), (rx, ry), strength, foot_reach in PASS_BUTTRESSES:
        apron *= 1+strength*np.exp(-((cx-px)/rx)**2-((cy-py)/ry)**2)
    inner = 1-smooth((radius[::3, ::3]-6500)/4000)
    # Keep a short snow apron, then rise into a real rock face. The former
    # basin-wide height reduction erased the narrow divides in all four
    # sectors, leaving low snow rolls inside broad navigation barriers.
    # Snow-loaded feet alternate with rock rising directly from the valley.
    # Long geological transitions replace the same apron on every bank.
    foot_shape = fbm(cx+260*noise, cy-190*noise, scale=1050, octaves=2, seed=5643)
    foot_strength = smooth((radius[::3, ::3]-6000)/2000)
    for site in CHECKPOINTS:
        px, py = site['position']
        keep = 2000 if site['template'] == 'Inn' else 1300
        foot_strength = np.minimum(foot_strength,
                                   smooth((np.hypot(cx-px, cy-py)-keep)/1300))
    foot_run = 80+foot_strength*np.clip(240*foot_shape, -55, 120)
    # Round the change of grade into the cliff. The former hard hinge jumped
    # from a shallow apron directly to the full face slope along one crease.
    transition = 65+35*smooth(.5+foot_shape)
    run = apron-foot_run
    steep_run = np.where(run <= -transition, 0,
                         np.where(run >= transition, run,
                                  (run+transition)**2/(4*transition)))
    toe = np.maximum(apron-steep_run, 0)
    rock_face = .0012*toe**2+(1.35+.40*inner)*steep_run
    snow_flank = np.where(apron < 180, .0015*apron*apron,
                          48.6+.55*(apron-180)+.00025*(apron-180)**2)
    # Strong inner barriers, but retain most of the older, uneven shoulders
    # on the larger ranges instead of turning every massif into a tall wall.
    face_weight = inner+(1-inner)*(.25+.75*(1-smooth((apron-180)/500)))
    allowance = snow_flank*(1-face_weight)+rock_face*face_weight
    allowance *= 1-(.48-.33*inner)*cirque_shoulders[::3, ::3]
    # Ridge-oriented gullies leave projecting ribs between them. Broken rock
    # shelves vary the face depth; both fade into the protected snow floor.
    face_detail = (np.minimum(.42*allowance, 320)*np.clip(channels/130, 0, 1.5)
                   +130*crags+55*small)*smooth((allowance-120)/280)
    carved_face = cfloor+np.maximum(allowance-face_detail, 0)
    raw = np.minimum(np.maximum(raw, cfloor), carved_face)
    # Round the medial crest where opposing carved slopes meet. A raw
    # distance envelope otherwise produces a thin triangular knife edge.
    crown = .75-.35*smooth((radius[::3, ::3]-8000)/7000)-.40*inner
    for site in CHECKPOINTS:
        px, py = site['position']
        crown *= smooth((np.hypot(cx-px, cy-py)-800)/1100)
    raw = raw*(1-crown)+blur(raw, 5)*crown
    raw = drainage_incision(raw, 30, 1-smooth(depth/300))
    mountains = upscale(raw, cx, cy, x, y)
    floor_join = smooth((upscale(land_edge, cx, cy, x, y)-25)/110)
    floor_join[reserved] = 0
    z = floor+np.maximum(mountains-floor, 0)*floor_join
    # Long, low rolls give the paths a natural surface without changing any
    # construction pad or introducing slopes that block formations.
    rolls = upscale(14*fbm(cx, cy, scale=1200, octaves=2, seed=5604)
                    +3*fbm(cx, cy, scale=300, octaves=2, seed=5607), cx, cy, x, y)
    floor_blend = smooth(distance_to(basins | ice | checkpoints)*10/450)
    z += rolls*floor_blend*smooth(shore/500)
    z = np.maximum(z, ICE)
    basin = glacier(x, y, shore, ice)
    z[basin['crop']] += basin['relief']
    slope = np.hypot(*np.gradient(z, 10))
    rupture = np.zeros(x.shape, np.uint8)
    rupture[basin['crop']] = basin['rupture']
    inside = (x >= 0) & (y >= 0) & (x < EXTENT) & (y < EXTENT)
    # Navigation follows the shaped foot, not the complement of the route
    # reservations. Low, gentle snow aprons can open wherever they connect
    # to a start; steep faces and the raised mountain interiors stay closed.
    # Height alone does not stop units in the engine, so retain explicit
    # flags on that physical mountain body, including its gentler crest.
    mountain_body = (z-floor > 55) | (slope >= .60)
    candidate = ~mountain_body & inside & (rupture == 0)
    origin = (round(CENTRE[1]/10)+BORDER, round(CENTRE[0]/10)+BORDER)
    # Classify connectivity with the engine's eight-neighbour expansion of
    # blocked terrain, then restore one cell around the reachable ground.
    h, w = candidate.shape
    padded = np.pad(candidate, 1, constant_values=False)
    clear = candidate.copy()
    for row in range(3):
        for col in range(3):
            clear &= padded[row:row+h, col:col+w]
    reached = flood(clear, [origin])
    padded = np.pad(reached, 1)
    walk = reached.copy()
    for row in range(3):
        for col in range(3):
            walk |= padded[row:row+h, col:col+w]
    # Keep the sheet open up to the authored rupture outline, including
    # pointed tips smaller than the engine's own one-cell cliff margin.
    walk = candidate & (walk | ice)
    drift = upscale(noise, cx, cy, x, y)
    # Snow settles in gullies and across talus, while convex buttresses
    # expose stone. Broad terrain normals avoid per-cell rock freckles.
    broad = blur(raw, 2)
    gy, gx = np.gradient(broad, 30)
    coarse_grade = np.hypot(gx, gy)
    grade = upscale(coarse_grade, cx, cy, x, y)
    hollow = upscale(np.clip((blur(raw, 6)-raw)/65, 0, 1), cx, cy, x, y)
    lee = upscale(np.maximum((gx-.55*gy)/np.maximum(coarse_grade, .1), 0), cx, cy, x, y)
    materials = np.zeros(x.shape, np.uint16)
    # Fine debris is concentrated at the foot of the headwalls. Sheltered
    # faces and drainage hollows retain snow instead of a uniform rock band.
    debris = (z-floor < 260+100*drift) & (grade > .50+.15*drift) & (grade < 1.1)
    materials[debris & (edge > 180) & (hollow < .3)] = 3
    exposure = grade-(1.08+.12*drift+.55*hollow+.25*lee)
    materials[(exposure > -.16) & (edge > 210)] = TALUS
    materials[(exposure > 0) & (edge > 230)] = CLIFF
    # Broad wind-polished snow on exposed shoulders, and softer drifts in
    # the lee. These follow landforms instead of speckling every open floor.
    materials[(materials == 0) & (lee < .20)
              & (grade > .50+.18*drift+.12*scallop)
              & (z-floor > 100+100*recess) & (drift > -.20)] = WIND
    materials[(materials == 0) & (hollow > .16) & (edge > 100)] = DRIFT
    # Scree collects below exposed faces in unequal fans; a fixed distance
    # band would trace every pass and leave angular, painted cutouts.
    fan = (edge > 170+100*recess) & (edge < 300+170*scallop+90*recess)
    materials[debris & fan & (hollow < .18) & (recess+.5*scallop > -.04)] = SCREE
    wear = upscale(fbm(cx, cy, scale=530, octaves=2, seed=5605), cx, cy, x, y)
    # Snowfall ignores the construction reservation. Broad wind-stretched
    # drifts cross pads, basin margins and paths without exposing squares.
    snow = upscale(fbm(.82*cx+.57*cy+220*noise, -.57*cx+.82*cy,
                       scale=1100, octaves=3, seed=5630), cx, cy, x, y)
    filaments = upscale(fbm((.82*cx+.57*cy)*.28, -.57*cx+.82*cy,
                            scale=160, octaves=2, seed=5631), cx, cy, x, y)
    soft = (grade < .40) & (z-floor < 70) & ~ice
    materials[soft] = 0
    materials[soft & (snow+.40*filaments > .18)] = DRIFT
    # A quiet, low-contrast compacted trace links broad junctions. Its width
    # and axis wander; windblown cover interrupts it in the same field as
    # the surrounding floor instead of ending it at a pad boundary.
    packed = (main_edge < 0) & (slope < .35)
    materials[packed & (snow+.40*filaments < .25)] = 1
    # Broken snow wear, not an evenly painted perimeter around each shelf.
    materials[checkpoints & (wear+drift*.35 > .05)] = 1
    materials[ice] = 2
    fracture = np.sin((x+.3*y)/1650+drift)+.45*np.sin((y-.2*x)/975)
    materials[ice & (fracture > 1.05)] = 4
    # A few branching sheet-scale seams remain legible above the fine
    # cracks already present in the game's tiled ice texture.
    rows, cols = np.nonzero(ice)
    crop = (slice(rows.min(), rows.max()+1), slice(cols.min(), cols.max()+1))
    sheet = materials[crop]
    for seam in ICE_SEAMS:
        points = np.asarray(seam)+np.asarray(CENTRE)
        d, _ = polyline_distance(points, x[crop], y[crop], reach=170)
        sheet[ice[crop] & (d < 110+30*wear[crop])] = 4
        sheet[ice[crop] & (d < 18+12*wear[crop])] = 5
    # Fractured blue walls and dark beds beneath meltwater explain the hazards.
    # Frost follows the raised rims; the middle crossing retains clean ice.
    sheet[ice[crop] & (basin['frost'] > .08)] = 4
    sheet[basin['lips'] > 7] = 5
    sheet[(basin['lips'] > 32) & (basin['grain'] > .08)] = 0
    sheet[basin['depth'] > 12] = 4
    sheet[basin['depth'] > 80] = DEPTH
    paint_glacier_margin(materials, x, y, shore, z, slope, rupture, basin)
    return dict(z=z, blocked=~walk, slope=slope, materials=materials,
                pads=pads, reserved=reserved, ice=ice, rupture=rupture,
                route_core=route_core, basins=basins, checkpoints=checkpoints,
                tower_hollows=tower_hollows)
