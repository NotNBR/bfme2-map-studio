"""Nanduhirion v1's objects: the original's, at the original's density and by
its placement logic, on this map's scale.

Every object of the original (1,883) belongs to one of these:

- Scenery and life: trees, shrubs, Amon Hen ruins and animals are copied by
  the clump. The original keeps them in small clumps (mostly 2 to 6, linked
  within twice their group's median spacing), and each clump is copied whole
  with its layout and spacing. A clump lining a cliff edge (a member within
  EDGE of it: all the ruins, about 40% of the trees and shrubs) gets as many
  copies as the cliff edges grew (2.9 times), at its own distance from the
  edge and unturned; one in the open gets as many as the ground grew (SX*SY,
  8.2 times), turned freely. The copies are drawn around the clump's place in
  the original's frame, within the distance to its nearest neighbouring
  clump, stretched onto this map, and stand as far from other clumps as the
  original's do. So each kind of place looks as in the original at the same
  zoom: the same clumps at the same spacing in the open, the same spacing
  along the cliffs. Then AMOUNT (1.5) times as many copies are asked for,
  for a fuller map; where the clumps' spacing leaves no room, fewer stand.
  Ambient sound emitters are copied one by one, by the same rule. Every copy keeps its original's template and properties and stands on
  the same kind of ground: the same passability, within HEIGHT_MATCH of its
  height (scaled) and on a texture its group stands on in the original.
  Trees, shrubs and life turn freely; ruins keep their original's facing,
  within 0.3, turned with their clump.
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
CLUMPED = ('ruin', 'tree', 'shrub', 'life')                   # copied by the clump; sound one by one
LAYERS = dict(ruin='Ruins', tree='Trees', shrub='Shrubs', life='Life', sound='Sound', farm='Farm sites')
HEIGHT_MATCH = 40.0             # a copy stands within this of its original's height, scaled
TRIES = 60                      # attempts per copy
AMOUNT = 1.5                    # copies asked for, over what the original's density gives
EDGE = 60.0                     # a clump with a member this close to a cliff edge lines the edge
EDGE_MATCH = 20.0               # its copies stand within this of its distance to the edge
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
    """A terrain's height, passability, texture and distance to the cliff
    edges at map points."""
    def __init__(self, z, impassable, labels, names, border):
        self.z, self.impassable, self.labels, self.names, self.border = z, impassable, labels, names, border
        self.extent = (z.shape[1] - 2*border)*10, (z.shape[0] - 2*border)*10
        blocked = np.asarray(impassable, bool)
        # Signed: positive on open ground, negative on blocked ground.
        self.edges = (distance_to(blocked) - distance_to(~blocked))*10

    def edge(self, x, y):
        """Distance to the nearest edge of blocked ground, negative on it."""
        return float(self.edges[self.cell(x, y)])

    def edge_length(self):
        """The length of the edges between open and blocked playable ground."""
        b = self.border
        play = np.asarray(self.impassable, bool)[b:-b, b:-b]
        return float(((play[1:] != play[:-1]).sum() + (play[:, 1:] != play[:, :-1]).sum())*10)

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


def clumps(P, link):
    """The objects at points P in clumps: chains of neighbours at most `link`
    apart. Lists of indices."""
    parent = list(range(len(P)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    cells = defaultdict(list)
    for i, (x, y) in enumerate(P):
        cells[int(x//link), int(y//link)].append(i)
    for (cx, cy), ids in cells.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((cx + dx, cy + dy), ()):
                    for i in ids:
                        if i < j and math.dist(P[i], P[j]) <= link:
                            parent[root(i)] = root(j)
    out = defaultdict(list)
    for i in range(len(P)):
        out[root(i)].append(i)
    return list(out.values())


def nearest(P):
    """Each point's distance to its nearest other point."""
    d = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
    np.fill_diagonal(d, np.inf)
    return d.min(1)


