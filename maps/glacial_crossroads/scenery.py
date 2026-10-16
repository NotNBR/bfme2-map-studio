"""Winter waystations, Dwarf-road shrines, sealed gates, camps and remains.

An old Dwarven road crossed these passes. Small waystations overlook the
cirques; carved shrines stand at the mountain feet beside the main ways,
their backs set into the slope; and in the four high corner cirques the
sealed gates of abandoned holds are set into the headwalls, guarded by
weathered statues, with derelict ore carts before them. Travellers keep
fires in a few sheltered cirque margins. Bones and broken carts lie in the
four fighting hollows, where old battles were fought at the crossroads.

Forests, thickets, boulders and tarns come from wilds.py; boulder trains
follow the main passes. Every placement shares the clearances of
placement.py: level construction pads and the full widths of approach
routes keep an additional clear margin, and shrines and gates stand wholly
on the closed mountain side of the movement edge. The central ruined tower,
outer spires and ring walls have authored scales. Stable per-position seeds
prevent rerolling unrelated scenery when one cluster changes.
"""
import math
import numpy as np

from mapworkshop.mapkit.ambient import ambient
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.sites import neutral_site
from mapworkshop.mapkit.variety import spot_random
from .design import BASES, BORDER, CENTRE, PAD_HALF, ROUTES
from .features import ARENA_TOWER, BATTLE_HOLLOWS, CAPTURE_LINKS, CHECKPOINTS, GATES, ROCKS
from .placement import Placer
from .terrain import SCREE, STONES
from .wilds import populate_wilds

# Main surviving structure and nearby collapse fragments in its local frame.
# The fragments form one ruin, rather than detached props around an apron.
STATIONS = {
    'watchwall': ('DwarvishRuinSnow01', 48, math.pi, [
        (-65, -40, 'DwarvishRuinSnow05', 12, .1),
        (92, 25, 'DwarvishRuinSnow02', 33, .3),
        (-45, 65, 'DwarvishRuinSnow07', 25, -.2)]),
    'shelter': ('DwarvishRuinSnow03', 55, math.pi/2, [
        (-120, 10, 'DwarvishRuinSnow04', 52, math.pi/2),
        (72, 65, 'DwarvishRuinSnow02', 33, .25),
        (10, 82, 'DwarvishRuinSnow06', 15, .1)]),
    'fallenwall': ('DwarvishRuinSnow04', 52, math.pi, [
        (75, -55, 'DwarvishRuinSnow02', 33, .1),
        (-70, 45, 'DwarvishRuinSnow07', 25, .2),
        (-12, -78, 'DwarvishRuinSnow05', 12, -.2)]),
    'waymarkers': ('DwarvishRuinSnow05', 12, 0, [
        (40, 14, 'DwarvishRuinSnow06', 15, -.15),
        (-55, -5, 'DwarvishRuinSnow02', 33, .2),
        (18, 55, 'DwarvishRuinSnow05', 12, .1)]),
}
STATION_TYPES = {1: 'watchwall', 4: 'fallenwall', 7: 'shelter', 10: 'waymarkers',
                 2: 'shelter', 5: 'fallenwall', 8: 'watchwall', 12: 'shelter',
                 13: 'watchwall', 14: 'shelter', 15: 'fallenwall', 16: 'waymarkers'}

# Inspected 0/40, 90/40, 180/40, 270/40 and the diagonals: the arch's and
# the doors' carved faces are local -y; the niche's statue faces its local
# (-x, -y) corner and its back is an open shell, so it needs a slope behind;
# SnowyStatue02's hooded figure faces local +x.
GATE_FRONT = math.pi/2
NICHE_FRONT = 3*math.pi/4
STATUE_FRONT = 0.
# Pieces of each travellers' camp: template, offsets toward the base and
# across, footprint, turn. Tents face the fire; carts and stores stand back.
CAMP = [('Tent01', -30, -40, 26, .6), ('Tent01', -45, 42, 26, 2.4),
        ('FireCampfire', 15, 0, 10, 0.), ('CartWreck', -95, -10, 24, 1.6),
        ('Barrel02', -70, 70, 6, 0.), ('BarrelKeg', -62, 82, 4, .5),
        ('Beams', 40, -60, 14, .3), ('IthilienSupplies05', -80, -60, 8, .2)]
