"""Spruce forests, the treeline, shrub thickets, boulders, pinnacles and tarns.

Forests fill the sheltered lower slopes and valley margins below a treeline
that wanders around 1,400 units: dense, tall cores in hollows at the mountain
feet, thinner and smaller trees at their edges, stunted spruce and dead snags
where the forest gives out; stands thin out toward the routes. The high
corner cirques stand above it and stay nearly bare. Lone gnarled dead trees
punctuate the open floors; low thickets gather at the forest edges and in
the hollows. Talus boulders collect below the faces, groups of pinnacles
stand on the convex crests, and a small frozen tarn lies in the flat ground
of each lower cirque, outside the construction pads.

All of it keeps the shared clearances of placement.py. Trees and shrubs do
not obstruct movement; boulders on open ground keep well away from routes.
Candidates are a jittered lattice with fixed seeds; every object then draws
its own numbers from its position. Trees near the bases come first in map
order, so the most visible stands are the first the game loads.
"""
import math
import numpy as np

from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.relief import smooth
from mapworkshop.mapkit.variety import spot_random
from .design import BASES, BORDER, CENTRE, EXTENT, HIGH, PAD_HALF
from .terrain import CLIFF, LEDGES, SCREE, STONES, blur

# Crown radii measured from the stock models at scale 1.
SPRUCE = [('TreeSnowySpruce01', 24.), ('TreeSnowySpruce02', 21.),
          ('TreeSnowySpruce03', 23.), ('TreeSnowySpruce04', 16.)]
SNAGS = [('TreeSnowyDead06', 25.), ('TreeSnowyDead07', 17.), ('TreeSnowyDead08', 22.)]
GNARLED = [('TreeSnowyDead01', 34.), ('TreeSnowyDead02', 31.), ('TreeSnowyDead03', 26.),
           ('TreeSnowyDead04', 40.), ('TreeSnowyDead05', 37.)]
SHRUBS = [('SnowyShrub01', 9.), ('SnowyShrub02', 12.), ('SnowyShrub03', 14.),
          ('SnowyShrub04', 12.), ('SnowyShrub05', 10.)]
BOULDERS = [('SnowyRock01', 40.), ('SnowyRock03', 44.), ('SnowyRock04', 50.),
            ('SnowyRock06', 37.), ('SnowyRock07', 47.), ('SnowyRock08', 38.),
            ('SnowyRock13', 46.), ('SnowyRock14', 56.), ('SnowyRock16', 44.),
            ('SnowyRock17', 33.), ('SnowyRock18', 37.), ('SnowyRock05', 70.)]
PINNACLES = [('SnowyRock09', 30.), ('SnowyRock10', 28.), ('SnowyRock11', 20.),
             ('SnowyRock12', 21.)]


def lattice(step, seed, margin=400):
    """A jittered candidate lattice over the playable area."""
    rng = np.random.default_rng(seed)
    axis = np.arange(margin, EXTENT-margin, step)
    x, y = np.meshgrid(axis, axis)
    x = (x+rng.uniform(-.45, .45, x.shape)*step).ravel()
    y = (y+rng.uniform(-.45, .45, y.shape)*step).ravel()
    return x, y, rng.random(x.size)


def sample(field, x, y, stride=1):
    r = (np.rint(y/10).astype(int)+BORDER)//stride
    c = (np.rint(x/10).astype(int)+BORDER)//stride
    return field[np.clip(r, 0, field.shape[0]-1), np.clip(c, 0, field.shape[1]-1)]


def base_distance(x, y):
    return np.min([np.hypot(x-b['x'], y-b['y']) for b in BASES], axis=0)