def copies(originals, source, ground, scale, masks, ruins):
    """The scenery and life copies, as object dicts, and per group how many
    the original's clumps ask for and how many were placed."""
    sx, sy, sz = scale
    area, line = sx*sy, ground.edge_length()/source.edge_length()
    out, tally, n = [], {}, 0
    for g in GROUPS:
        objs = [o for o in originals if group(o['template']) == g]
        P = np.array([(o['x'], o['y']) for o in objs])
        spacing = nearest(P)
        link = 2*float(np.median(spacing)) if g in CLUMPED else 0.0
        found = clumps(P, link) if link else [[i] for i in range(len(objs))]
        centres = np.array([P[c].mean(0) for c in found])
        apart = nearest(centres) if len(found) > 1 else np.array([link])
        reach = np.clip(apart, link or float(np.median(spacing)), 4*float(np.median(apart)))
        hosts = Counter(source.texture(o['x'], o['y']) for o in objs)
        allowed = {t for t, c in hosts.items() if c >= .01*len(objs)}
        others = Spacing(link or float(np.percentile(spacing, 10)))   # from the other clumps
        mask = masks[g]
        wanted = placed = edge_clumps = 0
        for k, members in enumerate(found):
            rng = random.Random(f'{SEED}:{g}:{k}')
            c = centres[k]
            lines = min(source.edge(*P[i]) for i in members) <= EDGE
            edge_clumps += lines
            factor = (line if lines else area)*AMOUNT
            count = int(factor) + (rng.random() < factor - int(factor))
            wanted += count*len(members)
            made = 0
            for _ in range(TRIES*count):
                if made == count:
                    break
                a, r = rng.uniform(-math.pi, math.pi), reach[k]*math.sqrt(rng.random())
                cx, cy = (c[0] + r*math.cos(a))*sx, (c[1] + r*math.sin(a))*sy
                if not ground.inside(cx, cy):
                    continue
                if lines:
                    if abs(ground.edge(cx, cy) - source.edge(*c)) > EDGE_MATCH:
                        continue
                    turn = 0.0
                else:
                    if ground.edge(cx, cy) <= EDGE:
                        continue
                    turn = rng.uniform(-math.pi, math.pi)
                cos, sin = math.cos(turn), math.sin(turn)
                spots = []
                for i in members:
                    o = objs[i]
                    dx, dy = o['x'] - c[0], o['y'] - c[1]
                    x, y = cx + dx*cos - dy*sin, cy + dx*sin + dy*cos
                    if (not ground.inside(x, y) or mask[ground.cell(x, y)]
                            or ground.blocked(x, y) != source.blocked(o['x'], o['y'])
                            or abs(ground.height(x, y) - source.height(o['x'], o['y'])*sz) > HEIGHT_MATCH
                            or ground.texture(x, y) not in allowed or not others.free(x, y)
                            or (g in ('tree', 'shrub') and not ruins.free(x, y, RUIN_CLEAR))):
                        break
                    spots.append((o, x, y))
                else:
                    for o, x, y in spots:
                        angle = (o['angle'] + turn + rng.uniform(-.3, .3) if g == 'ruin'
                                 else rng.uniform(-math.pi, math.pi))
                        n += 1
                        out.append(dict(template=o['template'], x=x, y=y, z=o['z'], angle=angle, flags=o['flags'],
                                        properties=properties(o, f"{o['template']} {n}", LAYERS[g])))
                        others.add(x, y)
                        if g == 'ruin':
                            ruins.add(x, y)
                    placed += len(spots)
                    made += 1
        tally[g] = dict(original=len(objs), clumps=len(found), along_cliffs=edge_clumps,
                        wanted=wanted, placed=placed)
    return out, tally


def farm_sites(prototype, ground, sites, twin, count):
    """The AI's farm sites: `count` evenly spread (farthest first) over
    walkable ground FARM_FROM_BLOCKED from blocked ground and SITE_CLEAR
    from the base sites, each with its twin."""
    z, border = ground.z, ground.border
    yy, xx = ((np.mgrid[0:z.shape[0], 0:z.shape[1]] - border)*10.0 + 5)
    ok = ground.edges >= FARM_FROM_BLOCKED
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