REMAINS = ['Skeleton', 'Bones01', 'Bones02', 'Bones03', 'Bones04', 'Bones05',
           'Bones06', 'Discarded02', 'Discarded04']


def populate(m, t):
    """Compose all scenery; returns the counts and sites for the report."""
    p = Placer(m, t)
    stations = waystations(p)
    gates = sealed_gates(p, t)
    shrines = road_shrines(p, t)
    camps = travellers_camps(p)
    wild = populate_wilds(p, t)
    pass_moraines(p)
    cirque_erratics(p)
    remains = battle_remains(p, t)
    if p.trees < 1500 or len(stations) < 8 or len(gates) < 4:
        raise ValueError(f'Scenery sites too sparse: {p.trees} trees, '
                         f'{len(stations)} waystations, {len(gates)} gates')
    heights = [(s['x'], s['y']) for s in stations]+[g['position'] for g in gates]
    sounds = ambient(m, 'winter', CENTRE, zones=dict(
        woods=wild['stands'], heights=heights,
        open=[(13250, 15050), (15050, 13400), (14250, 16350), (14250, 12150)]),
        spacing=1200, limits=dict(woods=40, heights=16, open=4))
    return dict(objects=dict(p.counts), layers=dict(p.layers),
                total_scenery=sum(p.counts.values()), trees=p.trees, shrubs=p.shrubs,
                tree_limit_ignored=True,
                wilds={k: v for k, v in wild.items() if k != 'stands'},
                waystations=stations, gates=gates, shrines=len(shrines), camps=camps,
                battle_remains=remains, sounds=len(sounds),
                minimum_protected_margin=round(p.minimum_margin, 1),
                pads_and_approaches_clear=True)


def waystations(p):
    """Unequal small ruins beside the cirque mouths; landmarks, not gameplay sites."""
    stations = []
    for number in (13, 14, 15, 16, 1, 4, 7, 10, 2, 5, 8, 12):
        base = next(b for b in BASES if b['number'] == number)
        bearing = math.atan2(CENTRE[1]-base['y'], CENTRE[0]-base['x'])
        flank = bearing+(.88 if number % 2 else -1.02)
        target = (base['x']+1430*math.cos(flank), base['y']+1430*math.sin(flank))
        style = STATION_TYPES[number]
        main, footprint, front, pieces = STATIONS[style]
        site = p.find_site(*target, footprint)
        if site is None:
            continue
        x, y = site
        # Four inspected views: 03's arch faces local -y; 01's stair/wall
        # face and 04's carved broken face are local -x. 05 is a plain pillar.
        angle = math.atan2(base['y']-y, base['x']-x)+front
        layer = f'Waystation {number:02}'
        if not p.place(main, x, y, layer, footprint, angle, .12, 9):
            continue
        p.paint(x, y, footprint*.8, SCREE, 1.3, angle)
        stations.append(dict(base=number, x=x, y=y, facing=angle, style=style))
        rng = spot_random(8640, layer, x, y)
        for dx, dy, template, radius, turn in pieces:
            dx += rng.uniform(-8, 8)
            dy += rng.uniform(-8, 8)
            turn += rng.uniform(-.15, .15)
            px = x+dx*math.cos(angle)-dy*math.sin(angle)
            py = y+dx*math.sin(angle)+dy*math.cos(angle)
            ground = p.find_site(px, py, radius, reach=60)
            if ground and p.place(template, *ground, layer, radius, angle+turn, .12, 9):
                p.paint(*ground, radius*.8, SCREE, 1.15, angle+turn)
        # Small rubble joins the masonry into a collapse fan. No large,
        # smooth oval of different snow marks the station's footprint.
        for _ in range(30):
            dx, dy = rng.gauss(0, 70), rng.gauss(35, 55)
            px = x+dx*math.cos(angle)-dy*math.sin(angle)
            py = y+dx*math.sin(angle)+dy*math.cos(angle)
            if p.place('SnowyRock19', px, py, layer+' collapse', 15,
                       max_slope=.20, max_rise=5, sink=.5):
                p.paint(px, py, 12, SCREE)
    return stations