def populate_wilds(p, t):
    """Place the forests, thickets, boulders, pinnacles and tarns; returns counts."""
    coarse = t['z'][::3, ::3]
    # Concavity over about 250 units: positive in hollows and at the foot
    # of slopes, negative on spurs and crests.
    concavity = blur(coarse, 8)-coarse
    report = {}

    # -- Frozen tarns in the level cirque floors, outside the pads: clear
    # blue ice, the same as the central sheet, rimmed with frost. They are
    # painted; the FrozenPond models read as dark holes against the snow.
    tarns = []
    for base in BASES:
        if base['height'] == HIGH:
            continue  # The high corner cirques lie above the meltwater.
        rng = spot_random(8750, 'tarns', base['x'], base['y'])
        start = rng.random()*math.tau
        for k in range(36):
            a = start+k*2.4
            reach = PAD_HALF+260+rng.random()*700
            px, py = base['x']+reach*math.cos(a), base['y']+reach*math.sin(a)
            radius = rng.uniform(60, 105)
            stretch, turn = rng.uniform(1.2, 1.9), rng.random()*math.pi
            if not p.free(px, py, radius*stretch+30, max_slope=.10, max_rise=12, margin=60):
                continue
            p.paint(px, py, radius*1.30, 5, stretch, turn)
            p.paint(px, py, radius, 2, stretch, turn)
            for _ in range(3):
                d, b = rng.uniform(0, radius*.6), rng.random()*math.tau
                p.paint(px+d*math.cos(b), py+d*math.sin(b), radius*.30, 4, 1.4, turn)
            p.reserve(px, py, radius*stretch+20)
            tarns.append((px, py))
            break
    report['tarns'] = len(tarns)

    # -- Forest: density field at each candidate, then placement by priority.
    x, y, u = lattice(32, 8700)
    z, slope = sample(t['z'], x, y), sample(t['slope'], x, y)
    material = sample(t['materials'], x, y)
    shelter = smooth(.5+sample(concavity, x, y, 3)/45)
    treeline = 1400+170*fbm(x, y, scale=3200, octaves=2, seed=8702)
    altitude = 1-smooth((z-treeline+300)/300)
    gentle = 1-smooth((slope-.42)/.43)
    ground = np.where(np.isin(material, (CLIFF, LEDGES)), 0., np.where(material == STONES, .45, 1.))
    stands = smooth((fbm(x, y, scale=1250, octaves=3, seed=8703)+.40*(shelter-.5)+.06)/.20)
    lowland = .50+.50*(1-smooth((z-260)/950))
    ice_gap = smooth((np.hypot(x-CENTRE[0], y-CENTRE[1])-2900)/1600)
    # Stands thin out toward routes and pads instead of ending in a row
    # along the clearance line.
    open_edge = smooth((sample(p.clearance, x, y)-90)/320)
    density = stands*altitude*gentle*ground*lowland*ice_gap*(.25+.75*open_edge)
    chosen = np.nonzero(u < .85*density)[0]
    chosen = chosen[np.argsort(base_distance(x[chosen], y[chosen]), kind='stable')]
    stand_points = []
    for i in chosen:
        px, py = float(x[i]), float(y[i])
        rng = spot_random(8704, 'forest', px, py)
        core = density[i]*shelter[i]
        layer = 'Spruce forest'
        if altitude[i] < .45:
            # Stunted spruce and weathered snags where the forest gives out.
            layer = 'Treeline'
            if rng.random() < .35:
                template, radius = SNAGS[int(rng.random()*len(SNAGS))]
                scale = rng.uniform(.75, 1.15)
            else:
                template, radius = SPRUCE[int(rng.random()*len(SPRUCE))]
                scale = rng.uniform(.52, .78)
        elif density[i] < .35:
            template, radius = SPRUCE[3 if rng.random() < .45 else int(rng.random()*3)]
            scale = rng.uniform(.70, 1.02)
        else:
            if rng.random() < .025:
                if p.place('TreeSnowyDeadLog01', px, py, layer+' windfall', 45,
                           max_slope=.45, spacing=30, kind='tree'):
                    continue
            template, radius = SPRUCE[int(rng.random()*3)]
            scale = rng.uniform(.90, 1.10)+.38*core*rng.random()
        if p.place(template, px, py, layer, radius*scale, max_slope=.85,
                   spacing=11*scale, scale=scale, kind='tree'):
            if len(stand_points) < 400 and rng.random() < .015:
                stand_points.append((px, py))
    report['forest_trees'] = p.trees

    # -- Lone dead trees on the open floors, at the edges of the plains.
    x, y, u = lattice(260, 8710)
    z, slope = sample(t['z'], x, y), sample(t['slope'], x, y)
    scatter = smooth((fbm(x, y, scale=1800, octaves=2, seed=8711)+.05)/.25)
    for i in np.nonzero((u < .22*scatter) & (slope < .30) & (z < 1800))[0]:
        px, py = float(x[i]), float(y[i])
        rng = spot_random(8712, 'snag', px, py)
        template, radius = GNARLED[int(rng.random()*len(GNARLED))]
        scale = rng.uniform(.85, 1.30)
        p.place(template, px, py, 'Lone dead trees', radius*scale, max_slope=.30,
                margin=120, scale=scale, kind='tree')
    report['trees'] = p.trees

    # -- Thickets: low clumps at forest edges and in sheltered hollows.
    x, y, u = lattice(90, 8720)
    z, slope = sample(t['z'], x, y), sample(t['slope'], x, y)
    shelter = smooth(.5+sample(concavity, x, y, 3)/45)
    treeline = 1400+170*fbm(x, y, scale=3200, octaves=2, seed=8702)
    stands = smooth((fbm(x, y, scale=1250, octaves=3, seed=8703)+.40*(shelter-.5)+.06)/.20)
    edge = 4*stands*(1-stands)
    thicket = (.55*edge+.35*smooth((shelter-.55)/.25))*smooth((treeline+250-z)/200)
    thicket *= (1-smooth((slope-.45)/.3))
    for i in np.nonzero(u < .40*thicket)[0]:
        px, py = float(x[i]), float(y[i])
        rng = spot_random(8721, 'thicket', px, py)
        for _ in range(2+int(rng.random()*4)):
            template, radius = SHRUBS[int(rng.random()*len(SHRUBS))]
            scale = rng.uniform(.80, 1.40)
            a, d = rng.random()*math.tau, rng.uniform(0, 34)
            p.place(template, px+d*math.cos(a), py+d*math.sin(a), 'Thickets',
                    radius*scale, max_slope=.55, spacing=5*scale, scale=scale, kind='shrub')
    report['shrubs'] = p.shrubs

    # -- Talus boulders below the faces, and a few out on the moraines.
    before = sum(p.counts.values())
    x, y, u = lattice(55, 8730)
    z, slope = sample(t['z'], x, y), sample(t['slope'], x, y)
    material = sample(t['materials'], x, y)
    blocked = sample(t['blocked'], x, y)
    foot = smooth((sample(concavity, x, y, 3)-4)/20)
    talus = np.where(np.isin(material, (STONES, SCREE)), .30, .05*foot)
    talus *= (slope > .18) & (slope < .95) & (z < 2250)
    for i in np.nonzero(u < talus)[0]:
        px, py = float(x[i]), float(y[i])
        rng = spot_random(8731, 'talus', px, py)
        template, radius = BOULDERS[int(rng.random()*len(BOULDERS))]
        scale = rng.uniform(.70, 1.55 if blocked[i] else 1.15)
        # Open ground keeps boulders well clear of the routes they flank.
        margin = 70 if blocked[i] else 170
        sink = 3+.35*radius*scale*float(slope[i])
        p.place(template, px, py, 'Talus boulders', radius*scale,
                max_slope=.95 if blocked[i] else .35, sink=sink, scale=scale, margin=margin)
    report['boulders'] = sum(p.counts.values())-before

    # -- Pinnacles on convex crests and spurs; they never stand on open ground.
    before = sum(p.counts.values())
    x, y, u = lattice(150, 8740)
    z, slope = sample(t['z'], x, y), sample(t['slope'], x, y)
    crest = smooth((-sample(concavity, x, y, 3)-20)/30)
    groups = smooth((fbm(x, y, scale=900, octaves=2, seed=8742)-.10)/.20)
    for i in np.nonzero((u < .22*crest*groups) & sample(t['blocked'], x, y)
                        & (slope < 1.1) & (z > 500))[0]:
        px, py = float(x[i]), float(y[i])
        rng = spot_random(8741, 'pinnacle', px, py)
        template, radius = PINNACLES[int(rng.random()*len(PINNACLES))]
        scale = rng.uniform(1.3, 2.4)
        p.place(template, px, py, 'Crest pinnacles', radius*scale, max_slope=1.1,
                sink=6*scale, scale=scale)
    report['pinnacles'] = sum(p.counts.values())-before

    report['stands'] = stand_points
    return report
