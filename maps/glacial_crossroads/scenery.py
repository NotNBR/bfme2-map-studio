"""Winter waystations, sheltered spruce groves and broken moraine margins.

The scenery follows the existing cirques and pass edges. Level construction
pads and the full widths of approach routes retain an additional clear margin.
All assets retain native scale. Stable per-position seeds prevent rerolling
unrelated scenery when one cluster changes.
"""
from collections import Counter, defaultdict
import math
import numpy as np

from mapworkshop.mapkit.ambient import ambient
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.relief import distance_to
from mapworkshop.mapkit.sites import neutral_site
from mapworkshop.mapkit.variety import spot_random
from .design import BASES, BORDER, CENTRE, EXTENT, ROUTES
from .features import CAPTURE_LINKS, CHECKPOINTS, ROCKS, TREES
from .terrain import DRIFT, SCREE, WIND


def populate(m, t):
    """Compose clear-margin scenery and its small, terrain-following aprons."""
    protected = t['pads'] | t['route_core'] | t['ice'] | t['checkpoints']
    clearance = distance_to(protected)*10
    open_clearance = distance_to(t['blocked'])*10
    closed_clearance = distance_to(~t['blocked'])*10
    counts, layers = Counter(), Counter()
    occupied = defaultdict(list)
    trees = 0
    minimum_margin = math.inf

    def at(x, y):
        return round(y/10)+BORDER, round(x/10)+BORDER

    def free(x, y, radius, max_slope=.25, max_rise=None):
        if not (300 < x < EXTENT-300 and 300 < y < EXTENT-300):
            return False
        r, c = at(x, y)
        if clearance[r, c] < radius+70 or t['slope'][r, c] > max_slope:
            return False
        # A footprint must sit entirely on one side of the terrain's
        # movement edge, avoiding tiny enclosed pockets behind a rock.
        if max(open_clearance[r, c]-30, closed_clearance[r, c]) < radius+20:
            return False
        if max_rise is not None:
            n = math.ceil(radius/10)
            ground = t['z'][r-n:r+n+1, c-n:c+n+1]
            if np.ptp(ground) > max_rise:
                return False
        key = (int(x//250), int(y//250))
        for ky in range(key[1]-1, key[1]+2):
            for kx in range(key[0]-1, key[0]+2):
                if any((x-a)**2+(y-b)**2 < (radius+size+5)**2
                       for a, b, size in occupied[kx, ky]):
                    return False
        return True

    def paint(x, y, radius, material, stretch=1.):
        r, c = at(x, y)
        n = math.ceil(radius*max(1, stretch)/10)+2
        sy, sx = slice(r-n, r+n+1), slice(c-n, c+n+1)
        yy, xx = np.mgrid[-n:n+1, -n:n+1]*10.
        contour = radius*(1+.12*np.sin(xx/65+yy/110)+.07*np.cos(yy/43))
        mask = (np.hypot(xx/stretch, yy) < contour) & ~protected[sy, sx]
        t['materials'][sy, sx][mask] = material

    def place(template, x, y, layer, radius, angle=None, max_slope=.25, max_rise=None, sink=0.):
        nonlocal minimum_margin
        if not free(x, y, radius, max_slope, max_rise):
            return False
        rng = spot_random(8612, template, x, y)
        add_object(m, template, x, y, z=-sink,
                   angle=rng.random()*math.tau if angle is None else angle, layer=layer)
        occupied[int(x//250), int(y//250)].append((x, y, radius))
        counts[template] += 1
        layers[layer] += 1
        r, c = at(x, y)
        minimum_margin = min(minimum_margin, clearance[r, c]-radius)
        return True

    def find_site(px, py, radius, reach=650, max_height=2100):
        candidates = []
        for dy in range(-reach, reach+1, 40):
            for dx in range(-reach, reach+1, 40):
                if dx*dx+dy*dy > reach*reach:
                    continue
                x, y = px+dx, py+dy
                r, c = at(x, y)
                if (300 < x < EXTENT-300 and 300 < y < EXTENT-300
                        and t['z'][r, c] < max_height and free(x, y, radius, .12, 9)):
                    candidates.append((dx*dx+dy*dy, x, y))
        return min(candidates)[1:] if candidates else None

    stations = []
    # An old Dwarven way crosses the cirques. Unequal small remnants stand
    # beside its mouths; they are landmarks, not capturable/gameplay sites.
    for number in (13, 14, 15, 16, 1, 4, 7, 10, 2, 5, 8, 12):
        base = next(b for b in BASES if b['number'] == number)
        bearing = math.atan2(CENTRE[1]-base['y'], CENTRE[0]-base['x'])
        flank = bearing+(.88 if number % 2 else -1.02)
        target = (base['x']+1430*math.cos(flank), base['y']+1430*math.sin(flank))
        site = find_site(*target, 55)
        if site is None:
            continue
        x, y = site
        # Four inspected views: 03's open arch faces local -y; 04's
        # carved broken face is local -x. Both look into the base clearing.
        angle = math.atan2(base['y']-y, base['x']-x)+math.pi/2
        layer = f'Waystation {number:02}'
        if not place('DwarvishRuinSnow03', x, y, layer, 55, angle, .12, 9):
            continue
        paint(x, y, 140, WIND, 1.3)
        paint(x, y, 45, SCREE)
        stations.append(dict(base=number, x=x, y=y, facing=angle))
        pieces = [(-130, 30, 'DwarvishRuinSnow04', 52, math.pi/2),
                  (115, 20, 'DwarvishRuinSnow02', 33, .23),
                  (75, 120, 'DwarvishRuinSnow07', 25, -.4),
                  (-80, 125, 'DwarvishRuinSnow06', 15, .6),
                  (20, 145, 'DwarvishRuinSnow06', 15, 1.4)]
        for dx, dy, template, radius, turn in pieces:
            px = x+dx*math.cos(angle)-dy*math.sin(angle)
            py = y+dx*math.sin(angle)+dy*math.cos(angle)
            ground = find_site(px, py, radius, reach=170)
            if ground and place(template, *ground, layer, radius, angle+turn, .12, 9):
                paint(*ground, radius*.7, SCREE)

    groves = []
    # Unequal sheltered wings per lower cirque. The high corner
    # lookouts remain above the tree line. Cores are dense, their edges thin.
    for base in BASES:
        if base['height'] > 1200:
            continue
        bearing = math.atan2(CENTRE[1]-base['y'], CENTRE[0]-base['x'])
        for wing, turn in enumerate((-.95, 1.15, 2.6, -2.6)):
            angle = bearing+turn
            target = (base['x']+1510*math.cos(angle), base['y']+1510*math.sin(angle))
            site = find_site(*target, 40, reach=570, max_height=1400)
            if site is None:
                continue
            x, y = site
            layer = f'Cirque {base["number"]:02} spruce'
            before = trees
            for gy in range(-450, 451, 60):
                for gx in range(-285, 286, 60):
                    rng = spot_random(8614, layer, x+gx, y+gy)
                    dx, dy = gx+rng.uniform(-20, 20), gy+rng.uniform(-20, 20)
                    q = (dx/285)**2+(dy/460)**2
                    if q > 1 or rng.random() > 1-.38*q or trees >= 1080:
                        continue
                    px = x+dx*math.cos(angle)-dy*math.sin(angle)
                    py = y+dx*math.sin(angle)+dy*math.cos(angle)
                    r, c = at(px, py)
                    if t['z'][r, c] > 1400:
                        continue
                    template, radius = TREES[(wing+int(rng.random()*5)) % 2]
                    if place(template, px, py, layer, radius, max_slope=.30):
                        trees += 1
                        if rng.random() < .32:
                            paint(px, py, 40+rng.random()*20, DRIFT)
            if trees > before:
                groves.append((x, y))
            # Low twig scrub at the grove's ragged edge supplies a second
            # vegetation scale without filling the base or its main routes.
            for i in range(22):
                rng = spot_random(8620, layer, x+i, y)
                a = rng.random()*math.tau
                px, py = x+math.cos(a)*rng.uniform(170, 340), y+math.sin(a)*rng.uniform(270, 500)
                template = ('SnowyShrub01', 'SnowyShrub03', 'SnowyShrub05')[i % 3]
                place(template, px, py, layer+' scrub', 18, max_slope=.32)

    # Related boulder trains follow the valley sides. Offset from the actual
    # bent route axis, each train breaks into short groups rather than fences.
    for route in ROUTES:
        if not route['main']:
            continue
        p = np.asarray(route['points'])
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        for station in np.arange(240, arc[-1]-240, 250):
            j = min(np.searchsorted(arc, station)-1, len(p)-2)
            direction = p[j+1]-p[j]
            direction /= np.linalg.norm(direction)
            xy = p[j]+direction*(station-arc[j])
            rng = spot_random(8616, route['name'], *xy)
            if rng.random() > .73:
                continue
            normal = np.array([-direction[1], direction[0]])
            for side in (-1, 1):
                offset = route['width']/2+rng.uniform(140, 280)
                px, py = xy+side*normal*offset
                template, radius = ROCKS[int(rng.random()*len(ROCKS))]
                layer = 'Pass moraine '+route['name']
                if place(template, px, py, layer, radius, max_slope=.32, max_rise=24, sink=3):
                    paint(px, py, radius*.65, SCREE, 1.25)
                    # Smaller pieces spill downhill from the main outcrop.
                    for fragment in range(2):
                        qx, qy = np.array([px, py])+direction*(115+fragment*85)-normal*side*25
                        place('SnowyRock17', qx, qy, layer, 45, max_slope=.28, max_rise=15, sink=1)
                # Small loose fragments can rest on narrow shelves where
                # the large boulder meshes would overhang the valley floor.
                for fragment in range(3):
                    qx, qy = xy+side*normal*(route['width']/2+145+fragment*40)+direction*rng.uniform(-65, 65)
                    place('SnowyRock19', qx, qy, layer+' rubble', 15,
                          max_slope=.22, max_rise=5, sink=.5)

    # Boulders on the wider cirque margins give open base surrounds a few
    # obstacles while leaving the level construction rectangles untouched.
    for base in BASES:
        for i in range(32):
            angle = i*math.tau/32+.17*base['number']
            rng = spot_random(8618, 'cirque erratic', base['number'], i)
            radius = rng.uniform(1170, 1850)
            x, y = base['x']+radius*math.cos(angle), base['y']+radius*math.sin(angle)
            template, footprint = ROCKS[int(rng.random()*len(ROCKS))]
            if place(template, x, y, f'Cirque {base["number"]:02} erratics', footprint,
                     max_slope=.22, max_rise=18, sink=2):
                paint(x, y, footprint*.65, SCREE)

    if trees < 150 or len(stations) < 8:
        raise ValueError(f'Scenery sites too sparse: {trees} trees, {len(stations)} waystations')
    sounds = ambient(m, 'winter', CENTRE, zones=dict(
        woods=groves, heights=[(s['x'], s['y']) for s in stations],
        open=[(13250, 15050), (15050, 13400), (14250, 16350), (14250, 12150)]),
        spacing=1200, limits=dict(woods=24, heights=12, open=4))
    return dict(objects=dict(counts), layers=dict(layers), total_scenery=sum(counts.values()),
                trees=trees, tree_limit=1200, groves=groves, waystations=stations,
                sounds=len(sounds), minimum_protected_margin=round(minimum_margin, 1),
                pads_and_approaches_clear=True)


def checkpoint_sites(m, t):
    """Capturable mountain beacons on compact shelves at the spur feet."""
    results = []

    def route_margin(p):
        distances = []
        for route in ROUTES+CAPTURE_LINKS:
            points = np.asarray(route['points'])
            a, vector = points[:-1], np.diff(points, axis=0)
            along = np.clip(np.sum((p-a)*vector, axis=1)/np.sum(vector*vector, axis=1), 0, 1)
            distances.append(np.linalg.norm(p-(a+along[:, None]*vector), axis=1).min()-route['width']/2)
        return min(distances)

    for site in CHECKPOINTS:
        p = np.asarray(site['position'])
        outward = np.asarray(site['outward'])
        across = np.array([-outward[1], outward[0]])
        layer = f'{site["name"]} checkpoint'
        template = site['template']
        radius = 105 if template == 'Inn' else 55
        flag = p-(109 if template == 'Inn' else 76)*outward
        # Four inspected views: choose the stair-facing local -y side as
        # the front, toward the junction. Inn's inspected doorway also faces
        # local -y. Its flag sits in the forecourt clear of the model.
        angle = math.atan2(-outward[1], -outward[0])+math.pi/2
        for point, footprint in ((p, radius), (flag, 8)):
            r, c = round(point[1]/10)+BORDER, round(point[0]/10)+BORDER
            n = math.ceil(footprint/10)
            yy, xx = np.mgrid[-n:n+1, -n:n+1]*10.
            disk = xx*xx+yy*yy <= footprint*footprint
            if (route_margin(point) < footprint+70 or
                    t['blocked'][r-n:r+n+1, c-n:c+n+1][disk].any() or
                    np.ptp(t['z'][r-n:r+n+1, c-n:c+n+1][disk]) > (2 if template == 'Inn' else 1)):
                raise ValueError(f'{layer}: foundation or route clearance failed')
        neutral_site(m, template, *p, angle=angle, flag=tuple(flag), layer=layer,
                     extra=[('objectName', 3, site['name'].replace(' ', '_')+'_'+template)])
        # The flag approach stays open. A few low remnants hug the spur,
        # with at least 70 units of clearance beyond each existing route.
        pieces = [('DwarvishRuinSnow02', 65, 75, 33, -.3),
                  ('DwarvishRuinSnow07', 100, -35, 25, .5),
                  ('DwarvishRuinSnow06', 10, -90, 15, -.6)]
        if template == 'Inn':
            pieces = [('DwarvishRuinSnow06', 130, 70, 15, -.4),
                      ('DwarvishRuinSnow07', 130, -85, 25, .3)]
        placed = 0
        for ruin_template, along, side, radius, turn in pieces:
            q = p+along*outward+side*across
            r, c = round(q[1]/10)+BORDER, round(q[0]/10)+BORDER
            n = math.ceil(radius/10)
            if (route_margin(q) < radius+70 or
                    t['blocked'][r-n:r+n+1, c-n:c+n+1].any() or
                    np.ptp(t['z'][r-n:r+n+1, c-n:c+n+1]) > 6):
                continue
            # Turn the broken remnants inward toward the open forecourt.
            turn_angle = math.atan2(-outward[1], -outward[0])+math.pi+turn
            add_object(m, ruin_template, *q, angle=turn_angle, layer=layer)
            placed += 1
        # A small exposed-stone patch beneath the beacon,
        # surrounded by packed snow; irregular edges keep the court worn.
        r, c = round(p[1]/10)+BORDER, round(p[0]/10)+BORDER
        n = 23
        yy, xx = np.mgrid[-n:n+1, -n:n+1]*10.
        along = xx*outward[0]+yy*outward[1]
        across = xx*across[0]+yy*across[1]
        stone = ((along > -48+6*np.sin(across/19)) & (along < 65+7*np.cos(across/23))
                 & (across > -45+6*np.cos(along/16)) & (across < 47+9*np.sin(along/27)))
        t['materials'][r-n:r+n+1, c-n:c+n+1][stone] = SCREE
        results.append(dict(name=site['name'], template=template, position=p.tolist(),
                            junction=site['junction'], flag=flag.tolist(), ruins=placed,
                            surrounding_bases=site['players'],
                            route_margin=round(float(route_margin(p)-(105 if template == 'Inn' else 55)), 1),
                            neutral_owner=True))
    return results
