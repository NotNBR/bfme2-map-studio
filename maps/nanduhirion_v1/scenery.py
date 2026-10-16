"""Nanduhirion v1's objects: the original's, at the original's density and by
its placement logic, on this map's scale.

Every object of the original (1,883) belongs to one of these:

- Scenery and life: trees, shrubs, Amon Hen ruins, animals and ambient sound
  emitters. Their density is kept. Each original object stands for the
  ground around it, which is now SX*SY (8.2) times as large, so it gets that
  many copies, drawn within its own spacing to its nearest neighbour around
  it in the original's frame and stretched onto this map. Groves, thickets
  and ruin fields therefore keep their density and outline and grow with the
  terrain. A copy keeps its original's template and properties, and stands
  on the same kind of ground: the same passability, within HEIGHT_MATCH of
  its height (scaled), on a texture its group stands on in the original, and
  at least its group's closest original spacing (10th percentile) from the
  others. Trees, shrubs and life turn freely; ruins keep their original's
  facing, within 0.3, as they line the cliff edges.
- The skirmish AI's farm sites (FarmTemplate, invisible in the game; the AI
  builds farms at the one nearest its base): spread evenly over walkable
  ground at the original's spacing and its clearance from blocked ground, as
  many as the original's per area. Each comes with its half-turn twin.
- Neutral sites and lairs, for sixteen players: two for each of the
  original's, side by side where it stands. Outposts east and west of it;
  signal fires and the strip's lairs across the raised centre strip, one on
  each team's side; inns north and south in the central arena; cave troll
  lairs on either side of their (widened) ramp's foot. They keep their
  original's facing and flag offset. The north ones are made from the
  original's north ones and the south ones are their half-turn twins, so
  every team finds the same.
- One for one, stretched: the plateau columns, Gollum's spawn points and the
  ambient sound stream.

The original keeps the space around its starts and neutral sites free; this
map keeps the same distances around its sixteen base sites (SITE_CLEAR) and
its neutral sites (OBJECTIVE_CLEAR), in map units, since buildings do not
grow with the map.
"""
import math
import random
from collections import Counter, defaultdict

import numpy as np

from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.relief import distance_to
from mapworkshop.mapkit.sites import creep_lair, gollum_spawns, neutral_site

SEED = 'nanduhirion-v1'
LIFE = ('Crow', 'Rabbit', 'Boar', 'Dog', 'Dog1', 'Wolf', 'AnimalWanderPoint')
GROUPS = ('ruin', 'tree', 'shrub', 'life', 'sound')          # placed in this order
LAYERS = dict(ruin='Ruins', tree='Trees', shrub='Shrubs', life='Life', sound='Sound', farm='Farm sites')
HEIGHT_MATCH = 40.0             # a copy stands within this of its original's height, scaled
TRIES = 40                      # attempts per copy
# Free space the original keeps (its nearest object of each group) around
# its starts and around its neutral sites and lairs, map units.
SITE_CLEAR = dict(ruin=450, tree=190, shrub=130, life=190, sound=0, farm=510)
OBJECTIVE_CLEAR = dict(ruin=140, tree=130, shrub=90, life=90, sound=0, farm=0)
RUIN_CLEAR = 40                 # trees and shrubs keep this from ruins
FARM_FROM_BLOCKED = 115         # the original's farm sites: at least this from blocked ground

# Neutral sites and lairs: how the pair stands where the original's one did.
PAIRS = {'Outpost': ('east-west', 650), 'SignalFire': ('strip', 330), 'FireDrakeLair': ('strip', 330),
         'MoriarGoblinLair': ('strip', 330), 'Inn': ('arena', 500), 'CaveTrollLair': ('ramp', 330)}
OBJECTIVE_GROUND = 120          # a neutral site's ground within this is walkable and level
OBJECTIVE_RELIEF = 20.0


def group(template):
    if template.startswith(('Amb_', 'BirdEmitter')):
        return 'sound'
    if 'Tree' in template:
        return 'tree'
    if 'Shrub' in template:
        return 'shrub'
    if template.startswith('GondorAmonHen'):
        return 'ruin'
    if template in LIFE:
        return 'life'
    return None