def ground_at(t, x, y):
    return float(t['z'][round(y/10)+BORDER, round(x/10)+BORDER])


def sealed_gates(p, t):
    """Sealed hold gates in the headwalls behind the four high corner cirques.

    Each stands at its authored position in features.GATES, in the portal
    terrain.py carves: a level forecourt before it and a sheer face behind,
    which covers the back of the arch. Statues guard the forecourt, ore
    carts stand derelict before the doors and masonry has fallen around it.
    """
    gates = []
    for gate in GATES:
        gx, gy = gate['position']
        facing = gate['facing']
        # u: out of the mountain toward the cirque is -u here.
        ux, uy = -math.cos(facing), -math.sin(facing)
        layer = f'Sealed gate {gate["base"]:02}'
        z0 = ground_at(t, gx+120*math.cos(facing), gy+120*math.sin(facing))
        rise = ground_at(t, gx+150*ux, gy+150*uy)-z0

        def sunk(x, y, extra=0.):
            # Masonry stays level at the forecourt height where ground rises.
            return ground_at(t, x, y)-z0+extra

        add_object(p.m, 'EreborDestructableDoor', gx, gy, angle=facing+GATE_FRONT,
                   z=-sunk(gx, gy, 4), layer=layer)
        # The doors stand just behind the arch, inside the slope.
        dx, dy = gx+16*ux, gy+16*uy
        add_object(p.m, 'EreborGateDoors', dx, dy, angle=facing+GATE_FRONT,
                   z=-sunk(dx, dy, 2), layer=layer)
        for side in (-1, 1):
            cx, cy = gx-235*side*uy-12*ux, gy+235*side*ux-12*uy
            add_object(p.m, 'EreborColumn01', cx, cy, angle=facing+GATE_FRONT,
                       z=-sunk(cx, cy, 6), layer=layer)
            sx, sy = gx-130*side*uy-120*ux, gy+130*side*ux-120*uy
            p.place('SnowyStatue02', sx, sy, layer+' guardians', 14,
                    angle=facing+STATUE_FRONT+.12*side, max_slope=.8, sink=3, margin=60)
        rng = spot_random(8650, layer, gx, gy)
        # Derelict ore carts in a broken line, and fallen masonry.
        for k in range(4):
            along = 190+k*38+rng.uniform(-8, 8)
            off = rng.uniform(-40, 40)
            px, py = gx-along*ux-off*uy, gy-along*uy+off*ux
            p.place(f'EreborCart0{1+k % 3}', px, py, layer+' carts', 12,
                    angle=facing+GATE_FRONT+rng.uniform(-.4, .4), max_slope=.5, margin=60)
        for k in range(14):
            depth, spread = rng.uniform(80, 300), rng.gauss(0, 150)
            px, py = gx-depth*ux-spread*uy, gy-depth*uy+spread*ux
            template = 'DwarvishRuinSnow02' if k < 3 else 'SnowyRock19'
            p.place(template, px, py, layer+' rubble', 33 if k < 3 else 15,
                    max_slope=.6, sink=1, margin=60)
        p.place('Skeleton', gx-150*ux, gy-150*uy, layer+' carts', 12, max_slope=.5, margin=60)
        # The arch, doors and columns bypass the placement checks; keep the
        # forest and later scenery off the gate and its forecourt.
        p.reserve(gx-120*ux, gy-120*uy, 330)
        gates.append(dict(base=gate['base'], position=(gx, gy), facing=facing,
                          wall_rise=round(rise, 1)))
    return gates


def road_shrines(p, t):
    """Carved niches at the mountain feet beside the main ways, every ~1,900 units."""
    shrines = []
    for route in ROUTES:
        if not route['main']:
            continue
        pts = np.asarray(route['points'])
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        rng = spot_random(8660, route['name'], *pts[0])
        side = 1 if rng.random() < .5 else -1
        for station in np.arange(800+rng.random()*700, arc[-1]-700, 1900):
            j = min(np.searchsorted(arc, station)-1, len(pts)-2)
            direction = (pts[j+1]-pts[j])/np.linalg.norm(pts[j+1]-pts[j])
            xy = pts[j]+direction*(station-arc[j])
            normal = np.array([-direction[1], direction[0]])
            for s in (side, -side):
                foot = None
                for d in range(int(route['width']/2)+140, int(route['width']/2)+1100, 20):
                    q = xy+s*normal*d
                    if t['blocked'][p.at(*q)]:
                        foot = q
                        break
                if foot is None:
                    continue
                # Wholly on the closed slope, its open back into the hill.
                pos = foot+s*normal*48
                facing = math.atan2(-s*normal[1], -s*normal[0])
                layer = 'Dwarf-road shrines'
                if p.place('EreborNiche01', *pos, layer, 26, angle=facing+NICHE_FRONT,
                           max_slope=.75, sink=6):
                    shrines.append(pos.tolist())
                    for _ in range(3):
                        qx, qy = pos-s*normal*rng.uniform(40, 70)+direction*rng.uniform(-60, 60)
                        p.place('SnowyRock19', qx, qy, layer+' rubble', 15, max_slope=.6, sink=1)
                    side = -s
                    break
    return shrines


def travellers_camps(p):
    """Fires and tents in sheltered margins of six middle cirques, where level ground is found."""
    camps = []
    for number in (2, 5, 6, 9, 11, 12):
        base = next(b for b in BASES if b['number'] == number)
        rng = spot_random(8680, 'camp', base['x'], base['y'])
        away = math.atan2(base['y']-CENTRE[1], base['x']-CENTRE[0])
        a = away+rng.choice((-1, 1))*rng.uniform(.6, 1.1)
        target = (base['x']+(PAD_HALF+380)*math.cos(a), base['y']+(PAD_HALF+380)*math.sin(a))
        site = p.find_site(*target, 110, reach=700, max_height=1400, max_slope=.16, max_rise=20)
        if site is None:
            continue
        x, y = site
        facing = math.atan2(base['y']-y, base['x']-x)
        layer = f'Camp {number:02}'
        placed = 0
        for template, along, across, radius, turn in CAMP:
            px = x+along*math.cos(facing)-across*math.sin(facing)
            py = y+along*math.sin(facing)+across*math.cos(facing)
            # Tent01's flap is its local -y side, turned toward the fire.
            angle = math.atan2(y-py, x-px)+math.pi/2 if template == 'Tent01' else facing+turn
            placed += p.place(template, px, py, layer, radius, angle=angle,
                              max_slope=.18, spacing=radius*.6)
        # Trampled snow in a few uneven lobes, with ash and stones by the fire.
        for _ in range(6):
            a, d = rng.random()*math.tau, rng.uniform(15, 70)
            p.paint(x+d*math.cos(a), y+d*math.sin(a), rng.uniform(28, 48), 1,
                    rng.uniform(1, 1.6), rng.random()*math.pi)
        fx, fy = x+15*math.cos(facing), y+15*math.sin(facing)
        p.paint(fx, fy, 18, STONES)
        camps.append(dict(base=number, position=(x, y), pieces=placed))
    return camps