class Spacing:
    """Points at least `gap` apart, found by grid buckets."""
    def __init__(self, gap):
        self.gap, self.cells = gap, defaultdict(list)

    def free(self, x, y, gap=None):
        gap = gap or self.gap
        cx, cy = int(x//self.gap), int(y//self.gap)
        reach = int(math.ceil(gap/self.gap))
        return all((x - px)**2 + (y - py)**2 >= gap*gap
                   for i in range(-reach, reach + 1) for j in range(-reach, reach + 1)
                   for px, py in self.cells.get((cx + i, cy + j), ()))

    def add(self, x, y):
        self.cells[int(x//self.gap), int(y//self.gap)].append((x, y))


class Ground:
    """A terrain's height, passability and texture at map points."""
    def __init__(self, z, impassable, labels, names, border):
        self.z, self.impassable, self.labels, self.names, self.border = z, impassable, labels, names, border
        self.extent = (z.shape[1] - 2*border)*10, (z.shape[0] - 2*border)*10

    def cell(self, x, y):
        return int(y//10) + self.border, int(x//10) + self.border

    def height(self, x, y):
        return float(self.z[round(y/10) + self.border, round(x/10) + self.border])

    def blocked(self, x, y):
        return bool(self.impassable[self.cell(x, y)])

    def texture(self, x, y):
        return self.names[self.labels[self.cell(x, y)]]

    def inside(self, x, y, margin=20):
        return margin <= x <= self.extent[0] - margin and margin <= y <= self.extent[1] - margin


def properties(o, uid, layer):
    """The original's properties with this object's ID and layer."""
    out = [(k, kind, v) for k, kind, v in o['properties'] if k not in ('uniqueID', 'objectLayer')]
    return out + [('uniqueID', 3, uid), ('objectLayer', 3, layer)]


def clear_masks(shape, border, points):
    """Per group, the cells within its clear distance of any of `points`,
    each (x, y, distances by group)."""
    masks = {}
    yy, xx = ((np.mgrid[0:shape[0], 0:shape[1]] - border)*10.0 + 5)
    for g in (*GROUPS, 'farm'):
        mask = np.zeros(shape, bool)
        for x, y, clear in points:
            r = clear[g]
            if r:
                i0, i1 = max(0, int((y - r)//10) + border), min(shape[0], int((y + r)//10) + border + 2)
                j0, j1 = max(0, int((x - r)//10) + border), min(shape[1], int((x + r)//10) + border + 2)
                mask[i0:i1, j0:j1] |= (xx[i0:i1, j0:j1] - x)**2 + (yy[i0:i1, j0:j1] - y)**2 < r*r
        masks[g] = mask
    return masks


def copies(originals, source, ground, scale, masks, ruins):
    """The scenery and life copies, as object dicts, and per group how many
    the original's density asks for and how many were placed."""
    sx, sy, sz = scale
    k = sx*sy
    out, tally, n = [], {}, 0
    for g in GROUPS:
        objs = [o for o in originals if group(o['template']) == g]
        P = np.array([(o['x'], o['y']) for o in objs])
        d = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
        np.fill_diagonal(d, np.inf)
        nearest = d.min(1)
        median = float(np.median(nearest))
        reach = np.clip(nearest, median/2, 4*median)
        gap = float(np.percentile(nearest, 10))
        hosts = Counter(source.texture(o['x'], o['y']) for o in objs)
        allowed = {t for t, c in hosts.items() if c >= .01*len(objs)}
        spacing, mask = Spacing(gap), masks[g]
        wanted = placed = 0
        for i, o in enumerate(objs):
            rng = random.Random(f'{SEED}:{g}:{i}')
            count = int(k) + (rng.random() < k - int(k))
            wanted += count
            level, blocked = source.height(o['x'], o['y'])*sz, source.blocked(o['x'], o['y'])
            made = 0
            for _ in range(TRIES*count):
                if made == count:
                    break
                a, r = rng.uniform(-math.pi, math.pi), reach[i]*math.sqrt(rng.random())
                x, y = (o['x'] + r*math.cos(a))*sx, (o['y'] + r*math.sin(a))*sy
                if not ground.inside(x, y) or mask[ground.cell(x, y)]:
                    continue
                if (ground.blocked(x, y) != blocked or abs(ground.height(x, y) - level) > HEIGHT_MATCH
                        or ground.texture(x, y) not in allowed or not spacing.free(x, y)):
                    continue
                if g in ('tree', 'shrub') and not ruins.free(x, y, RUIN_CLEAR):
                    continue
                angle = o['angle'] + rng.uniform(-.3, .3) if g == 'ruin' else rng.uniform(-math.pi, math.pi)
                n += 1
                out.append(dict(template=o['template'], x=x, y=y, z=o['z'], angle=angle, flags=o['flags'],
                                properties=properties(o, f"{o['template']} {n}", LAYERS[g])))
                spacing.add(x, y)
                if g == 'ruin':
                    ruins.add(x, y)
                made += 1
            placed += made
        tally[g] = dict(original=len(objs), wanted=wanted, placed=placed)
    return out, tally


def farm_sites(prototype, ground, sites, twin, count):
    """The AI's farm sites: `count` evenly spread (farthest first) over
    walkable ground FARM_FROM_BLOCKED from blocked ground and SITE_CLEAR
    from the base sites, each with its twin."""
    z, border = ground.z, ground.border
    clear = distance_to(ground.impassable)*10
    yy, xx = ((np.mgrid[0:z.shape[0], 0:z.shape[1]] - border)*10.0 + 5)
    ok = (clear >= FARM_FROM_BLOCKED) & ~ground.impassable
    ok[:border + 2] = ok[-border - 2:] = False
    ok[:, :border + 2] = ok[:, -border - 2:] = False
    for x, y in sites:
        ok &= (xx - x)**2 + (yy - y)**2 >= SITE_CLEAR['farm']**2
    every = ok[::5, ::5]                                 # candidates 50 apart
    P = np.c_[xx[::5, ::5][every], yy[::5, ::5][every]]
    best = np.min([np.hypot(P[:, 0] - x, P[:, 1] - y) for x, y in sites], axis=0)
    chosen = []
    while len(chosen) < count and best.max() > 0:
        p = tuple(P[int(np.argmax(best))])
        q = twin(p)
        for point in (p, q) if math.dist(p, q) > 100 and ok[ground.cell(*q)] else (p,):
            chosen.append(point)
            best = np.minimum(best, np.hypot(P[:, 0] - point[0], P[:, 1] - point[1]))
    return [dict(template='FarmTemplate', x=float(x), y=float(y), z=prototype['z'], angle=prototype['angle'],
                 flags=prototype['flags'], properties=properties(prototype, f'FarmTemplate {i}', LAYERS['farm']))
            for i, (x, y) in enumerate(chosen[:count], 1)]


def flag_offset(site, flags):
    """The original's flag for `site`: distance and turn from its facing."""
    f = min(flags, key=lambda f: math.dist((f['x'], f['y']), (site['x'], site['y'])))
    dx, dy = f['x'] - site['x'], f['y'] - site['y']
    return math.hypot(dx, dy), math.atan2(dy, dx) - site['angle']


def objectives(originals, scale, centre, twin, ramps):
    """The neutral sites and lairs: (template, x, y, angle, flag or None),
    two for each north original and the twins of those."""
    sx, sy, _ = scale
    flags = [o for o in originals if o['template'] == 'CaptureFlag']
    north = [o for o in originals if o['template'] in PAIRS and o['y']*sy > centre[1]]
    out = []
    for o in north:
        x, y = o['x']*sx, o['y']*sy
        how, off = PAIRS[o['template']]
        if how == 'east-west':
            pair = [(x - off, y), (x + off, y)]
        elif how == 'strip':
            pair = [(centre[0] - off, y), (centre[0] + off, y)]
        elif how == 'arena':
            pair = [(centre[0], centre[1] + off)]          # its twin is the south one
        else:
            top, bottom = min(ramps, key=lambda r: math.dist(r[1], (x, y)))
            ux, uy = bottom[0] - top[0], bottom[1] - top[1]
            length = math.hypot(ux, uy); ux, uy = ux/length, uy/length
            s = (x - top[0])*ux + (y - top[1])*uy
            a = max(abs(-(x - top[0])*uy + (y - top[1])*ux), off)
            pair = [(top[0] + ux*s - uy*a, top[1] + uy*s + ux*a), (top[0] + ux*s + uy*a, top[1] + uy*s - ux*a)]
        link = flag_offset(o, flags) if o['template'] in ('Outpost', 'SignalFire', 'Inn') else None
        for p in pair:
            for (px, py), angle in ((p, o['angle']), (twin(p), o['angle'] + math.pi)):
                flag = None
                if link:
                    flag = (px + link[0]*math.cos(angle + link[1]), py + link[0]*math.sin(angle + link[1]))
                out.append((o['template'], px, py, angle, flag))
    return out


def check_objectives(placed, ground):
    """Each neutral site and lair on walkable, level ground."""
    problems = []
    r = OBJECTIVE_GROUND//10
    for template, x, y, _, _ in placed:
        i, j = ground.cell(x, y)
        box = (slice(i - r, i + r + 1), slice(j - r, j + r + 1))
        if ground.impassable[box].any() or np.ptp(ground.z[box]) > OBJECTIVE_RELIEF:
            problems.append(f'{template} at ({x:.0f}, {y:.0f})')
    return problems


def populate(m, original, source, ground, scale, sites, centre, twin, ramps):
    """Add the original's objects to `m` (see the module docstring).
    `original`: the original's objects; `source`, `ground`: Ground of the
    original and of this map; `scale`: (sx, sy, sz); `sites`: the sixteen
    base sites. Returns what was placed, for the report."""
    sx, sy, _ = scale
    placed = objectives(original, scale, centre, twin, ramps)
    problems = check_objectives(placed, ground)
    if problems:
        raise ValueError('Neutral sites on blocked or uneven ground: ' + '; '.join(problems))
    for template, x, y, angle, flag in placed:
        if flag:
            neutral_site(m, template, x, y, angle, flag=flag)
        else:
            creep_lair(m, template, x, y, angle)

    count = Counter()
    for o in original:
        if o['template'] in ('WeathertopColumn01', 'AmbStream_PlainsOfRohan'):
            count[o['template']] += 1
            add_object(m, o['template'], o['x']*sx, o['y']*sy, o['angle'], z=o['z'],
                       layer='Columns' if o['template'].startswith('Weathertop') else 'Sound',
                       extra=properties(o, f"{o['template']} {count[o['template']]}", '')[:-1])
    spawns = [(o['x']*sx, o['y']*sy) for o in original
              if any(v.startswith('SpawnPoint_SkirmishGollum') for k, _, v in o['properties'] if k == 'waypointName')]
    gollum_spawns(m, spawns)

    keep = [(x, y, SITE_CLEAR) for x, y in sites]
    keep += [(x, y, OBJECTIVE_CLEAR) for _, x, y, _, _ in placed]
    keep += [(*flag, OBJECTIVE_CLEAR) for *_, flag in placed if flag]
    masks = clear_masks(ground.z.shape, ground.border, keep)
    scenery, tally = copies(original, source, ground, scale, masks, Spacing(RUIN_CLEAR))
    farms = [o for o in original if o['template'] == 'FarmTemplate']
    sown = farm_sites(farms[0], ground, sites, twin, round(len(farms)*sx*sy))
    tally['farm'] = dict(original=len(farms), wanted=round(len(farms)*sx*sy), placed=len(sown))
    m.set_objects(m.objects() + scenery + sown)
    return dict(objects=tally, objectives=Counter(t for t, *_ in placed), spawns=len(spawns))