def pass_moraines(p):
    """Related boulder trains along the main passes, broken into short groups."""
    for route in ROUTES:
        if not route['main']:
            continue
        pts = np.asarray(route['points'])
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        for station in np.arange(240, arc[-1]-240, 250):
            j = min(np.searchsorted(arc, station)-1, len(pts)-2)
            direction = pts[j+1]-pts[j]
            direction /= np.linalg.norm(direction)
            xy = pts[j]+direction*(station-arc[j])
            rng = spot_random(8616, route['name'], *xy)
            if rng.random() > .73:
                continue
            normal = np.array([-direction[1], direction[0]])
            for side in (-1, 1):
                offset = route['width']/2+rng.uniform(140, 280)
                px, py = xy+side*normal*offset
                template, radius = ROCKS[int(rng.random()*len(ROCKS))]
                layer = 'Pass moraine '+route['name']
                if p.place(template, px, py, layer, radius, max_slope=.32, max_rise=24, sink=3):
                    p.paint(px, py, radius*.65, SCREE, 1.25)
                    # Smaller pieces spill downhill from the main outcrop.
                    for fragment in range(2):
                        qx, qy = np.array([px, py])+direction*(115+fragment*85)-normal*side*25
                        p.place('SnowyRock17', qx, qy, layer, 45, max_slope=.28, max_rise=15, sink=1)
                # Small loose fragments can rest on narrow shelves where
                # the large boulder meshes would overhang the valley floor.
                for fragment in range(3):
                    qx, qy = (xy+side*normal*(route['width']/2+145+fragment*40)
                              + direction*rng.uniform(-65, 65))
                    p.place('SnowyRock19', qx, qy, layer+' rubble', 15,
                            max_slope=.22, max_rise=5, sink=.5)


def cirque_erratics(p):
    """A few obstacles on the wider cirque margins, outside the construction pads."""
    for base in BASES:
        for i in range(32):
            angle = i*math.tau/32+.17*base['number']
            rng = spot_random(8618, 'cirque erratic', base['number'], i)
            radius = rng.uniform(1170, 1850)
            x, y = base['x']+radius*math.cos(angle), base['y']+radius*math.sin(angle)
            template, footprint = ROCKS[int(rng.random()*len(ROCKS))]
            if p.place(template, x, y, f'Cirque {base["number"]:02} erratics', footprint,
                       max_slope=.22, max_rise=18, sink=2):
                p.paint(x, y, footprint*.65, SCREE)


def battle_remains(p, t):
    """Bones, cast-off arms and broken carts strewn through the fighting hollows.

    They are flat props that do not obstruct movement, so unlike the other
    scenery they may lie inside the hollows; they still keep off route cores.
    """
    counts = {}
    for hollow in BATTLE_HOLLOWS:
        px, py = hollow['center']
        rng = spot_random(8670, hollow['name'], px, py)
        bearing = math.radians(hollow['bearing'])
        layer = f'Battle remains {hollow["name"]}'
        placed = 0
        for _ in range(7):
            along = rng.uniform(-.85, .85)*hollow['length']
            across = rng.uniform(-.9, .9)*hollow['breadth']
            cx = px+along*math.cos(bearing)-across*math.sin(bearing)
            cy = py+along*math.sin(bearing)+across*math.cos(bearing)
            for _ in range(rng.randint(5, 11)):
                qx, qy = cx+rng.gauss(0, 55), cy+rng.gauss(0, 55)
                if t['route_core'][p.at(qx, qy)]:
                    continue
                placed += p.place(rng.choice(REMAINS), qx, qy, layer, 10, max_slope=.35,
                                  spacing=3, margin=-1000)
            if rng.random() < .55:
                qx, qy = cx+rng.gauss(0, 40), cy+rng.gauss(0, 40)
                if not t['route_core'][p.at(qx, qy)]:
                    placed += p.place(rng.choice(('CartWreck', 'CartPiece')), qx, qy, layer, 22,
                                      max_slope=.25, margin=-1000)
        counts[hollow['name']] = placed
    return counts


def arena_tower(m, t):
    """A four-times-scale ruin, broad snow mound, broken ring and outer spires."""
    x, y = ARENA_TOWER['position']
    r, c = round(y/10)+BORDER, round(x/10)+BORDER
    footing = t['z'][r-12:r+13, c-12:c+13]
    yy, xx = np.mgrid[-12:13, -12:13]*10.
    if np.ptp(footing[xx*xx+yy*yy <= 120**2]) > .1:
        raise ValueError('Arena tower foundation is not level')
    # Inspected 0/40,90/40,180/40,270/40: the intact doorway is on local
    # -y. Angle zero faces it south; the rocky buttresses leave it open.
    add_object(m, ARENA_TOWER['template'], x, y, angle=0, layer='Arena tower',
               extra=[('objectName', 3, 'Arena_RuinedTower'),
                      ('objectPrototypeScale', 2, ARENA_TOWER['scale'])])
    # Rock ribs climb toward the tower; the south doorway remains open.
    rocks = [
        ('GlacialArenaSpireSmall', -192, 35, .25, 13),
        ('GlacialArenaSpireSmall', 169, 112, 2.1, 14),
        ('SnowyRock09', -42, 198, 4.0, 6),
        ('SnowyRock03', -246, -30, .8, 5),
        ('SnowyRock08', 242, 55, 2.7, 5),
        ('SnowyRock04', 40, 254, 4.6, 5),
        ('SnowyRock14', -260, 92, 1.1, 3),
        ('SnowyRock18', 258, -83, .2, 3),
        ('SnowyRock19', -151, -165, 2.4, 1),
        ('SnowyRock19', 148, -195, .7, 1),
    ]
    for template, dx, dy, angle, sink in rocks:
        add_object(m, template, x+dx, y+dy, angle=angle, z=-sink,
                   layer='Arena foundation rocks')
    # Inspected four views: this snowy arch runs along local x, with its
    # front on -y. Tangential placement turns that face out from the ring.
    # Four broken arcs leave broad cardinal entrances, never a closed fence.
    wall_angles = (20, 39, 58, 119, 138, 157, 203, 222, 241, 299, 318, 337)
    for i, degrees in enumerate(wall_angles):
        a = math.radians(degrees)
        px, py = x+420*math.cos(a), y+330*math.sin(a)
        tangent = math.atan2(330*math.cos(a), -420*math.sin(a))
        add_object(m, 'GlacialArenaRingWall', px, py, angle=tangent,
                   z=-12-(i % 3)*4, layer='Arena broken ring')
        # Collapse material joins each surviving arc to the snow apron.
        if i % 3 == 2:
            add_object(m, 'DwarvishRuinSnow02', px+35*math.cos(a),
                       py+35*math.sin(a), angle=tangent+.3, z=-4,
                       layer='Arena ring collapse')
    spires = [
        (-690, -180, 'Large', .3), (-580, 300, 'Medium', 1.6),
        (-260, 520, 'Small', 2.8), (250, 470, 'Medium', 4.0),
        (650, 240, 'Large', .9), (720, -180, 'Small', 2.0),
        (390, -460, 'Medium', 3.3), (-290, -480, 'Small', 5.1),
    ]
    for dx, dy, size, angle in spires:
        px, py = x+dx, y+dy
        rr, cc = round(py/10)+BORDER, round(px/10)+BORDER
        if t['rupture'][rr, cc] or t['blocked'][rr, cc]:
            raise ValueError('Arena spire falls inside a glacier rupture')
        add_object(m, 'GlacialArenaSpire'+size, px, py, angle=angle, z=-10,
                   layer='Arena outer spires')
        add_object(m, 'SnowyRock18', px+35, py-32, angle=angle+.5, z=-3,
                   layer='Arena spire rubble')
    return dict(template=ARENA_TOWER['template'], position=[x, y],
                scale=ARENA_TOWER['scale'], foundation_height=float(t['z'][r, c]),
                rocks=len(rocks), ring_walls=len(wall_angles), outer_spires=len(spires),
                door_faces='south')


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
        # The same functional beacon/inn is identifiable in different local
        # scenes: a fallen lintel, a wall remnant, or a snow-buried rockfall.
        # All details sit behind the model; the entire flag forecourt is open.
        scenes = {
            'Northwest inner': [('DwarvishRuinSnow01', 95, 60, 48, .2),
                                ('DwarvishRuinSnow02', 90, -75, 33, -.3),
                                ('DwarvishRuinSnow06', 35, -95, 15, .1)],
            'Northeast inner': [('DwarvishRuinSnow07', 90, -55, 25, .8),
                                ('DwarvishRuinSnow05', 65, 75, 12, -.5),
                                ('DwarvishRuinSnow05', 105, 55, 12, -.3)],
            'Southwest inner': [('SnowyRock12', 95, 40, 28, 1.2),
                                ('SnowyRock11', 70, -65, 30, .8),
                                ('SnowyRock19', 120, -25, 15, 0)],
            'Southeast inner': [('DwarvishRuinSnow02', 95, -48, 33, .4),
                                ('DwarvishRuinSnow06', 75, 70, 15, .2),
                                ('SnowyRock19', 115, 35, 15, .1)],
            'North saddle': [('DwarvishRuinSnow05', 125, 80, 12, -.4),
                             ('DwarvishRuinSnow05', 140, -70, 12, .1),
                             ('DwarvishRuinSnow02', 170, 15, 33, .6)],
            'East saddle': [('SnowyRock12', 130, -100, 28, .9),
                            ('SnowyRock19', 165, -50, 15, .3),
                            ('SnowyRock19', 145, 75, 15, .8)],
            'South saddle': [('DwarvishRuinSnow07', 140, 70, 25, -.7),
                             ('DwarvishRuinSnow06', 135, -75, 15, -.2)],
            'West saddle': [('DwarvishRuinSnow01', 165, -60, 48, -.2),
                            ('DwarvishRuinSnow02', 140, 95, 33, .4),
                            ('DwarvishRuinSnow05', 125, -80, 12, .1)],
        }
        pieces = scenes[site['name']]
        placed = 0
        details = []
        occupied = [(p, radius), (flag, 70.)]
        for ruin_template, along, side, radius, turn in pieces:
            n = math.ceil(radius/10)
            yy, xx = np.mgrid[-n:n+1, -n:n+1]*10.
            disk = xx*xx+yy*yy <= radius*radius
            candidates = []
            # Settle the ruin on a nearby natural ledge, without reshaping
            # terrain or letting it migrate into the flag's forecourt.
            for da in range(-60, 61, 20):
                for ds in range(-60, 61, 20):
                    if along+da < (90 if template == 'Inn' else 35):
                        continue
                    q = p+(along+da)*outward+(side+ds)*across
                    r, c = round(q[1]/10)+BORDER, round(q[0]/10)+BORDER
                    crop = (slice(r-n, r+n+1), slice(c-n, c+n+1))
                    blocked = t['blocked'][crop][disk]
                    if (any(np.linalg.norm(q-centre) < radius+size+5 for centre, size in occupied)
                            or route_margin(q) < radius+70
                            or (blocked.any() and not blocked.all())
                            or np.ptp(t['z'][crop][disk]) > 6):
                        continue
                    candidates.append((da*da+ds*ds, along+da, side+ds))
            if not candidates:
                continue
            _, settled_along, settled_side = min(candidates)
            q = p+settled_along*outward+settled_side*across
            # Turn the broken remnants inward toward the open forecourt.
            turn_angle = math.atan2(-outward[1], -outward[0])+math.pi+turn
            add_object(m, ruin_template, *q, angle=turn_angle, layer=layer)
            occupied.append((q, radius))
            details.append(dict(template=ruin_template, position=q.tolist()))
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
                            scenery=details,
                            surrounding_bases=site['players'],
                            route_margin=round(float(route_margin(p)-(105 if template == 'Inn' else 55)), 1),
                            neutral_owner=True))
    return results
